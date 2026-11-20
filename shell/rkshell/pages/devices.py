"""DEVICES: what is plugged in, as it is plugged in."""
import pygame

from .. import gfx as G
from .. import theme as T
from ..widgets import ListView, Menu
from .base import Page


class DevicesPage(Page):
    title, icon = "Devices", "devices"
    hints = [("A", "details"), ("B", "close")]

    def __init__(self, app):
        super().__init__(app)
        self.list = ListView(row_lines=2)
        self.enter()

    def enter(self):
        self.list.set(self.app.system.usb_devices())

    def tick(self):                         # a device plugged in or pulled out shows within a second
        self.enter()

    def handle(self, action):
        if self.list.move(action):
            return
        d = self.list.current
        if action == "a" and d:
            self.app.push(Menu(self.app, d["name"], [("Close", None)],
                               f"{d['kind']}. USB id {d['id']}. Driver: {d['driver']}."))

    def draw(self, surf, f, area):
        lst = pygame.Rect(area.x + 12, area.y + 10, area.w - 24, area.h - 16)
        if not self.list.items:
            G.text(surf, f.mono, "Nothing plugged in.", (lst.x + 8, lst.y + 8), T.MUTED)
            for i, ln in enumerate(G.wrap(f.small, "Keyboards, Wi-Fi cards, radios and USB drives show here "
                                          "as soon as they are plugged in, alone or through a hub.", lst.w - 16)):
                G.text(surf, f.small, ln, (lst.x + 8, lst.y + 14 + f.line + i * f.small_line), T.DIM)
            return
        self.list.draw(surf, f, lst, self.row)

    def row(self, surf, f, r, d, selected):
        G.text(surf, f.big, d["kind"], (r.x + 14, r.y + 6), T.EMBER_BRIGHT if selected else T.TEXT)
        G.text(surf, f.small, G.fit(f.small, d["name"], r.w - 28), (r.x + 14, r.y + 10 + f.line), T.MUTED)
        ok = d["driver"] != "no driver"
        G.text(surf, f.small, "ready" if ok else "no driver", (r.right - 14, r.y + 10), T.OK if ok else T.ERROR, right=True)
