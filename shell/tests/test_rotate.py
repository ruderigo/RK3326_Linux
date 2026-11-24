"""A panel mounted on its side, and a direction pad that reports as a hat.

Fourteen of the RK3326 handhelds arkos4clone supports have a portrait panel
(RGB10, RG351P, R40S, U8...). None of them is on the bench, so this is where
the turned picture is checked: against a file standing in for /dev/fb0.
"""
import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pygame

from rkshell.backends import device

pygame.display.init()

assert device.screen_rotation("root=/dev/mmcblk0p2 fbcon=rotate:3 console=tty1") == 3
assert device.screen_rotation("root=/dev/mmcblk0p2 console=tty1") == 0
assert device.screen_rotation("fbcon=rotate:3", "1\n") == 1, "rotate.txt comes first"
assert device.screen_rotation("fbcon=rotate:3", "sideways") == 3, "a rotate.txt that is not 0-3 is ignored"


def fake(d, pw, ph, bpp, rotate):
    stride = pw * bpp // 8
    for name, text in (("virtual_size", f"{pw},{ph}"), ("bits_per_pixel", str(bpp)), ("stride", str(stride))):
        open(os.path.join(d, name), "w").write(text + "\n")
    path = os.path.join(d, "fb0")
    open(path, "wb").write(bytes(stride * ph))
    return device.Framebuffer(path, sys_dir=d, rotate=rotate), path


def pixel(path, pw, bpp, x, y):
    size = bpp // 8
    raw = open(path, "rb").read()
    return raw[(y * pw + x) * size:(y * pw + x) * size + size]


PW, PH = 320, 480                       # the RGB10's panel: upright in memory, looked at lying down
for bpp in (32, 16):
    for rotate in (0, 1, 2, 3):
        with tempfile.TemporaryDirectory() as d:
            fb, path = fake(d, PW, PH, bpp, rotate)
            want = (PH, PW) if rotate in (1, 3) else (PW, PH)
            assert fb.surf.get_size() == want, f"rotate {rotate}: the picture is {fb.surf.get_size()}, not {want}"
            W, H = want
            # one bright dot at the picture's top left corner must land on the right corner of the panel
            fb.surf.fill((0, 0, 0))
            fb.surf.set_at((0, 0), (255, 255, 255))
            fb.show()
            corner = {0: (0, 0), 1: (PW - 1, 0), 2: (PW - 1, PH - 1), 3: (0, PH - 1)}[rotate]
            assert any(pixel(path, PW, bpp, *corner)), f"rotate {rotate}, {bpp} bits: the top left dot is not at {corner}"
            # the pointer moved without a new frame must leave exactly what a whole new frame would
            fb.surf.fill((10, 40, 90))
            pygame.draw.rect(fb.surf, (200, 30, 30), (20, 30, 50, 12))
            cursor = pygame.Surface((9, 14))
            cursor.fill((255, 255, 0))
            fb.show(cursor, (25, 28))
            fb.move_pointer(cursor, (W - 5, H - 6))             # partly off the edge
            moved = open(path, "rb").read()
            fb.show(cursor, (W - 5, H - 6))
            assert moved == open(path, "rb").read(), f"rotate {rotate}, {bpp} bits: moving the pointer drew it somewhere else"
            fb.move_pointer(None, None)
            gone = open(path, "rb").read()
            fb.show()
            assert gone == open(path, "rb").read(), f"rotate {rotate}, {bpp} bits: the pointer left a mark"

# ------------------------------------------- programs that draw through the GPU
from rkshell import panel

with tempfile.TemporaryDirectory() as d:
    gpu, rga = os.path.join(d, "rk-gpu"), os.path.join(d, "librga.so.2")
    for n in (1, 2, 3):
        os.makedirs(os.path.join(gpu, f"turn{n}"))
        open(os.path.join(gpu, f"turn{n}", "libSDL2-2.0.so.0"), "w").close()
    # a panel that is not turned: dArkOS's own SDL2, and RetroArch told so
    env = panel.app_environment({"LD_LIBRARY_PATH": "/opt/x"}, 0, gpu, rga)
    assert env["LD_LIBRARY_PATH"] == f"{gpu}:/opt/x" and env["RK_ROTATE"] == "0", env
    # turned, but nothing to turn the picture with: the SDL2 that starts, not the one that cannot load
    env = panel.app_environment({}, 3, gpu, rga)
    assert env["LD_LIBRARY_PATH"] == gpu and env["RK_ROTATE"] == "3", env
    open(rga, "w").close()
    for n in (1, 2, 3):
        env = panel.app_environment({"LD_LIBRARY_PATH": f"{gpu}:/opt/x"}, n, gpu, rga)
        assert env["LD_LIBRARY_PATH"] == f"{gpu}/turn{n}:{gpu}:/opt/x" and env["RK_ROTATE"] == str(n), env
    # asked twice (the dock, then rk-video inside it): the same answer
    again = panel.app_environment(dict(env), 3, gpu, rga)
    assert again["LD_LIBRARY_PATH"] == env["LD_LIBRARY_PATH"], again
    assert panel.app_environment({}, 2, os.path.join(d, "nothing"), rga) == {"RK_ROTATE": "2"}

# ------------------------------------------------------------------ the hat
inputs = device.Inputs()
inputs.next_scan = float("inf")         # no real devices in this test
r, w = os.pipe()
os.set_blocking(r, False)
inputs.fds[r] = "pipe"


def send(etype, code, value):
    os.write(w, device.EVENT.pack(0, 0, etype, code, value))


send(device.EV_ABS, device.ABS_HAT0X, -1)
assert inputs.read(0.1) == [(546, 1)], "hat left is not the left key going down"
send(device.EV_ABS, device.ABS_HAT0X, 1)                        # straight across, as a thumb rolls
assert inputs.read(0.1) == [(546, 0), (547, 1)]
send(device.EV_ABS, device.ABS_HAT0Y, -1)
assert inputs.read(0.1) == [(544, 1)], "hat up is not the up key"
send(device.EV_ABS, device.ABS_HAT0X, 0)
send(device.EV_ABS, device.ABS_HAT0Y, 0)
assert inputs.read(0.1) == [(547, 0), (544, 0)]
send(device.EV_ABS, 0, 512)                                     # a stick: not a key
assert inputs.read(0.1) == []
for code in (544, 545, 546, 547):
    assert device.PAD[code] in ("up", "down", "left", "right")
print("test_rotate: ok")
