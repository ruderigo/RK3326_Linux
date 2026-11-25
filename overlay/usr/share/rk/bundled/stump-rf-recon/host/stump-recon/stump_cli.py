#!/usr/bin/env python3
"""
stump_cli.py — Headless CLI reader & JSONL recorder for RK3326_Linux / R36MAX
Supports:
  - Heltec V3 / ESP32 USB serial (Sub-GHz LoRa + ESP32 Wi-Fi)
  - Any monitor-capable USB Wi-Fi dongle (RT3070/rt2800usb, AR9271/ath9k_htc, MT76*, Realtek 88xx/8188/8852)
    or consumer client-only Wi-Fi adapter (managed AP scan fallback) via /usr/local/sbin/rk-stump-wifi or wifi_mon.py
  - Both simultaneously (unified JSONL capture stream)

Stores logs under /data/ark/stump-recon/exports (survives OS reflashes) with
automatic fallback to /roms/stump or ~/stump-recon/exports.
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import threading
import time

try:
    import serial
except ImportError:
    serial = None


def resolve_log_dir():
    env_dir = os.environ.get("STUMP_RECON_DATA_DIR")
    if env_dir:
        return os.path.join(env_dir, "exports")
    if os.path.isdir("/data/ark") and os.access("/data/ark", os.W_OK):
        return "/data/ark/stump-recon/exports"
    if os.path.isdir("/roms/stump") and os.access("/roms/stump", os.W_OK):
        return "/roms/stump"
    return os.path.expanduser("~/stump-recon/exports")


def find_port():
    candidates = [
        "/dev/ttyUSB0",
        "/dev/ttyACM0",
        "/dev/ttyUSB1",
        "/dev/ttyACM1",
    ]
    candidates.extend(sorted(glob.glob("/dev/serial/by-id/*")))
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def fmt_rx(d):
    tag = "RX " if d.get("crc_ok") else "RX!"
    sync = d.get("sync")
    proto = "RNS " if sync == 18 else "MESH" if sync == 43 else "LORA"
    base = (
        f"{tag} [{proto}] {d.get('freq'):>7}MHz SF{d.get('sf')} BW{d.get('bw')} "
        f"len={d.get('len', '?'):>3} RSSI={d.get('rssi'):>6}dBm "
        f"SNR={d.get('snr'):>5}dB ferr={d.get('ferr', '?')}Hz"
    )
    pl = d.get("payload")
    if pl:
        base += f"  pl={pl[:28]}…" if len(pl) > 28 else f"  pl={pl}"
    return base


def fmt_wifi(d):
    src = str(d.get("src") or "WIFI")[:12]
    ssid = d.get("ssid") or "<Wildcard>"
    return (
        f"{src:<12} Ch{int(d.get('ch', 1)):02d} {str(d.get('ftype', 'MGMT')):<9} "
        f"{d.get('mac', '')} RSSI={d.get('rssi')}dBm SSID=\"{ssid[:24]}\""
    )


def _start_wifi_helper(iface, channel, monitor_only=False):
    local_helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wifi_mon.py")
    sys_helper = "/usr/local/sbin/rk-stump-wifi"
    base_args = ["--watch", "--iface", iface, "--channel", str(int(channel))]
    if monitor_only:
        base_args.append("--monitor-only")

    if os.geteuid() == 0 and os.path.isfile(local_helper):
        cmd = [sys.executable, "-u", local_helper] + base_args
    elif os.path.isfile(sys_helper) and os.access(sys_helper, os.X_OK):
        cmd = ["sudo", "-n", sys_helper] + base_args
    elif os.path.isfile(local_helper):
        cmd = [sys.executable, "-u", local_helper] + base_args
    else:
        return None

    return subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def main():
    parser = argparse.ArgumentParser(
        description="STUMP RF Recon headless logger (Heltec V3 serial + universal monitor/consumer USB Wi-Fi)"
    )
    parser.add_argument("--port", help="Override serial device path (e.g. /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    parser.add_argument("--no-serial", action="store_true", help="Disable Heltec V3 serial capture")
    parser.add_argument(
        "--wifi-iface",
        default="auto",
        help="USB/onboard wireless interface, 'auto' (default), or 'none'",
    )
    parser.add_argument("--channel", type=int, default=0, help="Fixed 2.4 GHz Wi-Fi channel 1-13, or 0 for hop")
    parser.add_argument("--monitor-only", action="store_true", help="Disable managed AP scan fallback")
    args = parser.parse_args()

    port = None if args.no_serial else (args.port or find_port())
    use_wifi = args.wifi_iface.lower() != "none"

    if not port and not use_wifi:
        sys.exit("No capture source enabled. Plug in Heltec V3 (USB serial) or a USB Wi-Fi adapter.")

    log_dir = resolve_log_dir()
    os.makedirs(log_dir, exist_ok=True)
    logpath = os.path.join(log_dir, f"recon_{time.strftime('%Y%m%d_%H%M%S')}.jsonl")
    logf = open(logpath, "a", encoding="utf-8")
    io_lock = threading.Lock()
    stop_ev = threading.Event()

    def record_line(text):
        with io_lock:
            logf.write(text + "\n")
            logf.flush()
            try:
                d = json.loads(text)
                ev_t = d.get("ev")
                if ev_t == "rx":
                    print(fmt_rx(d))
                elif ev_t == "wifi":
                    print(fmt_wifi(d))
                elif ev_t == "wifi_hw":
                    print(f"[wifi-hw] {d.get('status')} {d.get('chip', '')} {d.get('iface', '')} {d.get('driver', '')} {d.get('reason', '')}".strip())
                elif ev_t == "scan":
                    print(f"SCAN {d.get('freq')}MHz  {d.get('rssi')}dBm")
                elif ev_t == "status":
                    print(f"[status] {d}")
            except Exception:
                print("· " + text)

    ser = None
    if port:
        if serial is None:
            print("[warn] pyserial not installed; skipping serial capture (sudo apt install -y python3-serial)")
        else:
            try:
                ser = serial.Serial(port, args.baud, timeout=0.5)
                print(f"[serial connected {port} @ {args.baud}, logging to {logpath}]")
            except PermissionError:
                print(
                    f"[warn] Permission denied opening {port}. Ensure user is in 'dialout' group."
                )

    wifi_proc = None
    if use_wifi:
        try:
            wifi_proc = _start_wifi_helper(args.wifi_iface, args.channel, monitor_only=args.monitor_only)
            if wifi_proc:
                print(f"[wifi capture helper started (iface={args.wifi_iface}, ch={args.channel or 'hop'}), logging to {logpath}]")
        except Exception as exc:
            print(f"[warn] Could not start Wi-Fi capture helper: {exc}")

    if ser is None and wifi_proc is None:
        logf.close()
        sys.exit("Neither Heltec V3 serial nor Wi-Fi capture helper could be started.")

    threads = []
    if ser is not None:
        def _serial_reader():
            while not stop_ev.is_set():
                try:
                    raw = ser.readline()
                except Exception:
                    break
                if not raw:
                    continue
                text = raw.decode("utf-8", "replace").strip()
                if text:
                    record_line(text)

        t_ser = threading.Thread(target=_serial_reader, daemon=True)
        t_ser.start()
        threads.append(t_ser)

    if wifi_proc is not None:
        def _wifi_reader():
            for raw_ln in wifi_proc.stdout:
                if stop_ev.is_set():
                    break
                text = raw_ln.strip()
                if text:
                    record_line(text)

        t_wf = threading.Thread(target=_wifi_reader, daemon=True)
        t_wf.start()
        threads.append(t_wf)

    try:
        while any(t.is_alive() for t in threads):
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        stop_ev.set()
        if wifi_proc is not None:
            try:
                if wifi_proc.stdin and not wifi_proc.stdin.closed:
                    wifi_proc.stdin.write("quit\n")
                    wifi_proc.stdin.flush()
                    wifi_proc.stdin.close()
                wifi_proc.wait(timeout=1.5)
            except Exception:
                try:
                    wifi_proc.terminate()
                except Exception:
                    pass
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
        logf.close()


if __name__ == "__main__":
    main()
