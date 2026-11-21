"""Stump setup: the questions the Stump's installer needs, asked with the gamepad.

The dock opens this in place of the Stump until it has been set up. The
answers go to the Stump's own installer (R36MAX-Stump's install.sh
--answers), the same way the RK3326 Provisioner drives it, so nothing is
typed in a terminal. The handheld's password is asked because the installer
needs root for a few steps; it is handed to sudo and not kept.
"""
import pygame

from .. import gfx as G
from .. import theme as T
from ..system import START_PASSWORD, stump_answers
from ..widgets import Keyboard, Menu
from .base import Page

CHAIN = [("none", "On its own"), ("first", "First Stump of a chain"), ("member", "Joins another Stump")]
RADIO = [("none", "None"), ("usb", "Heltec on USB")]
ABOUT = {"name": "The name other people see for this Stump.",
         "pw": "Opens the Stump's /admin page and its bot. Note it down. 4 characters or more.",
         "chain": "A chain links Stumps over Wi-Fi. On its own is fine to start.",
         "parent": "The Stump this one joins. A looks for Stumps on the Wi-Fi you are on now.",
         "secret": "Every Stump in a chain has the same secret. Note it down.",
         "storage": "Room for what visitors share on this Stump. It fills to three quarters, then the oldest files make room.",
         "radio": "The LoRa radio. Choose USB only if a Heltec is plugged in.",
         "sudo": "This handheld's own password, for the installer's root steps. SELECT on the keyboard shows it.",
         "new": "This handheld still has its starting password. Choose your own, 8 characters or more: "
                "the one for SSH too.",
         "go": "Runs the Stump's installer. It takes a few minutes and needs Wi-Fi."}


class StumpSetupPage(Page):
    title, icon = "Stump setup", "stump"
    job = None                      # the running install outlives the window
    form = None

    def __init__(self, app):
        super().__init__(app)
        self.sel, self.view, self.told = 0, "form", False
        self.expired, self.search, self.quiet = False, None, False
        self.most, self.sizes = 256, [256]

    def enter(self):
        cls = StumpSetupPage
        if cls.form is None:
            cls.form = {"name": self.app.system.hostname(), "pw": "", "chain": "none", "parent": "", "parent_name": "", "secret": "",
                        "radio": "none", "sudo": ""}
        if cls.job is not None:
            self.view = "running"
        self.expired = self.app.system.password_expired()
        self.most, suggested, self.sizes = self.app.system.stump_storage()
        if cls.form.get("storage") not in self.sizes:
            cls.form["storage"] = suggested if suggested in self.sizes else self.sizes[0]

    # --------------------------------------------------------------- form
    def rows(self):
        chain = self.form["chain"]
        keys = ["name", "pw", "chain"]
        if chain == "member":
            keys.append("parent")
        if chain != "none":
            keys.append("secret")
        return keys + ["storage", "radio", "sudo", "go"]

    def label(self, key):
        return {"name": "Name", "pw": "Stump password", "chain": "Chain", "parent": "Joins",
                "secret": "Chain secret", "storage": "Storage", "radio": "Radio", "go": "",
                "sudo": "New password" if self.expired else "Your password"}[key]

    def value(self, key):
        v = self.form.get(key, "")
        if key == "chain":
            return dict(CHAIN)[v]
        if key == "radio":
            return dict(RADIO)[v]
        if key == "storage":
            return f"{v} MB  (max {self.most})"
        if key == "sudo":
            return "•" * len(v) if v else "needed"
        if key == "go":
            return "Set up the Stump"
        if key == "parent":
            if self.search is not None:
                return "looking for Stumps…"
            name = self.form.get("parent_name")
            return f"{v}  ({name})" if v and name else v or "needed"
        return v or ("needed" if key in ("pw", "parent") or (key == "secret" and self.form["chain"] == "member") else "none")

    def edit(self, key):
        def done(v):
            self.form[key] = v if key in ("pw", "sudo", "secret") else v.strip()
            if key == "parent":
                self.form["parent_name"] = ""
        self.app.push(Keyboard(self.app, self.label(key), done, secret=key == "sudo", initial=self.form[key]))

    def cycle(self, key, step):
        options = self.sizes if key == "storage" else [k for k, _ in (CHAIN if key == "chain" else RADIO)]
        self.form[key] = options[(options.index(self.form[key]) + step) % len(options)]
        if self.form["chain"] == "member" and not self.form["parent"] and self.search is None:
            self.look(quiet=True)

    # ------------------------------------------- the Stump it joins
    def look(self, quiet=False):
        """Search the network for Stumps; the list opens when it is done
        (quiet: only fill the address in when exactly one takes links)."""
        self.search, self.quiet = self.app.system.stump_search(), quiet

    def pick(self, stump):
        self.form["parent"], self.form["parent_name"] = stump["address"], stump["name"]

    def found(self, stumps):
        linking = [s for s in stumps if s["links"]]
        if self.quiet:
            if len(linking) == 1:
                self.pick(linking[0])
            return
        items = [(f"{s['name']}  {s['address']}" + ("" if s["links"] else "  (not taking links)"),
                  lambda s=s: self.pick(s)) for s in stumps]
        items += [("Look again", self.look), ("Type an address…", lambda: self.edit("parent"))]
        detail = ("Stumps on this Wi-Fi. One marked 'not taking links' is not the first Stump of a chain."
                  if stumps else "No Stump answered on this Wi-Fi. Is it on the same network as this handheld?")
        self.app.push(Menu(self.app, "The Stump it joins", items, detail))

    def start(self):
        answers = stump_answers(self.form)
        if "error" in answers:
            self.app.toast(answers["error"], 4, error=True)
            return
        if not self.form["sudo"]:
            self.app.toast("Choose a password for this handheld" if self.expired
                           else "Your password is needed for the install", 4, error=True)
            return
        if self.expired and (len(self.form["sudo"]) < 8 or self.form["sudo"] == START_PASSWORD):
            self.app.toast("The new password: 8 characters or more", 4, error=True)
            return
        if not self.app.system.online():
            self.app.toast("Join Wi-Fi first: the installer downloads the Stump", 4, error=True)
            return
        StumpSetupPage.job = self.app.system.stump_setup(answers, self.form["sudo"],
                                                         replaces=START_PASSWORD if self.expired else None)
        self.form["sudo"] = ""
        self.view, self.told = "running", False

    # -------------------------------------------------------------- state
    @property
    def live(self):
        return self.view == "running" or self.search is not None

    @property
    def hints(self):
        job = StumpSetupPage.job
        if self.view == "running":
            if job and job.done:
                return [("B", "close")] if job.ok else [("B", "back to the form")]
            return [("B", "hide")]
        return [("A", "change"), ("◄►", "choose"), ("START", "set up"), ("B", "close")]

    def wants_back(self):
        job = StumpSetupPage.job
        return self.view == "running" and bool(job and job.done and not job.ok)

    def poll(self):
        if self.search is not None:
            self.app.dirty = True
            if self.search.done:
                stumps, self.search = self.search.found, None
                self.found(stumps)
        job = StumpSetupPage.job
        if self.view == "running" and job:
            self.app.dirty = True
            if job.done and not self.told:
                self.told = True
                self.app.toast("The Stump is set up" if job.ok else "The setup stopped", 5, error=not job.ok)
                if job.ok:
                    self.app.fill_dock()
                self.expired = self.app.system.password_expired()

    def handle(self, action):
        if self.view == "running":
            job = StumpSetupPage.job
            if action == "b" and job and job.done and not job.ok:
                StumpSetupPage.job, self.view = None, "form"
            return
        keys = self.rows()
        self.sel = min(self.sel, len(keys) - 1)
        key = keys[self.sel]
        if action in ("up", "down"):
            self.sel = (self.sel + (-1 if action == "up" else 1)) % len(keys)
        elif action in ("left", "right") and key in ("chain", "radio", "storage"):
            self.cycle(key, -1 if action == "left" else 1)
        elif action == "a":
            if key == "go":
                self.start()
            elif key in ("chain", "radio", "storage"):
                self.cycle(key, 1)
            elif key == "parent":
                if self.search is None:
                    self.look()
            else:
                self.edit(key)
        elif action == "start":
            self.start()

    # --------------------------------------------------------------- draw
    def draw(self, surf, f, area):
        (self.draw_run if self.view == "running" else self.draw_form)(surf, f, area)

    def draw_form(self, surf, f, area):
        keys, pad = self.rows(), 12
        self.sel = min(self.sel, len(keys) - 1)
        foot = f.small_line * 2 + 18
        room = area.h - foot - 10
        row_h = f.line + 12 if len(keys) * (f.line + 12) <= room else f.line + 4
        visible = max(1, min(len(keys), room // row_h))
        top = max(0, min(self.sel - visible // 2, len(keys) - visible))
        label_w = f.mono.size("Stump password  ")[0]
        y = area.y + 6
        for i, key in list(enumerate(keys))[top:top + visible]:
            r = pygame.Rect(area.x + pad, y, area.w - 2 * pad, row_h - 3)
            sel = i == self.sel
            ty = r.y + (r.h - f.line) // 2
            if key == "go":
                G.box(surf, r, T.ROW if sel else T.PANEL, 8, T.EMBER if sel else T.BORDER)
                G.text(surf, f.mono, self.value(key), (r.centerx, ty), T.EMBER_BRIGHT if sel else T.TEXT, center=True)
            else:
                if sel:
                    G.box(surf, r, T.ROW, 6, T.EMBER)
                text = self.value(key)
                colour = T.ERROR if text == "needed" else T.EMBER_BRIGHT if sel else T.TEXT
                G.text(surf, f.mono, self.label(key), (r.x + 12, ty), T.MUTED)
                G.text(surf, f.mono, G.fit(f.mono, text, r.w - label_w - 70), (r.x + 12 + label_w, ty), colour)
                if sel:
                    G.text(surf, f.mono, "◄ ►" if key in ("chain", "radio", "storage") else "A", (r.right - 12, ty), T.EMBER, right=True)
            y += row_h
        y = area.bottom - foot
        pygame.draw.line(surf, T.BORDER, (area.x + pad, y), (area.right - pad, y))
        about = ABOUT["new" if keys[self.sel] == "sudo" and self.expired else keys[self.sel]]
        for k, ln in enumerate(G.wrap(f.small, about, area.w - 2 * pad)[:2]):
            G.text(surf, f.small, ln, (area.x + pad, y + 8 + k * f.small_line), T.DIM)

    def draw_run(self, surf, f, area):
        job = StumpSetupPage.job
        x, y = area.x + 16, area.y + 10
        done, ok = bool(job and job.done), bool(job and job.ok)
        head = "The Stump is set up" if ok else "The setup stopped" if done else "Setting up the Stump"
        G.text(surf, f.big, head, (x, y), T.OK if ok else T.ERROR if done else T.EMBER_BRIGHT)
        y += f.line + 6
        why = job.reason if job else ""
        sub = ("Close this and open Stump from the dock." if ok
               else "That is not this handheld's password. B goes back; SELECT on the keyboard shows it." if why == "password"
               else "The new password was not accepted: try a longer or less simple one. B goes back." if why == "newpassword"
               else "The reason is in the last lines. B goes back to the form." if done
               else (job.step if job else ""))
        G.text(surf, f.small, G.fit(f.small, sub, area.w - 32), (x, y), T.DIM if not done else T.TEXT)
        y += f.small_line + 10
        box = pygame.Rect(area.x + 12, y, area.w - 24, area.bottom - y - 6)
        G.box(surf, box, T.PANEL, 6, T.BORDER)
        lines = job.lines if job else []
        fit = max(1, (box.h - 16) // f.small_line)
        for i, ln in enumerate(lines[-fit:]):
            colour = T.EMBER if ln.startswith(">>>") else T.ERROR if ln.startswith("[x]") else T.TEXT
            G.text(surf, f.small, G.fit(f.small, ln, box.w - 24), (box.x + 12, box.y + 10 + i * f.small_line), colour)
