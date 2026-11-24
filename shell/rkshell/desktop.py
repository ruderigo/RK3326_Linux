"""The desktop: a wallpaper, a clock, and a dock whose icons grow under the cursor.

Everything is drawn by code, so there are no picture files to ship: the
wallpaper is a dusk sky with drifting fireflies, the icons are simple shapes
in the Amber palette.
"""
import math
import random
import time

import pygame

from . import gfx as G
from . import theme as T

ICON_PX = 192                      # icons are drawn once at this size, then scaled


# ------------------------------------------------------------------ wallpaper
class Wallpaper:
    def __init__(self, target, seed=7):
        """`target` is the surface it will be drawn on: the wallpaper is kept in
        the same pixel format, so putting it up is a plain copy."""
        self.size = size = target.get_size()
        w, h = size
        self.base = pygame.Surface(size, 0, target)
        top, mid, low = (0x0c, 0x0a, 0x10), (0x2a, 0x18, 0x14), (0x8a, 0x40, 0x1c)
        for y in range(h):                                    # dusk: dark above, embers at the horizon
            t = y / (h - 1)
            a, b, u = (top, mid, t / 0.6) if t < 0.6 else (mid, low, (t - 0.6) / 0.4)
            pygame.draw.line(self.base, tuple(int(a[i] + (b[i] - a[i]) * u) for i in range(3)), (0, y), (w, y))
        rnd = random.Random(seed)
        hill = [(0, h)]                                       # a line of trees against the glow
        x = 0
        while x <= w:
            hill.append((x, h - int(h * 0.20) - rnd.randint(0, h // 14) - int(math.sin(x / w * math.pi) * h * 0.05)))
            x += rnd.randint(w // 60, w // 24)
        hill += [(w, hill[-1][1]), (w, h)]
        pygame.draw.polygon(self.base, (0x12, 0x0d, 0x0b), hill)
        self.flies = [{"x": rnd.uniform(0, w), "y": rnd.uniform(h * 0.22, h * 0.78), "r": rnd.uniform(2.0, 4.5),
                       "phase": rnd.uniform(0, 6.28), "speed": rnd.uniform(0.4, 1.1), "drift": rnd.uniform(-6, 6)}
                      for _ in range(20)]
        self.glow = {}

    LEVELS = 6

    def _glow(self, radius, level):
        """A firefly's light at one of a few brightness levels, as a plain
        picture on black that is added to the sky: adding is much cheaper on
        the handheld than blending a transparent picture."""
        key = (int(radius * 2), level)
        if key not in self.glow:
            d = key[0] * 6
            k = level / self.LEVELS
            s = pygame.Surface((d, d), 0, self.base)
            s.fill((0, 0, 0))
            for i in range(d // 2, 0, -1):
                a = 0.42 * (1 - i / (d / 2)) ** 2 * k
                pygame.draw.circle(s, (int(0xf0 * a), int(0xb0 * a), int(0x50 * a)), (d // 2, d // 2), i)
            pygame.draw.circle(s, (int(0xff * k), int(0xe0 * k), int(0x90 * k)), (d // 2, d // 2), max(1, key[0] // 2))
            self.glow[key] = s
        return self.glow[key]

    def draw(self, surf, t):
        surf.blit(self.base, (0, 0))
        w, h = self.size
        for f in self.flies:
            pulse = 0.5 + 0.5 * math.sin(t * f["speed"] + f["phase"])
            level = int(pulse * self.LEVELS + 0.5)
            if level < 1:
                continue
            x = (f["x"] + f["drift"] * t) % w
            y = f["y"] + math.sin(t * 0.3 + f["phase"]) * 10
            g = self._glow(f["r"], level)
            surf.blit(g, (x - g.get_width() // 2, y - g.get_height() // 2), special_flags=pygame.BLEND_RGB_ADD)


# ---------------------------------------------------------------------- icons
def _tile():
    s = pygame.Surface((ICON_PX, ICON_PX), pygame.SRCALPHA)
    r = pygame.Rect(6, 6, ICON_PX - 12, ICON_PX - 12)
    pygame.draw.rect(s, (*T.PANEL, 235), r, border_radius=40)
    pygame.draw.rect(s, T.BORDER, r, width=3, border_radius=40)
    return s


def _files(s, c):
    pygame.draw.rect(s, c, (44, 62, 46, 22), border_radius=8)
    pygame.draw.rect(s, c, (44, 74, 104, 62), border_radius=10)
    pygame.draw.rect(s, T.PANEL, (52, 92, 88, 6))


def _network(s, c):
    for r, wd in ((62, 10), (42, 10), (22, 10)):
        pygame.draw.arc(s, c, (96 - r, 118 - r, 2 * r, 2 * r), math.radians(40), math.radians(140), wd)
    pygame.draw.circle(s, c, (96, 122), 9)


def _devices(s, c):
    pygame.draw.rect(s, c, (70, 52, 52, 60), border_radius=8)       # a USB plug
    pygame.draw.rect(s, T.PANEL, (82, 62, 10, 14))
    pygame.draw.rect(s, T.PANEL, (100, 62, 10, 14))
    pygame.draw.rect(s, c, (80, 112, 32, 16))
    pygame.draw.rect(s, c, (91, 128, 10, 22))


def _settings(s, c):
    for y, knob in ((66, 118), (96, 74), (126, 104)):               # three sliders
        pygame.draw.rect(s, c, (48, y - 4, 96, 8), border_radius=4)
        pygame.draw.circle(s, T.PANEL, (knob, y), 14)
        pygame.draw.circle(s, c, (knob, y), 11)


def _terminal(s, c):
    pygame.draw.lines(s, c, False, [(54, 70), (86, 96), (54, 122)], 12)
    pygame.draw.rect(s, c, (98, 116, 44, 11), border_radius=4)


def _firefly(s, c):
    for r, a in ((46, 40), (34, 70), (22, 120)):
        g = pygame.Surface((ICON_PX, ICON_PX), pygame.SRCALPHA)
        pygame.draw.circle(g, (0xf0, 0xb0, 0x50, a), (96, 108), r)
        s.blit(g, (0, 0))
    pygame.draw.circle(s, (0xff, 0xe8, 0xa0), (96, 108), 14)
    pygame.draw.ellipse(s, c, (58, 58, 34, 22))
    pygame.draw.ellipse(s, c, (100, 58, 34, 22))


def _stump(s, c):
    pygame.draw.rect(s, c, (56, 88, 80, 48), border_radius=6)        # a cut tree, seen from the side
    pygame.draw.ellipse(s, T.EMBER_BRIGHT, (50, 62, 92, 44))
    for r in (30, 18, 7):
        pygame.draw.ellipse(s, T.PANEL, (96 - r, 84 - r * 0.45, 2 * r, r * 0.9), 3)


def _chip(s, c):
    pygame.draw.rect(s, c, (62, 62, 68, 68), border_radius=8)
    pygame.draw.rect(s, T.PANEL, (80, 80, 32, 32), border_radius=4)
    for i in range(4):
        o = 68 + i * 18
        for x, y, w, h in ((o, 46, 6, 14), (o, 132, 6, 14), (46, o, 14, 6), (132, o, 14, 6)):
            pygame.draw.rect(s, c, (x, y, w, h))


def _radar(s, c):
    for r in (58, 38, 18):
        pygame.draw.circle(s, c, (96, 100), r, 6)
    pygame.draw.line(s, c, (96, 100), (140, 60), 8)
    pygame.draw.circle(s, T.EMBER_BRIGHT if c != T.DIM else c, (124, 122), 9)


def _survey(s, c):
    for i, h in enumerate((24, 44, 64, 84)):                        # signal bars
        pygame.draw.rect(s, c, (46 + i * 28, 140 - h, 18, h), border_radius=4)


def _ember(s, c):
    bright = T.EMBER_BRIGHT if c != T.DIM else c
    pygame.draw.polygon(s, c, [(96, 34), (130, 92), (124, 128), (96, 150),
                               (68, 128), (62, 92)])          # outer flame
    pygame.draw.polygon(s, bright, [(96, 72), (114, 110), (96, 140), (78, 110)])  # inner flame


def _update(s, c):
    """An arrow coming down into a tray: something new arriving."""
    pygame.draw.polygon(s, c, [(84, 40), (108, 40), (108, 88), (132, 88), (96, 128), (60, 88), (84, 88)])
    pygame.draw.lines(s, c, False, [(48, 118), (48, 150), (144, 150), (144, 118)], 10)


def _sound(s, c):
    """A loudspeaker with two waves."""
    pygame.draw.polygon(s, c, [(46, 80), (70, 80), (100, 52), (100, 140), (70, 112), (46, 112)])
    pygame.draw.arc(s, c, (88, 66, 44, 60), -1.0, 1.0, 9)
    pygame.draw.arc(s, c, (88, 44, 76, 104), -1.0, 1.0, 9)


def _video(s, c):
    """A screen with a play triangle."""
    pygame.draw.rect(s, c, (42, 52, 108, 82), width=9, border_radius=12)
    pygame.draw.polygon(s, c, [(84, 74), (84, 112), (116, 93)])
    pygame.draw.rect(s, c, (72, 142, 48, 9), border_radius=4)


def _games(s, c):
    """A pad: a cross on the left, two buttons on the right."""
    pygame.draw.rect(s, c, (36, 62, 120, 68), border_radius=30)
    pygame.draw.rect(s, T.PANEL, (56, 91, 34, 10))
    pygame.draw.rect(s, T.PANEL, (68, 79, 10, 34))
    pygame.draw.circle(s, T.PANEL, (116, 104), 8)
    pygame.draw.circle(s, T.PANEL, (134, 88), 8)


GLYPHS = {"radar": _radar, "video": _video, "games": _games, "sound": _sound, "survey": _survey, "files": _files, "network": _network, "devices": _devices, "settings": _settings, "terminal": _terminal, "ember": _ember, "update": _update,
          "firefly": _firefly, "stump": _stump, "chip": _chip}
_icons, _scaled = {}, {}


def icon(name, label, size, dim=False):
    """The icon `name` at `size` pixels; an unknown name gives the label's first letter."""
    key = (name if name in GLYPHS else "letter:" + label[:1].upper(), dim)
    if key not in _icons:
        s = _tile()
        color = T.DIM if dim else T.EMBER_BRIGHT
        if name in GLYPHS:
            GLYPHS[name](s, color)
        else:
            font = pygame.font.Font(T._find("DejaVuSansMono-Bold.ttf") or T._find("DejaVuSansMono.ttf"), 96)
            img = font.render(label[:1].upper(), True, color)
            s.blit(img, img.get_rect(center=(96, 98)))
        _icons[key] = s
    size -= size % 2                    # scaling is slow on the handheld: keep each size once it is made
    scaled = _scaled.get((key, size))
    if scaled is None:
        if len(_scaled) > 500:
            _scaled.clear()
        scaled = _scaled[(key, size)] = pygame.transform.smoothscale(_icons[key], (size, size))
    return scaled


# ----------------------------------------------------------------------- dock
class Dock:
    """A row of icons at the bottom. The one under the cursor is the largest
    and its neighbours grow with it, as in a desktop dock; the row slides so
    the cursor stays in view when there are more icons than fit.

    The cursor is the d-pad's selection, or the pointer while it is over the
    dock: then the icon under it is the selected one, the row grows around
    the pointer and stays put under it, and resting the pointer near the left
    or right edge of the screen brings in the icons that did not fit."""

    def __init__(self):
        self.items, self.sel, self.pos = [], 0, 0.0        # pos follows sel smoothly
        self.last, self.shelves = time.time(), {}
        self.hover = False          # the pointer is choosing
        self.scrolling = False      # ...and is at an edge, bringing more icons in
        self.px, self.size = 0, (720, 720)
        self.row_x = 0.0            # while hovering: where the row would start with no icon grown
        self.over = 0.0             # how far past the first or last icon's middle the pointer is, in icons
        self.slip = 0.0             # eases the row between the d-pad's place for it and the pointer's
        self.x0 = None              # where the row was last drawn...
        self.drawn = []             # ...and each icon in it: (x, size)

    def set(self, items):
        self.items = items
        self.sel = min(self.sel, max(0, len(items) - 1))

    def move(self, step):
        if self.items:
            self.sel = (self.sel + step) % len(self.items)

    @property
    def current(self):
        return self.items[self.sel] if self.items else None

    @property
    def moving(self):
        if abs(self.slip) > 0.5:
            return True
        return self.scrolling if self.hover else abs(self.pos - self.sel) > 0.01

    # ---------------------------------------------------------- the pointer
    @staticmethod
    def metrics(size):
        """base and grown icon size, the gap, the line the icons stand on."""
        W, H = size
        return W // 10, int(W / 5.5), W // 60, H - W // 28      # 72 and 130 px on a 720 screen

    def top(self, size):
        """Below this line the pointer is over the dock."""
        base, big, gap, floor = self.metrics(size)
        return floor - big - gap

    def span(self):
        """Width of the row with no icon grown, and the range its start may have."""
        W = self.size[0]
        base, _, gap, _ = self.metrics(self.size)
        n = len(self.items)
        width = n * base + (n - 1) * gap
        if width <= W - 40:
            return width, (W - width) / 2, (W - width) / 2
        return width, W - 20 - width, 20

    def point(self, pos, size):
        """Where the pointer is (None: hidden, or a window is open)."""
        self.size = size
        was = self.hover
        base, _, gap, _ = self.metrics(size)
        width, lo, hi = self.span()
        self.hover = bool(pos and self.items and pos[1] >= self.top(size))
        if self.hover:
            self.px = pos[0]
            if not was:
                # start from the icon that is under the pointer as drawn now
                at = None
                for i, (x, s) in enumerate(self.drawn):
                    if x - gap / 2 <= self.px < x + s + gap / 2:
                        at = i + (self.px - x + gap / 2) / (s + gap)
                        break
                if at is None and self.drawn and lo == hi:
                    self.hover = False              # beside a row that fits: not on it
                elif at is None:
                    at = 0 if self.drawn and self.px < self.drawn[0][0] else len(self.items)
                if self.hover:
                    self.row_x = max(lo, min(hi, self.px + gap / 2 - at * (base + gap)))
            elif lo == hi and not (lo - gap <= self.px <= lo + width + gap):
                self.hover = False
        if self.hover:
            self.track()
        else:
            self.scrolling = False
        if was != self.hover:
            self.slip = None                        # worked out at the next draw

    def track(self):
        """The icon under the pointer becomes the selected one."""
        base, _, gap, _ = self.metrics(self.size)
        n = len(self.items)
        at = (self.px + gap / 2 - self.row_x) / (base + gap) - 0.5      # 0 on the first icon's middle
        self.pos = max(0.0, min(n - 1.0, at))
        self.over = max(-0.5, min(0.5, at - self.pos))
        self.sel = int(self.pos + 0.5)

    def step(self):
        """Advance the animation. It goes by the clock, not by frames, so the
        cursor arrives in the same time however fast the handheld draws."""
        now = time.time()
        dt, self.last = min(0.2, now - self.last), now
        if self.slip:
            self.slip *= math.exp(-dt * 14)
            if abs(self.slip) < 0.5:
                self.slip = 0.0
        if self.hover:
            W = self.size[0]
            base, _, gap, _ = self.metrics(self.size)
            _, lo, hi = self.span()
            edge = W // 7
            push = 0.0                              # -1..1: how hard the pointer leans on an edge
            if self.px < edge and self.row_x < hi:
                push = 1 - self.px / edge
            elif self.px > W - edge and self.row_x > lo:
                push = -(1 - (W - 1 - self.px) / edge)
            self.scrolling = push != 0
            if push:
                speed = (base + gap) * (1.5 + 5 * abs(push))        # icons a second: slow at the zone's start
                self.row_x = max(lo, min(hi, self.row_x + speed * dt * (1 if push > 0 else -1)))
                self.track()
            return
        d = self.sel - self.pos
        self.pos = self.sel if abs(d) < 0.01 else self.pos + d * (1 - math.exp(-dt * 14))

    def draw(self, surf, f):
        W, H = surf.get_size()
        base, big, gap, floor = self.metrics((W, H))
        sizes = []
        for i in range(len(self.items)):
            near = max(0.0, 1 - abs(i - self.pos) / 2.2)      # 1 under the cursor, 0 two icons away
            sizes.append(int(base + (big - base) * near * near))
        total = sum(sizes) + gap * (len(sizes) - 1)
        centre = sum(sizes[:int(self.pos)]) + gap * int(self.pos)
        frac = self.pos - int(self.pos)
        if int(self.pos) < len(sizes):
            centre += sizes[int(self.pos)] / 2 + (sizes[int(self.pos)] / 2 + gap + (sizes[min(int(self.pos) + 1, len(sizes) - 1)] / 2)) * frac
        if self.hover and sizes:    # the grown icon stays under the pointer
            x0 = self.px - centre - self.over * (sizes[self.sel] + gap)
        elif total <= W - 40:
            x0 = (W - total) // 2
        else:                       # more icons than fit: slide, but never past either end of the row
            x0 = max(W - 20 - total, min(20, W / 2 - centre))
        if self.slip is None:       # the pointer just took over, or let go: no jump
            self.slip = (self.x0 - x0) if self.x0 is not None else 0.0
        x0 = self.x0 = x0 + self.slip
        x0 = int(x0)
        self.drawn = []
        floor = H - W // 28
        shelf = pygame.Rect(max(10, x0 - 14), floor - base - 10, min(W - 20, total + 28), base + 20)
        shelf.w -= shelf.w % 8                              # a few widths only: each is drawn once and kept
        veil = self.shelves.get(shelf.size)
        if veil is None:
            if len(self.shelves) > 60:
                self.shelves.clear()
            veil = self.shelves[shelf.size] = pygame.Surface(shelf.size, pygame.SRCALPHA)
            pygame.draw.rect(veil, (*T.BAR, 170), veil.get_rect(), border_radius=22)
            pygame.draw.rect(veil, (*T.BORDER, 255), veil.get_rect(), width=1, border_radius=22)
        surf.blit(veil, shelf.topleft)
        x = x0
        for i, (it, s) in enumerate(zip(self.items, sizes)):
            self.drawn.append((x, s))
            surf.blit(icon(it.get("icon", ""), it["name"], s, dim=not it.get("ready", True)), (x, floor - s))
            G.spot((x, floor - s, s, s), lambda i=i: setattr(self, "sel", i))
            if i == self.sel:
                label = (f"{it['name']} (not installed)" if not it.get("ready", True)
                         else f"{it['name']} (set up)" if it.get("needs_setup") else it["name"])
                tw = f.mono.size(label)[0] + 28
                r = pygame.Rect(0, 0, tw, f.line + 10)
                r.centerx = max(tw // 2 + 8, min(W - tw // 2 - 8, x + s // 2))
                r.bottom = floor - s - 12
                G.box(surf, r, T.PANEL, 10, T.EMBER)
                G.text(surf, f.mono, label, (r.centerx, r.y + 5), T.EMBER_BRIGHT, center=True)
                pygame.draw.circle(surf, T.EMBER_BRIGHT, (x + s // 2, floor + W // 80), W // 180)
            x += s + gap
