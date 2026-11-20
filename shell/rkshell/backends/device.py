"""The handheld: draw to the framebuffer, read the gamepad and keyboards.

Screen. SDL has no usable video driver on these kernels without the GPU's
user-space libraries, so pygame draws into a surface in memory (SDL's
"dummy" driver) and each finished frame is copied to /dev/fb0. Size, depth
and colour order are read from the framebuffer, never assumed. The text
console on the same screen is switched to graphics mode while the shell
runs, and nothing is drawn while another console (Alt+F2) is in front.

Input. Every /dev/input/event* device is read directly: the built-in pad
("GO-Super Gamepad"), the volume keys, and any USB keyboard or pad, as soon
as it is plugged in. Key codes, not device names, decide what a key does, so
a second controller works without setup.
"""
import fcntl
import glob
import mmap
import os
import select
import signal
import struct
import subprocess
import sys
import time

import pygame

from ..app import App
from ..widgets import Keyboard

# ---------------------------------------------------------------- key codes
# The pad's letters follow where they are printed on the handheld (A right, B
# bottom, X top, Y left), not the kernel's names: code 304 is the bottom
# button, which the R36MAX labels B.
PAD = {305: "a", 304: "b", 307: "x", 308: "y", 310: "l1", 311: "r1", 312: "l2", 313: "r2",
       704: "select", 705: "start", 544: "up", 545: "down", 546: "left", 547: "right"}
KEYS = {103: "up", 108: "down", 105: "left", 106: "right", 28: "a", 96: "a", 1: "b", 15: "select"}
VOLUME = {114: -5, 115: 5}
REPEATING = {"up", "down", "left", "right"}
REPEAT_DELAY, REPEAT_RATE = 0.35, 0.09
SHIFT = {42, 54}
PLAIN = {2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7", 9: "8", 10: "9", 11: "0", 12: "-", 13: "=",
         16: "q", 17: "w", 18: "e", 19: "r", 20: "t", 21: "y", 22: "u", 23: "i", 24: "o", 25: "p", 26: "[", 27: "]",
         30: "a", 31: "s", 32: "d", 33: "f", 34: "g", 35: "h", 36: "j", 37: "k", 38: "l", 39: ";", 40: "'", 41: "`",
         43: "\\", 44: "z", 45: "x", 46: "c", 47: "v", 48: "b", 49: "n", 50: "m", 51: ",", 52: ".", 53: "/", 57: " "}
SHIFTED = dict(zip("1234567890-=[];'`\\,./", "!@#$%^&*()_+{}:\"~|<>?"))
EVENT = struct.Struct("qqHHi")          # struct input_event on a 64-bit kernel
EV_KEY = 1


# -------------------------------------------------------------- framebuffer
class Framebuffer:
    def __init__(self, path="/dev/fb0"):
        sys_dir = "/sys/class/graphics/" + os.path.basename(path)
        self.w, self.h = (int(x) for x in open(sys_dir + "/virtual_size").read().split(","))
        self.bpp = int(open(sys_dir + "/bits_per_pixel").read())
        try:
            self.stride = int(open(sys_dir + "/stride").read())
        except (OSError, ValueError):
            self.stride = self.w * self.bpp // 8
        self.fd = os.open(path, os.O_RDWR)
        # which byte is red: from the driver (FBIOGET_VSCREENINFO), red at bit 16 unless it says otherwise
        red_offset = 16
        try:
            info = fcntl.ioctl(self.fd, 0x4600, bytes(160))
            red_offset = struct.unpack_from("I", info, 32)[0]
        except OSError:
            pass
        self.mm = mmap.mmap(self.fd, self.stride * self.h)
        if self.bpp == 32:
            masks = (0xFF0000, 0xFF00, 0xFF, 0) if red_offset == 16 else (0xFF, 0xFF00, 0xFF0000, 0)
            self.out = None
            self.surf = pygame.Surface((self.w, self.h), 0, 32, masks)
        elif self.bpp == 16:
            self.surf = pygame.Surface((self.w, self.h), 0, 32)
            self.out = pygame.Surface((self.w, self.h), 0, 16, (0xF800, 0x07E0, 0x001F, 0))
        else:
            raise SystemExit(f"rkshell: a {self.bpp}-bit screen is not supported")

    def show(self):
        src = self.surf
        if self.out is not None:
            self.out.blit(self.surf, (0, 0))
            src = self.out
        row = self.w * self.bpp // 8
        if src.get_pitch() == self.stride:      # the usual case: one copy, straight from the surface
            self.mm.seek(0)
            self.mm.write(src.get_buffer())
        else:                                   # the driver pads each line: copy line by line
            raw = src.get_buffer().raw
            pitch = src.get_pitch()
            for y in range(self.h):
                self.mm[y * self.stride:y * self.stride + row] = raw[y * pitch:y * pitch + row]


# ------------------------------------------------------------------ console
class Console:
    """The text console that shares the screen: quiet while the shell draws."""
    KDSETMODE, KD_TEXT, KD_GRAPHICS = 0x4B3A, 0, 1

    def __init__(self):
        self.fd = None
        for path in ("/dev/tty", "/dev/tty1", "/dev/tty0"):
            try:
                self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
                fcntl.ioctl(self.fd, self.KDSETMODE, self.KD_GRAPHICS)
                self.name = os.ttyname(self.fd) if path == "/dev/tty" else path
                return
            except OSError:
                if self.fd is not None:
                    os.close(self.fd)
                self.fd = None
        self.name = None
        print("rkshell: could not put the console in graphics mode; its cursor may show through", file=sys.stderr)

    def restore(self):
        if self.fd is not None:
            try:
                fcntl.ioctl(self.fd, self.KDSETMODE, self.KD_TEXT)
            except OSError:
                pass

    def in_front(self):
        """False while the user has switched to another console (Alt+F2)."""
        if not self.name or not self.name.startswith("/dev/tty") or self.name in ("/dev/tty", "/dev/tty0"):
            return True
        try:
            return open("/sys/class/tty/tty0/active").read().strip() == os.path.basename(self.name)
        except OSError:
            return True


# -------------------------------------------------------------------- input
class Inputs:
    def __init__(self):
        self.fds, self.next_scan, self.shift = {}, 0, False

    def scan(self):
        """Open input devices that appeared; called every couple of seconds."""
        self.next_scan = time.time() + 2
        for path in glob.glob("/dev/input/event*"):
            if path not in self.fds.values():
                try:
                    self.fds[os.open(path, os.O_RDONLY | os.O_NONBLOCK)] = path
                except OSError:
                    pass

    def read(self, timeout):
        """Key events since the last call: a list of (code, value). value 1 = down, 0 = up."""
        if time.time() >= self.next_scan:
            self.scan()
        out = []
        try:
            ready, _, _ = select.select(list(self.fds), [], [], timeout)
        except (OSError, ValueError):
            ready = []
        for fd in ready:
            try:
                data = os.read(fd, EVENT.size * 64)
            except BlockingIOError:
                continue
            except OSError:                     # unplugged
                os.close(fd)
                del self.fds[fd]
                continue
            for off in range(0, len(data) - EVENT.size + 1, EVENT.size):
                _, _, etype, code, value = EVENT.unpack_from(data, off)
                if etype == EV_KEY and value in (0, 1):
                    out.append((code, value))
        return out


# --------------------------------------------------------------------- loop
def run(system, fps=10):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_mode((1, 1))
    fb = Framebuffer()
    console = Console()
    inputs = Inputs()
    app = App(system, fb.surf)
    held = {}                                   # action -> time of its next repeat
    stop = []
    signal.signal(signal.SIGTERM, lambda *a: stop.append(1))
    signal.signal(signal.SIGINT, lambda *a: stop.append(1))
    drawn, draw_time = 0, 0.0
    print(f"rkshell: screen {fb.w}x{fb.h}, {fb.bpp} bits, line {fb.stride} bytes; console {console.name}", file=sys.stderr)
    try:
        while app.running and not stop:
            wait = 0.005 if app.dock.moving or held else (1 / fps if app.animating else 0.25)
            for code, value in inputs.read(wait):
                typing = isinstance(app.current, Keyboard)
                if code in SHIFT:
                    inputs.shift = bool(value)
                elif code in VOLUME and value:
                    v = system.volume()
                    if v is not None:
                        app.toast(f"Volume {system.set_volume(v + VOLUME[code])}%", 1.5)
                elif typing and code == 14 and value:
                    app.text_input("\x08")
                elif typing and code in (28, 96) and value:
                    app.text_input("\n")
                elif typing and code in PLAIN and value:
                    ch = PLAIN[code]
                    app.text_input((SHIFTED.get(ch, ch.upper()) if inputs.shift else ch))
                else:
                    action = PAD.get(code) or KEYS.get(code)
                    if action and value:
                        app.handle(action)
                        if action in REPEATING:
                            held[action] = time.time() + REPEAT_DELAY
                    elif action:
                        held.pop(action, None)
            now = time.time()
            for action, due in list(held.items()):
                if now >= due:
                    app.handle(action)
                    held[action] = now + REPEAT_RATE
            app.tick()
            if app.launch:
                cmd, app.launch = app.launch, None
                console.restore()
                try:
                    subprocess.run(cmd)
                except OSError as e:
                    app.toast(str(e), 5, error=True)
                console.__init__()
                held.clear()
                app.dirty = True
            if (app.dirty or app.animating) and console.in_front():
                t = time.time()
                app.draw()
                fb.show()
                drawn, draw_time = drawn + 1, draw_time + time.time() - t
    finally:
        console.restore()
        if drawn:
            print(f"rkshell: {drawn} frames, {draw_time / drawn * 1000:.0f} ms each on average", file=sys.stderr)
    return 0
