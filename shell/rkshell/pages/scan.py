"""Scan: what is on the network this handheld is connected to.

Two steps, both through rk-scan (which refuses any target outside the
handheld's own network): find the addresses that answer, then, for one of
them, find its common open ports. Reports are saved where Files shows them.
"""
import threading

import pygame

from .. import gfx as G
from .. import theme as T
from ..widgets import ListView, Menu, TextView
from .base import Page


class ScanPage(Page):
    title, icon = "Scan", "radar"

    def __init__(self, app):
        super().__init__(app)
        self.list = ListView(row_lines=2)
        self.networks, self.net, self.busy, self.done, self.error = [], None, "", False, ""

    @property
    def hints(self):
        if self.busy:
            return [("B", "close")]
        if self.done:
            return [("A", "open ports"), ("X", "scan again"), ("Y", "save"), ("B", "close")]
        return [("A", "find devices"), ("B", "close")]

    def enter(self):
        self.networks = self.app.system.own_networks()
        self.net = self.networks[0] if self.networks else None

    def find(self):
        if self.busy or not self.net:
            return
        self.busy, self.error = f"Looking for devices on {self.net[1]}…", ""

        def job():
            ok, res = self.app.system.scan_hosts(self.net[1])
            if ok:
                for h in res:
                    h["me"] = h["address"] == self.net[2]
                self.list.set(res, keep=False)
                self.done = True
            else:
                self.error = res
            self.busy = ""
            self.app.dirty = True
        threading.Thread(target=job, daemon=True).start()

    def ports(self, host):
        self.busy = f"Looking for open ports on {host['address']}…"

        def job():
            ok, res = self.app.system.scan_ports(host["address"])
            self.busy = ""
            if not ok:
                self.app.toast(res, 5, error=True)
            else:
                host["ports"] = res
                lines = [f"{p['port']:>5}/{p['proto']}  {p['service']}  {p['product']}".rstrip() for p in res]
                text = "\n".join(lines) if lines else "None of the 100 most common ports is open."
                self.app.push(TextView(self.app, f"Open ports on {host['address']}", text))
            self.app.dirty = True
        threading.Thread(target=job, daemon=True).start()

    def save(self):
        lines = [f"Devices on {self.net[1]} ({len(self.list.items)} found)", ""]
        for h in self.list.items:
            lines.append(f"{h['address']:<16}{h['name'] or '-':<28}{h['mac'] or '-':<19}{h['vendor']}".rstrip())
            for p in h.get("ports", []):
                lines.append(f"    {p['port']}/{p['proto']}  {p['service']}  {p['product']}".rstrip())
        path = self.app.system.save_report("scan", "\n".join(lines) + "\n")
        self.app.toast(f"Saved to {path}" if path else "Could not save", 5, error=not path)

    def handle(self, action):
        if self.busy:
            return
        if self.done and self.list.move(action):
            return
        if action == "a":
            if not self.done:
                self.find()
            elif self.list.current:
                self.ports(self.list.current)
        elif action == "x" and self.done:
            self.find()
        elif action == "y" and self.done:
            self.save()

    def draw(self, surf, f, area):
        x, y = area.x + 16, area.y + 8
        if not self.net:
            G.text(surf, f.mono, "Not on a network.", (x, y), T.MUTED)
            for i, ln in enumerate(G.wrap(f.small, "Join one in the Network window first. This looks only at "
                                          "the network the handheld is connected to.", area.w - 32)):
                G.text(surf, f.small, ln, (x, y + f.line + 6 + i * f.small_line), T.DIM)
            return
        G.text(surf, f.small, f"Network {self.net[1]}", (x, y), T.MUTED)
        y += f.small_line + 8
        if self.busy:
            G.text(surf, f.mono, self.busy, (x, y), T.EMBER_BRIGHT)
            G.text(surf, f.small, "This takes from a few seconds to a minute.", (x, y + f.line + 4), T.DIM)
            return
        if self.error:
            G.text(surf, f.small, G.fit(f.small, self.error, area.w - 32), (x, y), T.ERROR)
            y += f.small_line + 6
        if not self.done:
            for i, ln in enumerate(G.wrap(f.small, "Press A to find the devices on this network. Only this network "
                                          "is looked at: do this on networks that are yours, or that you have "
                                          "been asked to test.", area.w - 32)):
                G.text(surf, f.small, ln, (x, y + i * f.small_line), T.TEXT)
            return
        if not self.list.items:
            G.text(surf, f.mono, "No device answered.", (x, y), T.MUTED)
            return
        G.text(surf, f.small, f"{len(self.list.items)} devices", (area.right - 16, area.y + 8), T.OK, right=True)
        self.list.draw(surf, f, pygame.Rect(area.x + 12, y, area.w - 24, area.bottom - y - 4), self.row)

    def row(self, surf, f, r, h, selected):
        G.text(surf, f.big, h["address"], (r.x + 14, r.y + 6), T.EMBER_BRIGHT if selected else T.TEXT)
        what = " · ".join(x for x in (h["name"], h["vendor"]) if x) or ("this handheld" if h.get("me") else "no name")
        if h.get("me") and what != "this handheld":
            what += " · this handheld"
        G.text(surf, f.small, G.fit(f.small, what, r.w - 28), (r.x + 14, r.y + 10 + f.line), T.MUTED)
        if "ports" in h:
            G.text(surf, f.small, f"{len(h['ports'])} open", (r.right - 14, r.y + 10), T.OK if h["ports"] else T.DIM, right=True)
