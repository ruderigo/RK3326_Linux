"""Small drawing helpers."""
import pygame
from . import theme as T


_rendered = {}

# ------------------------------------------------------------------ pointer
# What the pointer can press. Whatever draws something pressable says where it
# is (spot) while it draws; App.draw empties the list before each picture, so
# it always matches what is on the screen.
spots = []


def spot(rect, select=None, press=None):
    """`rect` can be pressed with the pointer. `select` moves the selection
    there (as the d-pad would); then `press` runs, or A's action if None."""
    spots.append((pygame.Rect(rect), select, press))


def spot_at(pos):
    for s in reversed(spots):                   # what was drawn last is on top
        if s[0].collidepoint(pos):
            return s
    return None


_cursors = {}


def cursor(size):
    """The pointer: an arrow `size` pixels tall, its tip at the top left."""
    img = _cursors.get(size)
    if img is None:
        k = 4                                   # drawn large, scaled down: smooth edges
        big = pygame.Surface((size * k, size * k), pygame.SRCALPHA)
        shape = [(0.04, 0.03), (0.04, 0.80), (0.24, 0.62), (0.39, 0.95), (0.53, 0.89), (0.38, 0.57), (0.66, 0.57)]
        pts = [(x * size * k, y * size * k) for x, y in shape]
        pygame.draw.polygon(big, T.EMBER_BRIGHT, pts)
        pygame.draw.polygon(big, T.BG, pts, width=max(2, size * k // 14))
        img = _cursors[size] = pygame.transform.smoothscale(big, (size, size))
    return img


def text(surf, font, s, pos, color=T.TEXT, right=False, center=False):
    # Drawing a string is the slow part on the handheld and most strings are
    # the same from one frame to the next, so rendered strings are kept.
    key = (id(font), s, color)
    img = _rendered.get(key)
    if img is None:
        if len(_rendered) > 400:
            _rendered.clear()
        img = _rendered[key] = font.render(s, True, color)
    x, y = pos
    if right:
        x -= img.get_width()
    elif center:
        x -= img.get_width() // 2
    surf.blit(img, (x, y))
    return img.get_width()


def box(surf, rect, color, radius=6, border=None):
    pygame.draw.rect(surf, color, rect, border_radius=radius)
    if border:
        pygame.draw.rect(surf, border, rect, width=1, border_radius=radius)


def fit(font, s, width):
    """The string, cut with an ellipsis when it is wider than `width` pixels."""
    if font.size(s)[0] <= width:
        return s
    while s and font.size(s + "…")[0] > width:
        s = s[:-1]
    return s + "…"


def wrap(font, s, width):
    out = []
    for para in s.split("\n"):
        line = ""
        for word in para.split(" "):
            cand = word if not line else line + " " + word
            if font.size(cand)[0] <= width:
                line = cand
            else:
                if line:
                    out.append(line)
                line = word
        out.append(line)
    return out


def meter(surf, rect, fraction, color=T.EMBER):
    """A horizontal bar filled to `fraction` (0..1)."""
    box(surf, rect, T.BAR, 4, T.BORDER)
    w = int((rect.w - 4) * max(0.0, min(1.0, fraction)))
    if w > 0:
        box(surf, pygame.Rect(rect.x + 2, rect.y + 2, w, rect.h - 4), color, 3)


def size(n):
    for unit in ("B", "K", "M", "G"):
        if n < 1024 or unit == "G":
            return f"{n:.0f}{unit}" if unit == "B" or n >= 10 else f"{n:.1f}{unit}"
        n /= 1024
