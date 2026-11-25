"""Adding the kernel modules the image carries to a card that was updated and
not flashed again (rk-tools kernel-modules), with a stand-in for the card.

    python3 tests/test_kmods.py              made-up modules, a stand-in depmod
    python3 tests/test_kmods.py KMODS_OUT    the bundle build-kernel-modules.sh made, the real depmod
"""
import glob
import hashlib
import io
import os
import subprocess
import sys
import tarfile
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RK_TOOLS = os.path.normpath(os.path.join(HERE, "..", "..", "overlay", "usr", "local", "sbin", "rk-tools"))
K510, K44 = "5.10.252-arkos4clone", "4.4.189"
CH341 = f"{K510}/kernel/drivers/usb/serial/ch341.ko"


def module(release, body=b"made up"):
    return b"\x7fELF" + body + b"\0vermagic=" + release.encode() + b" SMP mod_unload aarch64\0"


def bundle(path, files):
    """A rk-kernel-modules-<n>.tar.xz holding `files` ({name: bytes}), and its .sha256."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    open(path, "wb").write(buf.getvalue())
    open(path + ".sha256", "w").write(hashlib.sha256(buf.getvalue()).hexdigest() + "  " + os.path.basename(path) + "\n")


def card(d, stub_depmod=True):
    """A card's /usr/lib/modules with both kernels, as an update finds it: no ch341."""
    for release in (K510, K44):
        os.makedirs(f"{d}/usr/lib/modules/{release}/kernel/drivers/usb/serial")
        open(f"{d}/usr/lib/modules/{release}/kernel/drivers/usb/serial/cp210x.ko", "wb").write(module(release, b"the kernel's own"))
    os.makedirs(f"{d}/bin")
    open(f"{d}/want", "w").write("1\n")
    open(f"{d}/bin/ip", "w").write("#!/bin/sh\necho 'default via 10.0.0.1 dev wlan0'\n")
    if stub_depmod:
        open(f"{d}/bin/depmod", "w").write(f'#!/bin/sh\necho "depmod $*" >> {d}/LOG\n')
    for tool in os.listdir(f"{d}/bin"):
        os.chmod(f"{d}/bin/{tool}", 0o755)


def run(d, *args, online=True):
    env = dict(os.environ, PATH=(f"{d}/bin:" if online else f"{d}/offline:") + os.environ["PATH"],
               RK_KMOD_DIR=f"{d}/usr/lib/modules", RK_KMOD_WANT=f"{d}/want", RK_KMOD_BASE=f"file://{d}/release")
    if not online:                      # the same stand-ins, and an ip that shows no route
        os.makedirs(f"{d}/offline", exist_ok=True)
        open(f"{d}/offline/ip", "w").write("#!/bin/sh\n")
        os.chmod(f"{d}/offline/ip", 0o755)
    p = subprocess.run(["bash", RK_TOOLS, "kernel-modules", *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    return p.returncode, p.stdout


def tree(d):
    return sorted(os.path.relpath(f, f"{d}/usr/lib/modules") for f in glob.glob(f"{d}/usr/lib/modules/**/*", recursive=True) if os.path.isfile(f))


if len(sys.argv) > 1:
    # the real bundle: it installs, and the real depmod lists the driver for the CH340 (1a86:7523)
    real = glob.glob(os.path.join(sys.argv[1], "rk-kernel-modules-*.tar.xz"))
    assert len(real) == 1, real
    with tempfile.TemporaryDirectory() as d:
        card(d, stub_depmod=False)
        open(f"{d}/want", "w").write(os.path.basename(real[0]).split("-")[-1].split(".")[0] + "\n")
        rc, out = run(d, real[0])
        assert rc == 0 and f"added ch341.ko to kernel {K510}" in out, out
        alias = open(f"{d}/usr/lib/modules/{K510}/modules.alias").read()
        assert "usb:v1A86p7523" in alias and "ch341" in alias, alias
        assert not os.path.exists(f"{d}/usr/lib/modules/{K44}/kernel/drivers/usb/serial/ch341.ko")
    print("kmods (the real bundle): ok")
    sys.exit(0)

# after an update: fetched from the release, checked, added, listed; the kernel's own files as they were
with tempfile.TemporaryDirectory() as d:
    card(d)
    os.makedirs(f"{d}/release")
    bundle(f"{d}/release/rk-kernel-modules-1.tar.xz", {CH341: module(K510)})
    before = {f: open(f"{d}/usr/lib/modules/{f}", "rb").read() for f in tree(d)}
    rc, out = run(d, "--auto")
    assert rc == 0 and f"added ch341.ko to kernel {K510}" in out, out
    assert tree(d) == sorted(list(before) + [CH341, "rk-kernel-modules.bundle"]), tree(d)
    assert all(open(f"{d}/usr/lib/modules/{f}", "rb").read() == data for f, data in before.items()), "a kernel file changed"
    assert open(f"{d}/LOG").read() == f"depmod -b {d}/usr {K510}\n", open(f"{d}/LOG").read()
    assert open(f"{d}/usr/lib/modules/rk-kernel-modules.bundle").read() == f"bundle 1\n{CH341}\n"
    # the next start: nothing to do, nothing said, nothing fetched
    os.remove(f"{d}/release/rk-kernel-modules-1.tar.xz")
    rc, out = run(d, "--auto")
    assert (rc, out) == (0, ""), out
    # a later bundle replaces what the earlier one put there
    open(f"{d}/want", "w").write("2\n")
    bundle(f"{d}/release/rk-kernel-modules-2.tar.xz", {CH341: module(K510, b"a newer build")})
    rc, out = run(d, "--auto")
    assert rc == 0 and open(f"{d}/usr/lib/modules/{CH341}", "rb").read() == module(K510, b"a newer build"), out
    assert open(f"{d}/usr/lib/modules/rk-kernel-modules.bundle").read() == f"bundle 2\n{CH341}\n"

# a module the kernel's own build put there is never replaced
with tempfile.TemporaryDirectory() as d:
    card(d)
    own = f"{K510}/kernel/drivers/usb/serial/cp210x.ko"
    bundle(f"{d}/b.tar.xz", {own: module(K510, b"ours"), CH341: module(K510)})
    rc, out = run(d, f"{d}/b.tar.xz")
    assert rc == 0 and "left alone" in out, out
    assert open(f"{d}/usr/lib/modules/{own}", "rb").read() == module(K510, b"the kernel's own")
    assert open(f"{d}/usr/lib/modules/rk-kernel-modules.bundle").read() == f"bundle 1\n{CH341}\n"

# refused whole, with the card as it was: a module for another kernel, a file that is no module,
# a path that leaves the folder, a download that does not match its checksum
for what, files in (("another kernel", {CH341: module("5.10.999-other")}),
                    ("no module", {CH341: module(K510), f"{K510}/modules.dep": b"x"}),
                    ("leaves the folder", {f"{K510}/kernel/../../../../etc/x.ko": module(K510)}),
                    ("checksum", {CH341: module(K510)})):
    with tempfile.TemporaryDirectory() as d:
        card(d)
        before = tree(d)
        bundle(f"{d}/b.tar.xz", files)
        if what == "checksum":
            open(f"{d}/b.tar.xz.sha256", "w").write("0" * 64 + "  b.tar.xz\n")
        rc, out = run(d, f"{d}/b.tar.xz")
        assert rc != 0 and "nothing changed" in out, (what, out)
        assert tree(d) == before and not os.path.exists(f"{d}/LOG") and not os.path.exists(f"{d}/etc"), (what, tree(d))

# a card on kernels the bundle has nothing for: said once, then left alone
with tempfile.TemporaryDirectory() as d:
    card(d)
    bundle(f"{d}/b.tar.xz", {f"6.1.0-other/kernel/drivers/usb/serial/ch341.ko": module("6.1.0-other")})
    rc, out = run(d, f"{d}/b.tar.xz")
    assert rc == 0 and "nothing for this card's kernels" in out and not os.path.exists(f"{d}/LOG"), out

# not published yet, or no network: an update goes on; asked for by hand, it says why
with tempfile.TemporaryDirectory() as d:
    card(d)
    rc, out = run(d, "--auto")                       # the release has no such file
    assert rc == 0 and "were not added" in out, out
    rc, out = run(d, "--auto", online=False)
    assert (rc, out) == (0, ""), out
    rc, out = run(d, online=False)
    assert rc == 1 and "not online" in out, out
print("kmods: ok")
