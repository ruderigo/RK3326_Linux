"""Arsenal: the security tools on the handheld, grouped, with what is present
and what is not.

The light tools are in the image. The heavy ones (Metasploit, exploitdb) are
large, so they are fetched the first time you ask, over Wi-Fi: press X. A tool
that is present runs from the Terminal; a USB keyboard helps with the big
keyboard-driven ones. Everything here is for testing machines that are yours,
or that you have been asked to test.
"""
import pygame

from .. import arsenal as A
from .. import gfx as G
from .. import theme as T
from ..widgets import TextView
from .base import Page


class ArsenalPage(Page):
    title, icon = "Arsenal", "chip"
    install = None                  # the running install outlives the window

    def __init__(self, app):
        super().__init__(app)
        self.rows, self.sel, self.top = [], 0, 0
        self.view = "list"

    def enter(self):
        self.refresh()
        if ArsenalPage.install and not ArsenalPage.install.done:
            self.view = "installing"

    def refresh(self):
        status = self.app.system.tools_status()
        self.rows = []
        audit = self.app.system.wifi_audit()
        for title, heavy, tools in A.CATALOGUE:
            head = {"head": title, "heavy": heavy}
            if title.startswith("Wi-Fi"):
                head["note"] = audit["line"]
                head["note_level"] = audit["level"]
            self.rows.append(head)
            for cmd, label, about in tools:
                self.rows.append({"cmd": cmd, "label": label, "about": about, "heavy": heavy, "on": status.get(cmd, False)})
        if not any(r.get("cmd") for r in self.rows[:self.sel + 1]):
            self.sel = next((i for i, r in enumerate(self.rows) if r.get("cmd")), 0)

    # counts
    def tally(self, heavy):
        tools = [r for r in self.rows if r.get("cmd") and r["heavy"] == heavy]
        return sum(r["on"] for r in tools), len(tools)

    def heavy_missing(self):
        return any(r.get("cmd") and r["heavy"] and not r["on"] for r in self.rows)

    @property
    def live(self):
        return self.view == "installing"

    @property
    def hints(self):
        if self.view == "installing":
            inst = ArsenalPage.install
            return [("B", "back")] if inst and inst.done else [("B", "hide")]
        hints = [("A", "about")]
        if self.heavy_missing():
            hints.append(("X", "get heavy tools"))
        return hints + [("B", "close")]

    def wants_back(self):
        return self.view != "list"

    # ------------------------------------------------------------- input
    def move(self, step):
        n = len(self.rows)
        for _ in range(n):
            self.sel = (self.sel + step) % n
            if self.rows[self.sel].get("cmd"):
                break

    def start_install(self):
        if not self.heavy_missing():
            return
        if not self.app.system.online():
            self.app.toast("Join Wi-Fi first, then try again.", 4, error=True)
            return
        ArsenalPage.install = self.app.system.install_heavy()
        self.view = "installing"

    def handle(self, action):
        if self.view == "installing":
            if action == "b":
                self.view = "list"
                self.refresh()
            return
        if action in ("up", "down"):
            self.move(-1 if action == "up" else 1)
        elif action == "a":
            r = self.rows[self.sel]
            if r.get("cmd"):
                where = "In the image." if not r["heavy"] else "Heavy: press X to fetch it."
                state = "Installed." if r["on"] else ("Not installed. " + where)
                self.app.push(TextView(self.app, r["label"], f"{r['about']}\n\n{state}\n\nRun it from the Terminal."))
        elif action == "x":
            self.start_install()

    def poll(self):
        if self.view == "installing" and ArsenalPage.install:
            self.app.dirty = True
            if ArsenalPage.install.done and not getattr(self, "_announced", False):
                self._announced = True
                ok = ArsenalPage.install.ok
                self.app.toast("Heavy tools installed" if ok else "Some heavy tools did not install", 5, error=not ok)
                self.refresh()

    # -------------------------------------------------------------- draw
    def draw(self, surf, f, area):
        if self.view == "installing":
            self.draw_install(surf, f, area)
        else:
            self.draw_list(surf, f, area)

    def draw_list(self, surf, f, area):
        x, y = area.x + 16, area.y + 8
        li, lt = self.tally(False)
        hi, ht = self.tally(True)
        G.text(surf, f.small, f"{li}/{lt} light tools", (x, y), T.OK if li else T.MUTED)
        G.text(surf, f.small, f"{hi}/{ht} heavy", (area.right - 16, y), T.OK if hi else T.MUTED, right=True)
        top_y = y + f.small_line + 8
        pygame.draw.line(surf, T.BORDER, (area.x + 12, top_y - 4), (area.right - 12, top_y - 4))
        row_h = f.line + f.small_line + 8
        head_h = f.line + 8
        # a simple scroller that keeps the selected row in view
        area_rows = pygame.Rect(area.x + 12, top_y, area.w - 24, area.bottom - top_y - 4)
        # measure a running offset for each row
        note_h = f.small_line + 2
        heights = [(head_h + (note_h if r.get("note") else 0)) if r.get("head") else row_h for r in self.rows]
        offs, acc = [], 0
        for h in heights:
            offs.append(acc); acc += h
        sel_top = offs[self.sel]
        if sel_top - self.top < 0:
            self.top = sel_top
        elif sel_top + row_h - self.top > area_rows.h:
            self.top = sel_top + row_h - area_rows.h
        self.top = max(0, min(self.top, max(0, acc - area_rows.h)))
        for i, r in enumerate(self.rows):
            ry = area_rows.y + offs[i] - self.top
            if ry + heights[i] < area_rows.y or ry > area_rows.bottom:
                continue
            if r.get("head"):
                G.text(surf, f.small, r["head"].upper(), (area_rows.x + 2, ry + 6), T.EMBER)
                if r.get("note"):
                    colour = {"ok": T.OK, "warn": T.ERROR}.get(r.get("note_level"), T.MUTED)
                    G.text(surf, f.small, G.fit(f.small, r["note"], area_rows.w - 8),
                           (area_rows.x + 2, ry + 6 + f.small_line), colour)
            else:
                rr = pygame.Rect(area_rows.x, ry, area_rows.w, row_h - 3)
                sel = i == self.sel
                if sel:
                    G.box(surf, rr, T.ROW, 6, T.BORDER)
                G.spot(rr.clip(area_rows), lambda i=i: setattr(self, "sel", i))
                dot = T.OK if r["on"] else T.DIM
                pygame.draw.circle(surf, dot, (rr.x + 14, rr.y + 12), 5)
                G.text(surf, f.mono, r["label"], (rr.x + 28, rr.y + 4), T.EMBER_BRIGHT if sel else T.TEXT)
                G.text(surf, f.small, r["on"] and "installed" or "not yet", (rr.right - 10, rr.y + 6),
                       T.OK if r["on"] else T.DIM, right=True)
                G.text(surf, f.small, G.fit(f.small, r["about"], rr.w - 40), (rr.x + 28, rr.y + 6 + f.line), T.MUTED)
        if self.top > 0:
            G.text(surf, f.small, "▲", (area.right - 14, top_y + 2), T.DIM, right=True)
        if self.top < acc - area_rows.h:
            G.text(surf, f.small, "▼", (area.right - 14, area.bottom - 6), T.DIM, right=True)

    def draw_install(self, surf, f, area):
        inst = ArsenalPage.install
        x, y = area.x + 16, area.y + 10
        G.text(surf, f.big, "Fetching the heavy tools", (x, y), T.EMBER_BRIGHT)
        y += f.line + 6
        done = inst.done if inst else True
        sub = ("This downloads Metasploit over Wi-Fi; give it a few minutes." if not done
               else ("Done." if inst and inst.ok else "Finished; some tools did not install."))
        G.text(surf, f.small, G.fit(f.small, sub, area.w - 32), (x, y),
               T.DIM if not done else (T.OK if inst and inst.ok else T.ERROR))
        y += f.small_line + 10
        box = pygame.Rect(area.x + 12, y, area.w - 24, area.bottom - y - 6)
        G.box(surf, box, T.PANEL, 6, T.BORDER)
        lines = inst.lines if inst else []
        fit = (box.h - 16) // f.small_line
        for i, ln in enumerate(lines[-fit:]):
            G.text(surf, f.small, G.fit(f.small, ln.replace("rk-tools: ", ""), box.w - 24), (box.x + 12, box.y + 10 + i * f.small_line), T.TEXT)
