"""Colours and fonts.

The palette is the Stump ecosystem's "Amber" theme, the one FireFly uses, so
the system and its apps look like one product. Fonts are DejaVu (Debian
package fonts-dejavu-core).
"""
import os
import pygame

BG = (0x1b, 0x15, 0x12)
PANEL = (0x2a, 0x21, 0x19)
BAR = (0x22, 0x1b, 0x15)
ROW = (0x2f, 0x27, 0x1e)
BORDER = (0x49, 0x3c, 0x2e)
EMBER = (0xd9, 0x7a, 0x3a)
EMBER_BRIGHT = (0xf0, 0xa0, 0x50)
TEXT = (0xec, 0xdf, 0xc8)
MUTED = (0x9c, 0x8d, 0x76)
DIM = (0x7d, 0x71, 0x5f)
ERROR = (0xe0, 0x7a, 0x5a)      # the only red: something went wrong
OK = (0x9c, 0xb8, 0x76)         # connected, ready

FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF"]


def _find(name):
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


class Fonts:
    def __init__(self, screen_h):
        base = max(13, screen_h // 30)                  # 24 px on a 720-line screen
        mono, bold, sans = _find("DejaVuSansMono.ttf"), _find("DejaVuSansMono-Bold.ttf"), _find("DejaVuSans.ttf")
        self.base = base
        self.mono = pygame.font.Font(mono, base)
        self.small = pygame.font.Font(mono, max(11, base * 3 // 4))
        self.big = pygame.font.Font(bold or mono, base * 5 // 4)
        self.title = pygame.font.Font(bold or mono, base * 7 // 4)
        self.clock = pygame.font.Font(bold or mono, base * 4)
        self.body = pygame.font.Font(sans or mono, base)
        self.line = self.mono.get_linesize()
        self.small_line = self.small.get_linesize()
