"""The boot logo: bootlogo.py makes it for every panel, at build time and once on an updated card.

Runs the real program on a made-up boot partition: stock logos of each size
(plain colour), the list of turns from the overlay, and our picture.
"""
import os
import struct
import subprocess
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

HERE = os.path.dirname(os.path.abspath(__file__))
OVERLAY = os.path.normpath(os.path.join(HERE, "..", "..", "overlay"))
PROG = os.path.join(OVERLAY, "usr", "lib", "rk", "bootlogo.py")
SHARE = os.path.join(OVERLAY, "usr", "share", "rk", "boot-logo")
ENV = dict(os.environ, RK_BOOTLOGO_DIR=SHARE)
SIZES = {"320P": (320, 481), "480P": (640, 480), "480P-1": (480, 640), "480P-270": (480, 640), "480P5-3": (480, 800),
         "540P": (720, 540), "720P": (720, 720), "720x1280P": (720, 1280), "720x1280P-90": (720, 1280),
         "768P": (1024, 768), "854x480P": (480, 854)}


def head(path):
    b = open(path, "rb").read(34)
    w, h, _, bpp, comp = struct.unpack("<iiHHI", b[18:34])
    return b[:2], (w, h), bpp, comp


def stock(path, size):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    s = pygame.Surface(size, depth=24)
    s.fill((255, 128, 0))
    pygame.image.save(s, path)


def run(*args):
    p = subprocess.run([sys.executable, PROG, *args], env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.returncode, p.stdout


turns = {ln.split("|")[0]: int(ln.split("|")[1]) for ln in open(os.path.join(SHARE, "turns.txt")) if ln.strip() and not ln.startswith("#")}
assert set(turns) == set(SIZES), set(turns) ^ set(SIZES)

with tempfile.TemporaryDirectory() as t:
    for name, size in SIZES.items():
        stock(f"{t}/consoles/logo/{name}/logo.bmp", size)
    stock(f"{t}/consoles/logo/NEW-PANEL/logo.bmp", (800, 600))      # a folder arkos4clone added later
    stock(f"{t}/logo.bmp", (720, 720))
    open(f"{t}/rk-device.txt", "w").write("console=r36max type1\nkernel=5.10\n")
    open(f"{t}/consoles/logos.txt", "w").write("origin|logo/480P\nr36max type1|logo/720P\n")
    before = open(f"{t}/logo.bmp", "rb").read()
    rc, out = run("boot", t)
    assert rc == 0 and "11 boot logos made" in out and "logo.bmp is now ours, for 720P" in out, out
    assert "NEW-PANEL is not in turns.txt" in out, out
    for name, size in SIZES.items():
        magic, got, bpp, comp = head(f"{t}/consoles/logo/{name}/logo.bmp")
        assert (magic, got, bpp, comp) == (b"BM", size, 24, 0), (name, magic, got, bpp, comp)
    assert head(f"{t}/consoles/logo/NEW-PANEL/logo.bmp")[1] == (800, 600)
    assert pygame.image.load(f"{t}/consoles/logo/NEW-PANEL/logo.bmp").get_at((5, 5))[:3] == (255, 128, 0), "an unlisted folder was written"
    ours = open(f"{t}/logo.bmp", "rb").read()
    assert ours != before and ours == open(f"{t}/consoles/logo/720P/logo.bmp", "rb").read()
    assert not [f for f in os.listdir(t) if "logo-new" in f], "a work file was left on the boot partition"
    # nothing is kept: a logo put there by hand is written over at the next run
    stock(f"{t}/logo.bmp", (720, 720))
    rc, out = run("boot", t)
    assert rc == 0 and open(f"{t}/logo.bmp", "rb").read() == ours, out

    # the turn: the eye (the only green in the picture) is in the top half of an upright
    # logo, so in the left half of one turned 90 counter-clockwise, the right half at 270,
    # and the bottom half at 180
    def green_centre(name):
        im = pygame.image.load(f"{t}/consoles/logo/{name}/logo.bmp")
        w, h = im.get_size()
        pts = [(x, y) for x in range(0, w, 4) for y in range(0, h, 4)
               if (lambda c: c[1] > 150 and c[0] < 110 and c[2] > 100)(im.get_at((x, y)))]
        assert pts, name
        return sum(p[0] for p in pts) / len(pts) / w, sum(p[1] for p in pts) / len(pts) / h
    for name, turn in turns.items():
        x, y = green_centre(name)
        ok = {0: y < 0.5, 90: x < 0.5, 180: y > 0.5, 270: x > 0.5}[turn]
        assert ok, (name, turn, x, y)

    # a card whose handheld is not known: the folders are made, logo.bmp is left alone
    stock(f"{t}/logo.bmp", (720, 720))
    open(f"{t}/rk-device.txt", "w").write("console=something else\n")
    rc, out = run("boot", t)
    assert rc == 0 and "left as it is" in out and open(f"{t}/logo.bmp", "rb").read() == before, out

    # the build's call
    rc, out = run("make", f"{t}/consoles/logo")
    assert rc == 0 and "11 boot logos made" in out, out
    rc, out = run("boot", f"{t}/nowhere")
    assert rc == 1 and "nothing done" in out, out

# the migration: once, only on a mounted boot partition that is ours, and it does not stop the steps after it
step = os.path.join(OVERLAY, "usr", "lib", "rk", "migrations", "0004-boot-logo.sh")
with tempfile.TemporaryDirectory() as t:
    p = subprocess.run(["bash", step], env=dict(os.environ, RK_BOOT=t), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert p.returncode == 1 and "not mounted" in p.stdout, p.stdout
p = subprocess.run(["bash", step], env=dict(os.environ, RK_MIG_DIR="x"), stdout=subprocess.PIPE, text=True)
assert p.returncode == 0 and p.stdout == ""
print("test_bootlogo: ok")
