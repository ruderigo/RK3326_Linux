"""SYSTEM: sound, screen, power, and what this handheld is running."""
import pygame

from .. import gfx as G
from .. import theme as T
from ..widgets import ListView, TextView
from .base import Page


class SystemPage(Page):
    title, icon = "Settings", "settings"
    hints = [("←→", "adjust"), ("A", "choose"), ("B", "close")]

    def __init__(self, app):
        super().__init__(app)
        self.list = ListView()
        self.enter()

    def enter(self):
        s = self.app.system
        rows = []
        if s.volume() is not None:
            rows.append({"name": s.volume_name(), "get": s.volume, "set": s.set_volume})
        if s.mic() is not None:
            rows.append({"name": s.mic_name(), "get": s.mic, "set": s.set_mic})
        if s.brightness() is not None:
            rows.append({"name": "Brightness", "get": s.brightness, "set": s.set_brightness})
        rows += [{"name": "About this handheld", "do": self.about},
                 {"name": "Restart", "do": lambda: self.app.confirm("Restart?", "The handheld starts again.", "Restart", self.restart)},
                 {"name": "Power off", "do": lambda: self.app.confirm("Power off?", "Press the power button to start it again.",
                                                                     "Power off", self.power_off)}]
        self.list.set(rows)

    def restart(self):
        self.app.toast("Restarting…", 30)
        self.app.system.restart()

    def power_off(self):
        self.app.toast("Powering off…", 30)
        self.app.system.power_off()

    def about(self):
        s = self.app.system
        rel, boot = s.release(), s.boot_selection()
        used, total = s.memory()
        up = int(s.uptime())
        lines = [f"{rel['RK_NAME']} {rel['RK_VERSION']}", "",
                 f"Handheld   {boot.get('console') or rel.get('RK_CONSOLE') or 'unknown'}",
                 f"Kernel     {s.kernel()}",
                 f"Memory     {used} of {total} MB in use",
                 f"Running    {up // 3600} h {up % 3600 // 60} min", ""]
        for st in s.storage():
            lines.append(f"{st['label']:<11}{G.size(st['used'])} of {G.size(st['total'])} used")
        bat = s.battery()
        if bat and bat["percent"] >= 0:
            lines += ["", f"Battery    {bat['percent']}%, {bat['status'].lower()}"]
        self.app.push(TextView(self.app, "About this handheld", "\n".join(lines)))

    def handle(self, action):
        if self.list.move(action):
            return
        it = self.list.current
        if not it:
            return
        if "set" in it and action in ("left", "right"):
            it["set"]((it["get"]() or 0) + (5 if action == "right" else -5))
        elif "do" in it and action == "a":
            it["do"]()

    def draw(self, surf, f, area):
        self.list.draw(surf, f, pygame.Rect(area.x + 12, area.y + 10, area.w - 24, area.h - 16), self.row)

    def row(self, surf, f, r, it, selected):
        G.text(surf, f.mono, it["name"], (r.x + 14, r.y + 5), T.EMBER_BRIGHT if selected else T.TEXT)
        if "get" in it:
            v = it["get"]() or 0
            G.meter(surf, pygame.Rect(r.right - f.base * 12, r.y + 9, f.base * 9, f.line - 12), v / 100)
            G.text(surf, f.small, f"{v}%", (r.right - 14, r.y + 9), T.TEXT, right=True)
