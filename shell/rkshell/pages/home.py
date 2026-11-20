"""HOME: the handheld at a glance, and everything it can start.

Apps are not built in. An app adds itself by putting a small JSON file in
/usr/share/rk/apps (see System.apps), and shows here under its group.
"""
import pygame

from .. import gfx as G
from .. import theme as T
from ..widgets import ListView
from .base import Page


class HomePage(Page):
    title = "HOME"
    hints = [("A", "open")]

    def __init__(self, app):
        super().__init__(app)
        self.list = ListView(row_lines=2)
        self.enter()

    def enter(self):
        rows, group = [], None
        for a in sorted(self.app.system.apps(), key=lambda a: (a.get("group", "Apps"), a["name"])):
            if a.get("group", "Apps") != group:
                group = a.get("group", "Apps")
                rows.append({"heading": group})
            rows.append(a)
        self.list.set(rows)
        if rows and "heading" in rows[self.list.sel]:
            self.list.move("down", lambda it: "heading" not in it)

    def tick(self):
        self.enter()

    def handle(self, action):
        if self.list.move(action, lambda it: "heading" not in it):
            return
        if action == "a" and self.list.current and "heading" not in self.list.current:
            a = self.list.current
            if a.get("ready") and a.get("exec"):
                self.app.launch = a["exec"]
            elif a.get("ready"):
                self.app.toast(f"{a['name']} would open here (demo)")
            else:
                self.app.toast(f"{a['name']} is not installed yet", error=True)

    def draw(self, surf, f, area):
        s = self.app.system
        # the handheld at a glance
        card = pygame.Rect(area.x + 12, area.y + 8, area.w - 24, f.line * 3 + 26)
        G.box(surf, card, T.PANEL, 8, T.BORDER)
        G.text(surf, f.title, s.hostname(), (card.x + 16, card.y + 10), T.EMBER_BRIGHT)
        wifi = s.wifi()
        if wifi and wifi["state"] == "connected":
            net, color = f"{wifi['ssid']}  {wifi['address']}", T.OK
        elif wifi:
            net, color = "Wi-Fi card ready, not connected", T.MUTED
        else:
            net, color = "No Wi-Fi card plugged in", T.MUTED
        G.text(surf, f.small, G.fit(f.small, net, card.w // 2 - 24), (card.x + 16, card.y + 18 + f.line * 2 - 6), color)
        col = card.x + card.w // 2
        used, total = s.memory()
        rows = [("Memory", used / total if total else 0, f"{used} of {total} MB")]
        for st in s.storage():
            if st["mount"] == "/data":
                rows.append(("Data", st["used"] / st["total"], f"{G.size(st['total'] - st['used'])} free"))
        bat = s.battery()
        if bat and bat["percent"] >= 0:
            rows.append(("Battery", bat["percent"] / 100, f"{bat['percent']}%"))
        y = card.y + 12
        for label, frac, note in rows[:3]:
            G.text(surf, f.small, label, (col, y), T.MUTED)
            G.meter(surf, pygame.Rect(col + f.base * 4, y + 3, f.base * 4, f.small_line - 6), frac)
            G.text(surf, f.small, note, (col + f.base * 8 + 10, y), T.TEXT)
            y += f.small_line + 6
        # what it can start
        lst = pygame.Rect(area.x + 12, card.bottom + 12, area.w - 24, area.bottom - card.bottom - 16)
        if not self.list.items:
            G.text(surf, f.mono, "No apps installed yet.", (lst.x + 8, lst.y + 8), T.MUTED)
            G.text(surf, f.small, "Apps appear here when they are installed.", (lst.x + 8, lst.y + 12 + f.line), T.DIM)
            return
        self.list.draw(surf, f, lst, self.row)

    def row(self, surf, f, r, it, selected):
        if "heading" in it:
            G.text(surf, f.small, it["heading"].upper(), (r.x + 6, r.bottom - f.small_line - 6), T.DIM)
            return
        G.text(surf, f.big, it["name"], (r.x + 14, r.y + 6), T.EMBER_BRIGHT if selected else T.TEXT)
        G.text(surf, f.small, G.fit(f.small, it.get("about", ""), r.w - 28), (r.x + 14, r.y + 10 + f.line), T.MUTED)
        if not it.get("ready"):
            G.text(surf, f.small, "not installed", (r.right - 14, r.y + 10), T.DIM, right=True)
