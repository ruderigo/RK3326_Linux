"""Look before installing: room, memory, and what apt says a package costs.

Runs the real scripts (overlay/usr/lib/rk/preflight.sh and the installers
that source it) with made-up measurements, and stand-ins for apt.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OVERLAY = os.path.normpath(os.path.join(HERE, "..", "..", "overlay"))
LIB = os.path.join(OVERLAY, "usr", "lib", "rk", "preflight.sh")
SBIN = os.path.join(OVERLAY, "usr", "local", "sbin")
sys.path.insert(0, os.path.join(HERE, ".."))


def sh(script, **env):
    p = subprocess.run(["bash", "-c", f'RK_WHO=test; . "{LIB}"\n{script}'], env=dict(os.environ, **env),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.returncode, p.stdout


# ---- room
rc, out = sh('rk_need_space 200 / "the video player"', RK_PREFLIGHT_FREE_MB="180")
assert rc == 1 and "180 MB free" in out and "about 200 MB" in out and "nothing was changed" in out, out
rc, out = sh('rk_need_space 200 / "the video player"', RK_PREFLIGHT_FREE_MB="200")
assert rc == 0 and out == "", out
rc, out = sh("rk_free_mb /no/such/folder/yet")           # a folder not made yet: its parent's room
assert rc == 0 and out.strip().isdigit(), out

# ---- memory
rc, out = sh('rk_need_mem 100 "installing firefly"', RK_PREFLIGHT_MEM_MB="64")
assert rc == 1 and "64 MB to spare" in out and "nothing was changed" in out, out
rc, out = sh('rk_need_mem 100 x', RK_PREFLIGHT_MEM_MB="640")
assert rc == 0 and out == "", out
rc, out = sh("rk_mem_mb")
assert rc == 0 and out.strip().isdigit(), out

# ---- what apt says: two packages to fetch, 1.5 MB + 40 MB down, 6 MB + 120 MB unpacked
with tempfile.TemporaryDirectory() as d:
    open(f"{d}/apt-get", "w").write("""#!/bin/sh
echo "Reading package lists..."
echo "'http://deb.debian.org/debian/pool/main/m/mpv/mpv_0.40.0-3_arm64.deb' mpv_0.40.0-3_arm64.deb 1572864 SHA256:aa"
echo "'http://deb.debian.org/debian/pool/main/f/ffmpeg/libavcodec61_7.1.1-1%2bb1_arm64.deb' libavcodec61_7.1.1-1+b1_arm64.deb 41943040 SHA256:bb"
""")
    open(f"{d}/apt-cache", "w").write("""#!/bin/sh
for a in "$@"; do case $a in mpv) echo "Package: mpv"; echo "Installed-Size: 6144"; echo;; libavcodec61) echo "Package: libavcodec61"; echo "Installed-Size: 122880"; echo;; esac; done
""")
    os.chmod(f"{d}/apt-get", 0o755); os.chmod(f"{d}/apt-cache", 0o755)
    path = d + ":" + os.environ["PATH"]
    rc, out = sh("rk_apt_cost mpv", PATH=path)
    assert out.split() == ["42", "126"], out
    rc, out = sh('rk_need_apt "the video player" mpv', PATH=path, RK_PREFLIGHT_FREE_MB="150")
    assert rc == 1 and "42 MB to download" in out and "126 MB once installed" in out and "150 MB free" in out, out
    rc, out = sh('rk_need_apt "the video player" mpv', PATH=path, RK_PREFLIGHT_FREE_MB="900")
    assert rc == 0 and "nothing was changed" not in out, out
    # apt that cannot answer (no lists, no network) must not stop the work
    open(f"{d}/apt-get", "w").write("#!/bin/sh\nexit 100\n")
    rc, out = sh('rk_need_apt "x" mpv', PATH=path, RK_PREFLIGHT_FREE_MB="1")
    assert rc == 0, out

# ---- the installers stop before fetching anything
for script, args in (("rk-apps", ["update", "firefly"]), ("rk-apps", ["install", "all"])):
    with tempfile.TemporaryDirectory() as d:
        open(f"{d}/ip", "w").write("#!/bin/sh\necho 'default via 10.0.0.1 dev wlan0'\n")
        open(f"{d}/curl", "w").write(f"#!/bin/sh\ntouch {d}/FETCHED\nexit 1\n")
        open(f"{d}/git", "w").write(f"#!/bin/sh\ntouch {d}/FETCHED\nexit 1\n")
        for n in ("ip", "curl", "git"):
            os.chmod(f"{d}/{n}", 0o755)
        p = subprocess.run(["bash", os.path.join(SBIN, script)] + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                           env=dict(os.environ, PATH=d + ":" + os.environ["PATH"], HOME=d, RK_PREFLIGHT_FREE_MB="20"))
        assert p.returncode == 1 and "not enough room" in p.stdout, p.stdout
        assert not os.path.exists(f"{d}/FETCHED"), f"{script} {args} fetched before looking at the room"

# ---- with room, every step of an install is there to run (a network that answers nothing: each app says so)
with tempfile.TemporaryDirectory() as d:
    open(f"{d}/ip", "w").write("#!/bin/sh\necho 'default via 10.0.0.1 dev wlan0'\n")
    open(f"{d}/curl", "w").write("#!/bin/sh\nexit 22\n")
    open(f"{d}/git", "w").write("#!/bin/sh\nexit 1\n")
    for n in ("ip", "curl", "git"):
        os.chmod(f"{d}/{n}", 0o755)
    for args in (["install", "all"], ["update", "all"], ["versions"]):
        p = subprocess.run(["bash", os.path.join(SBIN, "rk-apps")] + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                           env=dict(os.environ, PATH=d + ":" + os.environ["PATH"], HOME=d, RK_PREFLIGHT_FREE_MB="9000", RK_PREFLIGHT_MEM_MB="900"))
        assert "command not found" not in p.stdout and "syntax error" not in p.stdout, f"rk-apps {args}:\n{p.stdout}"

# ---- a Stump update takes the files from the source chosen in Apps, then runs the installer
for source, repo in (("sandbox", "SandBox_RK3326_Stump"), ("stable", "R36MAX-Stump")):
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(f"{d}/R36MAX-Stump/.git"); os.makedirs(f"{d}/R36MAX-Stump/handheld"); os.makedirs(f"{d}/Stump"); os.makedirs(f"{d}/.config")
        open(f"{d}/Stump/stump_pc.py", "w").close()
        open(f"{d}/.config/rk-apps", "w").write(f"STUMP_SOURCE={source}\n")
        open(f"{d}/R36MAX-Stump/handheld/VERSION", "w").write("2.7.4-b.87\n")
        # the installer, as it is: its own pull has already happened (or quietly failed) by now
        open(f"{d}/R36MAX-Stump/handheld/install.sh", "w").write(f'echo "installer $(cat {d}/R36MAX-Stump/handheld/VERSION)" >> {d}/LOG\n')
        open(f"{d}/ip", "w").write("#!/bin/sh\necho 'default via 10.0.0.1 dev wlan0'\n")
        # git: note what was asked; "reset" is the moment the new files are there
        open(f"{d}/git", "w").write(f"""#!/bin/sh
echo "git $*" >> {d}/LOG
case "$*" in *reset*) echo 2.7.6-b.88 > {d}/R36MAX-Stump/handheld/VERSION ;; esac
""")
        os.chmod(f"{d}/ip", 0o755); os.chmod(f"{d}/git", 0o755)
        p = subprocess.run(["bash", os.path.join(SBIN, "rk-apps"), "update", "stump"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                           env=dict(os.environ, PATH=d + ":" + os.environ["PATH"], HOME=d, RK_PREFLIGHT_FREE_MB="170", RK_PREFLIGHT_MEM_MB="300"))
        log = open(f"{d}/LOG").read()
        assert p.returncode == 0, p.stdout
        assert f"git remote set-url origin https://github.com/ruderigo/{repo}" in log, log
        assert log.index("reset --hard") < log.index("installer 2.7.6-b.88"), "the installer ran on the old files:\n" + log
        assert "Stump is now 2.7.6-b.88" in p.stdout, p.stdout

# ---- the updater: room first, and old backups do not pile up
RK_UPDATE = os.path.join(SBIN, "rk-update")
with tempfile.TemporaryDirectory() as root:
    os.makedirs(f"{root}/usr/lib/python3/dist-packages/rkshell")
    os.makedirs(f"{root}/data/ark/.rk-backups")
    for stamp in ("20261101T000000Z", "20261102T000000Z", "20261103T000000Z", "20261104T000000Z", "20261105T000000Z"):
        os.makedirs(f"{root}/data/ark/.rk-backups/{stamp}/files")
    body = f'RK_UPDATE_SOURCE=1 RK_ROOT="{root}" source "{RK_UPDATE}"\n'
    p = subprocess.run(["bash", "-c", body + "prune_backups; ls $BK_DIR"], stdout=subprocess.PIPE, text=True, env=dict(os.environ, RK_ROOT=root))
    assert p.stdout.split() == ["20261103T000000Z", "20261104T000000Z", "20261105T000000Z"], p.stdout
    p = subprocess.run(["bash", "-c", body + "room"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                       env=dict(os.environ, RK_ROOT=root, RK_PREFLIGHT_FREE_MB="3"))
    assert p.returncode == 1 and "not enough room" in p.stdout, p.stdout
    p = subprocess.run(["bash", "-c", body + "room"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                       env=dict(os.environ, RK_ROOT=root, RK_PREFLIGHT_FREE_MB="900", RK_PREFLIGHT_MEM_MB="300"))
    assert p.returncode == 0, p.stdout

# ---- an update never writes over a script that is running (the updater itself is one of them)
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
with tempfile.TemporaryDirectory() as root:
    os.makedirs(f"{root}/usr/lib/python3/dist-packages")
    os.makedirs(f"{root}/usr/local/sbin")
    old = f"{root}/usr/local/sbin/rk-update"
    open(old, "w").write("# the version that is running\n")
    held = open(old)                                # as bash holds the script it is reading
    body = f'RK_UPDATE_SOURCE=1 RK_ROOT="{root}" source "{RK_UPDATE}"\ninstall_soft "{REPO}"'
    p = subprocess.run(["bash", "-c", body], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=dict(os.environ, RK_ROOT=root))
    assert p.returncode == 0, p.stdout
    assert held.read() == "# the version that is running\n", "the running updater was written over"
    assert open(old).read() == open(RK_UPDATE).read(), "the new updater is not in place"
    held.close()
assert open(RK_UPDATE).read().rstrip().splitlines()[-1].startswith("esac; exit"), "rk-update must not read on after its work"

# ---- the settings files: put in place once, the same on a second run
with tempfile.TemporaryDirectory() as root:
    os.makedirs(f"{root}/usr/share/rk")
    subprocess.run(["cp", "-r", os.path.join(OVERLAY, "usr", "share", "rk", "sysconf"), f"{root}/usr/share/rk/"], check=True)
    run = lambda: subprocess.run(["bash", os.path.join(SBIN, "rk-sysconf"), root], stdout=subprocess.PIPE, text=True).stdout
    first = run()
    assert os.path.isfile(f"{root}/etc/systemd/journald.conf.d/rk.conf") and os.path.isfile(f"{root}/etc/sysctl.d/30-rk-memory.conf")
    assert os.path.isfile(f"{root}/etc/apt/apt.conf.d/90rk") and os.path.islink(f"{root}/etc/systemd/system/apt-daily.timer")
    assert "0 changed" not in first and "0 changed" in run(), "the second run changed something"

# ---- the desktop says so when room or memory runs short
from rkshell import system

MB = 1024 * 1024
full = [{"label": "System", "mount": "/", "used": 2900 * MB, "total": 2960 * MB},
        {"label": "Data", "mount": "/data", "used": 1000 * MB, "total": 83000 * MB}]
assert [k for k, _ in system.health_warnings(full, 400)] == ["system"]
assert "60 MB free" in system.health_warnings(full, 400)[0][1]
assert [k for k, _ in system.health_warnings(full[1:], 20)] == ["memory"]
assert system.health_warnings(full[1:], None) == []
print("test_preflight: ok")
