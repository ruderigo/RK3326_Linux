"""What the interface knows about the handheld, and what it can ask it to do.

Everything the pages show comes through a System object, so the pages hold no
shell commands. DemoSystem returns fixed, made-up values: it is what the
screenshots and the tests run on, on any machine.

Commands that need root go through "sudo -n"; the image installs a sudoers
file that allows exactly those commands for the user the shell runs as.
"""
import glob
import json
import os
import shutil
import socket
import subprocess
import time

APPS_DIRS = ["/usr/share/rk/apps", "/data/ark/apps"]
SERIAL_DRIVERS = {"cp210x", "ch341", "cdc_acm", "ftdi_sio", "ch343"}
WIFI_DRIVERS = {"rt2800usb", "rtl8xxxu", "ath9k_htc", "mt7601u", "mt76x0u", "mt76x2u", "88x2bu", "8812au",
                "8821cu", "rtw_8822bu", "rtw_8821cu", "rtw_8812au", "rtw_8821au", "rtw_8723du"}


def run(cmd, timeout=8, root=False):
    """Run a command; return (ok, output). Never raises."""
    if root:
        cmd = ["sudo", "-n"] + cmd
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, text=True)
        return p.returncode == 0, p.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


class System:
    demo = False

    def __init__(self):
        self._cache = {}

    def cached(self, key, secs, fn):
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < secs:
            return hit[1]
        value = fn()
        self._cache[key] = (time.time(), value)
        return value

    def forget(self, *keys):
        for k in keys:
            self._cache.pop(k, None)

    # ------------------------------------------------------------ identity
    def hostname(self):
        return socket.gethostname()

    def release(self):
        """Name and version of the system, and the handheld it was built for."""
        info = {"RK_NAME": "RK3326 Linux", "RK_VERSION": "dev", "RK_CONSOLE": ""}
        for line in read("/etc/os-release.rk").splitlines():
            k, _, v = line.partition("=")
            info[k] = v.strip('"')
        return info

    def kernel(self):
        return os.uname().release

    def uptime(self):
        try:
            return float(read("/proc/uptime").split()[0])
        except (ValueError, IndexError):
            return 0.0

    def memory(self):
        """(used, total) in megabytes."""
        m = {}
        for line in read("/proc/meminfo").splitlines():
            k, _, v = line.partition(":")
            m[k] = int(v.split()[0]) // 1024 if v.split() else 0
        total = m.get("MemTotal", 0)
        return total - m.get("MemAvailable", 0), total

    # ------------------------------------------------------------- battery
    def battery(self):
        def get():
            for d in glob.glob("/sys/class/power_supply/*"):
                if read(d + "/type") == "Battery":
                    try:
                        pct = int(read(d + "/capacity", "-1"))
                    except ValueError:
                        pct = -1
                    return {"percent": pct, "status": read(d + "/status", "Unknown")}
            return None
        return self.cached("battery", 10, get)

    # --------------------------------------------------------------- Wi-Fi
    def wifi(self):
        """State of the first Wi-Fi card: None when there is no card."""
        def get():
            ok, out = run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev"])
            dev = None
            for line in out.splitlines() if ok else []:
                p = line.split(":")
                if len(p) >= 4 and p[1] == "wifi":
                    dev = {"device": p[0], "state": p[2], "ssid": p[3] if p[2] == "connected" else "", "address": ""}
                    break
            if dev and dev["state"] == "connected":
                ok, out = run(["nmcli", "-t", "-g", "IP4.ADDRESS", "dev", "show", dev["device"]])
                dev["address"] = out.splitlines()[0].split("/")[0] if ok and out else ""
            return dev
        return self.cached("wifi", 4, get)

    def wifi_scan(self):
        """Networks in range, strongest first: dicts with ssid, signal, secure, active."""
        run(["nmcli", "dev", "wifi", "rescan"], root=True, timeout=10)
        ok, out = run(["nmcli", "-t", "-f", "ACTIVE,SIGNAL,SECURITY,SSID", "dev", "wifi", "list"], timeout=15)
        nets, seen = [], set()
        for line in out.splitlines() if ok else []:
            active, signal, rest = line.split(":", 2)
            security, _, ssid = rest.partition(":")
            ssid = ssid.replace("\\:", ":")
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            nets.append({"ssid": ssid, "signal": int(signal or 0), "secure": bool(security and security != "--"),
                         "active": active == "yes"})
        return sorted(nets, key=lambda n: (-n["active"], -n["signal"]))

    def wifi_join(self, ssid, password):
        cmd = ["nmcli", "dev", "wifi", "connect", ssid] + (["password", password] if password else [])
        ok, out = run(cmd, timeout=45, root=True)
        self.forget("wifi")
        return ok, out.splitlines()[-1] if out else ("Connected" if ok else "Could not connect")

    def ssh_enabled(self):
        return run(["systemctl", "is-active", "--quiet", "ssh"])[0]

    def set_ssh(self, on):
        return run(["systemctl", "enable" if on else "disable", "--now", "ssh"], root=True, timeout=20)

    # ------------------------------------------------- sound and backlight
    def volume(self):
        """Speaker volume, 0 to 100, or None when there is no mixer control."""
        ok, out = run(["amixer", "-c0", "cget", "name=Playback Volume"])
        try:
            mx = int(out.split("max=")[1].split(",")[0])
            val = int(out.split(": values=")[1].split(",")[0])
            return round(val * 100 / mx) if mx else None
        except (IndexError, ValueError):
            return None

    def set_volume(self, pct):
        pct = max(0, min(100, pct))
        run(["amixer", "-c0", "cset", "name=Playback Volume", f"{pct}%"])
        return pct

    def _backlight(self):
        d = glob.glob("/sys/class/backlight/*")
        return d[0] if d else None

    def brightness(self):
        d = self._backlight()
        try:
            return round(int(read(d + "/brightness")) * 100 / int(read(d + "/max_brightness"))) if d else None
        except (ValueError, ZeroDivisionError):
            return None

    def set_brightness(self, pct):
        d = self._backlight()
        pct = max(5, min(100, pct))                 # never fully dark: the screen is the only way back
        if d:
            try:
                with open(d + "/brightness", "w") as f:
                    f.write(str(int(read(d + "/max_brightness")) * pct // 100))
            except (OSError, ValueError):
                pass
        return pct

    # ------------------------------------------------------------- devices
    def usb_devices(self):
        """What is plugged in: dicts with name, kind, id. Hubs are left out."""
        out = []
        for d in sorted(glob.glob("/sys/bus/usb/devices/*")):
            if ":" in os.path.basename(d) or os.path.basename(d).startswith("usb"):
                continue
            kinds, drivers = set(), set()
            for i in glob.glob(d + "/*:*"):
                cls, proto = read(i + "/bInterfaceClass"), read(i + "/bInterfaceProtocol")
                drv = os.path.basename(os.path.realpath(i + "/driver")) if os.path.exists(i + "/driver") else ""
                drivers.add(drv)
                if drv in WIFI_DRIVERS:
                    kinds.add("Wi-Fi card")
                elif drv in SERIAL_DRIVERS:
                    kinds.add("Serial device")
                elif cls == "03":
                    kinds.add({"01": "Keyboard", "02": "Mouse"}.get(proto, "Controller"))
                elif cls == "08":
                    kinds.add("Storage")
                elif cls == "01":
                    kinds.add("Sound")
                elif cls == "e0":
                    kinds.add("Bluetooth")
                elif cls == "09":
                    kinds.add("Hub")
            if kinds == {"Hub"}:
                continue
            name = " ".join(x for x in (read(d + "/manufacturer"), read(d + "/product")) if x) or "USB device"
            out.append({"name": name, "kind": ", ".join(sorted(kinds - {"Hub"})) or "Other",
                        "id": f"{read(d + '/idVendor')}:{read(d + '/idProduct')}",
                        "driver": ", ".join(sorted(x for x in drivers if x)) or "no driver"})
        return out

    def storage(self):
        out = []
        for mount, label in (("/", "System"), ("/data", "Data"), ("/boot", "Boot files")):
            try:
                u = shutil.disk_usage(mount)
                if mount == "/data" and not os.path.ismount(mount):
                    continue
                out.append({"label": label, "mount": mount, "used": u.used, "total": u.total})
            except OSError:
                pass
        return out

    # ---------------------------------------------------------------- apps
    def apps(self):
        """Entries of the HOME page: every *.json in the apps folders.

        {"name": "...", "group": "...", "about": "one line", "exec": ["cmd", "arg"]}
        An entry whose "exec" program is missing shows as "not installed".
        """
        found = []
        for d in APPS_DIRS:
            for f in sorted(glob.glob(os.path.join(d, "*.json"))):
                try:
                    with open(f) as fh:
                        a = json.load(fh)
                    a["ready"] = bool(a.get("exec")) and shutil.which(a["exec"][0]) is not None
                    found.append(a)
                except (OSError, ValueError, KeyError, IndexError):
                    continue
        return found

    # --------------------------------------------------------------- power
    def boot_selection(self):
        return {k: v for k, _, v in (ln.partition("=") for ln in read("/boot/rk-device.txt").splitlines())}

    def power_off(self):
        return run(["poweroff"], root=True)

    def restart(self):
        return run(["reboot"], root=True)

    # --------------------------------------------------------------- files
    def listdir(self, path):
        """(name, is_dir, size) for a folder, folders first; None if unreadable."""
        try:
            rows = []
            for e in os.scandir(path):
                if e.name.startswith("."):
                    continue
                try:
                    rows.append((e.name, e.is_dir(), 0 if e.is_dir() else e.stat().st_size))
                except OSError:
                    rows.append((e.name, False, 0))
            return sorted(rows, key=lambda r: (not r[1], r[0].lower()))
        except OSError:
            return None

    def places(self):
        out = [("Home", "/data/ark" if os.path.isdir("/data/ark") else os.path.expanduser("~")),
               ("Card settings", "/boot")]
        for m in sorted(glob.glob("/media/*/*") + glob.glob("/run/media/*/*")):
            if os.path.ismount(m):
                out.append((os.path.basename(m), m))
        return out


class DemoSystem(System):
    """Fixed, made-up values: for screenshots and tests on any machine."""
    demo = True

    def hostname(self): return "r36max"
    def release(self): return {"RK_NAME": "RK3326 Linux", "RK_VERSION": "0.1.0", "RK_CONSOLE": "r36max type1"}
    def kernel(self): return "5.10.252-arkos4clone"
    def uptime(self): return 3 * 3600 + 12 * 60
    def memory(self): return 96, 714
    def battery(self): return {"percent": 78, "status": "Discharging"}
    def wifi(self): return {"device": "wlan0", "state": "connected", "ssid": "Workshop", "address": "192.168.0.167"}

    def wifi_scan(self):
        return [{"ssid": "Workshop", "signal": 82, "secure": True, "active": True},
                {"ssid": "LaBuche3-192.168.4.1", "signal": 64, "secure": False, "active": False},
                {"ssid": "Guest", "signal": 41, "secure": True, "active": False}]

    def wifi_join(self, ssid, password): return True, f"Connected to {ssid}"
    def ssh_enabled(self): return True
    def set_ssh(self, on): return True, ""
    _vol, _bri = 60, 80
    def volume(self): return self._vol
    def set_volume(self, pct): self._vol = max(0, min(100, pct)); return self._vol
    def brightness(self): return self._bri
    def set_brightness(self, pct): self._bri = max(5, min(100, pct)); return self._bri

    def usb_devices(self):
        return [{"name": "Ralink 802.11 n WLAN", "kind": "Wi-Fi card", "id": "148f:3070", "driver": "rt2800usb"},
                {"name": "Silicon Labs CP2102 USB to UART", "kind": "Serial device", "id": "10c4:ea60", "driver": "cp210x"},
                {"name": "Lite-On USB wired keyboard", "kind": "Keyboard", "id": "04ca:007d", "driver": "usbhid"}]

    def storage(self):
        g = 1024 ** 3
        return [{"label": "System", "mount": "/", "used": int(0.7 * g), "total": int(2.9 * g)},
                {"label": "Data", "mount": "/data", "used": int(1.2 * g), "total": 83 * g},
                {"label": "Boot files", "mount": "/boot", "used": int(0.11 * g), "total": int(0.25 * g)}]

    def apps(self):
        return [{"name": "FireFly", "group": "Comms", "about": "Messages over LoRa and Wi-Fi", "ready": True},
                {"name": "Stump", "group": "Comms", "about": "Run and watch a Stump node", "ready": True},
                {"name": "Provisioner", "group": "Workshop", "about": "Flash ESP32 boards and radios", "ready": False}]

    def boot_selection(self): return {"console": "r36max type1", "kernel": "5.10"}
    def power_off(self): return True, ""
    def restart(self): return True, ""

    def listdir(self, path):
        if path == "/data/ark":
            return [("captures", True, 0), ("recordings", True, 0), ("notes.txt", False, 1840),
                    ("scan-2026-11-20.txt", False, 12288)]
        return [("example.txt", False, 420)]

    def places(self): return [("Home", "/data/ark"), ("Card settings", "/boot")]
