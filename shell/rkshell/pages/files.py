"""FILES: look through the data partition, the card's settings and USB drives."""
import os

import pygame

from .. import gfx as G
from .. import theme as T
from ..widgets import ListView, Menu, TextView
from .base import Page

TEXT_LIMIT = 200 * 1024


class FilesPage(Page):
    title = "FILES"

    def __init__(self, app):
        super().__init__(app)
        self.list = ListView()
        self.path = None                # None: the list of places
        self.enter()

    @property
    def hints(self):
        return [("A", "open")] + ([("B", "up"), ("X", "more")] if self.path else [])

    def enter(self):
        s = self.app.system
        if self.path is None:
            self.list.set([{"name": n, "path": p, "dir": True, "place": True} for n, p in s.places()])
            return
        rows = s.listdir(self.path)
        if rows is None:
            self.app.toast(f"Cannot read {self.path}", error=True)
            self.path = None
            return self.enter()
        self.list.set([{"name": n, "path": os.path.join(self.path, n), "dir": d, "size": sz} for n, d, sz in rows])

    def open(self, it):
        if it["dir"]:
            self.path = it["path"]
            self.list.sel = 0
            return self.enter()
        if it.get("size", 0) > TEXT_LIMIT:
            return self.app.toast("Too large to show here", error=True)
        try:
            with open(it["path"], "rb") as fh:
                raw = fh.read(TEXT_LIMIT)
            if b"\0" in raw:
                return self.app.toast("Not a text file", error=True)
            self.app.push(TextView(self.app, it["name"], raw.decode("utf-8", "replace")))
        except OSError as e:
            self.app.toast(str(e), error=True)

    def delete(self, it):
        def go():
            try:
                os.rmdir(it["path"]) if it["dir"] else os.remove(it["path"])
                self.app.toast(f"Deleted {it['name']}")
            except OSError as e:
                self.app.toast(e.strerror or str(e), error=True)
            self.enter()
        what = "this empty folder" if it["dir"] else "this file"
        self.app.confirm(f"Delete {it['name']}?", f"Delete {what}. This cannot be undone.", "Delete", go)

    def handle(self, action):
        if self.list.move(action):
            return
        it = self.list.current
        if action == "a" and it:
            self.open(it)
        elif action == "b" and self.path:
            places = [p for _, p in self.app.system.places()]
            self.path = None if self.path in places else os.path.dirname(self.path)
            self.list.sel = 0
            self.enter()
        elif action == "x" and it and self.path:
            self.app.push(Menu(self.app, it["name"], [("Open", lambda: self.open(it)), ("Delete", lambda: self.delete(it))]))

    def draw(self, surf, f, area):
        where = self.path or "Places"
        G.text(surf, f.small, G.fit(f.small, where, area.w - 24), (area.x + 14, area.y + 6), T.MUTED)
        lst = pygame.Rect(area.x + 12, area.y + 12 + f.small_line, area.w - 24, area.h - 16 - f.small_line)
        if not self.list.items:
            G.text(surf, f.mono, "Empty folder", (lst.x + 8, lst.y + 8), T.DIM)
            return
        self.list.draw(surf, f, lst, self.row)

    def row(self, surf, f, r, it, selected):
        color = T.EMBER_BRIGHT if selected else T.TEXT
        mark = "▸ " if it["dir"] else "  "
        G.text(surf, f.mono, mark + G.fit(f.mono, it["name"], r.w - f.base * 7), (r.x + 10, r.y + 5), color)
        note = it["path"] if it.get("place") else ("folder" if it["dir"] else G.size(it.get("size", 0)))
        G.text(surf, f.small, G.fit(f.small, note, f.base * 9), (r.right - 12, r.y + 9), T.MUTED, right=True)
