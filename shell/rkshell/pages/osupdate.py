"""Update this handheld: the OS's own version, and updating it in place.

rk-update replaces only the desktop and our system files — never the kernel,
/home or /data — and checks the new desktop draws before swapping it in, backs
up what it replaces, runs migrations, and rolls back by itself if the desktop
does not come back. So an update keeps the adopter's identity, apps and
settings. The handheld's password is asked because it writes system files.
"""
import threading

import pygame

from .. import gfx as G
from .. import theme as T
from ..system import same_version
from ..widgets import Keyboard
from .base import Page


class OsUpdatePage(Page):
    title = "Update this handheld"
    job = None                      # survives closing the window
    action = ""

    def __init__(self, app):
        super().__init__(app)
        self.info = {}
        self.view = "running" if OsUpdatePage.job else "info"
        self.told = False
        self.looking = False

    def enter(self):
        if self.view != "running":
            # what this card has is shown at once; the newest version is
            # asked of the network beside it, and fills in when it answers
            self.info = self.app.system.os_status()
            self.looking = True
            info = self.info

            def look():
                info["newest"] = self.app.system.os_newest()
                if info is self.info:
                    self.looking = False
                    self.app.dirty = True
            threading.Thread(target=look, daemon=True).start()

    @property
    def same(self):
        return same_version(self.info.get("installed"), self.info.get("newest"))

    @property
    def live(self):
        return self.view == "running" or self.looking

    @property
    def hints(self):
        if self.view == "running":
            job = OsUpdatePage.job
            return [("B", "back")] if job and job.done else [("B", "hide")]
        rows = [("A", "security updates" if self.same else "update now"), ("Y", "undo last update"), ("B", "close")]
        return rows

    def wants_back(self):
        return self.view == "running" and bool(OsUpdatePage.job and OsUpdatePage.job.done)

    def poll(self):
        job = OsUpdatePage.job
        if self.view == "running" and job:
            self.app.dirty = True
            if job.done and not self.told:
                self.told = True
                verb = "updated" if OsUpdatePage.action == "apply" else "rolled back"
                self.app.toast(f"The handheld was {verb}" if job.ok else "The update stopped", 5, error=not job.ok)

    def start(self, action):
        if not self.app.system.online() and action == "apply":
            self.app.toast("Join Wi-Fi first", 4, error=True)
            return

        def go(pw):
            if not pw:
                return
            OsUpdatePage.job = (self.app.system.os_update if action == "apply" else self.app.system.os_rollback)(pw)
            OsUpdatePage.action, self.view, self.told = action, "running", False

        prompt = "This handheld's password (SELECT shows it)"
        self.app.push(Keyboard(self.app, prompt, go, secret=True))

    def handle(self, action):
        if self.view == "running":
            if action == "b":
                if OsUpdatePage.job and OsUpdatePage.job.done:
                    OsUpdatePage.job, self.view = None, "info"
                    self.enter()
                else:
                    self.app.pop()          # hide; the update keeps running
            return
        if action == "b":
            self.app.pop()
            return
        if action == "a":
            # say what is about to happen, from which version to which, before the password is asked
            have, new = self.info.get("installed") or "unknown", self.info.get("newest")
            if self.same:
                title, detail = "Look for security updates?", (
                    f"This handheld is on {have}, the newest version. Debian's security updates are looked for and applied.")
            elif new:
                title, detail = f"Update to {new.lstrip('v')}?", (
                    f"This handheld is on {have}. It goes to {new.lstrip('v')}, then Debian's security updates are applied.")
            else:
                title, detail = "Update this handheld?", (
                    f"This handheld is on {have}. The newest version could not be looked up"
                    + (" yet" if self.looking else "") + ": if there is one it is installed, then Debian's security updates.")
            self.app.confirm(title, detail, "Update", lambda: self.start("apply"))
        elif action == "y":
            self.app.confirm("Undo the last update?", "Puts back the version from before the last update.",
                             "Undo", lambda: self.start("rollback"))

    # ---------------------------------------------------------------- draw
    def panel(self, surf, f, area):
        """A full-area panel with the title, so the screen below does not show
        through (this page is drawn over the Settings window that opened it)."""
        r = pygame.Rect(area.x + 12, area.y + 12, area.w - 24, area.h - 24)
        G.box(surf, r, T.PANEL, 8, T.BORDER)
        G.text(surf, f.big, self.title, (r.x + 14, r.y + 10), T.EMBER_BRIGHT)
        return pygame.Rect(r.x + 2, r.y + 14 + f.line, r.w - 4, r.bottom - (r.y + 14 + f.line) - 8)

    def draw(self, surf, f, area):
        if self.view == "running":
            return self.draw_run(surf, f, area)
        inner = self.panel(surf, f, area)
        x, y = inner.x + 14, inner.y + 6
        i = self.info
        same, new = self.same, (i.get("newest") or "").lstrip("v")
        rows = [("Installed", i.get("installed") or "unknown", T.TEXT),
                ("Newest", new + ("  (up to date)" if same else "") if new
                 else "looking…" if self.looking else "could not look it up (Wi-Fi?)",
                 T.OK if same else T.EMBER_BRIGHT if new else T.MUTED),
                ("Updates from", i.get("source") or "official", T.MUTED),
                ("Channel", i.get("channel") or "—", T.MUTED),
                ("State schema", i.get("schema") or "—", T.MUTED)]
        for label, value, colour in rows:
            G.text(surf, f.mono, label, (x, y), T.MUTED)
            G.text(surf, f.mono, G.fit(f.mono, value, area.w - 230), (x + 200, y), colour)
            y += f.line + 10
        y += 8
        note = ("An update replaces only the desktop and system files — not the kernel, your apps or your data. "
                "It checks the new version works, backs up the old one, and undoes itself if the desktop does "
                "not come back. It also applies Debian's security updates, and A does that even when the "
                "system is up to date. Y puts the last update back.")
        for ln in G.wrap(f.small, note, inner.w - 28):
            G.text(surf, f.small, ln, (x, y), T.DIM)
            y += f.small_line

    def draw_run(self, surf, f, area):
        job = OsUpdatePage.job
        inner = self.panel(surf, f, area)
        x, y = inner.x + 14, inner.y + 4
        done, ok = bool(job and job.done), bool(job and job.ok)
        why = job.reason if job else ""
        verb = "Updated" if OsUpdatePage.action == "apply" else "Rolled back"
        doing = "Updating the handheld" if OsUpdatePage.action == "apply" else "Rolling back"
        head = f"{verb}." if ok else "It stopped." if done else doing
        G.text(surf, f.big, head, (x, y), T.OK if ok else T.ERROR if done else T.EMBER_BRIGHT)
        y += f.line + 6
        sub = ("B goes back." if ok
               else "That is not this handheld's password. B goes back; SELECT on the keyboard shows it." if why == "password"
               else "It put the old version back — nothing was lost. The reason is below." if done
               else "This takes a few minutes and keeps going if you close the window. The desktop may restart at the end.")
        G.text(surf, f.small, G.fit(f.small, sub, inner.w - 28), (x, y), T.TEXT if done else T.DIM)
        y += f.small_line + 10
        box = pygame.Rect(inner.x, y, inner.w, inner.bottom - y)
        G.box(surf, box, T.PANEL, 6, T.BORDER)
        lines = job.lines if job else []
        fit = max(1, (box.h - 16) // f.small_line)
        for k, ln in enumerate(lines[-fit:]):
            colour = T.EMBER if ln.startswith(("rk-update:", "rk-migrate:")) else T.TEXT
            G.text(surf, f.small, G.fit(f.small, ln, box.w - 24),
                   (box.x + 12, box.y + 10 + k * f.small_line), colour)
