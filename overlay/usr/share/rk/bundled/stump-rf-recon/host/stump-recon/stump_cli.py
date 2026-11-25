#!/usr/bin/env python3
"""
stump_cli.py — Headless CLI reader and JSONL recorder for RK3326_Linux / R36MAX
Stores logs under /data/ark/stump-recon/exports (survives OS reflashes) with
automatic fallback to /roms/stump or ~/stump-recon/exports.
"""

import argparse
import glob
import json
import os
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial not found. Run: sudo apt install -y python3-serial")


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


def main():
    parser = argparse.ArgumentParser(
        description="STUMP RF Recon headless serial logger for RK3326_Linux"
    )
    parser.add_argument("--port", help="Override serial device path (e.g. /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    args = parser.parse_args()

    port = args.port or find_port()
    if not port:
        sys.exit("No serial port found. Plug in Heltec V3 over USB OTG.")

    log_dir = resolve_log_dir()
    os.makedirs(log_dir, exist_ok=True)
    logpath = os.path.join(log_dir, f"recon_{time.strftime('%Y%m%d_%H%M%S')}.jsonl")
    logf = open(logpath, "a", encoding="utf-8")
    print(f"[connected to {port} @ {args.baud}, logging to {logpath}]")

    try:
        ser = serial.Serial(port, args.baud, timeout=1)
    except PermissionError:
        logf.close()
        sys.exit(
            f"Permission denied opening {port}. Ensure user is in the 'dialout' group "
            "(standard on RK3326_Linux)."
        )

    time.sleep(0.2)

    try:
        while True:
            raw = ser.readline()
            if not raw:
                continue
            text = raw.decode("utf-8", "replace").strip()
            if not text:
                continue
            logf.write(text + "\n")
            logf.flush()
            try:
                d = json.loads(text)
                if d.get("ev") == "rx":
                    print(fmt_rx(d))
                elif d.get("ev") == "scan":
                    print(f"SCAN {d.get('freq')}MHz  {d.get('rssi')}dBm")
                elif d.get("ev") == "status":
                    print(f"[status] {d}")
            except Exception:
                print("· " + text)
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        logf.close()


if __name__ == "__main__":
    main()
