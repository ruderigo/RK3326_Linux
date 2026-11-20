"""Scan: nmap, played as a loadout.

You pick a target, then equip the scan: its mission, how many ports, the
technique, and the extras (service versions, OS guess, script packs, speed).
Two gauges show what the loadout costs in time and in noise, and the nmap
command it stands for is written underneath, so the window teaches the tool
instead of hiding it. X launches; the hosts come back as a list to open,
aim at, or save.
"""
import math
import time

import pygame

from .. import gfx as G
from .. import nmapspec as N
from .. import theme as T
from ..widgets import Keyboard, ListView, Menu, TextView
from .base import Page

ROWS = ["target", "preset"] + [key for key, _, _ in N.ABILITIES]
NAMES = {key: name for key, name, _ in N.ABILITIES}
VALUES = {key: values for key, _, values in N.ABILITIES}
TIME_WORDS = ["seconds", "under a minute", "a few minutes", "many minutes", "a long wait"]
NOISE_WORDS = ["a whisper", "quiet", "noticeable", "loud", "very loud"]


def word(words, fraction):
    return words[min(len(words) - 1, int(fraction * len(words)))]


class ScanPage(Page):
    title, icon = "Scan", "radar"
    spec = None                     # the loadout, the last scan and its hosts outlive the window
    scan = None
    hosts = []

    def __init__(self, app):
        super().__init__(app)
        self.sel, self.view = 0, "loadout"
        self.list = ListView(row_lines=2)
        self.networks = []

    # ------------------------------------------------------------- state
    def enter(self):
        cls = ScanPage
        self.networks = self.app.system.own_networks()
        if cls.spec is None:
            cls.spec = N.preset("Quick look", self.networks[0][1] if self.networks else "")
        if cls.scan and cls.scan.result is None:
            self.view = "running"
        elif cls.hosts:
            self.show_results()

    @property
    def live(self):
        return self.view == "running"

    @property
    def hints(self):
        if self.view == "running":
            return [("B", "stop")]
        if self.view == "results":
            return [("A", "details"), ("X", "aim at it"), ("Y", "save"), ("B", "loadout")]
        hints = [("◄►", "change"), ("X", "launch")]
        if ScanPage.hosts:
            hints.append(("Y", "last result"))
        return hints + [("B", "close")]

    def wants_back(self):
        return self.view != "loadout"

    def preset_name(self):
        for name, _ in N.PRESETS:
            if N.preset(name, self.spec["target"]) == self.spec:
                return name
        return "Custom"

    def me(self):
        return {n[2] for n in self.networks}

    # ----------------------------------------------------------- loadout
    def change(self, step):
        key, spec = ROWS[self.sel], self.spec
        if key == "target":
            known = [n[1] for n in self.networks] + [h["address"] for h in ScanPage.hosts]
            if known:
                i = known.index(spec["target"]) + step if spec["target"] in known else 0
                spec["target"] = known[i % len(known)]
        elif key == "preset":
            names = [name for name, _ in N.PRESETS]
            now = self.preset_name()
            i = names.index(now) + step if now in names else 0
            ScanPage.spec = N.preset(names[i % len(names)], spec["target"])
        elif N.applies(key, spec):
            values = [v for v, _ in VALUES[key]]
            spec[key] = values[(values.index(spec[key]) + step) % len(values)] if spec[key] in values else values[0]

    def choose_target(self):
        def aim(target):
            self.spec["target"] = target
        items = [(f"{net}  (this network)", lambda net=net: aim(net)) for _, net, _ in self.networks]
        items += [(f"{own}  (this handheld)", lambda own=own: aim(own)) for _, _, own in self.networks]
        items.append(("Type a target…", lambda: self.app.push(
            Keyboard(self.app, "Target: address, name or range", lambda v: aim(" ".join(v.split())), initial=self.spec["target"]))))
        self.app.push(Menu(self.app, "Target", items, "An address (192.168.0.42), a name, a range (192.168.0.1-50) "
                           "or a network (192.168.0.0/24). Only scan what is yours, or what you have been asked to test."))

    def type_ports(self):
        def done(v):
            v = v.replace(" ", "")
            if v and N.PORTS_OK.match(v):
                self.spec["ports"] = v
            elif v:
                self.app.toast("Ports look like 22,80,8000-8100", 4, error=True)
        self.app.push(Keyboard(self.app, "Ports, such as 22,80,8000-8100", done,
                               initial="" if self.spec["ports"] in ("top100", "top1000", "all") else self.spec["ports"]))

    def launch(self):
        why = N.problem(self.spec)
        if why:
            self.app.toast(why, 4, error=True)
            if not self.spec["target"]:
                self.sel = 0
            return
        ScanPage.scan = self.app.system.start_scan(dict(self.spec))
        self.view = "running"

    # ----------------------------------------------------------- results
    def poll(self):
        scan = ScanPage.scan
        if self.view != "running" or scan is None:
            return
        self.app.dirty = True
        if scan.result is None:
            return
        ok, res = scan.result
        if ok:
            ScanPage.hosts = res
            self.show_results()
        else:
            self.view = "loadout"
            self.app.toast(res, 5, error=not scan.cancelled)

    def show_results(self):
        self.list.set(ScanPage.hosts, keep=False)
        self.view = "results"

    def report(self, hosts):
        scan, lines = ScanPage.scan, []
        if scan:
            lines += [" ".join(N.command(scan.spec)), f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(scan.started))}, "
                      f"{scan.seconds} s, {len(ScanPage.hosts)} hosts up", ""]
        for h in hosts:
            lines.append(h["address"] + (f"  {h['name']}" if h["name"] else "") + ("  (this handheld)" if h["address"] in self.me() else ""))
            if h["mac"]:
                lines.append(f"  {h['mac']}  {h['vendor']}".rstrip())
            if h["os"]:
                lines.append(f"  OS guess: {h['os']}")
            for p in h["ports"]:
                lines.append(f"  {p['port']:>5}/{p['proto']}  {p['service']}  {p['product']}".rstrip() + ("" if p["state"] == "open" else f"  [{p['state']}]"))
                for name, text in p["notes"]:
                    lines += [f"         {name}:"] + [f"           {ln.strip()}" for ln in text.splitlines() if ln.strip()]
            for name, text in h["notes"]:
                lines += [f"  {name}:"] + [f"    {ln.strip()}" for ln in text.splitlines() if ln.strip()]
            if scan and scan.spec["mode"] == "ports" and not h["ports"]:
                lines.append("  no open port found")
            lines.append("")
        return "\n".join(lines)

    def save(self):
        path = self.app.system.save_report("scan", self.report(ScanPage.hosts))
        self.app.toast(f"Saved to {path}" if path else "Could not save", 5, error=not path)

    # ------------------------------------------------------------- input
    def handle(self, action):
        if self.view == "running":
            if action == "b" and ScanPage.scan:
                ScanPage.scan.cancel()
        elif self.view == "results":
            host = self.list.current
            if self.list.move(action):
                pass
            elif action == "b":
                self.view = "loadout"
            elif action == "a" and host:
                self.app.push(TextView(self.app, host["address"], self.report([host]).split("\n\n", 1)[-1]))
            elif action == "x" and host:
                self.spec["target"] = host["address"]
                if self.spec["mode"] == "sweep":
                    ScanPage.spec = N.preset("Identify", host["address"])
                self.view, self.sel = "loadout", 1
                self.app.toast(f"Aimed at {host['address']}")
            elif action == "y":
                self.save()
        elif action in ("up", "down"):
            self.sel = (self.sel + (-1 if action == "up" else 1)) % len(ROWS)
        elif action in ("left", "right"):
            self.change(-1 if action == "left" else 1)
        elif action == "a":
            if ROWS[self.sel] == "target":
                self.choose_target()
            elif ROWS[self.sel] == "ports" and N.applies("ports", self.spec):
                self.app.push(Menu(self.app, "Ports", [(label, lambda v=v: self.spec.update(ports=v)) for v, label in VALUES["ports"]]
                                   + [("Type a list…", self.type_ports)]))
            else:
                self.change(1)
        elif action in ("x", "start"):
            self.launch()
        elif action == "y" and ScanPage.hosts:
            self.show_results()

    # -------------------------------------------------------------- draw
    def draw(self, surf, f, area):
        {"loadout": self.draw_loadout, "running": self.draw_running, "results": self.draw_results}[self.view](surf, f, area)

    def value(self, key):
        spec = self.spec
        if key == "target":
            mine = {n[1]: "local" for n in self.networks}
            mine.update({n[2]: "me" for n in self.networks})
            return (spec["target"] + (f"  ({mine[spec['target']]})" if spec["target"] in mine else "")) or "choose one"
        if key == "preset":
            return self.preset_name()
        return dict(VALUES[key]).get(spec[key], str(spec[key]))

    def draw_loadout(self, surf, f, area):
        spec, pad = self.spec, 12
        foot = f.small_line * 3 + 44
        room = area.h - foot - 14
        row_h = f.line + 10 if len(ROWS) * (f.line + 10) <= room else f.line + 4
        visible = max(1, min(len(ROWS), room // row_h))             # a short screen scrolls the rows
        top = max(0, min(self.sel - visible // 2, len(ROWS) - visible))
        label_w = f.mono.size("Skip the ping  ")[0]
        y = area.y + 6
        for i, key in list(enumerate(ROWS))[top:top + visible]:
            r = pygame.Rect(area.x + pad, y, area.w - 2 * pad, row_h - 3)
            on = key in ("target", "preset") or N.applies(key, spec)
            if i == self.sel:
                G.box(surf, r, T.ROW, 6, T.EMBER if on else T.BORDER)
            ty = r.y + (r.h - f.line) // 2
            G.text(surf, f.mono, {"target": "Target", "preset": "Loadout"}.get(key, NAMES.get(key)), (r.x + 12, ty),
                   (T.MUTED if on else T.DIM))
            color = T.DIM if not on else T.EMBER_BRIGHT if i == self.sel else T.TEXT
            if key == "target" and not spec["target"]:
                color = T.ERROR
            text = self.value(key) if on else "—"
            G.text(surf, f.mono, G.fit(f.mono, text, r.w - label_w - 70), (r.x + 12 + label_w, ty), color)
            if i == self.sel and on:
                G.text(surf, f.mono, "◄ ►" if key != "target" else "A", (r.right - 12, ty), T.EMBER, right=True)
            y += row_h
        if top > 0:
            G.text(surf, f.small, "▲", (area.right - pad, area.y - 2), T.DIM, right=True)
        if top + visible < len(ROWS):
            G.text(surf, f.small, "▼", (area.right - pad, area.bottom - foot - f.small_line), T.DIM, right=True)
        # what it costs, and the command it stands for
        y = area.bottom - foot
        pygame.draw.line(surf, T.BORDER, (area.x + pad, y), (area.right - pad, y))
        y += 10
        t, n = N.cost(spec)
        half = (area.w - 2 * pad - 16) // 2
        for j, (name, frac, words, color) in enumerate((("TIME", t, TIME_WORDS, T.EMBER), ("NOISE", n, NOISE_WORDS, T.ERROR if n > 0.7 else T.EMBER))):
            x = area.x + pad + j * (half + 16)
            G.text(surf, f.small, name, (x, y), T.MUTED)
            G.text(surf, f.small, word(words, frac), (x + half, y), T.TEXT, right=True)
            G.meter(surf, pygame.Rect(x, y + f.small_line + 2, half, 12), frac, color)
        y += f.small_line + 24
        why = N.problem(spec)
        cmd = "$ " + " ".join(N.command(spec)) if not why else why
        for k, ln in enumerate(G.wrap(f.small, cmd, area.w - 2 * pad)[:2]):
            G.text(surf, f.small, ln, (area.x + pad, y + k * f.small_line), T.OK if not why else T.ERROR)

    def draw_running(self, surf, f, area):
        scan = ScanPage.scan
        cx, cy, rad = area.centerx, area.y + area.h * 2 // 5, min(area.w, area.h) // 4
        for k in (1, 2, 3):
            pygame.draw.circle(surf, T.BORDER, (cx, cy), rad * k // 3, 2)
        ang = time.time() * 2.4
        for k in range(14):                                         # the sweep, with a fading tail
            a = ang - k * 0.05
            c = tuple(int(T.BG[i] + (T.EMBER_BRIGHT[i] - T.BG[i]) * (1 - k / 14)) for i in range(3))
            pygame.draw.line(surf, c, (cx, cy), (cx + math.cos(a) * rad, cy + math.sin(a) * rad), 3)
        y = cy + rad + 20
        secs = scan.seconds if scan else 0
        G.text(surf, f.big, "Stopping…" if scan and scan.cancelled else f"Scanning  {secs // 60}:{secs % 60:02d}", (cx, y), T.EMBER_BRIGHT, center=True)
        y += f.line + 14
        if scan:
            for ln in G.wrap(f.small, "$ " + " ".join(N.command(scan.spec)), area.w - 40)[:3]:
                G.text(surf, f.small, ln, (cx, y), T.OK, center=True)
                y += f.small_line
            G.text(surf, f.small, f"Expect {word(TIME_WORDS, N.cost(scan.spec)[0])}. B stops it.",
                   (cx, y + 8), T.DIM, center=True)

    def draw_results(self, surf, f, area):
        scan, x, y = ScanPage.scan, area.x + 16, area.y + 8
        up = len(self.list.items)
        opened = sum(len(h["ports"]) for h in self.list.items)
        head = f"{up} host{'s' * (up != 1)} up" + (f" · {opened} open port{'s' * (opened != 1)}" if scan and scan.spec["mode"] == "ports" else "")
        G.text(surf, f.small, head, (x, y), T.OK)
        if scan:
            G.text(surf, f.small, f"{scan.seconds} s", (area.right - 16, y), T.MUTED, right=True)
            G.text(surf, f.small, G.fit(f.small, "$ " + " ".join(N.command(scan.spec)), area.w - 32), (x, y + f.small_line), T.DIM)
        y += f.small_line * 2 + 8
        if not self.list.items:
            G.text(surf, f.mono, "Nothing answered.", (x, y), T.MUTED)
            G.text(surf, f.small, "A host that hides from pings may answer with Skip the ping on.", (x, y + f.line + 4), T.DIM)
            return
        self.list.draw(surf, f, pygame.Rect(area.x + 12, y, area.w - 24, area.bottom - y - 4), self.row)

    def row(self, surf, f, r, h, selected):
        G.text(surf, f.big, h["address"], (r.x + 14, r.y + 6), T.EMBER_BRIGHT if selected else T.TEXT)
        mine = h["address"] in self.me()
        what = " · ".join(x for x in (h["name"], h["vendor"], h["os"].split(" (")[0]) if x) or ("this handheld" if mine else "no name")
        if mine and what != "this handheld":
            what += " · this handheld"
        G.text(surf, f.small, G.fit(f.small, what, r.w - 28), (r.x + 14, r.y + 10 + f.line), T.MUTED)
        if h["ports"]:
            ports = " ".join(str(p["port"]) for p in h["ports"][:6]) + (" …" if len(h["ports"]) > 6 else "")
            G.text(surf, f.small, ports, (r.right - 14, r.y + 10), T.OK, right=True)
