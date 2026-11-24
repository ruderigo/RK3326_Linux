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
print("apps: ok")
