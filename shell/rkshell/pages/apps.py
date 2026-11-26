"""AppManager: the apps on this handheld, their versions, their updates, and
installing an app from a package.

Two kinds of app are listed. The system's own (FireFly, Stump, Ember, the
Provisioner): their versions here and the newest ones, and their updates.
And apps from packages: a .zip put in /data/ark/packages is listed with its
name and version, A installs it (or a newer one over the one installed), Y
removes it. A package changes nothing in the system: it is to this handheld
what a program's installer is to a computer.

An update runs the app's own installer (through rk-apps), so its data and
settings are kept as that installer keeps them. FireFly and the Stump come
from the main branch of their repositories, Ember and the Provisioner from
their newest release. The Provisioner can also be installed from here when a
card does not have it (one updated from before the image carried it). A
package's own installer does its work too; nothing checks a package, so the
window says where it comes from and asks before running it.
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
INSTALLS = ("provisioner",)
PACKAGES = "/data/ark/packages"
# (while it runs, when it worked) for what a job is doing
WORDS = {"update": ("Updating {}", "{} is up to date"), "install": ("Installing {}", "{} is installed"),
         "remove": ("Removing {}", "{} is removed")}


class AppsPage(Page):
    title, icon = "AppManager", "update"
    job = None                      # a running update outlives the window
    job_name = ""
    job_kind = "update"             # a key of WORDS

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
        if a.get("bad"):
            return "not a package: " + a["why"], T.DIM, False
        if a.get("pkg"):
            here, there = a["installed"], a["newest"]
            if here == "-":
                return f"package {there}  (A installs)", T.MUTED, True
            if there == "-":
                return f"{here}  from a package", T.OK, False
            if here == there:
                return f"{here}  from a package  (A installs it again)", T.OK, True
            return f"{here}  →  {there}", T.EMBER_BRIGHT, True
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
        a = self.apps[min(self.sel, len(self.apps) - 1)] if self.apps else {}
        hints = [("A", "install" if a.get("pkg") else "update"), ("X", "check again")]
        if a.get("source"):
            hints.append(("Y", "stable / sandbox"))
        elif a.get("pkg") and a["installed"] != "-":
            hints.append(("Y", "remove"))
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
                self.app.toast(WORDS[AppsPage.job_kind][1].format(AppsPage.job_name) if job.ok else "It stopped: see the last lines",
                               5, error=not job.ok)
                self.app.fill_dock()

    # --------------------------------------------------------------- input
    def update(self, a):
        if a.get("bad"):
            self.app.toast("That file is not an app package", 4, error=True)
            return
        if a.get("pkg"):
            return self.install_package(a)
        if not self.state(a)[2]:
            self.app.toast("Open Stump on the dock to set it up first" if a["id"] == "stump"
                           else f"{a['name']} is not installed", 4, error=True)
            return
        if not self.app.system.online():
            self.app.toast("Join Wi-Fi first", 4, error=True)
            return
        self.ask_password(lambda pw, old: self.app.system.app_update(a["id"], pw, old), a["name"], "update")

    def install_package(self, a):
        if not self.state(a)[2]:
            self.app.toast(f"For a newer {a['name']}, put its package in {PACKAGES}", 5)
            return
        # nothing checks a package: say what is about to run, and ask
        detail = (f"Version {a['newest']}, from {a['file']}. Its own installer runs with this handheld's password."
                  + (" It has steps for root: it may add programs that run as root." if a.get("root") else "")
                  + " Install only a package from someone you trust.")
        self.app.confirm(f"Install {a['name']}?", detail, "Install", lambda: self.ask_password(
            lambda pw, old: self.app.system.package_install(a["id"], pw, old), a["name"], "install"))

    def remove_package(self, a):
        detail = ("Its files, its dock entry and what its installer added for root are removed. "
                  "What it saved on the data partition stays.")
        self.app.confirm(f"Remove {a['name']}?", detail, "Remove", lambda: self.ask_password(
            lambda pw, old: self.app.system.package_remove(a["id"], pw), a["name"], "remove"))

    def ask_password(self, start, name, kind):
        """Ask for the handheld's password, then start(password, the starting
        password when this one is new) and show the job."""
        fresh = self.app.system.password_expired()

        def go(pw):
            if fresh and (len(pw) < 8 or pw == START_PASSWORD):
                self.app.toast("The new password: 8 characters or more", 4, error=True)
                return
            if not pw:
                return
            AppsPage.job = start(pw, START_PASSWORD if fresh else None)
            AppsPage.job_name, AppsPage.job_kind, self.view, self.told = name, kind, "running", False
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
            if a.get("pkg") and a["installed"] != "-":
                self.remove_package(a)
            elif a.get("source"):
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
            elif a.get("pkg") or a.get("bad"):
                G.text(surf, f.small, "package" if a.get("pkg") else "file", (r.right - 14, r.y + 10), T.MUTED, right=True)
            y += row_h
        if first > 0:
            G.text(surf, f.small, "▲", (area.right - 16, area.y + 2), T.MUTED, right=True)
        if first + fit < len(self.apps):
            G.text(surf, f.small, "▼", (area.right - 16, area.bottom - f.small_line - 2), T.MUTED, right=True)
        note = ("Checking again…" if self.check is not None else
                f"An update runs the app's own installer; its data is kept. For another app, put its package "
                f"(a .zip) in {PACKAGES}: it is listed here and A installs it.")
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
        doing, did = WORDS[AppsPage.job_kind]
        head = did.format(AppsPage.job_name) if ok else "It stopped" if done else doing.format(AppsPage.job_name)
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
