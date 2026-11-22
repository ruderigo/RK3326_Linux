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

Pointer. Anything that moves like a mouse moves the desktop's pointer: the
left stick (the rk-mouse service presents it as a mouse) and any USB mouse.
The pointer is drawn here, over the finished frame, and moving it rewrites
only the few pixels around it, so it stays quick on a slow frame.
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
SHIFT, CTRL = {42, 54}, {29, 97}
# what a real keyboard's other keys send to a screen that takes typing (a terminal's own codes)
SPECIAL = {28: "\r", 96: "\r", 14: "\x7f", 15: "\t", 1: "\x1b", 103: "\x1b[A", 108: "\x1b[B", 106: "\x1b[C",
           105: "\x1b[D", 102: "\x1b[H", 107: "\x1b[F", 111: "\x1b[3~", 104: "\x1b[5~", 109: "\x1b[6~"}
PLAIN = {2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7", 9: "8", 10: "9", 11: "0", 12: "-", 13: "=",
         16: "q", 17: "w", 18: "e", 19: "r", 20: "t", 21: "y", 22: "u", 23: "i", 24: "o", 25: "p", 26: "[", 27: "]",
         30: "a", 31: "s", 32: "d", 33: "f", 34: "g", 35: "h", 36: "j", 37: "k", 38: "l", 39: ";", 40: "'", 41: "`",
         43: "\\", 44: "z", 45: "x", 46: "c", 47: "v", 48: "b", 49: "n", 50: "m", 51: ",", 52: ".", 53: "/", 57: " "}
SHIFTED = dict(zip("1234567890-=[];'`\\,./", "!@#$%^&*()_+{}:\"~|<>?"))
EVENT = struct.Struct("qqHHi")          # struct input_event on a 64-bit kernel
EV_KEY, EV_REL = 1, 2
REL_X, REL_Y, REL_WHEEL = 0, 1, 8
MOUSE_LEFT, MOUSE_RIGHT, MOUSE_MIDDLE = 272, 273, 274
EVIOCGNAME = 0x81004506                 # the device's name, up to 256 bytes
STICK_MOUSE = "rk-mouse"                # the left stick as a mouse (overlay/usr/local/sbin/rk-mouse)
GPU_DIR = "/usr/lib/rk-gpu"                     # dArkOS's Mali driver and SDL2 (build-image.sh)
PAD_DB = "/usr/share/gamecontrollerdb.txt"      # dArkOS's controller database


def app_env():
    """The environment for an app the dock opens. None of the desktop's own SDL
    settings (its "dummy" driver would give the app a black screen); dArkOS's
    Mali driver and SDL2, which is what this panel shows; and the controller
    database that puts SELECT and START where they are on this pad."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("SDL_")}
    if os.path.isdir(GPU_DIR):
        env["LD_LIBRARY_PATH"] = ":".join(p for p in (GPU_DIR, env.get("LD_LIBRARY_PATH")) if p)
        env["SDL_VIDEODRIVER"] = "kmsdrm"
    if os.path.isfile(PAD_DB):
        env["SDL_GAMECONTROLLERCONFIG_FILE"] = PAD_DB
    return env


def run_app(cmd, env, inputs, system):
    """Run an app the dock opened, and wait for it. The desktop is paused
    meanwhile and the apps do not read the volume keys, so those are answered
    here; every other key is the app's own business."""
    p = subprocess.Popen(cmd, env=env)
    while p.poll() is None:
        for code, value in inputs.read(0.25):
            if code in VOLUME and value:
                v = system.volume()
                if v is not None:
                    system.set_volume(v + VOLUME[code])
    return p.returncode


def run_step(cmd):
    """An app's optional "before" or "after" step (a command list); quietly
    skipped when it is missing or fails."""
    if cmd:
        try:
            subprocess.run(cmd, timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass


# -------------------------------------------------------------- framebuffer
class Framebuffer:
    def __init__(self, path="/dev/fb0", sys_dir=None):
        sys_dir = sys_dir or "/sys/class/graphics/" + os.path.basename(path)
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
        self.pointer = None                     # where the pointer is on the screen now: a Rect, or None

    def unblank(self):
        """Turn the panel back on (FBIOBLANK): an app that crashes on its way
        out can leave it blanked, with the desktop drawing unseen behind."""
        try:
            fcntl.ioctl(self.fd, 0x4611, 0)
        except OSError:
            pass

    def show(self, cursor=None, at=None):
        """Put the frame on the screen, with the pointer on top when `cursor`
        (its picture) is given. The drawing surface is left without it."""
        under = spot = None
        if cursor is not None:
            spot = cursor.get_rect(topleft=at).clip(self.surf.get_rect())
            under = self.surf.subsurface(spot).copy()
            self.surf.blit(cursor, at)
        try:
            self.write_frame()
        finally:
            if under is not None:
                self.surf.blit(under, spot)
        self.pointer = spot

    def move_pointer(self, cursor=None, at=None):
        """Move the pointer (or take it away: cursor None) without a new
        frame: only the pixels it leaves and the ones it lands on are written."""
        new = cursor.get_rect(topleft=at).clip(self.surf.get_rect()) if cursor is not None else None
        old, self.pointer = self.pointer, new
        if old and new and old.colliderect(new):
            areas = [old.union(new)]            # one write: no moment without a pointer
        else:
            areas = [r for r in (old, new) if r]
        size = self.bpp // 8
        for area in areas:
            if not area.w or not area.h:
                continue
            patch = self.surf.subsurface(area).copy()
            if new is not None:
                patch.blit(cursor, (at[0] - area.x, at[1] - area.y))
            if self.out is not None:
                small = pygame.Surface(area.size, 0, 16, (0xF800, 0x07E0, 0x001F, 0))
                small.blit(patch, (0, 0))
                patch = small
            raw, pitch, row = patch.get_buffer().raw, patch.get_pitch(), area.w * size
            for y in range(area.h):
                to = (area.y + y) * self.stride + area.x * size
                self.mm[to:to + row] = raw[y * pitch:y * pitch + row]

    def write_frame(self):
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
        self.fds, self.next_scan, self.shift, self.ctrl = {}, 0, False, False
        self.stick = set()                      # the left stick's mouse: its buttons are the pad's own
        self.dx = self.dy = self.wheel = 0      # mouse movement since take_motion()

    def scan(self):
        """Open input devices that appeared; called every couple of seconds."""
        self.next_scan = time.time() + 2
        for path in glob.glob("/dev/input/event*"):
            if path not in self.fds.values():
                try:
                    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                except OSError:
                    continue
                self.fds[fd] = path
                try:
                    name = fcntl.ioctl(fd, EVIOCGNAME, bytes(256)).split(b"\0")[0].decode("utf-8", "replace")
                except OSError:
                    name = ""
                if name == STICK_MOUSE:
                    self.stick.add(fd)

    def take_motion(self):
        """How far the mice moved since the last call: (dx, dy, wheel)."""
        m = self.dx, self.dy, self.wheel
        self.dx = self.dy = self.wheel = 0
        return m

    def read(self, timeout):
        """Key events since the last call: a list of (code, value). value 1 = down, 0 = up.
        Mouse movement is added up on the side, for take_motion()."""
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
                self.stick.discard(fd)
                continue
            stick = fd in self.stick
            for off in range(0, len(data) - EVENT.size + 1, EVENT.size):
                _, _, etype, code, value = EVENT.unpack_from(data, off)
                if etype == EV_REL:
                    if code == REL_X:
                        self.dx += value
                    elif code == REL_Y:
                        self.dy += value
                    elif code == REL_WHEEL and not stick:
                        self.wheel += value
                elif etype == EV_KEY and value in (0, 1, 2):
                    # the stick's mouse clicks with the triggers, for apps; here
                    # those are the pad's buttons, already read from the pad
                    if not (stick and MOUSE_LEFT <= code <= MOUSE_MIDDLE):
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
    drawn, draw_time, last_frame = 0, 0.0, 0.0
    print(f"rkshell: screen {fb.w}x{fb.h}, {fb.bpp} bits, line {fb.stride} bytes; console {console.name}", file=sys.stderr)
    try:
        while app.running and not stop:
            wait = 0.005 if app.dock.moving or held else (0.03 if app.live else (1 / fps if app.animating else 0.25))
            # The pointer wakes the loop many times a second. Frames keep their
            # own pace: `wait` after the last one, however often it wakes.
            now = time.time()
            pause = min(wait, max(0.0, last_frame + wait - now)) if app.animating else wait
            if app.pointer_on:
                pause = min(pause, max(0.0, app.pointer_until - now) + 0.01)
            for code, value in inputs.read(pause):
                typing = bool(app.current and app.current.wants_keys)
                if code in SHIFT:
                    inputs.shift = bool(value)
                elif code in CTRL:
                    inputs.ctrl = bool(value)
                elif code in VOLUME and value:
                    v = system.volume()
                    if v is not None:
                        app.toast(f"{system.volume_name()} {system.set_volume(v + VOLUME[code])}%", 1.5)
                elif typing and code in SPECIAL:            # value 2 is the keyboard's own repeat
                    if value:
                        app.text_input(SPECIAL[code])
                elif typing and code in PLAIN:
                    if value:
                        ch = PLAIN[code]
                        if inputs.ctrl and ch.isalpha():
                            app.text_input(chr(ord(ch) & 0x1f))
                        else:
                            app.text_input(SHIFTED.get(ch, ch.upper()) if inputs.shift else ch)
                elif code == MOUSE_LEFT:                    # a USB mouse: on nothing, a click does nothing
                    if value == 1:
                        app.move_pointer(0, 0)
                        app.click()
                elif code == MOUSE_RIGHT:
                    if value == 1:
                        app.press("b")
                else:
                    action = PAD.get(code) or KEYS.get(code)
                    if value == 2:                          # the shell does its own repeating for these
                        continue
                    if action and value:
                        app.press(action)
                        if action in REPEATING:
                            held[action] = time.time() + REPEAT_DELAY
                    elif action:
                        held.pop(action, None)
            dx, dy, wheel = inputs.take_motion()
            if dx or dy:
                app.move_pointer(dx, dy)
            for _ in range(min(abs(wheel), 10)):            # a mouse wheel is up and down
                app.handle("up" if wheel > 0 else "down")
            now = time.time()
            for action, due in list(held.items()):
                if now >= due:
                    app.handle(action)
                    held[action] = now + REPEAT_RATE
            app.tick()
            if app.launch:
                cmd, app.launch = app.launch, None
                item, app.launch_item = app.launch_item or {}, None
                # the console stays in graphics mode, as EmulationStation keeps it
                # while a port runs: the app owns the screen until it quits
                run_step(item.get("before"))
                try:
                    run_app(cmd, app_env(), inputs, system)
                except OSError as e:
                    app.toast(str(e), 5, error=True)
                run_step(item.get("after"))
                fb.unblank()
                console.__init__()
                held.clear()
                inputs.take_motion()                        # the stick was the app's meanwhile
                app.hide_pointer()
                app.dirty = True
            if console.in_front():
                t = time.time()
                cursor, at = (app.cursor, tuple(app.pointer)) if app.pointer_on else (None, None)
                if app.dirty or (app.animating and t >= last_frame + wait):
                    app.draw()
                    fb.show(cursor, at)
                    last_frame = time.time()
                    drawn, draw_time = drawn + 1, draw_time + last_frame - t
                elif (fb.pointer.topleft if fb.pointer else None) != at:
                    fb.move_pointer(cursor, at)
    finally:
        console.restore()
        if drawn:
            print(f"rkshell: {drawn} frames, {draw_time / drawn * 1000:.0f} ms each on average", file=sys.stderr)
    return 0
