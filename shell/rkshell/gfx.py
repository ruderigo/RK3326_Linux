"""Small drawing helpers."""
import pygame
from . import theme as T


_rendered = {}


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
