"""The shell: a status strip, pages across the top, a hint bar at the bottom.

L1/R1 and L2/R2 change the page. A page can push screens (menus, the
keyboard) on a stack; B closes the top one. The loop that feeds it actions
and puts the picture on the screen lives in the display back ends, so the
same App runs on the handheld, in a window and in the tests.
"""
import time

import pygame

from . import gfx as G
from . import theme as T
from .pages.devices import DevicesPage
from .pages.files import FilesPage
from .pages.home import HomePage
from .pages.network import NetworkPage
from .pages.system import SystemPage


class App:
    def __init__(self, system, surf):
        self.system, self.surf = system, surf
        self.fonts = T.Fonts(surf.get_height())
        self.pages = [HomePage(self), FilesPage(self), NetworkPage(self), DevicesPage(self), SystemPage(self)]
        self.page, self.stack = 0, []
        self.running, self.dirty = True, True
        self.toast_text, self.toast_until, self.toast_error = "", 0, False
        self.last_tick = 0
        self.launch = None          # set to a command by a page: the back end runs it and comes back

    # --------------------------------------------------------- navigation
    @property
    def current(self):
        return self.stack[-1] if self.stack else self.pages[self.page]

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

    # -------------------------------------------------------------- input
    def handle(self, action):
        self.dirty = True
        if not self.stack and action in ("l1", "l2", "r1", "r2"):
            self.page = (self.page + (1 if action in ("r1", "r2") else -1)) % len(self.pages)
            self.pages[self.page].enter()
            return
        self.current.handle(action)

    def text_input(self, s):
        self.dirty = True
        self.current.text_input(s)

    def tick(self):
        now = time.time()
        if now - self.last_tick >= 1:
            self.last_tick = now
            self.current.tick()
            self.dirty = True           # the clock, the battery, the toast
        if self.toast_text and now > self.toast_until:
            self.toast_text = ""
            self.dirty = True

    # ------------------------------------------------------------ drawing
    def draw(self):
        surf, f = self.surf, self.fonts
        W, H = surf.get_size()
        surf.fill(T.BG)
        # status strip
        strip = f.small_line + 10
        pygame.draw.rect(surf, T.BAR, (0, 0, W, strip))
        rel = self.system.release()
        G.text(surf, f.small, f"{self.system.hostname()}  ·  {rel['RK_NAME']} {rel['RK_VERSION']}", (12, 5), T.MUTED)
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
            bits.append((f"{'+' if charging else ''}{bat['percent']}%", T.ERROR if bat["percent"] < 15 and not charging else T.TEXT))
        bits.append((time.strftime("%H:%M"), T.TEXT))
        x = W - 12
        for s, color in reversed(bits):
            x -= G.text(surf, f.small, s, (x, 5), color, right=True) + 18
        # pages
        tabs_y, tabs_h = strip, f.line + 18
        x = 12
        for i, p in enumerate(self.pages):
            w = f.mono.size(p.title)[0] + 24
            if i == self.page:
                G.box(surf, pygame.Rect(x, tabs_y + 6, w, tabs_h - 8), T.PANEL, 6, T.EMBER)
            G.text(surf, f.mono, p.title, (x + 12, tabs_y + 10), T.EMBER_BRIGHT if i == self.page else T.MUTED)
            x += w + 6
        pygame.draw.line(surf, T.BORDER, (0, tabs_y + tabs_h + 2), (W, tabs_y + tabs_h + 2))
        # hint bar
        bar_h = f.small_line + 14
        area = pygame.Rect(0, tabs_y + tabs_h + 6, W, H - (tabs_y + tabs_h + 6) - bar_h)
        self.pages[self.page].draw(surf, f, area)
        if self.stack:
            veil = pygame.Surface(area.size, pygame.SRCALPHA)
            veil.fill((*T.BG, 190))
            surf.blit(veil, area.topleft)
            self.stack[-1].draw(surf, f, area)
        pygame.draw.rect(surf, T.BAR, (0, H - bar_h, W, bar_h))
        x = 12
        hints = list(self.current.hints) + ([] if self.stack else [("L/R", "page")])
        for button, label in hints:
            x += G.text(surf, f.small, button, (x, H - bar_h + 7), T.EMBER_BRIGHT) + 6
            x += G.text(surf, f.small, label, (x, H - bar_h + 7), T.MUTED) + 18
        if self.toast_text:
            w = min(W - 40, f.small.size(self.toast_text)[0] + 32)
            r = pygame.Rect((W - w) // 2, H - bar_h - f.line - 22, w, f.line + 10)
            G.box(surf, r, T.PANEL, 8, T.ERROR if self.toast_error else T.EMBER)
            G.text(surf, f.small, G.fit(f.small, self.toast_text, w - 24), (r.centerx, r.y + 8),
                   T.ERROR if self.toast_error else T.TEXT, center=True)
        self.dirty = False
