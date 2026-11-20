"""NETWORK: Wi-Fi and remote access."""
import threading

import pygame

from .. import gfx as G
from .. import theme as T
from ..widgets import Keyboard, ListView, Screen
from .base import Page


class WifiList(Screen):
    """Networks in range. The scan runs in the background: the list fills in."""
    title = "Join a network"
    hints = [("A", "join"), ("X", "scan again"), ("B", "back")]

    def __init__(self, app):
        super().__init__(app)
        self.list, self.scanning = ListView(), False
        self.scan()

    def scan(self):
        if self.scanning:
            return
        self.scanning = True

        def job():
            nets = self.app.system.wifi_scan()
            self.list.set(nets)
            self.scanning = False
            self.app.dirty = True
        threading.Thread(target=job, daemon=True).start()

    def join(self, net, password=""):
        self.app.toast(f"Joining {net['ssid']}…", 40)

        def job():
            ok, msg = self.app.system.wifi_join(net["ssid"], password)
            self.app.toast(f"Connected to {net['ssid']}" if ok else msg, 5, error=not ok)
            if ok and self.app.current is self:
                self.app.pop()
        threading.Thread(target=job, daemon=True).start()

    def handle(self, action):
        if self.list.move(action):
            return
        net = self.list.current
        if action == "b":
            self.app.pop()
        elif action == "x":
            self.scan()
        elif action == "a" and net:
            if net["secure"] and not net["active"]:
                self.app.push(Keyboard(self.app, f"Password for {net['ssid']}", lambda pw: self.join(net, pw), secret=True))
            elif not net["active"]:
                self.join(net)

    def draw(self, surf, f, area):
        r = pygame.Rect(area.x + 12, area.y + 12, area.w - 24, area.h - 24)
        G.box(surf, r, T.PANEL, 8, T.EMBER)
        G.text(surf, f.big, self.title, (r.x + 14, r.y + 10), T.EMBER_BRIGHT)
        if self.scanning:
            G.text(surf, f.small, "looking…", (r.right - 14, r.y + 16), T.MUTED, right=True)
        inner = pygame.Rect(r.x + 8, r.y + 20 + f.line, r.w - 16, r.h - 30 - f.line)
        if not self.list.items:
            msg = "Looking for networks…" if self.scanning else "No networks found. Most USB cards only see 2.4 GHz."
            for i, ln in enumerate(G.wrap(f.small, msg, inner.w - 16)):
                G.text(surf, f.small, ln, (inner.x + 8, inner.y + 8 + i * f.small_line), T.MUTED)
            return
        self.list.draw(surf, f, inner, self.row)

    def row(self, surf, f, r, net, selected):
        G.text(surf, f.mono, G.fit(f.mono, net["ssid"], r.w - f.base * 9), (r.x + 10, r.y + 5),
               T.EMBER_BRIGHT if selected else T.TEXT)
        tag = "connected" if net["active"] else ("password" if net["secure"] else "open")
        G.text(surf, f.small, tag, (r.right - f.base * 4 - 16, r.y + 9), T.OK if net["active"] else T.MUTED, right=True)
        G.meter(surf, pygame.Rect(r.right - f.base * 4, r.y + 10, f.base * 4 - 12, f.small_line - 8), net["signal"] / 100)


class NetworkPage(Page):
    title = "NETWORK"
    hints = [("A", "change")]

    def __init__(self, app):
        super().__init__(app)
        self.list = ListView(row_lines=2)
        self.enter()

    def enter(self):
        s = self.app.system
        wifi = s.wifi()
        if wifi is None:
            w = ("Wi-Fi", "No Wi-Fi card. Plug one in.", None)
        elif wifi["state"] == "connected":
            w = ("Wi-Fi", f"{wifi['ssid']}  ·  {wifi['address']}", self.join)
        else:
            w = ("Wi-Fi", "Not connected. Press A to join a network.", self.join)
        ssh = s.cached("ssh", 5, s.ssh_enabled)
        addr = wifi["address"] if wifi and wifi.get("address") else f"{s.hostname()}.local"
        self.list.set([w, ("Remote access (SSH)", f"On  ·  ssh ark@{addr}" if ssh else "Off", self.toggle_ssh)])

    def tick(self):
        self.enter()

    def join(self):
        self.app.push(WifiList(self.app))

    def toggle_ssh(self):
        s = self.app.system
        on = s.cached("ssh", 5, s.ssh_enabled)

        def go():
            ok, msg = s.set_ssh(not on)
            s.forget("ssh")
            self.app.toast(("Remote access is " + ("off" if on else "on")) if ok else (msg or "Could not change it"), error=not ok)
            self.enter()
        if on:
            self.app.confirm("Turn remote access off?", "Nobody can log in over the network until you turn it on again here.",
                             "Turn off", go)
        else:
            go()

    def handle(self, action):
        if self.list.move(action):
            return
        if action == "a" and self.list.current and self.list.current[2]:
            self.list.current[2]()

    def draw(self, surf, f, area):
        self.list.draw(surf, f, pygame.Rect(area.x + 12, area.y + 10, area.w - 24, area.h - 16), self.row)

    def row(self, surf, f, r, it, selected):
        G.text(surf, f.big, it[0], (r.x + 14, r.y + 6), T.EMBER_BRIGHT if selected else T.TEXT)
        G.text(surf, f.small, G.fit(f.small, it[1], r.w - 28), (r.x + 14, r.y + 10 + f.line), T.MUTED)
