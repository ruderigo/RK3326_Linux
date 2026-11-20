"""Survey: every Wi-Fi access point the card can hear, and how crowded each channel is.

This only listens to what access points announce about themselves, the same
information any phone shows when it lists networks, with the channel and the
address added. Nothing is sent to them.
"""
import threading

import pygame

from .. import gfx as G
from .. import theme as T
from ..widgets import ListView, Menu
from .base import Page

REFRESH = 15            # seconds between looks


class SurveyPage(Page):
    title, icon = "Survey", "survey"
    hints = [("A", "details"), ("X", "look again"), ("Y", "save"), ("B", "close")]

    def __init__(self, app):
        super().__init__(app)
        self.list, self.busy, self.age, self.seen = ListView(), False, REFRESH, False

    def enter(self):
        self.look()

    def look(self):
        if self.busy:
            return
        self.busy = True

        def job():
            self.list.set(self.app.system.survey())
            self.busy, self.age, self.seen = False, 0, True
            self.app.dirty = True
        threading.Thread(target=job, daemon=True).start()

    def tick(self):
        self.age += 1
        if self.age >= REFRESH:
            self.look()

    def save(self):
        lines = [f"Wi-Fi survey, {len(self.list.items)} access points", ""]
        lines += [f"{n['signal']:>3}%  ch {n['channel']:<3} {n['bssid']}  {n['security']:<12} {n['ssid']}" for n in self.list.items]
        path = self.app.system.save_report("survey", "\n".join(lines) + "\n")
        self.app.toast(f"Saved to {path}" if path else "Could not save", 5, error=not path)

    def handle(self, action):
        if self.list.move(action):
            return
        n = self.list.current
        if action == "x":
            self.look()
        elif action == "y" and self.list.items:
            self.save()
        elif action == "a" and n:
            band = "2.4 GHz" if n["freq"] < 3000 else "5 GHz"
            self.app.push(Menu(self.app, n["ssid"], [("Close", None)],
                               f"Channel {n['channel']} ({n['freq']} MHz, {band}). Signal {n['signal']}%. "
                               f"Security: {n['security']}. Address {n['bssid']}."))

    def draw(self, surf, f, area):
        nets = self.list.items
        # how many access points sit on each 2.4 GHz channel, and the strongest of them
        chart = pygame.Rect(area.x + 14, area.y + 6, area.w - 28, f.line * 3 + 12)
        G.box(surf, chart, T.PANEL, 8, T.BORDER)
        per = {}
        for n in nets:
            if n["freq"] < 3000 and 1 <= n["channel"] <= 13:
                c = per.setdefault(n["channel"], [0, 0])
                c[0], c[1] = c[0] + 1, max(c[1], n["signal"])
        top = max([c[0] for c in per.values()] + [1])
        slot = (chart.w - 24) // 13
        base = chart.bottom - f.small_line - 4
        for ch in range(1, 14):
            x = chart.x + 12 + (ch - 1) * slot
            G.text(surf, f.small, str(ch), (x + slot // 2, base + 2), T.MUTED if ch in per else T.DIM, center=True)
            if ch in per:
                h = max(4, int((base - chart.y - 12 - f.small_line) * per[ch][0] / top))
                strong = per[ch][1] >= 60
                pygame.draw.rect(surf, T.EMBER_BRIGHT if strong else T.EMBER, (x + 4, base - h, slot - 8, h), border_radius=3)
                G.text(surf, f.small, str(per[ch][0]), (x + slot // 2, base - h - f.small_line), T.TEXT, center=True)
        other = sum(1 for n in nets if n["freq"] >= 3000)
        status = "looking…" if self.busy else f"{len(nets)} access points" + (f", {other} on 5 GHz" if other else "")
        G.text(surf, f.small, status, (area.right - 16, chart.bottom + 4), T.MUTED, right=True)
        G.text(surf, f.small, "2.4 GHz channels", (area.x + 16, chart.bottom + 4), T.DIM)
        lst = pygame.Rect(area.x + 12, chart.bottom + f.small_line + 10, area.w - 24, area.bottom - chart.bottom - f.small_line - 12)
        if not nets:
            msg = "Looking for access points…" if self.busy or not self.seen else "Nothing heard. Is a Wi-Fi card plugged in?"
            G.text(surf, f.mono, msg, (lst.x + 8, lst.y + 8), T.MUTED)
            return
        self.list.draw(surf, f, lst, self.row)

    def row(self, surf, f, r, n, selected):
        name_w = r.w - f.base * 13
        G.text(surf, f.mono, G.fit(f.mono, n["ssid"], name_w), (r.x + 10, r.y + 5),
               T.OK if n["active"] else (T.EMBER_BRIGHT if selected else T.TEXT))
        G.text(surf, f.small, f"ch {n['channel']}", (r.right - f.base * 12, r.y + 9), T.MUTED)
        sec = "open" if n["security"] == "open" else n["security"].split()[-1]
        G.text(surf, f.small, sec, (r.right - f.base * 8 - 8, r.y + 9), T.ERROR if sec == "open" else T.MUTED)
        G.meter(surf, pygame.Rect(r.right - f.base * 4, r.y + 10, f.base * 4 - 12, f.small_line - 8), n["signal"] / 100)
