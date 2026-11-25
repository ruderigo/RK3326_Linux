#!/usr/bin/env python3
"""
wifi_mon.py — Universal Monitor & Consumer USB Wi-Fi Capture Helper for STUMP RF Recon
Target: RK3326_Linux (R36MAX / 93 RK3326 handhelds, kernels 5.10 & 4.4) + Desktop Linux

Supports ALL monitor-capable USB Wi-Fi adapters AND consumer client-only Wi-Fi dongles:
  - Tier 1 (Full Raw 802.11 Monitor + Radiotap via AF_PACKET):
      Any USB adapter reporting `* monitor` in `iw phy`:
      * Ralink / MediaTek rt2x00: RT3070 / RT3071 / RT3072 / RT5370 / RT2870 (rt2800usb), rt73usb, rt2500usb
      * Atheros / Qualcomm: AR9271 (ath9k_htc), AR9170 (carl9170)
      * MediaTek mt76: MT7601U (mt7601u), MT7610U (mt76x0u), MT7612U (mt76x2u), MT7921U (mt7921u)
      * Realtek: RTL8812AU / RTL8814AU / RTL8821AU / RTL8821CU / RTL8822BU / RTL8188EU / RTL8192EU / RTL8852BU
        (mainline rtw88/rtw89/rtl8xxxu AND vendor 88XXau/8812au/8814au/8821cu/88x2bu/8188eu/r8188eu/8852bu)
      * ZyDAS (zd1211rw) & any other mac80211/WEXT USB monitor driver
  - Tier 2 (Consumer Managed AP Scan Fallback — zero dead-ends, never drops Wi-Fi/SSH):
      Client-only consumer USB dongles (e.g. AIC8800 Wi-Fi 6, stock Realtek/TP-Link without monitor mode)
      or onboard handheld Wi-Fi automatically run read-only `iw dev <iface> scan` AP radar and hot-upgrade
      to full Monitor Mode the moment a monitor-capable USB dongle is plugged in.

Pure Python 3 stdlib (zero pip dependencies).
Installed as root-owned `/usr/local/sbin/rk-stump-wifi` (mirroring RK3326_Linux's `rk-scan` stdin-controlled
privilege isolation model). Closing stdin immediately exits and restores managed mode + NetworkManager.
"""

import argparse
import glob
import json
import os
import re
import select
import signal
import socket
import struct
import subprocess
import sys
import time

IFACE_RE = re.compile(r"^[a-zA-Z0-9_-]{2,15}$")

# Known USB VID:PIDs for popular monitor-capable & consumer Wi-Fi dongles
KNOWN_USB_CHIPS = {
    # Ralink / MediaTek RT2800 / RT3070 / RT5370 family (rt2800usb)
    "148f:3070": "RT3070",
    "148f:3071": "RT3071",
    "148f:3072": "RT3072",
    "148f:2070": "RT2070/RT3070",
    "148f:2870": "RT2870",
    "148f:5370": "RT5370",
    "148f:5372": "RT5372",
    "0b05:1784": "RT3070 (ASUS)",
    "0df6:0042": "RT3070 (Sitecom)",
    "07d1:3c0a": "RT3070 (D-Link)",
    "07d1:3c0f": "RT3070 (D-Link)",
    "13d3:3273": "RT3070 (AzureWave)",
    "14b2:3c12": "RT3070 (Alfa)",
    "1740:9703": "RT3070 (EnGenius)",
    "7392:7711": "RT3070 (Edimax)",
    "083a:7511": "RT3070 (SMC)",
    "04bb:0944": "RT3070 (I-O DATA)",
    # Atheros AR9271 / AR7010 (ath9k_htc, carl9170)
    "0cf3:9271": "AR9271 (Atheros)",
    "0cf3:7015": "AR7010 (Atheros)",
    "0cf3:1006": "AR9271 (TP-Link)",
    "13d3:3327": "AR9271",
    "0846:9030": "AR9271 (Netgear)",
    # MediaTek mt76 USB family (mt7601u, mt76x0u, mt76x2u, mt7921u)
    "148f:7601": "MT7601U",
    "0e8d:7601": "MT7601U",
    "148f:761a": "MT7610U",
    "0e8d:7610": "MT7610U",
    "2357:0105": "MT7610U (Archer T2U)",
    "0e8d:7612": "MT7612U (AC1200)",
    "0e8d:7632": "MT7612U",
    "0e8d:7961": "MT7921U (Wi-Fi 6E)",
    "0846:9060": "MT7921U (Netgear A8000)",
    # Realtek monitor-capable & consumer USB dongles
    "0bda:8812": "RTL8812AU",
    "0bda:881a": "RTL8812AU",
    "2357:0101": "RTL8812AU (Archer T4U)",
    "2357:010d": "RTL8812AU (Archer T4U v2)",
    "0bda:8813": "RTL8814AU (AC1900)",
    "0bda:0811": "RTL8821AU",
    "0bda:a811": "RTL8821AU",
    "0bda:c811": "RTL8821CU (AC600)",
    "0bda:c820": "RTL8821CU (AC600)",
    "0bda:b812": "RTL8822BU (AC1200)",
    "2357:012d": "RTL8822BU (Archer T3U)",
    "2357:0115": "RTL8822BU (Archer T4U v3)",
    "2357:0138": "RTL8822BU (Archer T3U+)",
    "2357:010c": "RTL8188EUS (TL-WN722N v2/v3)",
    "0bda:8179": "RTL8188EUS",
    "0bda:0179": "RTL8188ETV",
    "0bda:8176": "RTL8188CUS",
    "0bda:f179": "RTL8188FTV",
    "2357:0109": "RTL8192EU (TL-WN823N)",
    "0bda:818b": "RTL8192EU",
    "0bda:b852": "RTL8852BU (Wi-Fi 6)",
    "0bda:a85b": "RTL8852AU (Wi-Fi 6)",
    "0bda:b832": "RTL8832BU (Wi-Fi 6)",
    # AIC Wi-Fi 6 consumer mini-dongles (commonly client-only)
    "a69c:8801": "AIC8800 (Wi-Fi 6)",
    "a69c:8d80": "AIC8800D80 (Wi-Fi 6)",
}

DRIVER_CHIP_FALLBACK = {
    "rt2800usb": "RT3070/rt2800usb",
    "rt73usb": "RT73 (Ralink)",
    "rt2500usb": "RT2500 (Ralink)",
    "ath9k_htc": "AR9271 (Atheros)",
    "carl9170": "AR9170 (Atheros)",
    "mt7601u": "MT7601U",
    "mt76x0u": "MT7610U",
    "mt76x2u": "MT7612U",
    "mt7921u": "MT7921U",
    "8812au": "RTL8812AU",
    "88XXau": "RTL8812AU",
    "rtl8812au": "RTL8812AU",
    "rtl88xxau": "RTL8812AU",
    "rtw88_8812au": "RTL8812AU",
    "8814au": "RTL8814AU",
    "rtl8814au": "RTL8814AU",
    "8821au": "RTL8821AU",
    "rtw88_8821au": "RTL8821AU",
    "8821cu": "RTL8821CU",
    "rtl8821cu": "RTL8821CU",
    "rtw88_8821cu": "RTL8821CU",
    "8822bu": "RTL8822BU",
    "88x2bu": "RTL8822BU",
    "rtl88x2bu": "RTL8822BU",
    "rtw88_8822bu": "RTL8822BU",
    "8188eu": "RTL8188EU",
    "r8188eu": "RTL8188EU",
    "8188fu": "RTL8188FTV",
    "8192eu": "RTL8192EU",
    "rtl8xxxu": "Realtek USB",
    "8852bu": "RTL8852BU",
    "8852au": "RTL8852AU",
    "rtw89_8852bu": "RTL8852BU",
    "rtw89_8852au": "RTL8852AU",
    "aic8800_fdrv_usb": "AIC8800",
    "zd1211rw": "ZD1211B",
}

# Proven high-reliability USB monitor drivers prioritized first when multiple USB adapters are attached
PREFERRED_MONITOR_DRIVERS = {
    "rt2800usb", "ath9k_htc", "mt76x2u", "mt76x0u", "mt7601u", "mt7921u",
    "8812au", "88XXau", "rtl8812au", "rtl88xxau", "rtw88_8812au",
    "8814au", "rtl8814au", "8821au", "rtw88_8821au",
    "8822bu", "88x2bu", "rtl88x2bu", "rtw88_8822bu",
    "8821cu", "rtl8821cu", "rtw88_8821cu",
    "8188eu", "r8188eu", "8192eu", "rtl8xxxu",
    "8852bu", "8852au", "rtw89_8852bu", "rtw89_8852au",
    "carl9170", "rt73usb", "rt2500usb", "zd1211rw",
}

# Hit the 3 non-overlapping 2.4 GHz primary channels first, then sweep remaining 2.4 GHz channels
DEFAULT_HOP_ORDER_24GHZ = [1, 6, 11, 2, 7, 12, 3, 8, 13, 4, 9, 5, 10]

MGMT_SUBTYPES = {
    0: ("ASSOC_REQ", 4),
    1: ("ASSOC_RSP", 6),
    2: ("REASSOC_REQ", 10),
    3: ("REASSOC_RSP", 6),
    4: ("PROBE_REQ", 0),
    5: ("PROBE_RSP", 12),
    8: ("BEACON", 12),
    10: ("DISASSOC", 2),
    11: ("AUTH", 6),
    12: ("DEAUTH", 2),
    13: ("ACTION", 0),
}


def valid_iface_name(name):
    return bool(name and IFACE_RE.match(name))


def identify_chipset(driver, usb_id=""):
    uid = (usb_id or "").lower()
    if uid in KNOWN_USB_CHIPS:
        return KNOWN_USB_CHIPS[uid]
    if driver in DRIVER_CHIP_FALLBACK:
        return DRIVER_CHIP_FALLBACK[driver]
    return driver or "USB Wi-Fi"


def channel_to_freq_mhz(ch):
    ch = int(ch)
    if 1 <= ch <= 13:
        return 2407 + ch * 5
    if ch == 14:
        return 2484
    if 36 <= ch <= 177:
        return 5000 + ch * 5
    return 2412


def freq_to_channel(freq_mhz):
    """Convert 802.11 center frequency (MHz) to IEEE channel number."""
    if 2412 <= freq_mhz <= 2472:
        return (freq_mhz - 2407) // 5
    if freq_mhz == 2484:
        return 14
    if 5180 <= freq_mhz <= 5885:
        return (freq_mhz - 5000) // 5
    return 0


def parse_iw_phy_capabilities(iw_phy_text):
    """
    Parse `iw phy` output (matching RK3326_Linux rkshell/system.py) into per-phy capabilities:
      {0: {"monitor": True, "channels_24": [1..13], "channels_5": [36..]}}
    """
    out = {}
    cur = None
    in_modes = False
    in_freqs = False

    for raw_line in (iw_phy_text or "").splitlines():
        m = re.match(r"^\s*Wiphy\s+phy(\d+)", raw_line)
        if m:
            cur = int(m.group(1))
            out[cur] = {"monitor": False, "channels_24": [], "channels_5": []}
            in_modes = False
            in_freqs = False
            continue
        if cur is None:
            continue

        stripped = raw_line.strip()
        if "Supported interface modes:" in raw_line:
            in_modes, in_freqs = True, False
            continue
        if stripped == "Frequencies:":
            in_modes, in_freqs = False, True
            continue

        if in_modes:
            if stripped.startswith("*"):
                if "monitor" in stripped.lower():
                    out[cur]["monitor"] = True
            elif stripped:
                in_modes = False
        elif in_freqs:
            if stripped.startswith("*"):
                if "(disabled)" in stripped.lower():
                    continue
                fm = re.search(r"(\d+(?:\.\d+)?)\s*MHz\s*\[(\d+)\]", stripped)
                if fm:
                    freq = int(float(fm.group(1)))
                    ch = int(fm.group(2))
                    if 2400 <= freq <= 2500 and 1 <= ch <= 13:
                        if ch not in out[cur]["channels_24"]:
                            out[cur]["channels_24"].append(ch)
                    elif 5000 <= freq <= 5900:
                        if ch not in out[cur]["channels_5"]:
                            out[cur]["channels_5"].append(ch)
            elif stripped:
                in_freqs = False

    return out


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except Exception:
        return ""


def _usb_vid_pid_for_device(dev_path):
    """Walk up sysfs from device path to find USB idVendor:idProduct."""
    cur = os.path.realpath(dev_path)
    for _ in range(6):
        vid = _read_text(os.path.join(cur, "idVendor")).lower()
        pid = _read_text(os.path.join(cur, "idProduct")).lower()
        if len(vid) == 4 and len(pid) == 4:
            return f"{vid}:{pid}"
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return ""


def _run_cmd(args, timeout=8.0):
    return subprocess.run(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


def discover_wifi_adapters(sys_root="/sys", iw_phy_text=None):
    """
    Discover ALL wireless interfaces (USB monitor dongles, consumer client-only USB dongles,
    and onboard SDIO/PCI Wi-Fi) using `/sys/class/ieee80211/phy*` + `iw phy`, matching
    RK3326_Linux's `rkshell/system.py` contract.

    Returns priority-sorted list of dicts:
      {
        "phy": 1, "iface": "wlan1", "driver": "rt2800usb", "bus": "usb",
        "usb_id": "148f:3070", "chip": "RT3070", "monitor": True,
        "channels_24": [1..13], "channels_5": [], "mode_cap": "monitor"|"scan",
        "priority": 0
      }
    """
    if iw_phy_text is None:
        try:
            r = _run_cmd(["iw", "phy"])
            iw_phy_text = r.stdout if r.returncode == 0 else ""
        except Exception:
            iw_phy_text = ""

    caps = parse_iw_phy_capabilities(iw_phy_text)
    found = []
    seen_ifaces = set()

    phy_dirs = sorted(glob.glob(os.path.join(sys_root, "class/ieee80211/phy*")))
    for d in phy_dirs:
        m = re.search(r"phy(\d+)$", d)
        if not m:
            continue
        phy = int(m.group(1))
        dev_link = os.path.join(d, "device")
        real_dev = os.path.realpath(dev_link) if os.path.exists(dev_link) else ""
        bus = "usb" if "/usb" in real_dev else ("sdio" if ("mmc" in real_dev or "sdio" in real_dev) else "other")
        drv_link = os.path.join(dev_link, "driver")
        driver = os.path.basename(os.path.realpath(drv_link)) if os.path.exists(drv_link) else ""
        usb_id = _usb_vid_pid_for_device(dev_link) if bus == "usb" else ""

        nets = sorted(glob.glob(os.path.join(dev_link, "net/*")))
        if not nets:
            # Fallback: look for net devices pointing to this phy
            nets = sorted(glob.glob(os.path.join(d, "device/net/*")))
        if not nets:
            continue

        iface = os.path.basename(nets[0])
        if not valid_iface_name(iface) or iface in seen_ifaces:
            continue
        seen_ifaces.add(iface)

        phy_cap = caps.get(phy, {"monitor": False, "channels_24": [], "channels_5": []})
        # If `iw phy` wasn't available (e.g. minimal chroot), infer monitor for known drivers
        mon = bool(phy_cap["monitor"]) or (not iw_phy_text and bus == "usb" and driver in PREFERRED_MONITOR_DRIVERS)
        ch24 = list(phy_cap["channels_24"]) or list(range(1, 14))
        ch5 = list(phy_cap["channels_5"])
        chip = identify_chipset(driver, usb_id)

        if bus == "usb" and mon:
            if driver == "rt2800usb" and usb_id == "148f:3070":
                prio = 0
            elif driver in PREFERRED_MONITOR_DRIVERS:
                prio = 1
            else:
                prio = 5
            mode_cap = "monitor"
        elif bus == "usb":
            prio = 20
            mode_cap = "scan"
        elif mon:
            # Non-USB internal adapter with monitor support (e.g. desktop Linux laptop card)
            prio = 15
            mode_cap = "monitor"
        else:
            prio = 30
            mode_cap = "scan"

        found.append({
            "phy": phy,
            "iface": iface,
            "driver": driver,
            "bus": bus,
            "usb_id": usb_id,
            "chip": chip,
            "monitor": mon,
            "channels_24": ch24,
            "channels_5": ch5,
            "mode_cap": mode_cap,
            "priority": prio,
        })

    # Fallback for WEXT-only Realtek drivers that expose /sys/class/net/<iface>/wireless without ieee80211/phy*
    net_root = os.path.join(sys_root, "class/net")
    if os.path.isdir(net_root):
        for iface in sorted(os.listdir(net_root)):
            if iface in seen_ifaces or not valid_iface_name(iface) or iface == "lo":
                continue
            net_dir = os.path.join(net_root, iface)
            if not (os.path.isdir(os.path.join(net_dir, "wireless")) or os.path.exists(os.path.join(net_dir, "phy80211"))):
                continue
            dev_link = os.path.join(net_dir, "device")
            real_dev = os.path.realpath(dev_link) if os.path.exists(dev_link) else ""
            bus = "usb" if "/usb" in real_dev else ("sdio" if ("mmc" in real_dev or "sdio" in real_dev) else "other")
            drv_link = os.path.join(dev_link, "driver")
            driver = os.path.basename(os.path.realpath(drv_link)) if os.path.exists(drv_link) else ""
            usb_id = _usb_vid_pid_for_device(dev_link) if bus == "usb" else ""
            mon = bool(bus == "usb" and driver in PREFERRED_MONITOR_DRIVERS)
            found.append({
                "phy": -1,
                "iface": iface,
                "driver": driver,
                "bus": bus,
                "usb_id": usb_id,
                "chip": identify_chipset(driver, usb_id),
                "monitor": mon,
                "channels_24": list(range(1, 14)),
                "channels_5": [],
                "mode_cap": "monitor" if mon else "scan",
                "priority": 2 if mon else (21 if bus == "usb" else 31),
            })

    found.sort(key=lambda item: (item["priority"], item["iface"]))
    return found


def parse_radiotap(frame):
    """
    Parse IEEE 802.11 Radiotap header produced by Linux mac80211 / rt2800usb / ath9k_htc / mt76 / Realtek.
    Handles chained 32-bit it_present bitmasks and strict natural field alignment.
    Returns (it_len, channel_or_0, rssi_dbm_or_None, has_fcs, bad_fcs) or None.
    """
    n = len(frame)
    if n < 8:
        return None
    ver, _pad, it_len = struct.unpack_from("<BBH", frame, 0)
    if ver != 0 or it_len < 8 or it_len > n:
        return None

    first_present = struct.unpack_from("<I", frame, 4)[0]
    offset = 8
    cur_present = first_present
    while cur_present & 0x80000000:
        if offset + 4 > it_len:
            return None
        cur_present = struct.unpack_from("<I", frame, offset)[0]
        offset += 4

    has_fcs = False
    bad_fcs = False
    ch = 0
    rssi = None

    # Bit 0: TSFT (8 bytes, align 8)
    if first_present & (1 << 0):
        offset = (offset + 7) & ~7
        offset += 8

    # Bit 1: Flags (1 byte, align 1)
    if first_present & (1 << 1):
        if offset + 1 > it_len:
            return (it_len, ch, rssi, has_fcs, bad_fcs)
        flags = frame[offset]
        has_fcs = bool(flags & 0x10)
        bad_fcs = bool(flags & 0x40)
        offset += 1

    # Bit 2: Rate (1 byte, align 1)
    if first_present & (1 << 2):
        offset += 1

    # Bit 3: Channel (4 bytes <HH: freq_mhz, flags; align 2)
    if first_present & (1 << 3):
        offset = (offset + 1) & ~1
        if offset + 4 <= it_len:
            freq_mhz, _ch_flags = struct.unpack_from("<HH", frame, offset)
            ch = freq_to_channel(freq_mhz)
        offset += 4

    # Bit 4: FHSS (2 bytes, align 2)
    if first_present & (1 << 4):
        offset = (offset + 1) & ~1
        offset += 2

    # Bit 5: dBm Antenna Signal (1 byte signed int8, align 1)
    if first_present & (1 << 5):
        if offset + 1 <= it_len:
            rssi = struct.unpack_from("<b", frame, offset)[0]
        offset += 1

    return (it_len, ch, rssi, has_fcs, bad_fcs)


def _fmt_mac(b):
    return ":".join(f"{x:02x}" for x in b)


def _parse_mgmt_ies(body):
    """Extract SSID (Tag 0) and DS Parameter Channel (Tag 3) from 802.11 management IEs."""
    ssid = ""
    ds_ch = 0
    pos = 0
    end = len(body)
    while pos + 2 <= end:
        tag_id = body[pos]
        tag_len = body[pos + 1]
        pos += 2
        if pos + tag_len > end:
            break
        if tag_id == 0 and tag_len > 0:
            raw_ssid = body[pos:pos + tag_len]
            if not all(b == 0 for b in raw_ssid):
                cleaned = raw_ssid.decode("utf-8", "replace").replace("\x00", "").strip()
                ssid = "".join(c if 32 <= ord(c) <= 126 else "." for c in cleaned)[:32]
        elif tag_id == 3 and tag_len == 1:
            c = body[pos]
            if 1 <= c <= 14:
                ds_ch = c
        pos += tag_len
    return ssid, ds_ch


def parse_80211_frame(raw, fallback_ch=1, driver_tag="rt2800usb"):
    """
    Decode a raw AF_PACKET Radiotap + 802.11 frame into a STUMP RF Recon JSON event dict.
    Returns None for bad-FCS, truncated, control-only, or invalid-MAC frames.
    """
    rt = parse_radiotap(raw)
    if rt is None:
        return None
    it_len, rt_ch, rssi, has_fcs, bad_fcs = rt
    if bad_fcs:
        return None

    dot11 = raw[it_len:-4] if (has_fcs and len(raw) - it_len >= 4) else raw[it_len:]
    if len(dot11) < 24:
        return None

    fc = struct.unpack_from("<H", dot11, 0)[0]
    ftype_bits = (fc >> 2) & 0x03
    subtype = (fc >> 4) & 0x0F
    to_ds = bool(fc & 0x0100)
    from_ds = bool(fc & 0x0200)

    addr1 = dot11[4:10]
    addr2 = dot11[10:16]
    addr3 = dot11[16:22]

    ssid = ""
    ds_ch = 0

    if ftype_bits == 0:
        info = MGMT_SUBTYPES.get(subtype)
        ftype = info[0] if info else "MGMT"
        fixed_len = info[1] if info else 0
        src_bytes = addr2
        bssid_bytes = addr3
        if info and subtype in (0, 2, 4, 5, 8) and len(dot11) > 24 + fixed_len:
            ssid, ds_ch = _parse_mgmt_ies(dot11[24 + fixed_len:])
    elif ftype_bits == 2:
        ftype = "QOS_DATA" if (subtype & 0x08) else "DATA"
        if not to_ds and not from_ds:
            src_bytes, bssid_bytes = addr2, addr3
        elif to_ds and not from_ds:
            src_bytes, bssid_bytes = addr2, addr1
        elif not to_ds and from_ds:
            src_bytes, bssid_bytes = addr3, addr2
        else:
            src_bytes = dot11[24:30] if len(dot11) >= 30 else addr2
            bssid_bytes = addr2
    else:
        return None

    if src_bytes in (b"\x00\x00\x00\x00\x00\x00", b"\xff\xff\xff\xff\xff\xff"):
        return None
    if src_bytes[0] & 0x01:
        return None

    mac = _fmt_mac(src_bytes)
    bssid = _fmt_mac(bssid_bytes)
    laa = bool(src_bytes[0] & 0x02)

    ch = ds_ch if ds_ch else (rt_ch if 1 <= rt_ch <= 14 else fallback_ch)
    ch = max(1, min(13, int(ch or 1)))
    rssi_val = int(rssi) if rssi is not None else -78
    if rssi_val > -5 or rssi_val < -115:
        rssi_val = max(-110, min(-10, rssi_val))

    return {
        "ev": "wifi",
        "src": driver_tag,
        "ch": ch,
        "rssi": rssi_val,
        "ftype": ftype,
        "mac": mac,
        "bssid": bssid,
        "ssid": ssid,
        "len": len(dot11),
        "laa": laa,
    }


def parse_iw_scan_output(scan_text, driver_tag="wifi:scan"):
    """
    Parse `iw dev <iface> scan` / `iw dev <iface> scan dump` output for consumer client-only
    Wi-Fi dongles (e.g. AIC8800, stock Realtek, or onboard SDIO Wi-Fi) that lack monitor mode.
    Returns a list of STUMP `ev: wifi` BEACON dicts (2.4 GHz Ch 1–13).
    """
    events = []
    cur = None

    def flush():
        if not cur or not cur.get("mac"):
            return
        ch = cur.get("ds_ch") or freq_to_channel(cur.get("freq", 0))
        if not (1 <= ch <= 13):
            return
        mac = cur["mac"].lower()
        try:
            laa = bool(int(mac[:2], 16) & 0x02)
        except Exception:
            laa = False
        events.append({
            "ev": "wifi",
            "src": driver_tag,
            "ch": ch,
            "rssi": int(round(cur.get("rssi", -80.0))),
            "ftype": "BEACON",
            "mac": mac,
            "bssid": mac,
            "ssid": cur.get("ssid", ""),
            "len": 0,
            "laa": laa,
        })

    for raw_ln in (scan_text or "").splitlines():
        m_bss = re.match(r"^BSS\s+([0-9a-fA-F:]{17})", raw_ln)
        if m_bss:
            flush()
            cur = {"mac": m_bss.group(1).lower(), "freq": 0, "ds_ch": 0, "rssi": -80.0, "ssid": ""}
            continue
        if cur is None:
            continue
        ln = raw_ln.strip()
        if ln.startswith("freq:"):
            try:
                cur["freq"] = int(float(ln.split(":", 1)[1].strip().split()[0]))
            except Exception:
                pass
        elif ln.startswith("signal:"):
            ms = re.search(r"(-?\d+(?:\.\d+)?)\s*dBm", ln)
            if ms:
                cur["rssi"] = float(ms.group(1))
        elif ln.startswith("SSID:"):
            s = ln.split(":", 1)[1].strip()
            cur["ssid"] = "".join(c if 32 <= ord(c) <= 126 else "." for c in s)[:32]
        elif "DS Parameter set: channel" in ln:
            mc = re.search(r"channel\s+(\d+)", ln)
            if mc:
                cur["ds_ch"] = int(mc.group(1))

    flush()
    return events


def _emit(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _build_hop_order(supported_ch24):
    allowed = set(supported_ch24 or range(1, 14))
    ordered = [c for c in DEFAULT_HOP_ORDER_24GHZ if c in allowed]
    return ordered or [1, 6, 11]


class MonitorCaptureSession:
    """
    Drives ANY Linux monitor-capable USB Wi-Fi adapter (rt2800usb, ath9k_htc, mt76*,
    Realtek 8812au/8814au/8821cu/88x2bu/8188eu/8852bu/rtl8xxxu, zd1211rw, etc.) with
    multi-driver iw/iwconfig fallbacks and guaranteed NetworkManager restoration.
    """

    def __init__(self, adapter_info, initial_channel=0, dwell_sec=0.28):
        self.info = adapter_info
        self.iface = adapter_info["iface"]
        self.driver = adapter_info["driver"] or "usb-wifi"
        self.chip = adapter_info["chip"]
        self.usb_id = adapter_info.get("usb_id", "")
        self.hop_order = _build_hop_order(adapter_info.get("channels_24"))
        self.target_ch = int(initial_channel)
        self.cur_ch = self.target_ch if self.target_ch in self.hop_order else self.hop_order[0]
        self.hop_idx = 0
        self.dwell_sec = dwell_sec
        self.paused = False
        self.was_nm_managed = False
        self.monitor_active = False
        self.sock = None

    def _nm_is_managed(self):
        try:
            r = _run_cmd(["nmcli", "-t", "-f", "DEVICE,STATE", "dev", "status"])
            if r.returncode != 0:
                return False
            for ln in r.stdout.splitlines():
                parts = ln.split(":", 1)
                if len(parts) == 2 and parts[0] == self.iface:
                    return parts[1].strip().lower() != "unmanaged"
        except FileNotFoundError:
            pass
        return False

    def _set_channel(self, ch):
        ch = max(1, min(13, int(ch)))
        freq = channel_to_freq_mhz(ch)
        # Multi-driver fallback chain: covers mac80211 (rt2800usb/ath9k/mt76), Realtek out-of-tree, and WEXT
        attempts = [
            ["iw", "dev", self.iface, "set", "channel", str(ch), "HT20"],
            ["iw", "dev", self.iface, "set", "channel", str(ch)],
            ["iw", "dev", self.iface, "set", "freq", str(freq)],
            ["iwconfig", self.iface, "channel", str(ch)],
        ]
        for cmd in attempts:
            try:
                r = _run_cmd(cmd, timeout=3.0)
                if r.returncode == 0:
                    self.cur_ch = ch
                    return True
            except FileNotFoundError:
                continue
            except Exception:
                continue
        return False

    def start(self):
        if not valid_iface_name(self.iface):
            raise RuntimeError(f"Invalid interface name: {self.iface}")

        try:
            _run_cmd(["rfkill", "unblock", "wifi"], timeout=3.0)
        except Exception:
            pass

        self.was_nm_managed = self._nm_is_managed()
        if self.was_nm_managed:
            _run_cmd(["nmcli", "dev", "set", self.iface, "managed", "no"], timeout=5.0)
            time.sleep(0.15)

        r = _run_cmd(["ip", "link", "set", self.iface, "down"])
        if r.returncode != 0:
            raise RuntimeError(f"ip link down failed on {self.iface}: {r.stderr.strip()}")

        # Multi-driver monitor activation chain (mac80211 + Realtek vendor drivers + WEXT)
        mon_ok = False
        last_err = ""
        for cmd in (
            ["iw", "dev", self.iface, "set", "monitor", "otherbss"],
            ["iw", "dev", self.iface, "set", "type", "monitor"],
            ["iwconfig", self.iface, "mode", "monitor"],
        ):
            try:
                r = _run_cmd(cmd)
                if r.returncode == 0:
                    mon_ok = True
                    break
                last_err = r.stderr.strip() or r.stdout.strip()
            except FileNotFoundError:
                continue
        if not mon_ok:
            raise RuntimeError(f"monitor mode failed on {self.iface} ({self.driver}): {last_err}")

        r = _run_cmd(["ip", "link", "set", self.iface, "up"])
        if r.returncode != 0:
            raise RuntimeError(f"ip link up failed on {self.iface}: {r.stderr.strip()}")

        self.monitor_active = True
        self._set_channel(self.cur_ch)

        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
        sock.bind((self.iface, 0))
        sock.setblocking(False)
        self.sock = sock

        _emit({
            "ev": "wifi_hw",
            "status": "monitor",
            "mode": "monitor",
            "iface": self.iface,
            "driver": self.driver,
            "chip": self.chip,
            "usb_id": self.usb_id,
            "ch": self.cur_ch,
            "hop": (self.target_ch == 0),
        })

    def stop(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

        if self.monitor_active and os.path.isdir(f"/sys/class/net/{self.iface}"):
            try:
                _run_cmd(["ip", "link", "set", self.iface, "down"], timeout=4.0)
                r = _run_cmd(["iw", "dev", self.iface, "set", "type", "managed"], timeout=4.0)
                if r.returncode != 0:
                    try:
                        _run_cmd(["iwconfig", self.iface, "mode", "managed"], timeout=4.0)
                    except FileNotFoundError:
                        pass
                _run_cmd(["ip", "link", "set", self.iface, "up"], timeout=4.0)
                if self.was_nm_managed:
                    _run_cmd(["nmcli", "dev", "set", self.iface, "managed", "yes"], timeout=5.0)
            except Exception:
                pass
        self.monitor_active = False

    def handle_command(self, line):
        cmd = line.strip().lower()
        if not cmd:
            return True
        if cmd in ("quit", "exit", "stop"):
            return False
        if cmd == "pause":
            self.paused = True
        elif cmd == "resume":
            self.paused = False
        elif cmd.startswith("ch "):
            arg = cmd.split(None, 1)[1].strip()
            if arg in ("hop", "0", "auto"):
                self.target_ch = 0
            else:
                try:
                    n = int(arg)
                    if 1 <= n <= 13:
                        self.target_ch = n
                        self._set_channel(n)
                except ValueError:
                    pass
        return True

    def run_loop(self, stop_flag):
        last_hop = time.monotonic()
        stdin_fd = sys.stdin.fileno() if sys.stdin and not sys.stdin.closed else None
        stdin_buf = ""

        while not stop_flag[0]:
            now = time.monotonic()
            if not self.paused and self.target_ch == 0 and (now - last_hop >= self.dwell_sec):
                self.hop_idx = (self.hop_idx + 1) % len(self.hop_order)
                if not self._set_channel(self.hop_order[self.hop_idx]):
                    if not os.path.isdir(f"/sys/class/net/{self.iface}"):
                        return "disconnected"
                last_hop = now

            read_fds = [self.sock]
            if stdin_fd is not None:
                read_fds.append(stdin_fd)

            try:
                readable, _, _ = select.select(read_fds, [], [], 0.12)
            except (InterruptedError, ValueError):
                continue

            if stdin_fd is not None and stdin_fd in readable:
                try:
                    chunk = os.read(stdin_fd, 256)
                except OSError:
                    chunk = b""
                if not chunk:
                    stop_flag[0] = True
                    break
                stdin_buf += chunk.decode("utf-8", "ignore")
                while "\n" in stdin_buf:
                    ln, stdin_buf = stdin_buf.split("\n", 1)
                    if not self.handle_command(ln):
                        stop_flag[0] = True
                        break

            if self.sock in readable and not stop_flag[0]:
                for _ in range(32):
                    try:
                        raw = self.sock.recv(4096)
                    except BlockingIOError:
                        break
                    except OSError:
                        return "disconnected"
                    if self.paused:
                        continue
                    pkt = parse_80211_frame(raw, fallback_ch=self.cur_ch, driver_tag=self.driver)
                    if pkt is not None:
                        _emit(pkt)
        return "stopped"


class ManagedScanSession:
    """
    Read-only managed-mode AP radar for consumer client-only USB Wi-Fi dongles (e.g. AIC8800,
    stock Realtek) or onboard handheld Wi-Fi when no monitor-capable USB dongle is attached.
    Never disconnects Wi-Fi or touches NetworkManager, and yields immediately if a monitor
    dongle is hot-plugged.
    """

    def __init__(self, adapter_info, initial_channel=0, interval_sec=4.0):
        self.info = adapter_info
        self.iface = adapter_info["iface"]
        self.driver = adapter_info["driver"] or "wifi"
        self.chip = adapter_info["chip"]
        self.usb_id = adapter_info.get("usb_id", "")
        self.target_ch = int(initial_channel)
        self.interval_sec = interval_sec
        self.paused = False

    def handle_command(self, line):
        cmd = line.strip().lower()
        if not cmd:
            return True
        if cmd in ("quit", "exit", "stop"):
            return False
        if cmd == "pause":
            self.paused = True
        elif cmd == "resume":
            self.paused = False
        elif cmd.startswith("ch "):
            arg = cmd.split(None, 1)[1].strip()
            if arg in ("hop", "0", "auto"):
                self.target_ch = 0
            else:
                try:
                    n = int(arg)
                    if 1 <= n <= 13:
                        self.target_ch = n
                except ValueError:
                    pass
        return True

    def _scan_once(self):
        # Try active scan first (fresh RSSI), fallback to cached scan dump (works even without root)
        for args in (
            ["iw", "dev", self.iface, "scan"],
            ["iw", "dev", self.iface, "scan", "dump"],
        ):
            try:
                r = _run_cmd(args, timeout=7.0)
                if r.returncode == 0 and r.stdout:
                    return parse_iw_scan_output(r.stdout, driver_tag=f"{self.driver}:scan")
            except Exception:
                continue
        return []

    def run_loop(self, stop_flag, requested_iface="auto", allow_internal_monitor=False):
        _emit({
            "ev": "wifi_hw",
            "status": "scan",
            "mode": "scan",
            "iface": self.iface,
            "driver": self.driver,
            "chip": self.chip,
            "usb_id": self.usb_id,
            "ch": self.target_ch,
            "hop": (self.target_ch == 0),
        })

        stdin_fd = sys.stdin.fileno() if sys.stdin and not sys.stdin.closed else None
        stdin_buf = ""
        last_scan = 0.0

        while not stop_flag[0]:
            if not os.path.isdir(f"/sys/class/net/{self.iface}"):
                return "disconnected"

            # Hot-upgrade immediately if user plugs in a true monitor-capable USB dongle!
            if requested_iface == "auto":
                cand = select_best_adapter("auto", allow_internal_monitor=allow_internal_monitor, allow_managed_scan=True)
                if cand and cand["mode_cap"] == "monitor" and (cand["bus"] == "usb" or allow_internal_monitor):
                    return "upgrade_monitor"

            now = time.monotonic()
            if not self.paused and (now - last_scan >= self.interval_sec):
                for pkt in self._scan_once():
                    if self.target_ch == 0 or pkt["ch"] == self.target_ch:
                        _emit(pkt)
                last_scan = time.monotonic()

            if stdin_fd is not None:
                try:
                    readable, _, _ = select.select([stdin_fd], [], [], 0.5)
                except (InterruptedError, ValueError):
                    continue
                if stdin_fd in readable:
                    try:
                        chunk = os.read(stdin_fd, 256)
                    except OSError:
                        chunk = b""
                    if not chunk:
                        stop_flag[0] = True
                        break
                    stdin_buf += chunk.decode("utf-8", "ignore")
                    while "\n" in stdin_buf:
                        ln, stdin_buf = stdin_buf.split("\n", 1)
                        if not self.handle_command(ln):
                            stop_flag[0] = True
                            break
            else:
                time.sleep(0.5)

        return "stopped"


def select_best_adapter(requested_iface="auto", allow_internal_monitor=False, allow_managed_scan=True,
                        sys_root="/sys", iw_phy_text=None):
    adapters = discover_wifi_adapters(sys_root=sys_root, iw_phy_text=iw_phy_text)
    if requested_iface and requested_iface != "auto":
        if not valid_iface_name(requested_iface):
            return None
        for a in adapters:
            if a["iface"] == requested_iface:
                if not a["monitor"] and not allow_managed_scan:
                    return None
                return a
        return None

    # 1. Always prefer a USB adapter with real monitor mode (RT3070, AR9271, MT76*, Realtek, etc.)
    for a in adapters:
        if a["bus"] == "usb" and a["monitor"]:
            return a

    # 2. Optional internal monitor-capable adapter (e.g. desktop Linux laptop card when requested)
    if allow_internal_monitor:
        for a in adapters:
            if a["monitor"]:
                return a

    # 3. Consumer client-only USB dongle (e.g. AIC8800, stock Realtek) -> Managed AP Scan fallback
    if allow_managed_scan:
        for a in adapters:
            if a["bus"] == "usb":
                return a
        # 4. Onboard handheld Wi-Fi -> read-only Managed AP Scan fallback (never drops SSH/Wi-Fi)
        if adapters:
            return adapters[0]

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Universal monitor & consumer USB Wi-Fi capture helper for STUMP RF Recon"
    )
    parser.add_argument("--iface", default="auto", help="Wireless interface (default: auto)")
    parser.add_argument("--channel", type=int, default=0, help="Fixed 2.4 GHz channel 1-13, or 0 for hop")
    parser.add_argument("--watch", action="store_true", help="Watch for hot-plugged dongles & auto-upgrade to monitor")
    parser.add_argument("--probe", action="store_true", help="Print all detected Wi-Fi adapters as JSON and exit")
    parser.add_argument("--monitor-only", action="store_true", help="Disable managed AP scan fallback for client-only dongles")
    parser.add_argument("--allow-internal", action="store_true", help="Allow monitor mode on non-USB internal Wi-Fi cards")
    args = parser.parse_args()

    if args.probe:
        adapters = discover_wifi_adapters()
        best = select_best_adapter(
            args.iface,
            allow_internal_monitor=args.allow_internal,
            allow_managed_scan=(not args.monitor_only),
        )
        _emit({
            "ev": "wifi_probe",
            "selected": best,
            "adapters": adapters,
        })
        return 0

    stop_flag = [False]

    def _on_signal(_sig, _frame):
        stop_flag[0] = True

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    stdin_fd = sys.stdin.fileno() if sys.stdin and not sys.stdin.closed else None
    waiting_announced = False

    while not stop_flag[0]:
        adapter = select_best_adapter(
            args.iface,
            allow_internal_monitor=args.allow_internal,
            allow_managed_scan=(not args.monitor_only),
        )

        if adapter is None:
            if not args.watch:
                _emit({"ev": "wifi_hw", "status": "absent", "reason": "No compatible Wi-Fi adapter found"})
                return 1
            if not waiting_announced:
                _emit({"ev": "wifi_hw", "status": "waiting", "reason": "Waiting for USB Wi-Fi adapter"})
                waiting_announced = True
            if stdin_fd is not None:
                try:
                    r_fds, _, _ = select.select([stdin_fd], [], [], 1.5)
                    if stdin_fd in r_fds:
                        data = os.read(stdin_fd, 256)
                        if not data or b"quit" in data.lower():
                            break
                except (InterruptedError, OSError, ValueError):
                    break
            else:
                time.sleep(1.5)
            continue

        waiting_announced = False
        use_monitor = bool(adapter["monitor"] and (adapter["bus"] == "usb" or args.allow_internal or args.iface != "auto"))

        if use_monitor:
            mon = MonitorCaptureSession(adapter, initial_channel=args.channel)
            try:
                mon.start()
                outcome = mon.run_loop(stop_flag)
                if outcome == "disconnected" and not stop_flag[0]:
                    _emit({"ev": "wifi_hw", "status": "disconnected", "iface": adapter["iface"], "driver": adapter["driver"]})
            except PermissionError as exc:
                # If run unprivileged without rk-stump-wifi, fall back gracefully to read-only scan if permitted
                _emit({
                    "ev": "wifi_hw",
                    "status": "error",
                    "reason": f"Monitor permission denied ({exc}). Run deploy/install.sh for /usr/local/sbin/rk-stump-wifi.",
                })
                return 13
            except Exception as exc:
                _emit({"ev": "wifi_hw", "status": "error", "reason": str(exc)})
                if not args.watch:
                    return 1
                time.sleep(2.0)
            finally:
                mon.stop()
        else:
            scanner = ManagedScanSession(adapter, initial_channel=args.channel)
            outcome = scanner.run_loop(
                stop_flag,
                requested_iface=args.iface,
                allow_internal_monitor=args.allow_internal,
            )
            if outcome == "upgrade_monitor":
                _emit({"ev": "wifi_hw", "status": "upgrading", "reason": "Monitor-capable USB adapter detected"})
                continue
            if outcome == "disconnected" and not stop_flag[0]:
                _emit({"ev": "wifi_hw", "status": "disconnected", "iface": adapter["iface"], "driver": adapter["driver"]})

        if not args.watch:
            break
        time.sleep(1.0)

    _emit({"ev": "wifi_hw", "status": "stopped"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
