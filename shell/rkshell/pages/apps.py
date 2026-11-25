"""AppManager: the versions of FireFly, Stump, Ember, the Provisioner and
STUMP Recon here and the newest ones, and their updates.

An update runs the app's own installer (through rk-apps), so its data and
settings are kept as that installer keeps them. FireFly and the Stump come
from the main branch of their repositories, Ember and the Provisioner from
their newest release, STUMP Recon from the copy that came with the system
or its repository, whichever is newer. The Provisioner and STUMP Recon can
also be installed from here when a card does not have them (one updated from
before the image carried them).
The handheld's password is asked because the installers need root for a few
steps; it goes to sudo and is not kept.
"""
import pygame

from .. import gfx as G
from .. import theme as T
from ..system import START_PASSWORD
from ..widgets import Keyboard
from .base import Page

# apps that need no setup of their own: A on their row installs them when the card has none
INSTALLS = ("provisioner", "stump-recon")
# those whose files came with the system: no network needed to install them
OFFLINE = ("stump-recon",)


class AppsPage(Page):
    title, icon = "AppManager", "update"
    job = None                      # a running update outlives the window
    job_name = ""

    def __init__(self, app):
        super().__init__(app)
        self.sel, self.apps, self.check, self.told = 0, [], None, False
        self.view = "list"
        self.first = 0              # the first row shown, when the list is longer than the window

    def enter(self):
        if AppsPage.job is not None:
            self.view = "running"
        self.look()

    def look(self):
        self.check = self.app.system.app_versions()

    # --------------------------------------------------------------- state
    def state(self, a):
        """(text, colour, can update) for a row."""
        if a["installed"] == "-":
            if a["id"] in INSTALLS:             # needs no setup: A fetches it
                return (f"not installed  (A installs {a['newest']})" if a["newest"] != "?" else "not installed",
                        T.MUTED, a["newest"] != "?")
            return "not set up", T.DIM, False
        if "?" in (a["newest"], a["installed"]):
            return (f"{a['installed']}  (newest {a['newest']})" if a["newest"] != "?" else f"{a['installed']}  (could not check)",
                    T.MUTED, a["newest"] != "?")
        if a["installed"] == a["newest"]:
            return f"{a['installed']}  up to date", T.OK, True
        return f"{a['installed']}  →  {a['newest']}", T.EMBER_BRIGHT, True

    @property
    def live(self):
        return self.view == "running" or self.check is not None

    @property
    def hints(self):
        if self.view == "running":
            job = AppsPage.job
            return [("B", "back")] if job and job.done else [("B", "hide")]
        hints = [("A", "update"), ("X", "check again")]
        if self.apps and self.apps[min(self.sel, len(self.apps) - 1)].get("source"):
            hints.append(("Y", "stable / sandbox"))
        return hints + [("B", "close")]

    def wants_back(self):
        return self.view == "running" and bool(AppsPage.job and AppsPage.job.done)

    def poll(self):
        if self.check is not None:
            self.app.dirty = True
            if self.check.done:
                self.apps, self.check = self.check.apps, None
                self.sel = min(self.sel, max(0, len(self.apps) - 1))
        job = AppsPage.job
        if self.view == "running" and job:
            self.app.dirty = True
            if job.done and not self.told:
                self.told = True
                self.app.toast(f"{AppsPage.job_name} is up to date" if job.ok else "The update stopped", 5, error=not job.ok)
                self.app.fill_dock()

    # --------------------------------------------------------------- input
    def update(self, a):
        if not self.state(a)[2]:
            self.app.toast("Open Stump on the dock to set it up first" if a["id"] == "stump"
                           else f"{a['name']} is not installed", 4, error=True)
            return
        if a["id"] not in OFFLINE and not self.app.system.online():
            self.app.toast("Join Wi-Fi first", 4, error=True)
            return
        fresh = self.app.system.password_expired()

        def go(pw):
            if fresh and (len(pw) < 8 or pw == START_PASSWORD):
                self.app.toast("The new password: 8 characters or more", 4, error=True)
                return
            if not pw:
                return
            AppsPage.job = self.app.system.app_update(a["id"], pw, START_PASSWORD if fresh else None)
            AppsPage.job_name, self.view, self.told = a["name"], "running", False
        self.app.push(Keyboard(self.app, "Choose a password for this handheld (8 or more)" if fresh
                               else "This handheld's password (SELECT shows it)", go, secret=True))

    def handle(self, action):
        if self.view == "running":
            if action == "b" and AppsPage.job and AppsPage.job.done:
                AppsPage.job, self.view = None, "list"
                self.look()
            return
        if action in ("up", "down") and self.apps:
            self.sel = (self.sel + (-1 if action == "up" else 1)) % len(self.apps)
        elif action == "a" and self.apps:
            self.update(self.apps[self.sel])
        elif action == "x" and self.check is None:
            self.look()
        elif action == "y" and self.apps and self.check is None:
            a = self.apps[self.sel]
            if a.get("source"):
                to = "sandbox" if a["source"] == "stable" else "stable"
                if self.app.system.app_source(a["id"], to):
                    self.app.toast(f"{a['name']} now comes from its {to} repository", 3)
                    self.look()

    # ---------------------------------------------------------------- draw
    def draw(self, surf, f, area):
        if self.view == "running":
            return self.draw_run(surf, f, area)
        x, y = area.x + 16, area.y + 10
        if not self.apps:
            G.text(surf, f.mono, "Checking the versions…" if self.check is not None else "Could not check the versions.",
                   (x, y), T.MUTED)
            return
        row_h = f.line + f.small_line + 14
        # a small screen holds fewer rows than there are apps: show the ones
        # around the selected row, with a mark where the list goes on
        fit = max(1, (area.bottom - 4 - y) // row_h)
        first = 0
        if len(self.apps) > fit:
            first = max(0, min(max(self.sel - fit + 1, self.first), self.sel, len(self.apps) - fit))
        self.first = first
        for i, a in enumerate(self.apps):
            if i < first or i >= first + fit:
                continue
            r = pygame.Rect(area.x + 12, y, area.w - 24, row_h - 4)
            sel = i == self.sel
            if sel:
                G.box(surf, r, T.ROW, 6, T.EMBER)
            G.spot(r, lambda i=i: setattr(self, "sel", i))
            text, colour, _ = self.state(a)
            G.text(surf, f.big, a["name"], (r.x + 14, r.y + 5), T.EMBER_BRIGHT if sel else T.TEXT)
            G.text(surf, f.small, G.fit(f.small, text, r.w - 28), (r.x + 14, r.y + 9 + f.line), colour)
            if a.get("source"):
                G.text(surf, f.small, "from: " + a["source"], (r.right - 14, r.y + 10), T.MUTED, right=True)
            y += row_h
        if first > 0:
            G.text(surf, f.small, "▲", (area.right - 16, area.y + 2), T.MUTED, right=True)
        if first + fit < len(self.apps):
            G.text(surf, f.small, "▼", (area.right - 16, area.bottom - f.small_line - 2), T.MUTED, right=True)
        note = ("Checking again…" if self.check is not None else
                "An update runs the app's own installer; its data is kept. FireFly has two sources, switched "
                "with Y: stable (its published repository) and sandbox (new versions land there first).")
        # the note takes what the rows leave: on a small screen four rows
        # leave room for less of it, or none
        fits = max(0, min(3, (area.bottom - 6 - y) // f.small_line))
        for k, ln in enumerate(G.wrap(f.small, note, area.w - 32)[:fits]):
            G.text(surf, f.small, ln, (x, area.bottom - fits * f.small_line - 6 + k * f.small_line), T.DIM)

    def draw_run(self, surf, f, area):
        job = AppsPage.job
        x, y = area.x + 16, area.y + 10
        done, ok = bool(job and job.done), bool(job and job.ok)
        why = job.reason if job else ""
        head = f"{AppsPage.job_name} is up to date" if ok else "The update stopped" if done else f"Updating {AppsPage.job_name}"
        G.text(surf, f.big, head, (x, y), T.OK if ok else T.ERROR if done else T.EMBER_BRIGHT)
        y += f.line + 6
        sub = ("B goes back to the list." if ok
               else "That is not this handheld's password. B goes back; SELECT on the keyboard shows it." if why == "password"
               else "The new password was not accepted: try a longer or less simple one." if why == "newpassword"
               else "The reason is in the last lines." if done else "This takes a few minutes. It keeps running if you close the window.")
        G.text(surf, f.small, G.fit(f.small, sub, area.w - 32), (x, y), T.TEXT if done else T.DIM)
        y += f.small_line + 10
        box = pygame.Rect(area.x + 12, y, area.w - 24, area.bottom - y - 6)
        G.box(surf, box, T.PANEL, 6, T.BORDER)
        lines = job.lines if job else []
        fit = max(1, (box.h - 16) // f.small_line)
        for i, ln in enumerate(lines[-fit:]):
            colour = T.EMBER if ln.startswith(("==", ">>>", "rk-apps:")) else T.ERROR if ln.startswith(("[x]", "ERROR")) else T.TEXT
            G.text(surf, f.small, G.fit(f.small, ln.replace("rk-apps: ", ""), box.w - 24),
                   (box.x + 12, box.y + 10 + i * f.small_line), colour)
