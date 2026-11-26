"""SYSTEM: sound, screen, power, and what this handheld is running."""
import time

import pygame

from .. import gfx as G
from .osupdate import OsUpdatePage
from .. import theme as T
from ..widgets import ListView, TextView
from .base import Page


class SystemPage(Page):
    title, icon = "Settings", "settings"
    hints = [("←→", "adjust"), ("A", "choose"), ("B", "close")]

    share_job = None                # asking for the part of the card a computer reads
    share_said, share_at = "", 0.0

    def __init__(self, app):
        super().__init__(app)
        self.list = ListView()
        self.enter()

    @property
    def live(self):
        return SystemPage.share_job is not None

    def poll(self):
        job = SystemPage.share_job
        if not job:
            return
        if not job.done:
            # it can take a minute (the exFAT tools are fetched): say so the
            # whole time, or it looks finished and a restart cuts it short
            said = [ln.split(": ", 1)[-1] for ln in job.lines if ln.startswith("rk-share: ")]
            text = "Preparing the card. Wait, do not restart yet. " + (said[-1] if said else "")
            if text != self.share_said or time.time() - self.share_at >= 1:
                self.share_said, self.share_at = text, time.time()
                self.app.toast(text.strip(), 3)
            return
        SystemPage.share_job = None
        said = [ln.split(": ", 1)[-1] for ln in job.lines if ln.startswith("rk-share: ")]
        self.enter()
        if job.ok:
            self.app.confirm("Restart now?", "The card is changed while the handheld starts: a few minutes. "
                             "Plug the charger in and do not switch off.", "Restart", self.restart)
        else:
            self.app.toast(said[-1] if said else "Could not prepare the card", 8, error=True)

    def share(self):
        if SystemPage.share_job:
            return
        SystemPage.share_job = self.app.system.share_request()
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
        if s.mouse_enabled() is not None:
            rows.append({"name": "Left-stick mouse", "on": s.mouse_enabled, "flip": s.set_mouse})
        share = s.share_state()
        if SystemPage.share_job:
            rows.append({"name": "Preparing the card… wait", "do": lambda: None})
        elif share == "none":
            # /data fills the card: a computer shows only the boot files
            rows.append({"name": "Show the card on a computer", "do": lambda: self.app.confirm(
                "Show the card on a computer?",
                "Makes a part of the card that a Mac or PC opens, for games and app packages. "
                "/data becomes 16 GB; what is in it is kept. Done at the next restart.", "Prepare", self.share)})
        elif share == "requested":
            rows.append({"name": "Card: changed at the next restart", "do": lambda: self.app.confirm(
                "Restart now?", "A few minutes. Plug the charger in and do not switch off.", "Restart", self.restart)})
        rows += [{"name": "Update this handheld", "do": lambda: self.app.push(OsUpdatePage(self.app))},
                 {"name": "About this handheld", "do": self.about},
                 {"name": "Restart", "do": lambda: self.app.confirm("Restart?", "The handheld starts again.", "Restart", self.restart)},
                 {"name": "Power off", "do": lambda: self.app.confirm("Power off?", "Press the power button to start it again.",
                                                                     "Power off", self.power_off)}]
        self.list.set(rows)

    def busy(self):
        """True, with a word to the owner, while the card is being prepared: a restart now would cut it short."""
        if SystemPage.share_job and not SystemPage.share_job.done:
            self.app.toast("The card is being prepared. Wait for it to finish.", 5, error=True)
            return True
        return False

    def restart(self):
        if self.busy():
            return
        self.app.toast("Restarting…", 30)
        self.app.system.restart()

    def power_off(self):
        if self.busy():
            return
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
        spare = s.memory_spare()
        if spare is not None:
            lines.insert(-2, f"           {spare} MB to spare (with compressed swap)")
        for st in s.storage():
            lines.append(f"{st['label']:<11}{G.size(st['used'])} of {G.size(st['total'])} used, "
                         f"{G.size(st['total'] - st['used'])} free")
        for _, text in s.health():
            lines += ["", "! " + text]
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
        elif "flip" in it and action in ("a", "left", "right"):
            it["flip"](not it["on"]())
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
        elif "on" in it:
            state = it["on"]()
            G.text(surf, f.mono, "On" if state else "Off",
                   (r.right - 14, r.y + 5), T.OK if state else T.MUTED, right=True)
