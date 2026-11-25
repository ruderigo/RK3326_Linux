"""Updating a dock app from the Apps window (overlay/usr/local/sbin/rk-apps),
with stand-ins for git and the network."""
import os
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RK_APPS = os.path.normpath(os.path.join(HERE, "..", "..", "overlay", "usr", "local", "sbin", "rk-apps"))

# a Stump update takes the files from the source chosen in Apps, then runs the installer
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

# The dock: an app's installer may have left an entry on /data before the
# image carried one of the same file name. The image's is kept: no icon twice.
import json
import sys
sys.path.insert(0, os.path.join(HERE, ".."))
from rkshell import system as rksystem
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
