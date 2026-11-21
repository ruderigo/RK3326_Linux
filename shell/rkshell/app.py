"""The shell: a desktop with a dock, and windows that open over it.

On the desktop, left and right move along the dock and A opens what is under
the cursor: one of the system's own windows (Files, Network, Devices,
Settings) or an installed app. A window covers the desktop; B closes it.
Windows can push screens (menus, the keyboard) on a stack; B closes the top
one first.

The loop that feeds actions in and puts the picture on the screen lives in
the back ends, so the same App runs on the handheld, in a window and in the
tests. `animating` tells the back end to keep drawing without input.
"""
import time

import pygame

from . import gfx as G
from . import theme as T
from .desktop import Dock, Wallpaper
from .pages.devices import DevicesPage
from .pages.files import FilesPage
from .pages.network import NetworkPage
from .pages.scan import ScanPage
from .pages.stumpsetup import StumpSetupPage
from .pages.apps import AppsPage
from .pages.arsenal import ArsenalPage
from .pages.survey import SurveyPage
from .pages.system import SystemPage
from .pages.terminal import TerminalPage

WINDOWS = [FilesPage, TerminalPage, ScanPage, ArsenalPage, SurveyPage, NetworkPage, DevicesPage, AppsPage, SystemPage]


# setup windows an app entry can name ("setup": "stump"), shown until its "needs" file exists
SETUPS = {"stump": StumpSetupPage}


class App:
    def __init__(self, system, surf):
        self.system, self.surf = system, surf
        self.fonts = T.Fonts(surf.get_height())
        self.wallpaper = Wallpaper(surf)
        self.bar = None
        self.dock = Dock()
        self.window, self.stack = None, []
        self.running, self.dirty = True, True
        self.toast_text, self.toast_until, self.toast_error = "", 0, False
        self.last_tick, self.t0 = 0, time.time()
        self.launch = None          # set to a command: the back end runs it and comes back
        self.launch_item = None     # the dock entry it came from (its "before"/"after" steps)
        self.fill_dock()

    def fill_dock(self):
        items = [{"name": w.title, "icon": w.icon, "ready": True, "window": w} for w in WINDOWS]
        items += sorted(self.system.apps(), key=lambda a: (a.get("group", ""), a["name"]))
        self.dock.set(items)

    # --------------------------------------------------------- navigation
    @property
    def current(self):
        return self.stack[-1] if self.stack else self.window

    @property
    def animating(self):
        return self.window is None or self.dock.moving

    def push(self, screen):
        self.stack.append(screen)
        self.dirty = True

    def pop(self):
        if self.stack:
            self.stack.pop()
        self.dirty = True

    def toast(self, text, secs=3, error=False):
        self.toast_text, self.toast_until, self.toast_error = text, time.time() + secs, error
        self.dirty = True

    def confirm(self, title, detail, label, on_yes):
        """Cancel comes first, so a double press of A never confirms."""
        from .widgets import Menu
        self.push(Menu(self, title, [("Cancel", None), (label, on_yes)], detail))

    def open(self, item):
        if "window" in item:
            self.window = item["window"](self)
            self.window.enter()
        elif item.get("needs_setup") and item.get("setup") in SETUPS:
            self.window = SETUPS[item["setup"]](self)        # its own setup first, asked here
            self.window.enter()
        elif not item.get("ready"):
            self.toast(f"{item['name']} is not installed yet", error=True)
        elif item.get("exec"):
            self.launch, self.launch_item = item["exec"], item
        else:
            self.toast(f"{item['name']} would open here (demo)")

    # -------------------------------------------------------------- input
    def handle(self, action):
        self.dirty = True
        if self.stack:
            self.stack[-1].handle(action)
        elif self.window:
            if action == "b" and not self.window.wants_back():
                self.window = None
            else:
                self.window.handle(action)
        elif action in ("left", "right"):
            self.dock.move(-1 if action == "left" else 1)
        elif action == "a" and self.dock.current:
            self.open(self.dock.current)

    def text_input(self, s):
        if self.current:
            self.dirty = True
            self.current.text_input(s)

    @property
    def live(self):
        """True while what is shown changes without input (a terminal, a scan)."""
        return bool(self.current and self.current.live)

    def tick(self):
        now = time.time()
        if self.current:
            self.current.poll()
        if now - self.last_tick >= 1:
            self.last_tick = now
            if self.current:
                self.current.tick()
            elif int(now) % 5 == 0:
                self.fill_dock()        # an app installed or removed shows up on the dock
            self.dirty = True           # the clock, the battery
        if self.toast_text and now > self.toast_until:
            self.toast_text = ""
            self.dirty = True

    # ------------------------------------------------------------ drawing
    def menu_bar(self, surf, f):
        W = surf.get_width()
        h = f.small_line + 12
        if self.bar is None:
            self.bar = pygame.Surface((W, h), pygame.SRCALPHA)
            self.bar.fill((*T.BAR, 215))
        surf.blit(self.bar, (0, 0))
        rel = self.system.release()
        x = 14 + G.text(surf, f.small, rel["RK_NAME"], (14, 6), T.EMBER_BRIGHT)
        if self.window:
            G.text(surf, f.small, "  ›  " + self.window.title, (x, 6), T.TEXT)
        wifi, bat = self.system.wifi(), self.system.battery()
        bits = []
        if wifi is None:
            bits.append(("no Wi-Fi card", T.DIM))
        elif wifi["state"] == "connected":
            bits.append((G.fit(f.small, wifi["ssid"], W // 5), T.OK))
        else:
            bits.append(("Wi-Fi off-line", T.DIM))
        if bat and bat["percent"] >= 0:
            charging = bat["status"] in ("Charging", "Full")
            low = bat["percent"] < 15 and not charging
            bits.append((f"{'+' if charging else ''}{bat['percent']}%", T.ERROR if low else T.TEXT))
        bits.append((time.strftime("%H:%M"), T.TEXT))
        x = W - 14
        for s, color in reversed(bits):
            x -= G.text(surf, f.small, s, (x, 6), color, right=True) + 18
        return h

    def draw(self):
        surf, f = self.surf, self.fonts
        W, H = surf.get_size()
        self.wallpaper.draw(surf, time.time() - self.t0)
        if self.window is None:
            self.dock.step()
            # the desktop: the time, the day, and where the handheld is on the network
            y = H // 8
            G.text(surf, f.clock, time.strftime("%H:%M"), (W // 2, y), T.TEXT, center=True)
            y += f.clock.get_linesize() + 2
            G.text(surf, f.mono, time.strftime("%A %-d %B"), (W // 2, y), T.MUTED, center=True)
            wifi = self.system.wifi()
            where = self.system.hostname()
            if wifi and wifi["state"] == "connected":
                where += "  ·  " + wifi["address"]
            G.text(surf, f.small, where, (W // 2, y + f.line + 6), T.DIM, center=True)
            self.dock.draw(surf, f)
            self.menu_bar(surf, f)
        else:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((*T.BG, 90))
            surf.blit(veil, (0, 0))
            top = self.menu_bar(surf, f)
            # a window: the desktop stays visible around it and faintly through it
            frame = pygame.Rect(W // 24, top + W // 36, W - W // 12, H - top - W // 14)
            shadow = pygame.Surface((frame.w + 24, frame.h + 24), pygame.SRCALPHA)
            pygame.draw.rect(shadow, (0, 0, 0, 90), shadow.get_rect(), border_radius=24)
            surf.blit(shadow, (frame.x - 12, frame.y - 6))
            panel = pygame.Surface(frame.size, pygame.SRCALPHA)
            pygame.draw.rect(panel, (*T.BG, 236), panel.get_rect(), border_radius=16)
            pygame.draw.rect(panel, (*T.EMBER, 255), panel.get_rect(), width=1, border_radius=16)
            surf.blit(panel, frame.topleft)
            head = f.line + 20
            G.text(surf, f.big, self.window.title, (frame.x + 18, frame.y + 10), T.EMBER_BRIGHT)
            pygame.draw.line(surf, T.BORDER, (frame.x + 1, frame.y + head), (frame.right - 2, frame.y + head))
            foot = f.small_line + 14
            area = pygame.Rect(frame.x + 2, frame.y + head + 4, frame.w - 4, frame.h - head - foot - 6)
            surf.set_clip(area)
            self.window.draw(surf, f, area)
            if self.stack:
                dim = pygame.Surface(area.size, pygame.SRCALPHA)
                dim.fill((*T.BG, 200))
                surf.blit(dim, area.topleft)
                self.stack[-1].draw(surf, f, area)
            surf.set_clip(None)
            x, y = frame.x + 18, frame.bottom - foot + 4
            for button, label in self.current.hints:
                x += G.text(surf, f.small, button, (x, y), T.EMBER_BRIGHT) + 6
                x += G.text(surf, f.small, label, (x, y), T.MUTED) + 18
        if self.toast_text:
            w = min(W - 40, f.small.size(self.toast_text)[0] + 32)
            r = pygame.Rect((W - w) // 2, H // 2 - f.line, w, f.line + 10)
            G.box(surf, r, T.PANEL, 8, T.ERROR if self.toast_error else T.EMBER)
            G.text(surf, f.small, G.fit(f.small, self.toast_text, w - 24), (r.centerx, r.y + 8),
                   T.ERROR if self.toast_error else T.TEXT, center=True)
        self.dirty = False
