#!/usr/bin/env python3
"""
field_deck.py — RK Field Deck: Unified Device-Card Recon, Scan & Diagnostic Arsenal HUD
Target: RK3326_Linux v1.2.0+ (R36MAX 720x720 + 93 RK3326 panels) & Desktop Linux

Workflow:
  1. Discovers real devices across LAN (ip neigh / arp-scan / rk-scan Sweep),
     Wi-Fi (universal wifi_mon.py monitor + consumer AP scan), and Sub-GHz LoRa
     (Heltec V3 / ESP32 serial). Zero simulated or placeholder devices.
  2. Displays each detected device as an interactive card in `1:DEVICES`.
  3. Clicking a card (or pressing A on the gamepad) opens the Device Action Menu
     listing every compatible RK3326_Linux Scan (`rk-scan`) and diagnostic
     Arsenal tool for that device.
  4. Executing a tool streams live output in `3:EXEC CONSOLE`, updates cards
     with discovered ports/hosts, and saves reports & .pcap captures under
     `/data/ark/field-deck/`.

RK3326_Linux Contract:
  - Inherits SDL_VIDEODRIVER=kmsdrm & rotated Mali LD_LIBRARY_PATH
  - Scales 720x720 logical canvas cleanly onto any panel resolution
  - SDL_GameController via SDL_GAMECONTROLLERCONFIG_FILE + click/keyboard support
  - Quit chord: SELECT + START (single SELECT closes overlays only)
  - Zero ALSA / audio device init; SIGTERM clean shutdown
"""

import collections
import datetime
import glob
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time

import pygame

try:
    from pygame._sdl2 import controller as sdl_controller
except Exception:
    sdl_controller = None

try:
    import serial
except Exception:
    serial = None

import tool_runner as TR

APP_VERSION = "1.0.0-rk3326"
LOGICAL_W, LOGICAL_H = 720, 720

# Tactical high-contrast palette matching STUMP Recon & RK3326_Linux Ember accents
C_BG = (7, 9, 14)
C_PANEL = (17, 24, 39)
C_CARD = (13, 20, 36)
C_CARD_SEL = (28, 46, 74)
C_BORDER = (51, 65, 85)
C_ACCENT = (234, 88, 12)     # RK3326 Ember Orange
C_CYAN = (56, 189, 248)
C_GREEN = (52, 211, 153)
C_AMBER = (251, 191, 36)
C_RED = (248, 113, 113)
C_TEXT = (241, 245, 249)
C_MUTED = (148, 163, 184)
C_DIM = (100, 116, 139)

VIEW_TABS = ["1:DEVICES", "2:SPECTRUM", "3:EXEC CONSOLE", "4:TOOLS"]
RK_FIELD_WIFI_BIN = "/usr/local/sbin/rk-field-wifi"
RK_STUMP_WIFI_BIN = "/usr/local/sbin/rk-stump-wifi"


def _serial_candidates():
    found = []
    for pat in ("/dev/serial/by-id/*", "/dev/ttyUSB*", "/dev/ttyACM*"):
        for p in sorted(glob.glob(pat)):
            real = os.path.realpath(p)
            if real not in found:
                found.append(real)
    return found


class DeviceStore:
    """Thread-safe live registry of real LAN, Wi-Fi, and LoRa devices."""

    def __init__(self):
        self.lock = threading.Lock()
        self.devices = {}          # uid -> dict
        self.wifi_ch_rssi = {}     # ch (1..13) -> latest rssi
        self.lora_bins = {}        # freq_mhz -> latest rssi
        self.wifi_status = "probing"
        self.lora_status = "none"

    def upsert_lan(self, ip, mac="", vendor="", iface="", hostname="", os_name="", ports=None):
        if not ip:
            return
        with self.lock:
            # Correlate by MAC if a Wi-Fi card already exists for this hardware address
            uid = None
            if mac:
                for k, d in self.devices.items():
                    if d.get("mac") and d["mac"].lower() == mac.lower():
                        uid = k
                        break
            if uid is None:
                uid = f"lan:{ip}"
            cur = self.devices.get(uid, {
                "uid": uid,
                "band": "LAN",
                "label": hostname or ip,
                "ip": ip,
                "mac": mac.lower() if mac else "",
                "vendor": vendor,
                "iface": iface,
                "ssid": "",
                "ch": 0,
                "rssi": None,
                "os": "",
                "ports": [],
                "pkts": 0,
                "last_seen": time.time(),
            })
            cur["ip"] = ip
            if mac:
                cur["mac"] = mac.lower()
            if vendor:
                cur["vendor"] = vendor
            if iface:
                cur["iface"] = iface
            if hostname:
                cur["label"] = hostname
            elif cur["label"] in ("", cur.get("mac", "")):
                cur["label"] = ip
            if os_name:
                cur["os"] = os_name
            if ports:
                cur["ports"] = ports
            cur["band"] = "LAN+WIFI" if cur.get("ch") else "LAN"
            cur["pkts"] = cur.get("pkts", 0) + 1
            cur["last_seen"] = time.time()
            self.devices[uid] = cur

    def upsert_wifi(self, ev):
        mac = (ev.get("mac") or "").lower()
        if not mac:
            return
        ch = int(ev.get("ch") or 0)
        rssi = ev.get("rssi")
        ssid = (ev.get("ssid") or "").strip()
        with self.lock:
            if 1 <= ch <= 13 and rssi is not None:
                self.wifi_ch_rssi[ch] = max(int(rssi), self.wifi_ch_rssi.get(ch, -100))
            uid = None
            for k, d in self.devices.items():
                if d.get("mac") and d["mac"].lower() == mac:
                    uid = k
                    break
            if uid is None:
                uid = f"wifi:{mac}"
            cur = self.devices.get(uid, {
                "uid": uid,
                "band": "WIFI",
                "label": ssid or mac,
                "ip": "",
                "mac": mac,
                "vendor": "",
                "iface": "",
                "ssid": ssid,
                "ch": ch,
                "rssi": rssi,
                "os": "",
                "ports": [],
                "pkts": 0,
                "last_seen": time.time(),
            })
            if ssid:
                cur["ssid"] = ssid
                if not cur.get("ip"):
                    cur["label"] = ssid
            if ch:
                cur["ch"] = ch
            if rssi is not None:
                cur["rssi"] = int(rssi)
            cur["band"] = "LAN+WIFI" if cur.get("ip") else "WIFI"
            cur["pkts"] = cur.get("pkts", 0) + 1
            cur["last_seen"] = time.time()
            self.devices[uid] = cur

    def upsert_lora(self, ev):
        node_id = str(ev.get("src") or ev.get("id") or ev.get("from") or "lora-node")
        freq = float(ev.get("freq") or 915.0)
        rssi = int(ev.get("rssi") or -105)
        with self.lock:
            self.lora_bins[round(freq, 1)] = rssi
            uid = f"lora:{node_id}"
            cur = self.devices.get(uid, {
                "uid": uid,
                "band": "LORA",
                "label": f"LoRa {node_id}",
                "ip": "",
                "mac": "",
                "vendor": ev.get("proto", "Sub-GHz"),
                "iface": "",
                "ssid": "",
                "ch": 0,
                "freq": freq,
                "sf": ev.get("sf", 0),
                "rssi": rssi,
                "os": "",
                "ports": [],
                "pkts": 0,
                "last_seen": time.time(),
            })
            cur["freq"] = freq
            cur["rssi"] = rssi
            cur["pkts"] = cur.get("pkts", 0) + 1
            cur["last_seen"] = time.time()
            self.devices[uid] = cur

    def snapshot(self, band_filter="ALL"):
        with self.lock:
            items = list(self.devices.values())
        if band_filter != "ALL":
            items = [d for d in items if band_filter in d["band"]]
        items.sort(key=lambda d: (0 if d.get("ip") else 1, -(d.get("rssi") if d.get("rssi") is not None else -120), -d["last_seen"]))
        return items


class FieldDeckApp:
    def __init__(self):
        self.running = True
        self.store = DeviceStore()
        self.data_dir = TR.resolve_data_dir()
        os.makedirs(os.path.join(self.data_dir, "reports"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "captures"), exist_ok=True)

        self.view_idx = 0
        self.band_filter = "ALL"
        self.sel_card = 0
        self.card_scroll = 0
        self.menu_open = False
        self.menu_device = None
        self.menu_tools = []
        self.menu_sel = 0
        self.menu_scroll = 0

        self.active_job = None
        self.job_history = collections.deque(maxlen=20)
        self.console_scroll = 0
        self.toast_msg = ""
        self.toast_until = 0.0
        self.own_networks = TR.list_own_networks()
        self.tool_probe = TR.probe_environment()

        self._wifi_proc = None
        self._stop_evt = threading.Event()
        self._click_regions = []
        self._sel_down = False
        self._start_down = False

    def toast(self, msg, secs=4.0):
        self.toast_msg = msg
        self.toast_until = time.time() + secs

    # ------------------------------------------------------------------
    # Real hardware / network discovery workers (ZERO simulated data)
    # ------------------------------------------------------------------
    def start_workers(self):
        threading.Thread(target=self._wk_lan_neighbors, daemon=True).start()
        threading.Thread(target=self._wk_wifi, daemon=True).start()
        threading.Thread(target=self._wk_lora, daemon=True).start()

    def _wk_lan_neighbors(self):
        while not self._stop_evt.is_set():
            self.own_networks = TR.list_own_networks()
            for h in TR.read_local_arp_neighbors():
                self.store.upsert_lan(h["ip"], mac=h["mac"], iface=h["iface"])
            self._stop_evt.wait(8.0)

    def _wk_wifi(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        local_mon = os.path.join(script_dir, "wifi_mon.py")
        if os.path.exists(RK_FIELD_WIFI_BIN):
            cmd = [RK_FIELD_WIFI_BIN, "--watch"] if os.geteuid() == 0 else ["sudo", "-n", RK_FIELD_WIFI_BIN, "--watch"]
        elif os.path.exists(RK_STUMP_WIFI_BIN):
            cmd = [RK_STUMP_WIFI_BIN, "--watch"] if os.geteuid() == 0 else ["sudo", "-n", RK_STUMP_WIFI_BIN, "--watch"]
        elif os.path.exists(local_mon):
            cmd = [sys.executable, local_mon, "--watch"]
        else:
            self.store.wifi_status = "helper missing"
            return

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            self._wifi_proc = proc
            for raw in proc.stdout:
                if self._stop_evt.is_set():
                    break
                try:
                    ev = json.loads(raw)
                except ValueError:
                    continue
                if ev.get("ev") == "wifi":
                    self.store.upsert_wifi(ev)
                elif ev.get("ev") == "wifi_status":
                    st = ev.get("status", "")
                    chip = ev.get("chip", "")
                    ifc = ev.get("iface", "")
                    if st == "monitor":
                        self.store.wifi_status = f"MON:{chip}({ifc})"
                    elif st == "scan":
                        self.store.wifi_status = f"SCAN:{chip}({ifc})"
                    elif st:
                        self.store.wifi_status = st
        except Exception:
            self.store.wifi_status = "offline"

    def _wk_lora(self):
        if serial is None:
            self.store.lora_status = "pyserial n/a"
            return
        while not self._stop_evt.is_set():
            ports = _serial_candidates()
            if not ports:
                self.store.lora_status = "no board"
                self._stop_evt.wait(4.0)
                continue
            port = ports[0]
            try:
                with serial.Serial(port, 115200, timeout=1.0) as ser:
                    self.store.lora_status = os.path.basename(port)
                    while not self._stop_evt.is_set():
                        raw = ser.readline().decode("utf-8", errors="ignore").strip()
                        if not raw.startswith("{"):
                            continue
                        try:
                            ev = json.loads(raw)
                        except ValueError:
                            continue
                        if ev.get("ev") in ("lora", "rx", "packet"):
                            self.store.upsert_lora(ev)
                        elif ev.get("ev") == "wifi":
                            self.store.upsert_wifi(ev)
            except Exception:
                self.store.lora_status = "reconnecting"
                self._stop_evt.wait(3.0)

    def shutdown(self):
        self.running = False
        self._stop_evt.set()
        if self.active_job and self.active_job.running:
            self.active_job.cancel()
        if self._wifi_proc and self._wifi_proc.poll() is None:
            try:
                if self._wifi_proc.stdin:
                    self._wifi_proc.stdin.close()
                self._wifi_proc.wait(timeout=2.0)
            except Exception:
                try:
                    self._wifi_proc.terminate()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Device Card -> Menu -> Execute Actions
    # ------------------------------------------------------------------
    def open_device_menu(self, device):
        self.menu_device = dict(device)
        self.menu_tools = TR.tools_for_device(device)
        self.menu_sel = 0
        self.menu_scroll = 0
        self.menu_open = True

    def execute_tool(self, tool_id, device):
        if self.active_job and self.active_job.running:
            self.active_job.cancel()
        self.menu_open = False
        self.view_idx = 2  # Switch straight to 3:EXEC CONSOLE
        self.console_scroll = 0

        def on_done(job):
            for h in job.parsed_hosts:
                self.store.upsert_lan(
                    h["ip"],
                    mac=h.get("mac", ""),
                    vendor=h.get("vendor", ""),
                    hostname=h.get("hostname", ""),
                    os_name=h.get("os", ""),
                    ports=h.get("ports", []),
                )
            self.job_history.appendleft({
                "tool": job.tool["label"],
                "target": job.device.get("ip") or job.device.get("mac") or job.device.get("cidr", ""),
                "rc": job.returncode,
                "ts": datetime.datetime.now().strftime("%H:%M:%S"),
            })

        job = TR.ToolJob(tool_id, device, on_done=on_done)
        self.active_job = job
        job.start()
        self.toast(f"Running {job.tool['label']}...")

    def run_lan_refresh(self):
        if not self.own_networks:
            self.toast("No active IPv4 network interface found")
            return
        ifc, cidr, _ = self.own_networks[0]
        if TR.tool_available(TR.TOOL_BY_ID["arp_scan_lan"]):
            self.execute_tool("arp_scan_lan", {"band": "LAN", "iface": ifc, "cidr": cidr, "label": cidr})
        else:
            self.execute_tool("scan_sweep", {"band": "LAN", "iface": ifc, "cidr": cidr, "label": cidr})

    def save_active_report(self):
        if not self.active_job:
            self.toast("No tool output to save yet")
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{self.active_job.tool_id}_{ts}.txt"
        out_path = os.path.join(self.data_dir, "reports", fname)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"# RK Field Deck {APP_VERSION}\n")
            f.write(f"# Tool: {self.active_job.tool['label']}\n")
            f.write(f"# Command: {self.active_job.preview}\n\n")
            f.write("\n".join(self.active_job.lines) + "\n")
        self.toast(f"Saved report -> {out_path}")

    # ------------------------------------------------------------------
    # Input Handling (Gamepad + Keyboard + Mouse/Click)
    # ------------------------------------------------------------------
    def handle_action(self, action):
        if self.menu_open:
            if action in ("b", "select"):
                self.menu_open = False
                return
            if action == "up" and self.menu_tools:
                self.menu_sel = (self.menu_sel - 1) % len(self.menu_tools)
            elif action == "down" and self.menu_tools:
                self.menu_sel = (self.menu_sel + 1) % len(self.menu_tools)
            elif action == "a" and self.menu_tools:
                chosen = self.menu_tools[self.menu_sel]
                self.execute_tool(chosen["id"], self.menu_device)
            return

        if action == "l1":
            self.view_idx = (self.view_idx - 1) % len(VIEW_TABS)
            return
        if action == "r1":
            self.view_idx = (self.view_idx + 1) % len(VIEW_TABS)
            return

        if self.view_idx == 0:
            cards = self.store.snapshot(self.band_filter)
            if action == "y":
                self.run_lan_refresh()
            elif action == "x":
                order = ["ALL", "LAN", "WIFI", "LORA"]
                self.band_filter = order[(order.index(self.band_filter) + 1) % len(order)]
                self.sel_card = 0
            elif cards:
                if action == "right":
                    self.sel_card = min(len(cards) - 1, self.sel_card + 1)
                elif action == "left":
                    self.sel_card = max(0, self.sel_card - 1)
                elif action == "down":
                    self.sel_card = min(len(cards) - 1, self.sel_card + 2)
                elif action == "up":
                    self.sel_card = max(0, self.sel_card - 2)
                elif action == "a":
                    self.open_device_menu(cards[min(self.sel_card, len(cards) - 1)])
        elif self.view_idx == 2:
            if action == "b" and self.active_job and self.active_job.running:
                self.active_job.cancel()
                self.toast("Cancelled running tool")
            elif action == "x":
                self.save_active_report()
            elif action == "up":
                self.console_scroll += 4
            elif action == "down":
                self.console_scroll = max(0, self.console_scroll - 4)

    # ------------------------------------------------------------------
    # Rendering (720x720 logical canvas scaled cleanly to any panel)
    # ------------------------------------------------------------------
    def _draw_header(self, surf, f_title, f_sm):
        pygame.draw.rect(surf, C_PANEL, (8, 8, LOGICAL_W - 16, 52), border_radius=6)
        pygame.draw.rect(surf, C_BORDER, (8, 8, LOGICAL_W - 16, 52), 1, border_radius=6)
        surf.blit(f_title.render("RK FIELD DECK", True, C_ACCENT), (20, 14))
        status_line = f"WIFI:{self.store.wifi_status}  LORA:{self.store.lora_status}"
        surf.blit(f_sm.render(status_line[:52], True, C_GREEN), (20, 38))
        net_txt = self.own_networks[0][1] if self.own_networks else "no LAN IP"
        net_s = f_sm.render(f"LAN {net_txt}", True, C_AMBER)
        surf.blit(net_s, (LOGICAL_W - 20 - net_s.get_width(), 16))
        cnt_s = f_sm.render(f"{len(self.store.devices)} detected", True, C_MUTED)
        surf.blit(cnt_s, (LOGICAL_W - 20 - cnt_s.get_width(), 38))

        # 4 Tabs
        tw = (LOGICAL_W - 16 - 18) // 4
        for i, lbl in enumerate(VIEW_TABS):
            rx = 8 + i * (tw + 6)
            rect = pygame.Rect(rx, 66, tw, 28)
            active = i == self.view_idx
            pygame.draw.rect(surf, C_CARD_SEL if active else C_PANEL, rect, border_radius=4)
            pygame.draw.rect(surf, C_ACCENT if active else C_BORDER, rect, 1, border_radius=4)
            t = f_sm.render(lbl, True, C_TEXT if active else C_MUTED)
            surf.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - t.get_height() // 2))
            self._click_regions.append((rect, lambda idx=i: setattr(self, "view_idx", idx)))

    def _draw_devices(self, surf, f_md, f_sm):
        cards = self.store.snapshot(self.band_filter)
        top_bar = f"DETECTED DEVICE CARDS ({len(cards)}) · FILTER: {self.band_filter} · CLICK OR [A] FOR SCAN & ARSENAL MENU"
        surf.blit(f_sm.render(top_bar[:84], True, C_CYAN), (14, 104))

        if not cards:
            box = pygame.Rect(14, 132, LOGICAL_W - 28, 170)
            pygame.draw.rect(surf, C_PANEL, box, border_radius=6)
            pygame.draw.rect(surf, C_BORDER, box, 1, border_radius=6)
            lines = [
                "No live devices detected yet.",
                "Press [Y] to run LAN Discovery (arp-scan / rk-scan Sweep) on your active subnet,",
                "or plug in any monitor/consumer USB Wi-Fi adapter or Heltec V3 LoRa radio.",
                "Zero simulated or placeholder devices are shown.",
            ]
            for idx, ln in enumerate(lines):
                surf.blit(f_sm.render(ln, True, C_TEXT if idx == 0 else C_MUTED), (28, 152 + idx * 28))
            btn = pygame.Rect(28, 260, 210, 30)
            pygame.draw.rect(surf, C_ACCENT, btn, border_radius=4)
            surf.blit(f_sm.render("Run LAN Discovery [Y]", True, C_TEXT), (42, 267))
            self._click_regions.append((btn, self.run_lan_refresh))
            return

        self.sel_card = max(0, min(self.sel_card, len(cards) - 1))
        card_w = (LOGICAL_W - 36) // 2
        card_h = 112
        per_page = 8
        row_of_sel = self.sel_card // 2
        if row_of_sel < self.card_scroll:
            self.card_scroll = row_of_sel
        elif row_of_sel >= self.card_scroll + 4:
            self.card_scroll = row_of_sel - 3
        start_idx = self.card_scroll * 2

        for slot, idx in enumerate(range(start_idx, min(len(cards), start_idx + per_page))):
            d = cards[idx]
            col, row = slot % 2, slot // 2
            rect = pygame.Rect(14 + col * (card_w + 8), 126 + row * (card_h + 8), card_w, card_h)
            sel = idx == self.sel_card
            pygame.draw.rect(surf, C_CARD_SEL if sel else C_CARD, rect, border_radius=6)
            pygame.draw.rect(surf, C_ACCENT if sel else C_BORDER, rect, 2 if sel else 1, border_radius=6)

            band_col = C_GREEN if "LAN" in d["band"] else (C_AMBER if d["band"] == "WIFI" else C_CYAN)
            surf.blit(f_sm.render(d["band"], True, band_col), (rect.x + 10, rect.y + 8))
            n_tools = len(TR.tools_for_device(d))
            tc = f_sm.render(f"{n_tools} tools", True, C_MUTED)
            surf.blit(tc, (rect.right - 10 - tc.get_width(), rect.y + 8))

            title = (d.get("label") or d.get("ip") or d.get("mac") or "Device")[:28]
            surf.blit(f_md.render(title, True, C_TEXT), (rect.x + 10, rect.y + 28))

            sub1 = f"IP: {d['ip'] or '-'}   MAC: {d['mac'] or '-'}"
            surf.blit(f_sm.render(sub1[:44], True, C_MUTED), (rect.x + 10, rect.y + 54))

            extra_parts = []
            if d.get("ch"):
                extra_parts.append(f"Ch{d['ch']}")
            if d.get("rssi") is not None:
                extra_parts.append(f"{d['rssi']}dBm")
            if d.get("ports"):
                extra_parts.append(f"{len(d['ports'])} open ports")
            elif d.get("vendor"):
                extra_parts.append(d["vendor"][:18])
            surf.blit(f_sm.render(" · ".join(extra_parts)[:44], True, C_AMBER if d.get("ports") else C_DIM), (rect.x + 10, rect.y + 78))

            def _click_card(i=idx, dev=d):
                self.sel_card = i
                self.open_device_menu(dev)

            self._click_regions.append((rect, _click_card))

    def _draw_device_menu(self, surf, f_md, f_sm):
        dim = pygame.Surface((LOGICAL_W, LOGICAL_H), pygame.SRCALPHA)
        dim.fill((4, 6, 10, 215))
        surf.blit(dim, (0, 0))

        box = pygame.Rect(34, 48, LOGICAL_W - 68, LOGICAL_H - 96)
        pygame.draw.rect(surf, C_PANEL, box, border_radius=8)
        pygame.draw.rect(surf, C_ACCENT, box, 2, border_radius=8)

        dev = self.menu_device or {}
        hdr = f"ACTIONS FOR: {(dev.get('label') or dev.get('ip') or dev.get('mac') or 'Device')[:36]}"
        surf.blit(f_md.render(hdr, True, C_TEXT), (box.x + 16, box.y + 14))
        meta = f"IP: {dev.get('ip') or 'none'}  ·  MAC: {dev.get('mac') or 'none'}  ·  [A/Click] Execute  [B] Back"
        surf.blit(f_sm.render(meta[:76], True, C_MUTED), (box.x + 16, box.y + 40))
        pygame.draw.line(surf, C_BORDER, (box.x + 12, box.y + 62), (box.right - 12, box.y + 62))

        if not self.menu_tools:
            surf.blit(f_sm.render("No Scan or Arsenal tools match this device (needs IP or MAC).", True, C_AMBER), (box.x + 16, box.y + 84))
            return

        row_h = 46
        visible = 9
        if self.menu_sel < self.menu_scroll:
            self.menu_scroll = self.menu_sel
        elif self.menu_sel >= self.menu_scroll + visible:
            self.menu_scroll = self.menu_sel - visible + 1

        for slot, idx in enumerate(range(self.menu_scroll, min(len(self.menu_tools), self.menu_scroll + visible))):
            tool = self.menu_tools[idx]
            rr = pygame.Rect(box.x + 14, box.y + 72 + slot * (row_h + 4), box.w - 28, row_h)
            sel = idx == self.menu_sel
            pygame.draw.rect(surf, C_CARD_SEL if sel else C_CARD, rr, border_radius=5)
            pygame.draw.rect(surf, C_ACCENT if sel else C_BORDER, rr, 1, border_radius=5)

            surf.blit(f_sm.render(f"[{tool['group']}]  {tool['label']}", True, C_TEXT if sel else C_CYAN), (rr.x + 10, rr.y + 5))
            state_lbl = "ready" if tool["installed"] else f"missing {tool['binary']}"
            st_surf = f_sm.render(state_lbl, True, C_GREEN if tool["installed"] else C_RED)
            surf.blit(st_surf, (rr.right - 10 - st_surf.get_width(), rr.y + 5))
            surf.blit(f_sm.render(tool["description"][:76], True, C_MUTED), (rr.x + 10, rr.y + 24))

            def _exec(tid=tool["id"], d=dev):
                self.execute_tool(tid, d)

            self._click_regions.append((rr, _exec))

        # Exact command preview for currently highlighted tool
        cur = self.menu_tools[self.menu_sel]
        try:
            prev = TR.build_tool_command(
                cur["id"],
                target_ip=dev.get("ip", ""),
                target_mac=dev.get("mac", ""),
                target_cidr=dev.get("cidr", ""),
                iface=dev.get("iface", ""),
            )["preview"]
        except Exception as exc:
            prev = str(exc)
        foot = pygame.Rect(box.x + 14, box.bottom - 52, box.w - 28, 38)
        pygame.draw.rect(surf, C_BG, foot, border_radius=4)
        pygame.draw.rect(surf, C_BORDER, foot, 1, border_radius=4)
        surf.blit(f_sm.render(f"$ {prev}"[:78], True, C_AMBER), (foot.x + 10, foot.y + 10))

    def _draw_spectrum(self, surf, f_md, f_sm):
        surf.blit(f_md.render("2.4 GHz WI-FI CHANNEL ACTIVITY (LIVE)", True, C_AMBER), (16, 108))
        box = pygame.Rect(14, 138, LOGICAL_W - 28, 220)
        pygame.draw.rect(surf, C_PANEL, box, border_radius=6)
        pygame.draw.rect(surf, C_BORDER, box, 1, border_radius=6)
        slot = (box.w - 26) // 13
        for ch in range(1, 14):
            x = box.x + 14 + (ch - 1) * slot
            rssi = self.store.wifi_ch_rssi.get(ch)
            if rssi is not None:
                h = max(8, int(((rssi + 105) / 65.0) * (box.h - 54)))
                h = min(h, box.h - 54)
                pygame.draw.rect(surf, C_ACCENT if rssi > -60 else C_GREEN, (x + 4, box.bottom - 30 - h, slot - 10, h), border_radius=3)
            lbl = f_sm.render(str(ch), True, C_MUTED)
            surf.blit(lbl, (x + (slot - lbl.get_width()) // 2, box.bottom - 22))

        surf.blit(f_md.render("SUB-GHZ LORA LIVE CHANNELS", True, C_CYAN), (16, 378))
        lbox = pygame.Rect(14, 408, LOGICAL_W - 28, 190)
        pygame.draw.rect(surf, C_PANEL, lbox, border_radius=6)
        pygame.draw.rect(surf, C_BORDER, lbox, 1, border_radius=6)
        if not self.store.lora_bins:
            surf.blit(f_sm.render("No LoRa packets received yet (attach Heltec V3 / ESP32 USB serial).", True, C_MUTED), (28, 440))
        else:
            for idx, (freq, rssi) in enumerate(sorted(self.store.lora_bins.items())[:8]):
                surf.blit(f_sm.render(f"{freq:.1f} MHz  ·  {rssi} dBm", True, C_CYAN), (28, 426 + idx * 22))

    def _draw_console(self, surf, f_md, f_sm):
        job = self.active_job
        hdr = "EXECUTION CONSOLE"
        if job:
            state = "RUNNING" if job.running else f"EXIT {job.returncode}"
            hdr = f"{job.tool['label']}  [{state}]"
        surf.blit(f_md.render(hdr[:62], True, C_GREEN if (job and job.running) else C_TEXT), (16, 106))

        box = pygame.Rect(14, 136, LOGICAL_W - 28, 496)
        pygame.draw.rect(surf, C_BG, box, border_radius=6)
        pygame.draw.rect(surf, C_BORDER, box, 1, border_radius=6)

        if not job:
            surf.blit(f_sm.render("Select a Device Card in 1:DEVICES and execute any Scan or Arsenal tool.", True, C_MUTED), (28, 160))
            return

        with job._lock:
            lines = list(job.lines)
        max_rows = 24
        end = max(0, len(lines) - self.console_scroll)
        start = max(0, end - max_rows)
        for row, ln in enumerate(lines[start:end]):
            col = C_AMBER if ln.startswith("$ ") else (C_RED if ln.startswith("[error]") else C_TEXT)
            surf.blit(f_sm.render(ln[:84], True, col), (24, 146 + row * 20))

    def _draw_tools(self, surf, f_md, f_sm):
        p = self.tool_probe
        surf.blit(
            f_md.render(f"INSTALLED SCAN & DIAGNOSTIC ARSENAL ({p['installed_count']}/{p['total_count']})", True, C_TEXT),
            (16, 106),
        )
        for idx, t in enumerate(p["tools"][:18]):
            y = 136 + idx * 28
            col = C_GREEN if t["installed"] else C_DIM
            surf.blit(f_sm.render(f"[{'OK' if t['installed'] else '--'}] {t['group']:<20} {t['label']}", True, col), (18, y))

    def _draw_footer(self, surf, f_sm):
        rect = pygame.Rect(8, LOGICAL_H - 36, LOGICAL_W - 16, 28)
        pygame.draw.rect(surf, C_PANEL, rect, border_radius=4)
        pygame.draw.rect(surf, C_BORDER, rect, 1, border_radius=4)
        if time.time() < self.toast_until and self.toast_msg:
            surf.blit(f_sm.render(self.toast_msg[:84], True, C_GREEN), (18, rect.y + 6))
        else:
            if self.view_idx == 0:
                hint = "[L1/R1]Views [A/Click]Device Menu [Y]LAN Sweep [X]Filter [SEL+START]Exit"
            elif self.view_idx == 2:
                hint = "[L1/R1]Views [UP/DN]Scroll [X]Save Report [B]Cancel Job [SEL+START]Exit"
            else:
                hint = "[L1/R1]Views [SEL+START]Exit to rkshell"
            surf.blit(f_sm.render(hint, True, C_AMBER), (18, rect.y + 6))

    # ------------------------------------------------------------------
    # Main Loop
    # ------------------------------------------------------------------
    def run(self):
        pygame.init()
        pygame.font.init()
        if sdl_controller is not None:
            try:
                sdl_controller.init()
            except Exception:
                pass

        # Inherit SDL_VIDEODRIVER (kmsdrm under rkshell) without overwriting it
        drv = pygame.display.get_driver()
        fullscreen = drv in ("kmsdrm", "KMSDRM", "directfb", "fbcon")
        if fullscreen:
            info = pygame.display.Info()
            win_w, win_h = info.current_w or LOGICAL_W, info.current_h or LOGICAL_H
            screen = pygame.display.set_mode((win_w, win_h), pygame.FULLSCREEN)
            pygame.mouse.set_visible(False)
        else:
            win_w, win_h = LOGICAL_W, LOGICAL_H
            screen = pygame.display.set_mode((win_w, win_h))
            pygame.display.set_caption(f"RK Field Deck ({APP_VERSION})")

        canvas = pygame.Surface((LOGICAL_W, LOGICAL_H))
        f_title = pygame.font.SysFont("dejavusansmono", 19, bold=True)
        f_md = pygame.font.SysFont("dejavusansmono", 15, bold=True)
        f_sm = pygame.font.SysFont("dejavusansmono", 13)

        controllers = []
        if sdl_controller is not None:
            for i in range(pygame.joystick.get_count()):
                if sdl_controller.is_controller(i):
                    try:
                        controllers.append(sdl_controller.Controller(i))
                    except Exception:
                        pass

        self.start_workers()
        clock = pygame.time.Clock()

        def _scale_mouse(pos):
            sx = LOGICAL_W / max(1, screen.get_width())
            sy = LOGICAL_H / max(1, screen.get_height())
            return (int(pos[0] * sx), int(pos[1] * sy))

        try:
            while self.running:
                for ev in pygame.event.get():
                    if ev.type == pygame.QUIT:
                        self.running = False
                    elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                        pt = _scale_mouse(ev.pos)
                        for rect, cb in reversed(self._click_regions):
                            if rect.collidepoint(pt):
                                cb()
                                break
                    elif ev.type == pygame.KEYDOWN:
                        if ev.key == pygame.K_ESCAPE:
                            if self.menu_open:
                                self.menu_open = False
                            else:
                                self.running = False
                        elif ev.key == pygame.K_TAB:
                            self.handle_action("r1")
                        elif ev.key == pygame.K_UP:
                            self.handle_action("up")
                        elif ev.key == pygame.K_DOWN:
                            self.handle_action("down")
                        elif ev.key == pygame.K_LEFT:
                            self.handle_action("left")
                        elif ev.key == pygame.K_RIGHT:
                            self.handle_action("right")
                        elif ev.key in (pygame.K_RETURN, pygame.K_a):
                            self.handle_action("a")
                        elif ev.key in (pygame.K_BACKSPACE, pygame.K_b):
                            self.handle_action("b")
                        elif ev.key == pygame.K_x:
                            self.handle_action("x")
                        elif ev.key == pygame.K_y:
                            self.handle_action("y")
                    elif ev.type == pygame.CONTROLLERBUTTONDOWN:
                        b = ev.button
                        if b == pygame.CONTROLLER_BUTTON_BACK:
                            self._sel_down = True
                            if self._start_down:
                                self.running = False
                            else:
                                self.handle_action("select")
                        elif b == pygame.CONTROLLER_BUTTON_START:
                            self._start_down = True
                            if self._sel_down:
                                self.running = False
                        elif b == pygame.CONTROLLER_BUTTON_LEFTSHOULDER:
                            self.handle_action("l1")
                        elif b == pygame.CONTROLLER_BUTTON_RIGHTSHOULDER:
                            self.handle_action("r1")
                        elif b == pygame.CONTROLLER_BUTTON_DPAD_UP:
                            self.handle_action("up")
                        elif b == pygame.CONTROLLER_BUTTON_DPAD_DOWN:
                            self.handle_action("down")
                        elif b == pygame.CONTROLLER_BUTTON_DPAD_LEFT:
                            self.handle_action("left")
                        elif b == pygame.CONTROLLER_BUTTON_DPAD_RIGHT:
                            self.handle_action("right")
                        elif b == pygame.CONTROLLER_BUTTON_A:
                            self.handle_action("a")
                        elif b == pygame.CONTROLLER_BUTTON_B:
                            self.handle_action("b")
                        elif b == pygame.CONTROLLER_BUTTON_X:
                            self.handle_action("x")
                        elif b == pygame.CONTROLLER_BUTTON_Y:
                            self.handle_action("y")
                    elif ev.type == pygame.CONTROLLERBUTTONUP:
                        if ev.button == pygame.CONTROLLER_BUTTON_BACK:
                            self._sel_down = False
                        elif ev.button == pygame.CONTROLLER_BUTTON_START:
                            self._start_down = False

                self._click_regions = []
                canvas.fill(C_BG)
                self._draw_header(canvas, f_title, f_sm)
                if self.view_idx == 0:
                    self._draw_devices(canvas, f_md, f_sm)
                elif self.view_idx == 1:
                    self._draw_spectrum(canvas, f_md, f_sm)
                elif self.view_idx == 2:
                    self._draw_console(canvas, f_md, f_sm)
                elif self.view_idx == 3:
                    self._draw_tools(canvas, f_md, f_sm)
                self._draw_footer(canvas, f_sm)
                if self.menu_open:
                    self._draw_device_menu(canvas, f_md, f_sm)

                if screen.get_size() == (LOGICAL_W, LOGICAL_H):
                    screen.blit(canvas, (0, 0))
                else:
                    pygame.transform.smoothscale(canvas, screen.get_size(), screen)
                pygame.display.flip()
                clock.tick(20)
        finally:
            self.shutdown()
            pygame.quit()


def main():
    app = FieldDeckApp()
    signal.signal(signal.SIGTERM, lambda *_: app.shutdown())
    signal.signal(signal.SIGINT, lambda *_: app.shutdown())
    app.run()


if __name__ == "__main__":
    main()
