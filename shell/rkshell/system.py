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
import pty
import re
import select
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET

APPS_DIRS = ["/usr/share/rk/apps", "/data/ark/apps"]
SERIAL_DRIVERS = {"cp210x", "ch341", "cdc_acm", "ftdi_sio", "ch343"}
WIFI_DRIVERS = {"rt2800usb", "rtl8xxxu", "ath9k_htc", "mt7601u", "mt76x0u", "mt76x2u", "88x2bu", "8812au",
                "8821cu", "rtw_8822bu", "rtw_8821cu", "rtw_8812au", "rtw_8821au", "rtw_8723du"}


def run(cmd, timeout=8, root=False, env=None):
    """Run a command; return (ok, output). Never raises."""
    if root:
        cmd = ["sudo", "-n"] + cmd
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, text=True, env=env)
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


START_PASSWORD = "ark"                  # what a fresh card has, expired until it is changed
STUMP_INSTALLER = os.path.expanduser("~/R36MAX-Stump/handheld/install.sh")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
IPV4 = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")
ASKPASS = '#!/bin/sh\ncat "$RK_ASKPASS_FILE"\n'


STUMP_SIZES = (256, 512, 768, 1024, 1536, 2048, 4096, 8192, 16384)


def stump_storage(folder="~/Stump"):
    """How big the Stump's "card" (its sd/ folder) may be here, in MB:
    (most, suggested, sizes to offer). The same sums as the Stump's wizard:
    at most what is free, suggested a quarter of it in steps of 256 MB, 2048
    at most. A little is held back for what the installer itself writes."""
    p = os.path.expanduser(folder)
    used = 0
    for d, _, names in os.walk(os.path.join(p, "sd")):
        for n in names:
            try:
                used += os.path.getsize(os.path.join(d, n))
            except OSError:
                pass
    while not os.path.exists(p) and p != os.path.dirname(p):
        p = os.path.dirname(p)
    try:
        free = shutil.disk_usage(p).free
    except OSError:
        free = 0
    most = max(256, (free + used) // 1024 ** 2 - 128)
    suggested = max(256, min(2048, free // 4 // 1024 ** 2 // 256 * 256))
    return most, suggested, [n for n in STUMP_SIZES if n <= most] or [256]


def stump_answers(form):
    """The setup form -> the answers file of the Stump's wizard
    (SandBox_Stump_On's `provisioner.py --pc --answers`: the keys are its
    questions, up to their "?"). The same keys as the RK3326 Provisioner
    sends. {"error": why} when the form is not complete."""
    name = (form.get("name") or "").strip()
    pw = form.get("pw") or ""
    if not name:
        return {"error": "Give this Stump a name"}
    if not 4 <= len(pw) <= 64:
        return {"error": "The Stump's password: 4 to 64 characters"}
    try:
        mb = int(form.get("storage") or 0)
    except (TypeError, ValueError):
        mb = 0
    if mb < 256:
        return {"error": "Storage: 256 MB or more"}
    out = {"folder for this stump": os.path.expanduser("~/Stump"), "node name": name,
           "the wi-fi name visitors join": name, "storage for this stump, in mb": str(mb),
           "is this stump part of a chain": form.get("chain") in ("first", "member"),
           "the heltec": "Plugged into this computer by USB" if form.get("radio") == "usb" else "None",
           "start this stump automatically when you log in": True,
           "admin password": pw, "use the same password for the fserv bot": True,
           "fserv bot operator password": pw, "change any of those now": True, "admin password for /admin": "",
           "identity requirement": "open", "how should file sharing work": "Free", "theme": "Amber",
           "fix it, then check again": False,
           # a Stump folder already there (a setup that stopped part-way, or one
           # being redone): the wizard asks "Change something?"; "a" is all the
           # questions again, so this form's answers are the ones that count
           "change something": "a"}
    if form.get("radio") == "usb":
        out["its usb port"] = "auto"
    secret = form.get("secret") or ""
    if '"' in secret or "\\" in secret or len(secret) > 64:
        return {"error": "The chain secret: at most 64 characters, no quotes or backslashes"}
    if form.get("chain") == "first":
        out["its place in the chain"] = "The first"
        out["chain secret"] = secret
    elif form.get("chain") == "member":
        ip = (form.get("parent") or "").strip()
        m = IPV4.match(ip)
        if not m or not all(0 <= int(x) <= 255 for x in m.groups()):
            return {"error": "The Stump it joins: its address, like 192.168.1.20"}
        if not secret:
            return {"error": "The chain secret of the first Stump is needed"}
        out["its place in the chain"] = "Joins another"
        out["how does this computer reach that stump"] = "On the Wi-Fi"
        out["that stump's address"] = ip
        out["chain secret"] = secret
    return out


def os_release_version(text):
    """RK_VERSION from the text of /etc/os-release.rk, or ""."""
    m = re.search(r'^RK_VERSION="?([^"\n]*)"?', text, re.M)
    return m.group(1).strip() if m else ""


def same_version(a, b):
    """True when two version names are the same release ("v1.3.1" is "1.3.1")."""
    return bool(a) and bool(b) and a.lstrip("v") == b.lstrip("v")


def zone_names(zoneinfo):
    """Time zone names from the system's own table (zone1970.tab: one line a
    zone, the name in the third column), with UTC. Only those whose file is
    there. Without the table: the files themselves, one folder deep."""
    names = set()
    for line in read(os.path.join(zoneinfo, "zone1970.tab")).splitlines():
        cols = line.split("\t")
        if not line.startswith("#") and len(cols) >= 3:
            names.add(cols[2].strip())
    if not names:
        for path in glob.glob(os.path.join(zoneinfo, "[A-Z]*", "*")):
            if os.path.isfile(path):
                names.add(os.path.relpath(path, zoneinfo))
    names = {n for n in names if "/" in n and os.path.isfile(os.path.join(zoneinfo, n))}
    return sorted(names) + ["UTC"]


def password_expired(user=None):
    """True while the account still has its starting password, which must be
    changed before anything else accepts it (sudo refuses it as it is)."""
    ok, out = run(["chage", "-l", user or os.environ.get("USER") or "ark"], env=dict(os.environ, LC_ALL="C"))
    return ok and "password must be changed" in out


def change_password(old, new, timeout=20):
    """Change this user's password with passwd, on a pseudo-terminal (it only
    talks to a terminal). (True, "") or (False, passwd's reason)."""
    try:
        pid, fd = pty.fork()
    except OSError as e:
        return False, str(e)
    if pid == 0:
        os.environ["LC_ALL"] = "C"
        try:
            os.execvp("passwd", ["passwd"])
        finally:
            os._exit(127)
    answers, out, pending, end = [old, new, new], "", "", time.time() + timeout
    try:
        while time.time() < end:
            ready, _, _ = select.select([fd], [], [], 0.5)
            if not ready:
                continue
            try:
                data = os.read(fd, 4096)
            except OSError:
                break
            if not data:
                break
            text = data.decode("utf-8", "replace")
            out += text
            pending += text
            if pending.rstrip().endswith(":") and answers:      # a prompt: Current / New / Retype
                os.write(fd, (answers.pop(0) + "\n").encode())
                pending = ""
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            _, status = os.waitpid(pid, 0)
        except OSError:
            status = 1
    if status == 0 and not answers:
        return True, ""
    lines = [ln.strip() for ln in out.replace("\r", "").splitlines()
             if ln.strip() and not ln.strip().endswith(":") and "Changing password" not in ln]
    return False, (lines[-1] if lines else "The password was not changed")


def find_stumps(networks, timeout=1.5, workers=64):
    """Stumps answering on these networks (own_networks()): each address is
    asked for /node.json at once, as the Stump's own installer does. A list
    of {"address", "name", "links"}; "links" is True for one that takes
    chain links here (those come first)."""
    from concurrent.futures import ThreadPoolExecutor
    import ipaddress

    def ask(ip):
        try:
            with urllib.request.urlopen(f"http://{ip}/node.json", timeout=timeout) as r:
                node = json.load(r)
        except Exception:
            return None
        if not isinstance(node, dict):
            return None
        chain = node.get("chain") if isinstance(node.get("chain"), dict) else {}
        links = bool(chain.get("enabled") and (chain.get("lan_ip") == ip or
                                               (chain.get("role") == "root" and chain.get("ap_ip") == ip)))
        return {"address": ip, "name": str(node.get("name") or "a Stump"), "links": links}
    ips = []
    for _, net, own in networks:
        try:
            hosts = list(ipaddress.ip_network(net, strict=False).hosts())
        except ValueError:
            continue
        if len(hosts) <= 1024:
            ips += [str(h) for h in hosts if str(h) != own]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        found = [x for x in pool.map(ask, ips) if x]
    return sorted(found, key=lambda d: (not d["links"], d["address"]))


class StumpSearch:
    """find_stumps in the background: `found` once `done`."""

    def __init__(self, networks):
        self.done, self.found = False, []
        threading.Thread(target=self._run, args=(networks,), daemon=True).start()

    def _run(self, networks):
        try:
            self.found = find_stumps(networks)
        finally:
            self.done = True


class StumpSetup:
    """The Stump's own installer, running with the form's answers. `lines` is
    what it printed, `step` its current stage; `done` and `ok` at the end.

    The answers (they may hold the chain's secret) and the handheld's
    password live in files only this user can read, for as long as the
    installer runs. The password reaches sudo through its askpass helper, as
    the installer asks for it (never on a command line)."""

    def __init__(self, answers, password, installer=STUMP_INSTALLER, replaces=None):
        """replaces: the starting password, when `password` is a new one to set first."""
        self.lines, self.step, self.done, self.ok = [], "Starting", False, False
        self.reason = ""            # "password" when sudo refused it
        threading.Thread(target=self._run, args=(answers, password, installer, replaces), daemon=True).start()

    def _run(self, answers, password, installer, replaces):
        if replaces is not None:
            self.step = "Setting this handheld's password"
            ok, why = change_password(replaces, password)
            if not ok:
                self.lines += ["The password was not changed:", why]
                self.reason, self.done = "newpassword", True
                return
            self.lines.append("✓ this handheld's password is set")
        d = tempfile.mkdtemp(prefix="rk-stump-")           # 0700
        try:
            paths = {n: os.path.join(d, n) for n in ("answers.json", "askpass", "pw")}
            for n, text, mode in (("answers.json", json.dumps(answers), 0o600), ("askpass", ASKPASS, 0o700),
                                  ("pw", password + "\n", 0o600)):
                with os.fdopen(os.open(paths[n], os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode), "w") as f:
                    f.write(text)
            env = dict(os.environ, SUDO_ASKPASS=paths["askpass"], RK_ASKPASS_FILE=paths["pw"])
            env = {k: v for k, v in env.items() if not k.startswith("SDL_")}
            p = subprocess.Popen(["bash", installer, "--answers", paths["answers.json"]], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, errors="replace",
                                 bufsize=1, env=env, cwd=os.path.dirname(installer))
            for raw in p.stdout:
                line = ANSI.sub("", raw.rstrip("\n")).split("\r")[-1].strip()
                if not line:
                    continue
                if line.startswith(">>> "):
                    self.step = line[4:]
                self.lines.append(line)
                del self.lines[:-400]
            self.ok = p.wait() == 0
            if not self.ok and any("didn't take that password" in ln or "incorrect password" in ln for ln in self.lines[-6:]):
                self.reason = "password"
        except OSError as e:
            self.lines.append(str(e))
        finally:
            shutil.rmtree(d, ignore_errors=True)
            self.done = True


RK_APPS = "/usr/local/sbin/rk-apps"
RK_VIDEO = "/usr/local/bin/rk-video"
RK_TOOLS = "/usr/local/sbin/rk-tools"
GAMES_DIRS = ("/usr/games", "/usr/local/games")     # where Debian puts RetroArch; not on a service's PATH


def with_games(path=None):
    """PATH with Debian's games folders at the end, for finding and starting dock apps."""
    parts = [p for p in (os.environ.get("PATH", os.defpath) if path is None else path).split(":") if p]
    return ":".join(parts + [d for d in GAMES_DIRS if d not in parts])


def parse_video_status(out):
    """`rk-video status` -> {"mpv": bool, "ytdlp": version or None, "js": name or None}."""
    got = dict(line.split(None, 1) for line in out.splitlines() if len(line.split(None, 1)) == 2)
    return {"mpv": got.get("mpv") == "yes",
            "ytdlp": None if got.get("ytdlp", "absent") == "absent" else got["ytdlp"],
            "js": None if got.get("js", "none") == "none" else got["js"]}


def parse_video_results(out):
    """`rk-video search` -> [{"id", "length", "channel", "title"}]; lines that are not results are left out."""
    found = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 4 and re.fullmatch(r"[A-Za-z0-9_-]{6,20}", parts[0]) and parts[3].strip():
            found.append(dict(zip(("id", "length", "channel", "title"), (p.strip() for p in parts))))
    return found


class VideoSearch:
    """`rk-video search` in the background: `results` once `done`; `error` says why there are none."""

    def __init__(self, words):
        self.done, self.results, self.error = False, [], ""
        threading.Thread(target=self._run, args=(words,), daemon=True).start()

    def _run(self, words):
        ok, out = run([RK_VIDEO, "search", words], timeout=130)
        self.results = parse_video_results(out)
        if not self.results:
            said = [ln[len("rk-video: "):] for ln in out.splitlines() if ln.startswith("rk-video: ")]
            self.error = said[-1] if said else ("Nothing found" if ok else "The search did not answer")
        self.done = True


class Steps:
    """Commands run one after the other, as one job: `lines`, then `done` and
    `ok` (every step ended well). A step that fails stops the rest."""

    def __init__(self, cmds):
        self.lines, self.done, self.ok = ["Starting..."], False, False
        threading.Thread(target=self._run, args=(cmds,), daemon=True).start()

    def _run(self, cmds):
        ok = True
        for cmd in cmds:
            try:
                p = subprocess.Popen(list(cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, text=True, errors="replace", bufsize=1)
            except OSError as e:
                self.lines.append(str(e))
                ok = False
                break
            for line in p.stdout:
                line = ANSI.sub("", line.rstrip()).split("\r")[-1].strip()
                if line:
                    self.lines.append(line)
                    del self.lines[:-400]
            if p.wait() != 0:
                ok = False
                break
        self.ok, self.done = ok, True
RK_UPDATE = "/usr/local/sbin/rk-update"
RK_SHARE = "/usr/local/sbin/rk-share"


def parse_packages(out):
    """`rk-apps packages` -> rows for AppManager. An app from a package:
    {"pkg": True, "id", "name", "installed", "newest" (the package found), "root", "file"};
    a .zip that is not a package: {"bad": True, "name" (the file), "why"}."""
    rows = []
    for line in out.splitlines():
        parts = line.split("|")
        if parts[0] == "pkg" and len(parts) == 7:
            rows.append({"pkg": True, "id": parts[1], "name": parts[2], "installed": parts[3], "newest": parts[4],
                         "root": parts[5] == "root", "file": parts[6]})
        elif parts[0] == "bad" and len(parts) == 3:
            rows.append({"bad": True, "id": "", "name": parts[1], "why": parts[2], "installed": "-", "newest": "-"})
    return rows


class AppVersions:
    """`rk-apps versions` in the background (it asks GitHub): `apps` once
    `done`, a list of {"id", "name", "installed", "newest"}; "-" is not
    installed and "?" not known."""

    def __init__(self):
        self.done, self.apps = False, []
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        ok, out = run([RK_APPS, "versions"], timeout=45)
        for line in out.splitlines() if ok else []:
            parts = line.split("|")
            if len(parts) in (4, 5):
                self.apps.append(dict(zip(("id", "name", "installed", "newest", "source"), parts)))
        ok, out = run([RK_APPS, "packages"], timeout=30)
        self.apps += parse_packages(out) if ok else []
        self.done = True


class AppUpdate:
    """`rk-apps update <app>`, running: `lines`, then `done`, `ok`, and
    `reason` "password" when sudo refused it. The handheld's password goes to
    the app's installer through sudo's askpass helper, from a private file
    that lives only while it runs (replaces: the starting password, when
    `password` is a new one to set first)."""

    def __init__(self, app, password, replaces=None, action="update"):
        self.lines, self.done, self.ok, self.reason = [], False, False, ""
        self.action = action        # "update", or for an app from a package "package-install" / "package-remove"
        threading.Thread(target=self._run, args=(app, password, replaces), daemon=True).start()

    def _run(self, app, password, replaces):
        if replaces is not None:
            ok, why = change_password(replaces, password)
            if not ok:
                self.lines += ["The password was not changed:", why]
                self.reason, self.done = "newpassword", True
                return
            self.lines.append("✓ this handheld's password is set")
        d = tempfile.mkdtemp(prefix="rk-update-")          # 0700
        try:
            helper, secret = os.path.join(d, "askpass"), os.path.join(d, "pw")
            for path, text, mode in ((helper, ASKPASS, 0o700), (secret, password + "\n", 0o600)):
                with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode), "w") as f:
                    f.write(text)
            env = {k: v for k, v in os.environ.items() if not k.startswith("SDL_")}
            env.update(SUDO_ASKPASS=helper, RK_ASKPASS_FILE=secret)
            p = subprocess.Popen([RK_APPS, self.action, app], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, text=True, errors="replace", bufsize=1, env=env)
            for raw in p.stdout:
                line = ANSI.sub("", raw.rstrip("\n")).split("\r")[-1].strip()
                if line:
                    self.lines.append(line)
                    del self.lines[:-400]
            self.ok = p.wait() == 0
            if not self.ok and any("didn't take that password" in ln or "incorrect password" in ln for ln in self.lines[-8:]):
                self.reason = "password"
        except OSError as e:
            self.lines.append(str(e))
        finally:
            shutil.rmtree(d, ignore_errors=True)
            self.done = True


class OsUpdate:
    """Update the OS itself, or roll it back: `lines`, then `done`/`ok`, and
    `reason` "password" if sudo refused. rk-update does the safe work (fetch,
    check, back up, swap, migrate, restart, auto-rollback); this just runs it
    as root through sudo's askpass helper and streams what it says."""

    def __init__(self, password, action="apply"):
        self.lines, self.done, self.ok, self.reason = [], False, False, ""
        threading.Thread(target=self._run, args=(password, action), daemon=True).start()

    def _run(self, password, action):
        d = tempfile.mkdtemp(prefix="rk-os-")
        try:
            helper, secret = os.path.join(d, "askpass"), os.path.join(d, "pw")
            for path, text, mode in ((helper, ASKPASS, 0o700), (secret, password + "\n", 0o600)):
                with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode), "w") as f:
                    f.write(text)
            env = {k: v for k, v in os.environ.items() if not k.startswith("SDL_")}
            env.update(SUDO_ASKPASS=helper, RK_ASKPASS_FILE=secret)
            p = subprocess.Popen(["sudo", "-A", RK_UPDATE, action], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
                                 errors="replace", bufsize=1, env=env)
            for raw in p.stdout:
                line = ANSI.sub("", raw.rstrip("\n")).split("\r")[-1].strip()
                if line:
                    self.lines.append(line)
                    del self.lines[:-400]
            self.ok = p.wait() == 0
            if not self.ok and any("try again" in ln or "incorrect password" in ln or "Sorry" in ln for ln in self.lines[-8:]):
                self.reason = "password"
        except OSError as e:
            self.lines.append(str(e))
        finally:
            shutil.rmtree(d, ignore_errors=True)
            self.done = True


SOUND_STATUS = "/run/rk-audio/status"
SOUND_STATE = "/var/lib/rk-audio"
SOUND_CLIP = os.path.expanduser("~/.cache/rk-sound/clip.wav")
SOUND_TONE = os.path.expanduser("~/.cache/rk-sound/tone.wav")


def write_tone(path, seconds=1.2, hz=440, rate=44100):
    """A quiet test tone as a WAV file: left ear, then right, then both."""
    import array
    import math
    import wave
    n = int(seconds * rate)
    data = array.array("h")
    for i in range(n):
        v = int(9000 * math.sin(2 * math.pi * hz * i / rate) * min(1, i / 800, (n - i) / 800))
        third = i * 3 // n
        data.extend((v if third != 1 else 0, v if third != 0 else 0))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


class Recorder:
    """Records a few seconds from the default microphone, with a live level,
    and plays things back through the default output. What the Sound window
    hears and plays is what any app that opens "default" gets."""
    RATE = 44100

    def __init__(self):
        self.level = self.peak = 0.0          # now, and the loudest so far (0 to 1)
        self.elapsed = self.seconds = 0.0
        self.recording = False
        self.error = ""
        self.has_clip = False
        self._play = None

    def record(self, seconds=5):
        if self.recording:
            return
        self.stop()
        self.level = self.peak = self.elapsed = 0.0
        self.seconds, self.recording, self.error, self.has_clip = seconds, True, "", False
        threading.Thread(target=self._record, daemon=True).start()

    def _record(self):
        import array
        import wave
        frames = bytearray()
        try:
            proc = subprocess.Popen(["arecord", "-q", "-D", "default", "-f", "S16_LE", "-r", str(self.RATE), "-c", "1", "-t", "raw"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as e:
            self.error, self.recording = str(e), False
            return
        want = int(self.seconds * self.RATE) * 2
        try:
            while len(frames) < want:
                chunk = proc.stdout.read(min(self.RATE // 10 * 2, want - len(frames)))
                if not chunk:
                    break
                frames += chunk
                samples = array.array("h", chunk[:len(chunk) // 2 * 2])
                self.level = max((abs(v) for v in samples), default=0) / 32768
                self.peak = max(self.peak, self.level)
                self.elapsed = len(frames) / 2 / self.RATE
        finally:
            proc.terminate()
            try:
                err = proc.communicate(timeout=3)[1].decode(errors="replace").strip()
            except subprocess.SubprocessError:
                err = ""
        if frames:
            os.makedirs(os.path.dirname(SOUND_CLIP), exist_ok=True)
            with wave.open(SOUND_CLIP, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(self.RATE)
                w.writeframes(bytes(frames))
            self.has_clip = True
        else:
            self.error = (err.splitlines() or ["The microphone gave no sound"])[-1]
        self.level, self.recording = 0.0, False

    def _start(self, path):
        self.stop()
        try:
            self._play = subprocess.Popen(["aplay", "-q", "-D", "default", path], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except OSError as e:
            self.error = str(e)

    def play(self):
        if self.has_clip and not self.recording:
            self._start(SOUND_CLIP)

    def tone(self):
        if not self.recording:
            if not os.path.exists(SOUND_TONE):
                write_tone(SOUND_TONE)
            self._start(SOUND_TONE)

    @property
    def playing(self):
        p = self._play
        if p is None:
            return False
        if p.poll() is None:
            return True
        if p.returncode:
            err = p.stderr.read().decode(errors="replace").strip()
            self.error = (err.splitlines() or ["Could not play"])[-1]
        self._play = None
        return False

    def stop(self):
        if self._play is not None and self._play.poll() is None:
            self._play.terminate()
        self._play = None


def parse_mixer(text):
    """`amixer scontents` -> [{"name", "caps", "pct", "cpct", "on"}], one for
    each simple control: its capabilities (pvolume, cvolume, ...), its
    playback and capture levels as percentages (absent or None when it has
    none) and its switch (None when it has none)."""
    out, cur = [], None
    for line in text.splitlines():
        m = re.match(r"Simple mixer control '(.*)',\d+", line)
        if m:
            cur = {"name": m.group(1), "caps": set(), "pct": None, "on": None}
            out.append(cur)
        elif cur is not None:
            line = line.strip()
            if line.startswith("Capabilities:"):
                cur["caps"] = set(line.split(":", 1)[1].split())
            else:
                # a control can hold both directions on one line (a headset's
                # "Mic": its sidetone and its capture level): keep them apart
                for key, word in (("pct", "Playback"), ("cpct", "Capture")):
                    m = re.search(word + r" \d+ \[(\d+)%\]", line)
                    if m and cur.get(key) is None:
                        cur[key] = int(m.group(1))
                m = re.search(r"\[(\d+)%\]", line)
                if m and cur["pct"] is None and cur.get("cpct") is None:
                    cur["pct"] = int(m.group(1))
                m = re.search(r"\[(on|off)\]", line)
                if m and cur["on"] is None:
                    cur["on"] = m.group(1) == "on"
    return out


def usb_sound_cards(text):
    """/proc/asound/cards -> [(number, name)] of the USB sound devices."""
    return [(int(m.group(1)), m.group(2).strip())
            for m in re.finditer(r"(?m)^\s*(\d+)\s+\[.*?\]:\s+USB-Audio\s+-\s+(.*)$", text)]


def pick_control(controls, cap, prefer):
    """The control with this capability to use: a preferred name, else the first."""
    have = [c for c in controls if cap in c["caps"] or (cap + "-joined") in c["caps"]]
    for name in prefer:
        for c in have:
            if c["name"].lower() == name.lower():
                return c
    return have[0] if have else None


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


LOW_SYSTEM_MB, LOW_DATA_MB, LOW_MEMORY_MB = 150, 200, 48


def health_warnings(storage, spare_mb):
    """What is running short, in words for the owner: [(key, text)]. `storage`
    is storage()'s list; `spare_mb` the memory still to be had (available plus
    free swap), or None when it cannot be read."""
    out = []
    for st in storage:
        free = (st["total"] - st["used"]) // (1024 * 1024)
        if st["mount"] == "/" and free < LOW_SYSTEM_MB:
            out.append(("system", f"System partition almost full: {free} MB free. Installs and updates will be refused."))
        elif st["mount"] == "/data" and free < LOW_DATA_MB:
            out.append(("data", f"Data partition almost full: {free} MB free."))
    if spare_mb is not None and spare_mb < LOW_MEMORY_MB:
        out.append(("memory", f"Memory is short: {spare_mb} MB to spare. Close what you do not use."))
    return out


def parse_monitor_modes(iw_phy_text):
    """{phy index: supports monitor mode} from `iw phy` output."""
    out, cur, in_modes = {}, None, False
    for line in iw_phy_text.splitlines():
        m = re.match(r"\s*Wiphy phy(\d+)", line)
        if m:
            cur, in_modes = int(m.group(1)), False
            out[cur] = False
            continue
        if cur is None:
            continue
        if "Supported interface modes:" in line:
            in_modes = True
            continue
        if in_modes:
            t = line.strip()
            if t.startswith("*"):
                if "monitor" in t:
                    out[cur] = True
            elif t:
                in_modes = False
    return out


def wifi_adapters(sys_root="/sys", iw_phy_text=None):
    """Every wireless adapter: {"phy", "iface", "driver", "bus", "monitor"}.

    bus is "usb" for a dongle, "sdio"/"mmc" for the board's own radio. monitor
    is what the driver reports to `iw`, which is the capability the Wi-Fi tools
    need; it says nothing about injection, which only a real test confirms.
    """
    import glob as _glob
    if iw_phy_text is None:
        ok, iw_phy_text = run(["iw", "phy"])
        if not ok:
            iw_phy_text = ""
    monitor = parse_monitor_modes(iw_phy_text)
    found = []
    for d in sorted(_glob.glob(f"{sys_root}/class/ieee80211/phy*")):
        try:
            phy = int(re.search(r"phy(\d+)$", d).group(1))
        except (AttributeError, ValueError):
            continue
        link = os.path.realpath(f"{d}/device")
        bus = "usb" if "/usb" in link else "sdio" if ("mmc" in link or "sdio" in link) else "other"
        driver = os.path.basename(os.path.realpath(f"{d}/device/driver")) if os.path.exists(f"{d}/device/driver") else ""
        nets = _glob.glob(f"{d}/device/net/*")
        iface = os.path.basename(nets[0]) if nets else ""
        found.append({"phy": phy, "iface": iface, "driver": driver, "bus": bus,
                      "monitor": monitor.get(phy, False)})
    return found


def wifi_audit_status(adapters, have_iw=True):
    """A short readiness line for the Wi-Fi tools: {"line", "level", "ready"}.

    level is "ok" (a USB adapter reports monitor mode), "warn" (an adapter is
    there but does not), or "muted" (onboard radio only, or no check).
    """
    if not have_iw:
        return {"line": "Adapter check needs the 'iw' tool.", "level": "muted", "ready": False}
    usb = [a for a in adapters if a["bus"] == "usb"]
    ready = [a for a in usb if a["monitor"]]
    if ready:
        a = ready[0]
        name = a["driver"] or a["iface"] or "USB adapter"
        return {"line": f"Ready: {name} reports monitor mode.", "level": "ok", "ready": True}
    if usb:
        a = usb[0]
        name = a["driver"] or a["iface"] or "USB adapter"
        return {"line": f"{name} is plugged in but does not report monitor mode.",
                "level": "warn", "ready": False}
    return {"line": "Onboard radio is client-only. Plug in a monitor-capable USB adapter for Wi-Fi testing.",
            "level": "muted", "ready": False}


def nm_device(text, kind):
    """The device of one kind ("wifi", "ethernet") in `nmcli -t -f
    DEVICE,TYPE,STATE,CONNECTION dev`: the connected one when there are
    several, else the first. None when there is none."""
    found = None
    for line in text.splitlines():
        p = line.split(":")
        if len(p) >= 4 and p[1] == kind:
            dev = {"device": p[0], "state": p[2], "ssid": p[3] if p[2] == "connected" else "", "address": ""}
            if dev["state"] == "connected":
                return dev
            found = found or dev
    return found


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

    def memory_spare(self):
        """Megabytes still to be had: available memory plus free swap. None when unknown."""
        m = {}
        for line in read("/proc/meminfo").splitlines():
            k, _, v = line.partition(":")
            if v.split():
                m[k] = int(v.split()[0]) // 1024
        return m["MemAvailable"] + m.get("SwapFree", 0) if "MemAvailable" in m else None

    def health(self):
        """What is running short: [(key, text)], looked at twice a minute at most."""
        return self.cached("health", 30, lambda: health_warnings(self.storage(), self.memory_spare()))

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

    # ------------------------------------------------------ Wi-Fi and cable
    def _net(self, kind):
        def get():
            ok, out = run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev"])
            dev = nm_device(out if ok else "", kind)
            if dev and dev["state"] == "connected":
                ok, out = run(["nmcli", "-t", "-g", "IP4.ADDRESS", "dev", "show", dev["device"]])
                dev["address"] = out.splitlines()[0].split("/")[0] if ok and out else ""
            return dev
        return self.cached(kind, 4, get)

    def wifi(self):
        """State of the first Wi-Fi card: None when there is no card."""
        return self._net("wifi")

    def wired(self):
        """State of a network cable (a USB Ethernet adapter, or a hub or dock
        with a network socket): None when there is no such adapter. "state" is
        NetworkManager's: connected, connecting..., unavailable (no cable)."""
        return self._net("ethernet")

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
        """rk-remote refuses to turn it on while the handheld still has its
        first password: set_password comes first then."""
        ok, out = run(["/usr/local/sbin/rk-remote", "on" if on else "off"], root=True, timeout=20)
        return ok, "" if ok else (out.splitlines()[-1].replace("rk-remote: ", "") if out else "")

    def set_password(self, new):
        """Give the handheld its own password in place of the first one."""
        return change_password(START_PASSWORD, new)

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

    def wifi_audit(self):
        """Readiness of the Wi-Fi auditing path: {"line", "level", "ready"}."""
        return wifi_audit_status(wifi_adapters(), have_iw=bool(shutil.which("iw")))

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
    # ---------------------------------------------------------------- sound
    # Output: a USB sound device when one is plugged in (the apps play there
    # too), else the built-in sound chip. Microphone: the USB device's, else
    # the built-in one when the chip has a level for it.
    def _sound(self):
        """{"out": (card, control, pct, name), "mic": the same or None}, kept for a moment."""
        now = time.time()
        if getattr(self, "_sound_at", 0) > now - 0.4:
            return self._sound_now
        found = {"out": None, "mic": None}
        for card, name in usb_sound_cards(read("/proc/asound/cards")):
            ok, text = run(["amixer", "-c", str(card), "scontents"])
            controls = parse_mixer(text) if ok else []
            out = pick_control(controls, "pvolume", ("PCM", "Speaker", "Headphone", "Headset", "Master"))
            mic = pick_control(controls, "cvolume", ("Mic", "Capture", "Headset"))
            if out and not found["out"]:
                found["out"] = (card, out["name"], out["pct"], name)
            if mic and not found["mic"]:
                found["mic"] = (card, mic["name"], mic.get("cpct", mic["pct"]), name)
        if not found["mic"]:
            ok, text = run(["amixer", "-c", "0", "scontents"])
            mic = pick_control(parse_mixer(text) if ok else [], "cvolume", ("Mic", "Capture"))
            if mic:
                found["mic"] = (0, mic["name"], mic.get("cpct", mic["pct"]), "")
        self._sound_now, self._sound_at = found, now
        return found

    def volume_name(self):
        out = self._sound()["out"]
        return "Headphones" if out else "Volume"

    def sound_status(self):
        """What rk-audiod decided: {"mode", "jack", "jack_found", "jack_reversed", "path", "out", "mic"}, or {}."""
        try:
            return json.loads(read(SOUND_STATUS))
        except ValueError:
            return {}

    def set_sound_output(self, mode):
        """"auto" (follow the jack), "spk" or "hp"; rk-audiod applies it within a second."""
        return self._sound_choice("output", mode)

    def set_jack_reversed(self, on):
        return self._sound_choice("jack", "reversed" if on else "normal")

    def _sound_choice(self, name, value):
        try:
            with open(f"{SOUND_STATE}/{name}", "w") as f:
                f.write(value + "\n")
            return True
        except OSError:
            return False

    def recorder(self):
        return Recorder()

    def os_status(self):
        """{"installed","newest","source","channel","schema"}: what this card
        has, without asking the network ("newest" comes from os_newest, which
        can take its time). The installed version is read from its file as
        well: it is shown whatever becomes of the rest."""
        info = {"installed": "", "newest": "", "source": "", "channel": "", "schema": ""}
        ok, out = run([RK_UPDATE, "status", "--local"], timeout=20)
        for line in out.splitlines() if ok else []:
            k, _, v = line.partition(":")
            k = k.strip()
            if k in info:
                info[k] = v.strip()
        if info["installed"] in ("", "unknown"):
            info["installed"] = os_release_version(read("/etc/os-release.rk"))
        return info

    def os_newest(self):
        """The newest version there is to update to, or "" when it cannot be
        looked up (no network, or the source did not answer in time)."""
        ok, out = run([RK_UPDATE, "check"], timeout=45)
        tag = out.splitlines()[-1].strip() if ok and out else ""
        return tag if re.fullmatch(r"v?\d+\.\d+\.\d+", tag) else ""

    def os_update(self, password):
        return OsUpdate(password, "apply")

    def os_rollback(self, password):
        return OsUpdate(password, "rollback")

    MOUSE_BIN = "/usr/local/sbin/rk-mouse"
    MOUSE_ON = "/run/rk-mouse/on"

    def mouse_enabled(self):
        """True/False if the left-stick mouse service is present, else None."""
        if not os.path.exists(self.MOUSE_BIN):
            return None
        try:
            with open(self.MOUSE_ON) as f:
                return f.read().strip() != "0"
        except OSError:
            return True                     # present but not yet written: on by default

    def set_mouse(self, on):
        try:
            os.makedirs("/run/rk-mouse", exist_ok=True)
            with open(self.MOUSE_ON, "w") as f:
                f.write("1" if on else "0")
            return True
        except OSError:
            return False

    def volume(self):
        """Output volume, 0 to 100, or None when there is no mixer control."""
        out = self._sound()["out"]
        if out:
            return out[2]
        ok, text = run(["amixer", "-c0", "cget", "name=Playback Volume"])
        try:
            mx = int(text.split("max=")[1].split(",")[0])
            val = int(text.split(": values=")[1].split(",")[0])
            return round(val * 100 / mx) if mx else None
        except (IndexError, ValueError):
            return None

    def set_volume(self, pct):
        pct = max(0, min(100, pct))
        out = self._sound()["out"]
        if out:
            run(["amixer", "-q", "-c", str(out[0]), "sset", out[1], "playback", f"{pct}%", "unmute"])
        else:
            run(["amixer", "-c0", "cset", "name=Playback Volume", f"{pct}%"])
        self._sound_at = 0
        return pct

    def mic_name(self):
        mic = self._sound()["mic"]
        return ("Microphone (USB)" if mic[3] else "Microphone") if mic else ""

    def mic(self):
        """Microphone level, 0 to 100, or None when no microphone has one."""
        mic = self._sound()["mic"]
        return mic[2] if mic else None

    def set_mic(self, pct):
        pct = max(0, min(100, pct))
        mic = self._sound()["mic"]
        if mic:
            run(["amixer", "-q", "-c", str(mic[0]), "sset", mic[1], "capture", f"{pct}%", "cap"])
            self._sound_at = 0
        return pct

    def _backlight(self):
        d = glob.glob("/sys/class/backlight/*")
        return d[0] if d else None

    def backlight_off(self):
        """The screen's light off, for the screen's sleep. Returns the
        brightness to give back (set_brightness never goes this low: this is
        the one place that does, and backlight_restore undoes it)."""
        d, was = self._backlight(), self.brightness()
        if not d or was is None:
            return None
        if was > 0 and self.setting("brightness_awake") != was:
            self.set_setting("brightness_awake", was)       # if the desktop is restarted meanwhile
        try:
            with open(d + "/brightness", "w") as f:
                f.write("0")
        except OSError:
            return None
        return was or self.setting("brightness_awake", 50)

    def backlight_restore(self, pct=None):
        """Light the screen again. Without a value: only if it is dark (the
        desktop starting after it was stopped asleep)."""
        if pct is None:
            if self.brightness() != 0:
                return
            pct = self.setting("brightness_awake", 50)
        self.set_brightness(pct or 50)

    # --------------------------------------------- the desktop's own settings
    SETTINGS = ("/data/ark/.rk-desktop.json", os.path.expanduser("~/.rk-desktop.json"))
    SCREEN_OFF = (0, 1, 2, 5, 10, 30)       # minutes; 0 is never
    ZONEINFO = "/usr/share/zoneinfo"

    def _settings_path(self):
        """On the data partition, so a reflash keeps them; at home without one."""
        first = self.SETTINGS[0]
        return first if os.path.isdir(os.path.dirname(first)) else self.SETTINGS[1]

    def _settings(self):
        try:
            with open(self._settings_path()) as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def setting(self, key, default=None):
        return self.cached("settings", 5, self._settings).get(key, default)

    def set_setting(self, key, value):
        d = dict(self._settings(), **{key: value})
        path = self._settings_path()
        try:
            with open(path + ".new", "w") as f:
                json.dump(d, f, indent=2)
            os.replace(path + ".new", path)
        except OSError:
            pass
        self._cache["settings"] = (time.time(), d)

    def screen_off(self):
        """Minutes without a button before the screen goes dark; 0 is never."""
        m = self.setting("screen_off", 5)
        return m if m in self.SCREEN_OFF else 5

    def set_screen_off(self, minutes):
        self.set_setting("screen_off", minutes)

    def timezone(self):
        z = read("/etc/timezone").strip().splitlines()
        if z and z[0]:
            return z[0]
        try:
            return os.readlink("/etc/localtime").split("/zoneinfo/", 1)[1]
        except (OSError, IndexError):
            return "UTC"

    def timezones(self):
        """Every zone the system has files for, sorted: "Region/City" names and UTC."""
        return self.cached("timezones", 3600, lambda: zone_names(self.ZONEINFO))

    def set_timezone(self, zone):
        ok, out = run(["/usr/local/sbin/rk-region", "tz", zone], root=True, timeout=10)
        if ok:
            time.tzset()                    # this desktop's own clock, now
            self.set_setting("timezone", zone)
        return ok, "" if ok else (out.splitlines()[-1].replace("rk-region: ", "") if out else "Could not set it")

    def restore_timezone(self):
        """After a reflash the system is back on the image's zone, and the
        data partition still knows the owner's: put it back."""
        want = self.setting("timezone")
        if want and want != self.timezone():
            self.set_timezone(want)

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
        for mount, label in (("/", "System"), ("/data", "Data"), ("/share", "Computer"), ("/boot", "Boot files")):
            try:
                u = shutil.disk_usage(mount)
                if mount in ("/data", "/share") and not os.path.ismount(mount):
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
        The same file name in two folders is one app: the first folder's is kept.
        """
        found, seen = [], set()
        for d in APPS_DIRS:
            for f in sorted(glob.glob(os.path.join(d, "*.json"))):
                # the image's own entry wins over one of the same file name
                # on /data (an app's installer may have left one there
                # before the image carried it): no icon twice
                if os.path.basename(f) in seen:
                    continue
                seen.add(os.path.basename(f))
                try:
                    with open(f) as fh:
                        a = json.load(fh)
                    a["ready"] = bool(a.get("exec")) and shutil.which(a["exec"][0], path=with_games()) is not None
                    # "needs": a file (or several) that exists once the app's own setup has run;
                    # until then the dock opens the setup window named in "setup"
                    needs = a.get("needs") or []
                    needs = [needs] if isinstance(needs, str) else needs
                    a["needs_setup"] = any(not os.path.exists(os.path.expanduser(n)) for n in needs)
                    found.append(a)
                except (OSError, ValueError, KeyError, IndexError):
                    continue
        return found

    # --------------------------------------------------------------- video
    def video_status(self):
        """What Video has to work with (see parse_video_status)."""
        return parse_video_status(run([RK_VIDEO, "status"], timeout=70)[1])

    def video_search(self, words):
        return VideoSearch(words)

    def video_setup(self, packages=True):
        """Install what is missing (mpv, RetroArch and their kin, as root) and
        fetch the newest yt-dlp; with packages=False only the yt-dlp. Returns a Steps."""
        cmds = [("sudo", "-n", RK_TOOLS, "install-media")] if packages else []
        return Steps(cmds + [(RK_VIDEO, "fetch")])

    def games_installed(self):
        return os.access("/opt/rk-emulators/bin/retroarch", os.X_OK)

    def video_error(self, since):
        """Why the last play failed, when it did so after `since` (a time); else ""."""
        path = os.path.expanduser("~/.cache/rk-video/last.error")
        try:
            return read(path) if os.path.getmtime(path) >= since - 1 else ""
        except OSError:
            return ""

    def video_command(self, video_id):
        return [RK_VIDEO, "play", "https://www.youtube.com/watch?v=" + video_id]

    def stump_setup(self, answers, password, replaces=None):
        """Run the Stump's installer with these answers; returns a StumpSetup."""
        return StumpSetup(answers, password, replaces=replaces)

    def password_expired(self):
        return password_expired()

    def app_versions(self):
        return AppVersions()

    def app_update(self, app, password, replaces=None):
        return AppUpdate(app, password, replaces)

    def package_install(self, app, password, replaces=None):
        """Install or update an app from its package in /data/ark/packages."""
        return AppUpdate(app, password, replaces, action="package-install")

    def package_remove(self, app, password):
        return AppUpdate(app, password, action="package-remove")

    def app_source(self, app, source):
        """Where an app's updates come from ("stable" or "sandbox"); FireFly has both."""
        return run([RK_APPS, "source", app, source])[0]

    def stump_storage(self):
        return stump_storage()

    def stump_search(self):
        return StumpSearch(self.own_networks())

    # --------------------------------------------------------------- power
    def boot_selection(self):
        return {k: v for k, _, v in (ln.partition("=") for ln in read("/boot/rk-device.txt").splitlines())}

    def power_off(self):
        return run(["poweroff"], root=True)

    def restart(self):
        return run(["reboot"], root=True)

    # ------------------------------------- the part of the card a computer reads
    def share_state(self):
        """"ready", "requested", "none" (the card can get one) or "small"; "" without rk-share."""
        ok, out = run([RK_SHARE, "state"])
        return out.strip() if ok else ""

    def share_request(self):
        """Ask for the visible partition: a job (`lines`, `done`, `ok`). It is made at the next start."""
        return Steps([["sudo", "-n", RK_SHARE, "request"]])

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
    def memory_spare(self): return 618
    def health(self): return list(getattr(self, "_health", []))
    def battery(self): return {"percent": 78, "status": "Discharging"}
    def wifi(self): return {"device": "wlan0", "state": "connected", "ssid": "Workshop", "address": "192.168.0.167"}
    def wired(self): return None

    def wifi_scan(self):
        return [{"ssid": "Workshop", "signal": 82, "secure": True, "active": True},
                {"ssid": "LaBuche3-192.168.4.1", "signal": 64, "secure": False, "active": False},
                {"ssid": "Guest", "signal": 41, "secure": True, "active": False}]

    def wifi_join(self, ssid, password): return True, f"Connected to {ssid}"
    def ssh_enabled(self): return getattr(self, "_ssh", False)

    def set_ssh(self, on):
        if on and self.password_expired():
            return False, "this handheld still has its first password; choose your own first"
        self._ssh = on
        return True, ""

    def set_password(self, new):
        self._own_password = True
        return True, ""
    _vol, _bri = 60, 80
    def volume(self): return self._vol
    def set_volume(self, pct): self._vol = max(0, min(100, pct)); return self._vol
    def volume_name(self): return "Volume"
    def mic_name(self): return "Microphone (USB)"
    _snd = {"mode": "auto", "jack": False, "jack_found": True, "jack_reversed": False, "path": "SPK",
            "out": {"card": "rockchiprk817co", "dev": 0, "name": "rockchip,rk817-codec", "usb": False},
            "mic": {"card": "Headset", "dev": 0, "name": "USB-C Headset", "usb": True}}

    def sound_status(self): return dict(self._snd)

    def set_sound_output(self, mode):
        self._snd = dict(self._snd, mode=mode, path={"spk": "SPK", "hp": "HP"}.get(mode, "HP" if self._snd["jack"] else "SPK"))
        return True

    def set_jack_reversed(self, on):
        self._snd = dict(self._snd, jack_reversed=on, jack=not self._snd["jack"])
        return self.set_sound_output(self._snd["mode"])

    def os_status(self):
        return {"installed": "0.9.0", "newest": "", "source": "official (github.com/ruderigo/RK3326_Linux)", "channel": "os-update", "schema": "2 of 2"}

    def os_newest(self): return "v1.0.0"

    def os_update(self, password):
        job = OsUpdate.__new__(OsUpdate)
        job.lines = ["rk-update: fetching v1.0.0 from github.com/ruderigo/RK3326_Linux",
                     "rk-update: checking the new desktop...", "rk-update: backing up the current system...",
                     "rk-update: installing...", "rk-update: running migrations...",
                     "rk-migrate: already current (schema 1)", "rk-update: restarting the desktop...",
                     "rk-update: updated to 1.0.0. Backup kept at /data/ark/.rk-backups/…"]
        job.done, job.ok, job.reason = True, True, ""
        return job

    def os_rollback(self, password):
        return self.os_update(password)

    _mouse_on = True

    def mouse_enabled(self):
        return self._mouse_on

    def set_mouse(self, on):
        self._mouse_on = bool(on)
        return True

    def recorder(self):
        rec = Recorder()
        rec.record = lambda seconds=5: (setattr(rec, "has_clip", True), setattr(rec, "peak", 0.4))
        rec.play = rec.tone = lambda: None
        return rec
    def mic(self): return getattr(self, "_mic", 70)
    def set_mic(self, pct): self._mic = max(0, min(100, pct)); return self._mic
    def brightness(self): return self._bri
    def set_brightness(self, pct): self._bri = max(5, min(100, pct)); return self._bri

    def backlight_off(self):
        was, self._bri = self._bri, 0
        return was

    def _settings(self): return getattr(self, "_set", {})
    def setting(self, key, default=None): return self._settings().get(key, default)
    def set_setting(self, key, value): self._set = dict(self._settings(), **{key: value})
    def timezone(self): return self.setting("timezone", "America/Toronto")

    def timezones(self):
        return ["Africa/Cairo", "Africa/Lagos", "America/Mexico_City", "America/New_York", "America/Toronto",
                "America/Vancouver", "Asia/Tokyo", "Europe/Madrid", "Europe/Paris", "Pacific/Auckland", "UTC"]

    def set_timezone(self, zone):
        if zone not in self.timezones():
            return False, f"no such time zone: {zone}"
        self.set_setting("timezone", zone)
        return True, ""

    def usb_devices(self):
        return [{"name": "Ralink 802.11 n WLAN", "kind": "Wi-Fi card", "id": "148f:3070", "driver": "rt2800usb"},
                {"name": "Silicon Labs CP2102 USB to UART", "kind": "Serial device", "id": "10c4:ea60", "driver": "cp210x"},
                {"name": "Lite-On USB wired keyboard", "kind": "Keyboard", "id": "04ca:007d", "driver": "usbhid"}]

    def storage(self):
        g = 1024 ** 3
        return [{"label": "System", "mount": "/", "used": int(0.7 * g), "total": int(2.9 * g)},
                {"label": "Data", "mount": "/data", "used": int(1.2 * g), "total": 16 * g},
                {"label": "Computer", "mount": "/share", "used": int(4.6 * g), "total": 67 * g},
                {"label": "Boot files", "mount": "/boot", "used": int(0.11 * g), "total": int(0.25 * g)}]

    def apps(self):
        return [{"name": "FireFly", "icon": "firefly", "group": "Comms", "about": "Messages over LoRa and Wi-Fi", "ready": True},
                {"name": "Stump", "icon": "stump", "group": "Comms", "about": "This handheld as a Stump mesh node", "ready": True,
                 "setup": "stump", "needs_setup": True},
                {"name": "Ember", "icon": "ember", "group": "Audio", "about": "Analog pads and a vocoder", "ready": True},
                {"name": "Games", "icon": "games", "group": "Play", "about": "RetroArch, for your own game files", "ready": True},
                {"name": "Provisioner", "icon": "chip", "group": "Workshop", "about": "Flash ESP32 boards and radios", "ready": False},
                {"name": "STUMP Recon", "icon": "chip", "group": "Comms", "about": "Dual-band LoRa & 2.4 GHz RF recon", "ready": True}]   # from a package

    def video_status(self): return dict(getattr(self, "_video", {"mpv": True, "ytdlp": "2026.11.18", "js": "quickjs"}))

    def games_installed(self): return True
    def video_error(self, since): return ""

    def video_search(self, words):
        job = VideoSearch.__new__(VideoSearch)
        job.done, job.error = True, ""
        job.results = [{"id": "demo0000001", "length": "12:40", "channel": "Bench Notes", "title": "Reflowing a handheld's USB-C port"},
                       {"id": "demo0000002", "length": "1:02:15", "channel": "Mesh Radio Club", "title": "LoRa antennas, measured: what the range tests showed"},
                       {"id": "demo0000003", "length": "8:03", "channel": "Small Linux", "title": "Debian on an RK3326: the first boot"},
                       {"id": "demo0000004", "length": "24:31", "channel": "Synth Corner", "title": "A vocoder from scratch"}]
        return job

    def video_setup(self, packages=True):
        job = Steps.__new__(Steps)
        job.done, job.ok = False, False
        job.lines = ["rk-tools: mpv installed", "rk-tools: quickjs installed", "rk-tools: retroarch installed",
                     "rk-tools: done.", "rk-video: fetching yt-dlp from its releases..."]
        return job

    def password_expired(self): return not getattr(self, "_own_password", False)

    def app_versions(self):
        job = AppVersions.__new__(AppVersions)
        src = getattr(self, "_src", "stable")
        job.done, job.apps = True, [{"id": "firefly", "name": "FireFly", "installed": "0.9.11", "source": src,
                                     "newest": "0.9.12" if src == "sandbox" else "0.9.11"},
                                    {"id": "stump", "name": "Stump", "installed": "2.7.3-b.87", "newest": "2.7.4-b.87", "source": "stable"},
                                    {"id": "ember", "name": "Ember", "installed": "?", "newest": "0.4.0"},
                                    {"id": "provisioner", "name": "Provisioner", "installed": "-", "newest": "0.3.0-beta.24"},
                                    {"pkg": True, "id": "stump-recon", "name": "STUMP Recon", "installed": "0.4.1-rk3326",
                                     "newest": "0.6.0-rk3326", "root": True, "file": "stump-rf-recon-rk3326-v0.6.0-rk3326.zip"},
                                    {"pkg": True, "id": "rk-field-deck", "name": "Field Deck", "installed": "-",
                                     "newest": "1.0.0-rk3326", "root": True, "file": "rk-field-deck-v1.0.0-rk3326.zip"}]
        return job

    def app_source(self, app, source):
        self._src = source
        return True

    def package_install(self, app, password, replaces=None): return self.app_update(app, password)
    def package_remove(self, app, password): return self.app_update(app, password)

    def app_update(self, app, password, replaces=None):
        job = AppUpdate.__new__(AppUpdate)
        job.done, job.ok, job.reason = False, False, ""
        job.lines = ["rk-apps: FireFly: fetching the main branch...", "rk-apps: FireFly: running its installer...",
                     "== 2/5 App files -> /home/ark/firefly", "== 3/5 Reticulum + LXMF in a private environment"]
        return job
    def stump_storage(self): return 991, 256, [256, 512, 768]

    def stump_search(self):
        job = StumpSearch.__new__(StumpSearch)
        job.done, job.found = True, [{"address": "192.168.0.42", "name": "LaBuche3", "links": True},
                                     {"address": "192.168.0.57", "name": "Atelier", "links": False}]
        return job

    def stump_setup(self, answers, password, replaces=None):
        job = StumpSetup.__new__(StumpSetup)
        job.reason = ""
        job.step, job.done, job.ok = "3/6 The cockpit's files", False, False
        job.lines = ["1/6 Packages", "✓ all present", "2/6 SandBox_Stump_On", "✓ up to date",
                     "3/6 The cockpit's files", "✓ FireFly's font (DejaVu Sans Mono) next to the engine"]
        return job

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

    def wifi_audit(self):
        return {"line": "Ready: rtl8812au reports monitor mode.", "level": "ok", "ready": True}

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

    def share_state(self): return getattr(self, "_share", "ready")

    def share_request(self):
        job = Steps.__new__(Steps)
        job.lines, job.done, job.ok = ["rk-share: Ready. Restart the handheld."], True, True
        self._share = "requested"
        return job

    def listdir(self, path):
        if path == "/data/ark":
            return [("captures", True, 0), ("recordings", True, 0), ("notes.txt", False, 1840),
                    ("scan-2026-11-20.txt", False, 12288)]
        return [("example.txt", False, 420)]

    def places(self): return [("Home", "/data/ark"), ("Card settings", "/boot")]
