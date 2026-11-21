"""The handheld's screen code, run against a file standing in for /dev/fb0.

The screenshots the build draws use the demo back end, so a mistake in the
real one (backends/device.py) would only show on a handheld, as a desktop
that does not start. This opens the framebuffer class on a fake screen of
each depth, draws a frame, and calls what the run loop calls.
"""
import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pygame

from rkshell.backends import device

pygame.display.init()
for bpp in (32, 16):
    with tempfile.TemporaryDirectory() as d:
        w, h = 720, 720
        stride = w * bpp // 8
        for name, text in (("virtual_size", f"{w},{h}"), ("bits_per_pixel", str(bpp)), ("stride", str(stride))):
            open(os.path.join(d, name), "w").write(text + "\n")
        fbdev = os.path.join(d, "fb0")
        open(fbdev, "wb").write(bytes(stride * h))
        fb = device.Framebuffer(fbdev, sys_dir=d)
        assert fb.surf.get_size() == (w, h), "no drawing surface"
        fb.surf.fill((255, 128, 0))
        fb.show()
        fb.unblank()                      # not a real screen: must fail quietly
        assert any(open(fbdev, "rb").read(64)), "the frame did not reach the screen"
env = device.app_env()
assert not [k for k in env if k.startswith("SDL_") and k not in ("SDL_VIDEODRIVER", "SDL_GAMECONTROLLERCONFIG_FILE")]
device.run_step(None)
device.run_step(["/nonexistent"])


# the volume keys while an app has the screen: answered by the desktop
class Keys:
    def __init__(self):
        self.sent = False

    def read(self, timeout):
        if self.sent:
            import time
            time.sleep(timeout)
            return []
        self.sent = True
        return [(115, 1), (115, 0), (305, 1), (114, 1), (115, 2)]     # up, (release), A, down, up held


class Sound:
    level, sets = 50, 0

    def volume(self):
        return self.level

    def set_volume(self, pct):
        self.level, self.sets = pct, self.sets + 1


sound = Sound()
assert device.run_app(["sleep", "0.6"], dict(os.environ), Keys(), sound) == 0
assert (sound.level, sound.sets) == (55, 3), (sound.level, sound.sets)
print("device back end: ok")
