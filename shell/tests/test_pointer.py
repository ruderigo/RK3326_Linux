"""The desktop's pointer, without a handheld: pressing what it is on, how it
reaches the screen, and how the stick's mouse and a USB mouse are read.

    python3 tests/test_pointer.py
"""
import os
import sys
import tempfile
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pygame

from rkshell import app as A
from rkshell import gfx as G
from rkshell.backends import device
from rkshell.system import DemoSystem

pygame.display.init()
pygame.font.init()
pygame.display.set_mode((1, 1))


def settle(app):
    for _ in range(30):
        app.draw()


def point(app, rect):
    app.move_pointer(rect.centerx - app.pointer[0], rect.centery - app.pointer[1])


def test_press():
    for size in ((720, 720), (640, 480)):
        app = A.App(DemoSystem(), pygame.Surface(size))
        settle(app)
        assert not app.pointer_on                       # nothing shows until the stick moves
        assert not app.click()

        app.move_pointer(-5000, -5000)                  # it stops at the edges
        assert app.pointer == [0, 0] and app.pointer_on
        app.move_pointer(9000, 9000)
        assert app.pointer == [size[0] - 1, size[1] - 1]

        # the dock: A opens the icon the pointer is on, not the one the d-pad chose
        icons = [r for r, _, _ in G.spots]
        assert len(icons) == len(app.dock.items)
        target = next(i for i, r in enumerate(icons) if i != app.dock.sel and r.right < size[0] and r.x > 0)
        point(app, icons[target])
        app.press("a")
        assert app.dock.sel == target and app.window is not None
        settle(app)

        # the window's ×: the same as B
        point(app, G.spots[-1][0])
        app.press("a")
        assert app.window is None
        settle(app)

        # on nothing, A does what it always does
        app.move_pointer(-9000, -9000)
        app.press("a")
        assert app.window is not None
        app.handle("b")

        # the d-pad takes over: the pointer goes, and A is the d-pad's again
        settle(app)
        point(app, G.spots[0][0])
        app.press("right")
        assert not app.pointer_on
        sel = app.dock.sel
        app.press("a")
        assert app.dock.sel == sel

    # a row in a window, and a menu over it: what is under the menu cannot be pressed
    app = A.App(DemoSystem(), pygame.Surface((720, 720)))
    app.dock.sel = next(i for i, it in enumerate(app.dock.items) if it["name"] == "Settings")
    app.handle("a")
    settle(app)
    rows = [(r, i) for i, (r, _, _) in enumerate(G.spots[:-1])]
    names = [it["name"] for it in app.window.list.items]
    point(app, rows[names.index("Restart")][0])
    assert app.click() and app.window.list.sel == names.index("Restart") and app.stack
    settle(app)
    assert len(G.spots) == 3                            # Cancel, Restart, and the ×
    point(app, G.spots[0][0])
    assert app.click() and not app.stack                # Cancel

    # it goes away by itself
    app.pointer_until = time.time() - 0.01
    assert not app.pointer_on and not app.click()


def test_screen():
    for bpp in (32, 16):
        with tempfile.TemporaryDirectory() as d:
            w, h = 64, 48
            stride = w * bpp // 8 + 8                    # a driver that pads each line
            for name, text in (("virtual_size", f"{w},{h}"), ("bits_per_pixel", str(bpp)), ("stride", str(stride))):
                open(os.path.join(d, name), "w").write(text + "\n")
            path = os.path.join(d, "fb0")
            open(path, "wb").write(bytes(stride * h))
            fb = device.Framebuffer(path, sys_dir=d)
            fb.surf.fill((40, 80, 120))
            cur = pygame.Surface((8, 8), pygame.SRCALPHA)
            cur.fill((255, 255, 255, 255))
            size = bpp // 8
            white = b"\xff\xff\xff\x00" if bpp == 32 else b"\xff\xff"

            def screen():
                fb.mm.flush()
                raw = open(path, "rb").read()
                return [raw[y * stride:y * stride + w * size] for y in range(h)]

            fb.show()
            clean = screen()
            assert len(set(clean)) == 1 and any(clean[0])

            fb.show(cur, (10, 10))                      # a frame with the pointer on it
            with_ptr = screen()
            changed = {y for y in range(h) if with_ptr[y] != clean[y]}
            assert changed == set(range(10, 18)), changed
            assert with_ptr[10][10 * size:18 * size] == white * 8
            assert fb.surf.get_at((12, 12))[:3] == (40, 80, 120)    # the drawing itself stays clean

            fb.move_pointer(cur, (14, 12))              # a short move: old place restored, new one drawn
            moved = screen()
            assert {y for y in range(h) if moved[y] != clean[y]} == set(range(12, 20))
            assert moved[12][14 * size:22 * size] == white * 8
            assert moved[12][:14 * size] == clean[12][:14 * size]

            fb.move_pointer(cur, (60, 44))              # a jump to the corner: cut at the edges
            far = screen()
            assert {y for y in range(h) if far[y] != clean[y]} == set(range(44, 48))
            assert far[44][60 * size:] == white * 4

            fb.move_pointer()                           # gone
            assert screen() == clean and fb.pointer is None


def test_mice():
    ev = device.EVENT
    inputs = device.Inputs()
    inputs.next_scan = time.time() + 3600               # no real devices in this test
    stick_r, stick_w = os.pipe()
    usb_r, usb_w = os.pipe()
    os.set_blocking(stick_r, False)
    os.set_blocking(usb_r, False)
    inputs.fds = {stick_r: "stick", usb_r: "usb"}
    inputs.stick.add(stick_r)

    def send(fd, *events):
        os.write(fd, b"".join(ev.pack(0, 0, t, c, v) for t, c, v in events))

    # the stick's mouse: it moves the pointer; its clicks and wheel are the pad's own buttons
    send(stick_w, (2, 0, 7), (2, 1, -3), (1, 272, 1), (1, 272, 0), (2, 8, 1))
    assert inputs.read(0.2) == []
    assert inputs.take_motion() == (7, -3, 0)
    # a USB mouse: everything counts
    send(usb_w, (2, 0, -2), (2, 0, -2), (1, 272, 1), (2, 8, -1), (1, 273, 1))
    assert inputs.read(0.2) == [(272, 1), (273, 1)]
    assert inputs.take_motion() == (-4, 0, -1)
    assert inputs.take_motion() == (0, 0, 0)
    # the pad's keys come through as before
    send(usb_w, (1, 305, 1), (1, 305, 0))
    assert inputs.read(0.2) == [(305, 1), (305, 0)]
    for fd in (stick_r, stick_w, usb_r, usb_w):
        os.close(fd)


def test_loop():
    """The handheld's own loop on a made-up screen: the stick moves the pointer
    between frames, frames keep their pace, and the pointer goes away."""
    import signal
    with tempfile.TemporaryDirectory() as d:
        w, h = 720, 720
        for name, text in (("virtual_size", f"{w},{h}"), ("bits_per_pixel", "32"), ("stride", str(w * 4))):
            open(os.path.join(d, name), "w").write(text + "\n")
        path = os.path.join(d, "fb0")
        open(path, "wb").write(bytes(w * 4 * h))
        seen = {"reads": 0, "frames": 0, "moves": 0, "shown": False, "fb": None}

        def screen():
            fb = seen["fb"] = RealFb(path, sys_dir=d)
            show, move = fb.show, fb.move_pointer

            def count_show(*a):
                seen["frames"] += 1
                show(*a)

            def count_move(*a):
                seen["moves"] += 1
                move(*a)
            fb.show, fb.move_pointer = count_show, count_move
            return fb

        class Console:
            name = "test"
            def in_front(self): return True
            def restore(self): pass

        class Stick:
            """A second of pushing the stick right, 60 times a second, then rest."""
            def __init__(self):
                self.t0, self.dx = time.time(), 0
            def read(self, timeout):
                seen["reads"] += 1
                t = time.time() - self.t0
                if t < 1.0:
                    time.sleep(min(timeout, 1 / 60))
                    self.dx += 4
                else:
                    seen["shown"] = seen["shown"] or seen["fb"].pointer is not None
                    time.sleep(timeout)
                    if t > 2.0:
                        os.kill(os.getpid(), signal.SIGTERM)
                return []
            def take_motion(self):
                m, self.dx = (self.dx, 0, 0), 0
                return m

        RealFb, RealConsole, RealInputs, rest = device.Framebuffer, device.Console, device.Inputs, A.POINTER_REST
        device.Framebuffer, device.Console, device.Inputs, A.POINTER_REST = screen, Console, Stick, 0.4
        try:
            assert device.run(DemoSystem(), fps=10) == 0
        finally:
            device.Framebuffer, device.Console, device.Inputs, A.POINTER_REST = RealFb, RealConsole, RealInputs, rest
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            signal.signal(signal.SIGINT, signal.default_int_handler)
        assert seen["shown"], "the pointer never reached the screen"
        assert seen["fb"].pointer is None, "the pointer did not go away"
        assert seen["moves"] >= 20, seen                 # moved between frames...
        assert 10 <= seen["frames"] <= 40, seen          # ...which kept the desktop's pace (10 a second, 2 s)
        assert seen["reads"] < 400, seen                 # and the loop sleeps when there is nothing to do
        raw = open(path, "rb").read()
        assert any(raw[:w * 4 * 40])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("pointer: ok")
