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
import re
import shutil
import socket
import subprocess
import threading
import time
import xml.etree.ElementTree as ET

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


def last_line(out):
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return lines[-1].replace("rk-scan: ", "") if lines else ""


def parse_survey(out):
    """nmcli's terse list: fields separated by ":", with ":" inside a field written "\\:"."""
    nets = []
    for line in out.splitlines():
        p = [x.replace("\\:", ":") for x in re.split(r"(?<!\\):", line)]
        if len(p) < 7 or not p[2]:
            continue
        try:
            nets.append({"active": p[0] == "yes", "ssid": p[1] or "(hidden)", "bssid": p[2], "channel": int(p[3] or 0),
                         "freq": int((p[4] or "0").split()[0]), "signal": int(p[5] or 0),
                         "security": p[6] if p[6] and p[6] != "--" else "open"})
        except ValueError:
            continue
    return sorted(nets, key=lambda n: -n["signal"])


def _xml(out):
    try:
        return ET.fromstring(out[out.index("<?xml"):] if "<?xml" in out else out)
    except (ET.ParseError, ValueError):
        return None


def parse_scan(out):
    """nmap -oX: one dict for each host that is up, with address, name, mac,
    vendor, os (best guess, "" when none), ports and notes (host scripts).
    A port is a dict with port, proto, state, service, product and notes."""
    root, hosts = _xml(out), []
    for h in root.findall("host") if root is not None else []:
        if h.find("status") is None or h.find("status").get("state") != "up":
            continue
        d = {"address": "", "name": "", "mac": "", "vendor": "", "os": "", "ports": [], "notes": []}
        for a in h.findall("address"):
            if a.get("addrtype") in ("ipv4", "ipv6"):
                d["address"] = a.get("addr", "")
            elif a.get("addrtype") == "mac":
                d["mac"], d["vendor"] = a.get("addr", ""), a.get("vendor", "")
        name = h.find("hostnames/hostname")
        d["name"] = name.get("name", "") if name is not None else ""
        best = h.find("os/osmatch")
        if best is not None:
            d["os"] = f"{best.get('name', '')} ({best.get('accuracy', '?')}%)"
        for p in h.findall("ports/port"):
            st, sv = p.find("state"), p.find("service")
            if st is None or not st.get("state", "").startswith("open"):
                continue
            product = " ".join(sv.get(k, "") for k in ("product", "version", "extrainfo") if sv.get(k)) if sv is not None else ""
            d["ports"].append({"port": int(p.get("portid", 0)), "proto": p.get("protocol", ""), "state": st.get("state"),
                               "service": sv.get("name", "") if sv is not None else "", "product": product,
                               "notes": [(x.get("id", ""), x.get("output", "").strip()) for x in p.findall("script")]})
        d["ports"].sort(key=lambda q: (q["proto"], q["port"]))
        d["notes"] = [(x.get("id", ""), x.get("output", "").strip()) for x in h.findall("hostscript/script")]
        if d["address"]:
            hosts.append(d)

    def order(d):
        try:
            return (0, tuple(int(x) for x in d["address"].split(".")))
        except ValueError:
            return (1, (0,))
    return sorted(hosts, key=lambda d: (order(d), d["address"]))


class Scan:
    """A scan that is running, or has run. `result` is None while it runs, then
    (True, hosts) or (False, why). Closing rk-scan's standard input is how it
    is cancelled: it runs as root, so this user cannot signal it."""

    def __init__(self, spec):
        self.spec, self.started, self.ended, self.result, self.cancelled = spec, time.time(), None, None, False
        try:
            self.proc = subprocess.Popen(["sudo", "-n", "/usr/local/sbin/rk-scan", "run"], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.proc.stdin.write(json.dumps(spec) + "\n")
            self.proc.stdin.flush()
        except OSError as e:
            self.proc, self.result, self.ended = None, (False, str(e)), time.time()
            return
        threading.Thread(target=self._wait, daemon=True).start()

    def _wait(self):
        errs = []
        t = threading.Thread(target=lambda: errs.append(self.proc.stderr.read()), daemon=True)
        t.start()
        out = self.proc.stdout.read()
        code = self.proc.wait()
        t.join(2)
        self.ended = time.time()
        if self.cancelled:
            self.result = (False, "Scan stopped")
        elif code == 0:
            self.result = (True, parse_scan(out))
        else:
            self.result = (False, last_line("".join(errs)) or "The scan did not run")

    @property
    def seconds(self):
        return int((self.ended or time.time()) - self.started)

    def cancel(self):
        self.cancelled = True
        try:
            self.proc.stdin.close()
        except (OSError, AttributeError):
            pass


class Install:
    """rk-tools install-heavy, running. `lines` is its output so far; `done`
    is set when it ends, with `ok` saying whether everything installed."""

    def __init__(self, cmd=("sudo", "-n", "/usr/local/sbin/rk-tools", "install-heavy")):
        self.lines, self.done, self.ok = ["Starting..."], False, False
        try:
            self.proc = subprocess.Popen(list(cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        except OSError as e:
            self.lines, self.done, self.proc = [str(e)], True, None
            return
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            self.lines.append(line.rstrip())
            del self.lines[:-400]
        self.ok = self.proc.wait() == 0
        self.done = True


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
        run(["/usr/local/sbin/rk-wifi", "scan"], root=True, timeout=10)
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
        """Join a network. The name and the password go to the helper on its
        standard input: a password on a command line would end up in the
        system log and in the list of running programs."""
        try:
            p = subprocess.run(["sudo", "-n", "/usr/local/sbin/rk-wifi", "join"], input=f"{ssid}\n{password}\n",
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60, text=True)
            ok, out = p.returncode == 0, p.stdout.strip()
        except (OSError, subprocess.TimeoutExpired) as e:
            ok, out = False, str(e)
        self.forget("wifi")
        return ok, out.splitlines()[-1] if out else ("Connected" if ok else "Could not connect")

    def ssh_enabled(self):
        return run(["systemctl", "is-active", "--quiet", "ssh"])[0]

    def set_ssh(self, on):
        return run(["systemctl", "enable" if on else "disable", "--now", "ssh"], root=True, timeout=20)

    # --------------------------------------------------------------- tools
    def survey(self, rescan=True):
        """Every Wi-Fi access point in range, strongest first: dicts with ssid,
        bssid, channel, freq (MHz), signal (0-100), security, active."""
        if rescan:
            run(["/usr/local/sbin/rk-wifi", "scan"], root=True, timeout=10)
        ok, out = run(["nmcli", "-t", "-f", "ACTIVE,SSID,BSSID,CHAN,FREQ,SIGNAL,SECURITY", "dev", "wifi", "list"], timeout=15)
        return parse_survey(out) if ok else []

    def own_networks(self):
        """The networks the handheld is on: (interface, network, own address)."""
        ok, out = run(["/usr/local/sbin/rk-scan", "networks"])
        return [tuple(ln.split()) for ln in out.splitlines() if len(ln.split()) == 3] if ok else []

    def start_scan(self, spec):
        """Run the scan this loadout describes (see nmapspec); returns a Scan."""
        return Scan(spec)

    def online(self):
        ok, out = run(["ip", "route"])
        return ok and any(ln.startswith("default") for ln in out.splitlines())

    def tools_status(self):
        """For each tool in the catalogue, whether its command is on PATH."""
        from . import arsenal
        return {cmd: bool(shutil.which(cmd)) for cmd, _, _, _ in arsenal.COMMANDS}

    def install_heavy(self):
        """Fetch the heavy tools (Metasploit, exploitdb); returns an Install."""
        return Install()

    def save_report(self, name, text):
        """Write a report where the Files window shows it; returns its path or None."""
        folder = "/data/ark/scans" if os.path.isdir("/data/ark") else os.path.expanduser("~/scans")
        try:
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.txt")
            with open(path, "w") as f:
                f.write(text)
            return path
        except OSError:
            return None

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
        """Apps on the dock: every *.json in the apps folders.

        {"name": "...", "icon": "firefly", "group": "...", "about": "one line", "exec": ["cmd", "arg"]}
        "icon" names a drawing in desktop.py; without one the dock shows the first letter.
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
        return [{"name": "FireFly", "icon": "firefly", "group": "Comms", "about": "Messages over LoRa and Wi-Fi", "ready": True},
                {"name": "Stump", "icon": "stump", "group": "Comms", "about": "Run and watch a Stump node", "ready": True},
                {"name": "Provisioner", "icon": "chip", "group": "Workshop", "about": "Flash ESP32 boards and radios", "ready": False}]

    def survey(self, rescan=True):
        return [{"active": True, "ssid": "Workshop", "bssid": "38:AD:2B:91:52:48", "channel": 6, "freq": 2437, "signal": 82, "security": "WPA2"},
                {"active": False, "ssid": "LaBuche3-192.168.4.1", "bssid": "24:6F:28:AA:10:04", "channel": 1, "freq": 2412, "signal": 64, "security": "open"},
                {"active": False, "ssid": "Guest", "bssid": "38:AD:2B:91:52:49", "channel": 6, "freq": 2437, "signal": 58, "security": "WPA2"},
                {"active": False, "ssid": "Neighbour 2.4", "bssid": "A4:91:B1:0C:77:20", "channel": 11, "freq": 2462, "signal": 41, "security": "WPA2 WPA3"},
                {"active": False, "ssid": "(hidden)", "bssid": "A4:91:B1:0C:77:21", "channel": 11, "freq": 2462, "signal": 37, "security": "WPA2"},
                {"active": False, "ssid": "Printer-Setup", "bssid": "00:1B:A9:3E:5F:02", "channel": 3, "freq": 2422, "signal": 22, "security": "open"}]

    def own_networks(self): return [("wlan0", "192.168.0.0/24", "192.168.0.167")]

    def online(self): return True

    def tools_status(self):
        from . import arsenal
        absent = {"ffuf", "wfuzz", "hcxdumptool", "msfconsole", "searchsploit", "termshark"}
        return {cmd: cmd not in absent for cmd, _, _, _ in arsenal.COMMANDS}

    def install_heavy(self):
        inst = Install.__new__(Install)
        inst.proc, inst.ok, inst.done = None, False, False
        inst.lines = ["rk-tools: Fetching Metasploit (large; this takes a while)...",
                      "Get:1 https://apt.metasploit.com lucid/main arm64 metasploit-framework",
                      "Unpacking metasploit-framework ...",
                      "Setting up metasploit-framework ..."]
        return inst

    def start_scan(self, spec):
        sweep = spec.get("mode") == "sweep"
        tcp = lambda n, svc, prod="", notes=(): {"port": n, "proto": "tcp", "state": "open", "service": svc,
                                                 "product": prod if spec.get("versions") else "", "notes": list(notes)}
        os_ = lambda name: name if spec.get("os") and not sweep else ""
        hosts = [{"address": "192.168.0.1", "name": "router.lan", "mac": "38:AD:2B:91:52:48", "vendor": "Sagemcom", "os": os_("Linux 4.15 - 5.19 (96%)"),
                  "ports": [tcp(53, "domain", "dnsmasq 2.89"), tcp(80, "http", "nginx"), tcp(443, "https", "nginx")], "notes": []},
                 {"address": "192.168.0.42", "name": "labuche3.lan", "mac": "24:6F:28:AA:10:04", "vendor": "Espressif", "os": os_("lwIP 2.1 (91%)"),
                  "ports": [tcp(80, "http", "", [("http-title", "LaBuche Stump")])], "notes": []},
                 {"address": "192.168.0.110", "name": "", "mac": "F0:18:98:2C:11:9A", "vendor": "Apple", "os": os_("Apple macOS 14 - 15 (93%)"),
                  "ports": [tcp(22, "ssh", "OpenSSH 9.7"), tcp(5000, "rtsp", "AirTunes 775.3"), tcp(7000, "rtsp", "AirTunes 775.3")], "notes": []},
                 {"address": "192.168.0.167", "name": "r36max.lan", "mac": "", "vendor": "", "os": os_("Linux 5.10 (100%)"),
                  "ports": [tcp(22, "ssh", "OpenSSH 10.0p2 Debian")], "notes": []}]
        if sweep:
            for h in hosts:
                h["ports"] = []
        scan = Scan.__new__(Scan)
        scan.spec, scan.started, scan.ended, scan.cancelled, scan.proc = spec, time.time() - 41, time.time(), False, None
        scan.result = (True, hosts)
        return scan

    def save_report(self, name, text): return f"/data/ark/scans/{name}-20261120-160000.txt"
    def boot_selection(self): return {"console": "r36max type1", "kernel": "5.10"}
    def power_off(self): return True, ""
    def restart(self): return True, ""

    def listdir(self, path):
        if path == "/data/ark":
            return [("captures", True, 0), ("recordings", True, 0), ("notes.txt", False, 1840),
                    ("scan-2026-11-20.txt", False, 12288)]
        return [("example.txt", False, 420)]

    def places(self): return [("Home", "/data/ark"), ("Card settings", "/boot")]
