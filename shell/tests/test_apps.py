"""Updating a dock app from the AppManager window (overlay/usr/local/sbin/rk-apps),
with stand-ins for git and the network."""
import os
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RK_APPS = os.path.normpath(os.path.join(HERE, "..", "..", "overlay", "usr", "local", "sbin", "rk-apps"))

# a Stump update takes the files from the source chosen in AppManager, then runs the installer
for source, repo in (("sandbox", "SandBox_RK3326_Stump"), ("stable", "R36MAX-Stump")):
    with tempfile.TemporaryDirectory() as d:
        for sub in ("R36MAX-Stump/.git", "R36MAX-Stump/handheld", "Stump", ".config"):
            os.makedirs(f"{d}/{sub}")
        open(f"{d}/Stump/stump_pc.py", "w").close()
        open(f"{d}/.config/rk-apps", "w").write(f"STUMP_SOURCE={source}\n")
        open(f"{d}/R36MAX-Stump/handheld/VERSION", "w").write("2.7.4-b.87\n")
        open(f"{d}/R36MAX-Stump/handheld/install.sh", "w").write(f'echo "installer $(cat {d}/R36MAX-Stump/handheld/VERSION)" >> {d}/LOG\n')
        open(f"{d}/ip", "w").write("#!/bin/sh\necho 'default via 10.0.0.1 dev wlan0'\n")
        # git: note what was asked; "reset" is the moment the new files are there
        open(f"{d}/git", "w").write(f"""#!/bin/sh
echo "git $*" >> {d}/LOG
case "$*" in *reset*) echo 2.7.6-b.88 > {d}/R36MAX-Stump/handheld/VERSION ;; esac
""")
        os.chmod(f"{d}/ip", 0o755)
        os.chmod(f"{d}/git", 0o755)
        p = subprocess.run(["bash", RK_APPS, "update", "stump"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                           env=dict(os.environ, PATH=d + ":" + os.environ["PATH"], HOME=d))
        log = open(f"{d}/LOG").read()
        assert p.returncode == 0, p.stdout
        assert f"git remote set-url origin https://github.com/ruderigo/{repo}" in log, log
        assert log.index("reset --hard") < log.index("installer 2.7.6-b.88"), "the installer ran on the old files:\n" + log
        assert "Stump is now 2.7.6-b.88" in p.stdout, p.stdout

# The Provisioner: the newest release is read from the repository's tags
# (all of its releases are pre-releases), ranked as versions are, and its
# tarball is checked against SHA256SUMS before its installer runs.
import hashlib
import io
import tarfile


def provisioner(d, tags, sums_ok=True, command=("install", "provisioner")):
    """Run rk-apps with stand-ins: git lists `tags`, curl hands out a release made here."""
    version = "0.3.0-beta.24"
    name = f"RK3326-Provisioner-{version}"
    os.makedirs(f"{d}/release")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        body = (f'mkdir -p "$HOME/rk3326_provisioner" && echo {version} > "$HOME/rk3326_provisioner/VERSION" && '
                f'printf "#!/bin/sh\\n" > "$HOME/rk3326_provisioner/RK3326_Provisioner.sh" && '
                f'chmod +x "$HOME/rk3326_provisioner/RK3326_Provisioner.sh" && echo "installer ran" >> {d}/LOG\n').encode()
        info = tarfile.TarInfo(f"{name}/install.sh")
        info.size = len(body)
        tar.addfile(info, io.BytesIO(body))
    open(f"{d}/release/{name}.tar.gz", "wb").write(buf.getvalue())
    digest = hashlib.sha256(buf.getvalue()).hexdigest() if sums_ok else "0" * 64
    open(f"{d}/release/SHA256SUMS", "w").write(f"{digest}  {name}.tar.gz\n")
    open(f"{d}/ip", "w").write("#!/bin/sh\necho 'default via 10.0.0.1 dev wlan0'\n")
    open(f"{d}/git", "w").write("#!/bin/sh\n" + "".join(f"echo 'abc123\trefs/tags/{t}'\n" for t in tags))
    # curl -fsSL URL -o FILE: hand out the file of that name from the release made above
    open(f"{d}/curl", "w").write(f"""#!/bin/sh
echo "curl $2" >> {d}/LOG
cp "{d}/release/$(basename "$2")" "$4"
""")
    for tool in ("ip", "git", "curl"):
        os.chmod(f"{d}/{tool}", 0o755)
    p = subprocess.run(["bash", RK_APPS, *command], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                       env=dict(os.environ, PATH=d + ":" + os.environ["PATH"], HOME=d))
    return p, (open(f"{d}/LOG").read() if os.path.exists(f"{d}/LOG") else "")


TAGS = ["v0.3.0-beta.8", "v0.3.0-beta.24", "v0.3.0-beta.23", "v0.2.9", "v0.3.0-beta.24^{}", "not-a-version"]
with tempfile.TemporaryDirectory() as d:
    p, log = provisioner(d, TAGS)
    assert p.returncode == 0, p.stdout
    # beta.24 is above beta.8 (a plain sort puts 8 last) and above the older plain 0.2.9
    assert "/releases/download/v0.3.0-beta.24/RK3326-Provisioner-0.3.0-beta.24.tar.gz" in log, log
    assert "installer ran" in log and "The Provisioner is now 0.3.0-beta.24" in p.stdout, p.stdout
    v = subprocess.run(["bash", RK_APPS, "versions"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                       env=dict(os.environ, PATH=d + ":" + os.environ["PATH"], HOME=d)).stdout
    assert "provisioner|Provisioner|0.3.0-beta.24|0.3.0-beta.24\n" in v, v
# a plain release ranks above the same version with a suffix
with tempfile.TemporaryDirectory() as d:
    p, log = provisioner(d, ["v0.3.0-beta.24", "v0.3.0", "v0.3.0-rc.1"], command=("versions",))
    assert "provisioner|Provisioner|-|0.3.0\n" in p.stdout, p.stdout
# a download that does not match its checksum is not installed
with tempfile.TemporaryDirectory() as d:
    p, log = provisioner(d, TAGS, sums_ok=False)
    assert p.returncode == 1 and "does not match its checksum" in p.stdout, p.stdout
    assert "installer ran" not in log and not os.path.exists(f"{d}/rk3326_provisioner"), log
# no tags (offline, or the repository moved): said plainly, nothing fetched
with tempfile.TemporaryDirectory() as d:
    p, log = provisioner(d, [])
    assert p.returncode == 1 and "could not find a Provisioner release" in p.stdout and "curl" not in log, p.stdout

# ---------------------------------------------------------------- packages
# An app that is not the system's comes as a package: a .zip with VERSION,
# deploy/install.sh and deploy/<id>.json. rk-pkg lists the ones in the
# packages folder, runs a package's installer, notes what it added for root,
# and takes all of it off again. The system's files are not touched.
import json
import sys
import zipfile
RK_PKG = os.path.join(os.path.dirname(RK_APPS), "rk-pkg")


def make_package(path, app="demo-app", version="1.0.0", name="Demo App", wrap="", extra=None, leave_out=(), installer=None):
    """A package as a team would hand it over. Its installer puts the app in
    ~/demo, a helper in the first watched root folder, and saves data."""
    installer = installer or (
        'set -e\nsrc=$(cd "$(dirname "$0")/.." && pwd)\n'
        'mkdir -p "$HOME/demo" "$DEMO_DATA"\ncp "$src/host/run.sh" "$HOME/demo/run.sh"\ncp "$src/VERSION" "$HOME/demo/VERSION"\n'
        'echo saved > "$DEMO_DATA/capture.txt"\n'
        'if [ "$(id -u)" -eq 0 ]; then cp "$src/host/helper" "$DEMO_ROOT/rk-demo-helper"\n'
        'elif sudo -n true; then sudo cp "$src/host/helper" "$DEMO_ROOT/rk-demo-helper"; else echo "no root: helper skipped"; fi\n')
    files = {"VERSION": version + "\n", "deploy/install.sh": installer, "host/run.sh": "#!/bin/sh\n", "host/helper": "#!/bin/sh\n",
             f"deploy/{app}.json": json.dumps({"name": name, "exec": ["/home/ark/demo/run.sh"]})}
    files.update(extra or {})
    with zipfile.ZipFile(path, "w") as z:
        for f, text in files.items():
            if f not in leave_out:
                z.writestr(wrap + f, text)


def pkg(d, *command, askpass=True):
    """Run rk-pkg (through rk-apps when asked as it is from the desktop) in a made-up handheld under d."""
    for sub in ("packages", "dock", "home", "root-sbin", "sudoers", "data", "bin", "system-dock"):
        os.makedirs(f"{d}/{sub}", exist_ok=True)
    # sudo: note how it was asked, then do it (the test is whoever runs it)
    open(f"{d}/bin/sudo", "w").write(f'#!/bin/sh\necho "sudo $*" >> {d}/SUDO\nwhile [ "$1" = -A ] || [ "$1" = -n ]; do shift; done\nexec "$@"\n')
    os.chmod(f"{d}/bin/sudo", 0o755)
    env = dict(os.environ, PATH=f"{d}/bin:" + os.environ["PATH"], HOME=f"{d}/home", RK_PKG_DIR=f"{d}/packages",
               RK_PKG_DOCK=f"{d}/dock", RK_PKG_SYSTEM_DOCK=f"{d}/system-dock", RK_PKG_ROOT_DIRS=f"{d}/root-sbin:{d}/sudoers",
               DEMO_ROOT=f"{d}/root-sbin", DEMO_DATA=f"{d}/data")
    env.pop("SUDO_ASKPASS", None)
    if askpass:
        env["SUDO_ASKPASS"] = "/bin/true"
    p = subprocess.run(list(command), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, stdin=subprocess.DEVNULL)
    return p


with tempfile.TemporaryDirectory() as d:
    os.makedirs(f"{d}/packages")
    exe = f"{d}/home/demo/run.sh"
    entry = lambda: {"deploy/demo-app.json": json.dumps({"name": "Demo App", "group": "Comms", "exec": [exe]})}
    make_package(f"{d}/packages/demo-app-1.0.0.zip", extra=entry())
    make_package(f"{d}/packages/demo-app-1.0.10.zip", version="1.0.10", extra=entry(), wrap="demo-app-1.0.10/")   # a zip made of a folder
    make_package(f"{d}/packages/demo-app-1.0.9.zip", version="1.0.9", extra=entry())
    open(f"{d}/packages/holiday-photos.zip", "w").write("not a zip")
    make_package(f"{d}/packages/no-version.zip", app="other", leave_out=("VERSION",))
    # listed: the highest version of an app (1.0.10 is above 1.0.9), and why a zip is not a package
    p = pkg(d, "bash", RK_APPS, "packages")
    assert p.returncode == 0, p.stdout
    assert "pkg|demo-app|Demo App|-|1.0.10|root|demo-app-1.0.10.zip\n" in p.stdout, p.stdout
    assert "bad|holiday-photos.zip|not a zip file\n" in p.stdout and "bad|no-version.zip|no VERSION file\n" in p.stdout, p.stdout
    # installed, as the desktop does it (no terminal, the password through askpass): the
    # installer's "sudo -n" and its plain "sudo" both ask through askpass, so its root step is done
    p = pkg(d, "bash", RK_APPS, "package-install", "demo-app")
    assert p.returncode == 0 and "Demo App is now 1.0.10." in p.stdout, p.stdout
    assert os.access(exe, os.X_OK), "the app's program is not executable"
    assert json.load(open(f"{d}/dock/demo-app.json"))["name"] == "Demo App", "no dock entry"
    assert os.path.exists(f"{d}/root-sbin/rk-demo-helper"), p.stdout
    if os.geteuid() != 0:
        asked = open(f"{d}/SUDO").read()
        assert "sudo -A true" in asked and "sudo -A cp " in asked and "sudo -n" not in asked, asked
    rec = json.load(open(f"{d}/dock/.packages/demo-app.json"))
    assert rec["version"] == "1.0.10" and rec["root_files"] == [f"{d}/root-sbin/rk-demo-helper"], rec
    assert os.path.realpath(rec["app_dir"]) == os.path.realpath(f"{d}/home/demo"), rec
    assert f"added for root: {d}/root-sbin/rk-demo-helper" in p.stdout, p.stdout
    assert "pkg|demo-app|Demo App|1.0.10|1.0.10|root|demo-app-1.0.10.zip\n" in pkg(d, sys.executable, RK_PKG, "list").stdout
    # nothing of the system's changed, and the unpacked copy is gone
    assert os.listdir(f"{d}/system-dock") == [] and os.listdir(f"{d}/sudoers") == []
    # installed again (an update): the helper is still noted, though it was already there
    p = pkg(d, sys.executable, RK_PKG, "install", f"{d}/packages/demo-app-1.0.9.zip")
    assert p.returncode == 0 and "is now 1.0.9" in p.stdout, p.stdout
    assert json.load(open(f"{d}/dock/.packages/demo-app.json"))["root_files"] == [f"{d}/root-sbin/rk-demo-helper"]
    # removed: its files, its dock entry, what it added for root; its data stays
    open(f"{d}/root-sbin/rk-wifi", "w").close()                 # the system's own, not this app's
    p = pkg(d, "bash", RK_APPS, "package-remove", "demo-app")
    assert p.returncode == 0 and "Demo App is removed" in p.stdout, p.stdout
    assert not os.path.exists(f"{d}/home/demo") and not os.path.exists(f"{d}/dock/demo-app.json"), p.stdout
    assert not os.path.exists(f"{d}/root-sbin/rk-demo-helper") and os.path.exists(f"{d}/root-sbin/rk-wifi")
    assert open(f"{d}/data/capture.txt").read() == "saved\n" and os.path.isdir(f"{d}/home")
    assert "pkg|demo-app|Demo App|-|1.0.10|" in pkg(d, sys.executable, RK_PKG, "list").stdout
    assert pkg(d, sys.executable, RK_PKG, "remove", "demo-app").returncode == 1
    # a registry entry cannot be made to remove a file from somewhere else, or the home folder
    os.makedirs(f"{d}/dock/.packages", exist_ok=True)
    open(f"{d}/keep", "w").close()
    json.dump({"name": "Trick", "root_files": [f"{d}/keep", f"{d}/root-sbin/../keep", "/etc/passwd"], "app_dir": f"{d}/home"},
              open(f"{d}/dock/.packages/trick.json", "w"))
    p = pkg(d, sys.executable, RK_PKG, "remove", "trick")
    assert p.returncode == 0 and os.path.exists(f"{d}/keep") and os.path.isdir(f"{d}/home") and os.path.exists("/etc/passwd"), p.stdout
    # an installer that fails: said, nothing registered, no dock entry
    make_package(f"{d}/packages/broken-2.0.zip", app="broken", version="2.0", installer="echo cannot; exit 3\n")
    p = pkg(d, sys.executable, RK_PKG, "install", "broken")
    assert p.returncode == 1 and "its installer stopped" in p.stdout and not os.path.exists(f"{d}/dock/broken.json"), p.stdout
    # an installer that ends well but leaves no program: not called installed
    make_package(f"{d}/packages/empty-1.zip", app="empty", version="1", installer="true\n",
                 extra={"deploy/empty.json": json.dumps({"name": "Empty", "exec": [f"{d}/home/nowhere/run.sh"]})})
    p = pkg(d, sys.executable, RK_PKG, "install", "empty")
    assert p.returncode == 1 and "program is not there" in p.stdout and not os.path.exists(f"{d}/dock/.packages/empty.json"), p.stdout

# what is refused before anything is unpacked
with tempfile.TemporaryDirectory() as d:
    os.makedirs(f"{d}/packages"); os.makedirs(f"{d}/system-dock")
    make_package(f"{d}/packages/a.zip", app="escape", extra={"../outside.txt": "x"})
    make_package(f"{d}/packages/b.zip", app="firefly")                      # an app of the system's own
    open(f"{d}/system-dock/games2.json", "w").write("{}")
    make_package(f"{d}/packages/c.zip", app="games2")                       # an entry the image carries
    make_package(f"{d}/packages/d.zip", app="Bad Name")
    make_package(f"{d}/packages/e.zip", app="two", extra={"deploy/second.json": "{}"})
    make_package(f"{d}/packages/f.zip", app="noentry", extra={"deploy/noentry.json": "{not json"})
    make_package(f"{d}/packages/g.zip", app="ver", version="latest; reboot")
    with zipfile.ZipFile(f"{d}/packages/h.zip", "w") as z:                  # a symbolic link inside
        make = zipfile.ZipInfo("VERSION"); z.writestr(make, "1.0\n")
        z.writestr("deploy/install.sh", "true\n"); z.writestr("deploy/link.json", json.dumps({"name": "L", "exec": ["x"]}))
        link = zipfile.ZipInfo("host/passwd"); link.external_attr = 0o120777 << 16; z.writestr(link, "/etc/passwd")
    out = pkg(d, sys.executable, RK_PKG, "list").stdout
    for f, why in (("a.zip", "points outside"), ("b.zip", "system's own"), ("c.zip", "system's own"), ("d.zip", "usable id"),
                   ("e.zip", "more than one"), ("f.zip", "not valid"), ("g.zip", "not a version"), ("h.zip", "symbolic link")):
        assert any(ln.startswith(f"bad|{f}|") and why in ln for ln in out.splitlines()), (f, out)
    assert "pkg|" not in out, out
    for f in "abcdefgh":
        p = pkg(d, sys.executable, RK_PKG, "install", f"{d}/packages/{f}.zip")
        assert p.returncode == 1 and "is not a package" in p.stdout, p.stdout
    assert not os.path.exists(f"{d}/outside.txt") and not os.path.exists(f"{d}/dock/.packages")

# The AppManager window and packages: a package row says what A does; A asks
# before running an installer nobody checked; Y removes; a zip that is not
# a package is shown with the reason.
sys.path.insert(0, os.path.join(HERE, ".."))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
from rkshell import system as rksystem
from rkshell.pages.apps import AppsPage
rows = rksystem.parse_packages("pkg|demo-app|Demo App|1.0.9|1.0.10|root|demo-app-1.0.10.zip\n"
                               "pkg|plain|Plain|-|2.0|-|plain.zip\npkg|old|Old|3.1|-|-|-\nbad|photos.zip|not a zip file\nnoise\n")
assert [r.get("id") for r in rows] == ["demo-app", "plain", "old", ""] and rows[0]["root"] and not rows[1]["root"], rows


class _Sys:
    def __init__(self): self.calls, self.net = [], False
    def online(self): return self.net
    def password_expired(self): return False
    def package_install(self, app, pw, old=None): self.calls.append(("install", app, pw)); return "job"
    def package_remove(self, app, pw): self.calls.append(("remove", app, pw)); return "job"
    def app_update(self, app, pw, old=None): self.calls.append(("update", app, pw)); return "job"


class _App:
    def __init__(self): self.system, self.toasts, self.asked, self.keys = _Sys(), [], [], []
    def toast(self, text, *a, **k): self.toasts.append(text)
    def confirm(self, title, detail, label, on_yes): self.asked.append((title, detail, label, on_yes))
    def push(self, screen): self.keys.append(screen)


import rkshell.pages.apps as apps_page
apps_page.Keyboard = lambda app, title, go, **k: go          # "typing" is calling it
assert AppsPage.title == "AppManager"
page = AppsPage.__new__(AppsPage)
page.app, page.apps, page.sel, page.check, page.view = _App(), rows, 0, None, "list"
assert page.state(rows[0])[::2] == ("1.0.9  →  1.0.10", True) and page.state(rows[1])[0] == "package 2.0  (A installs)"
assert page.state(rows[2])[::2] == ("3.1  from a package", False) and "not a zip file" in page.state(rows[3])[0]
page.update(rows[0])                                        # A: asked first, nothing run yet, and no Wi-Fi needed
title, detail, label, yes = page.app.asked[-1]
assert title == "Install Demo App?" and "demo-app-1.0.10.zip" in detail and "as root" in detail and not page.app.system.calls
yes(); page.app.keys[-1]("secret")
assert page.app.system.calls == [("install", "demo-app", "secret")] and AppsPage.job_kind == "install" and page.view == "running"
page.view = "list"
page.update(rows[1])
assert "as root" not in page.app.asked[-1][1]               # a package whose installer has no root steps does not say so
page.sel = 0
assert ("Y", "remove") in page.hints
page.handle("y")
assert page.app.asked[-1][0] == "Remove Demo App?"
page.app.asked[-1][3](); page.app.keys[-1]("secret")
assert page.app.system.calls[-1] == ("remove", "demo-app", "secret") and AppsPage.job_kind == "remove"
page.view, page.sel = "list", 1
assert ("Y", "remove") not in page.hints                    # not installed: nothing to remove
before = len(page.app.asked)
page.handle("y"); page.update(rows[2]); page.update(rows[3])
assert len(page.app.asked) == before and len(page.app.toasts) == 2, page.app.toasts
# the system's own apps still want Wi-Fi
page.update({"id": "provisioner", "name": "Provisioner", "installed": "-", "newest": "0.3.0"})
assert page.app.toasts[-1] == "Join Wi-Fi first"
AppsPage.job, AppsPage.job_kind = None, "update"

# The dock: an app's installer may have left an entry on /data before the
# image carried one of the same file name. The image's is kept: no icon twice.
with tempfile.TemporaryDirectory() as d:
    os.makedirs(f"{d}/image"); os.makedirs(f"{d}/data")
    json.dump({"name": "Provisioner", "exec": ["sh"], "about": "the image's"}, open(f"{d}/image/provisioner.json", "w"))
    json.dump({"name": "Provisioner", "exec": ["sh"], "about": "left on /data"}, open(f"{d}/data/provisioner.json", "w"))
    json.dump({"name": "Mine", "exec": ["sh"]}, open(f"{d}/data/mine.json", "w"))
    old, rksystem.APPS_DIRS = rksystem.APPS_DIRS, [f"{d}/image", f"{d}/data"]
    try:
        found = rksystem.System.apps(None)
    finally:
        rksystem.APPS_DIRS = old
    assert [(a["name"], a.get("about")) for a in found] == [("Provisioner", "the image's"), ("Mine", None)], found
print("apps: ok")
