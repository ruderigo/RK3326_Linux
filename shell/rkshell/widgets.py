"""Building blocks shared by the pages: screens, lists, menus, the keyboard.

A screen implements:
    handle(action)   action is one of up down left right a b x y l1 r1 l2 r2 start select
    text_input(s)    optional: text typed on a real keyboard
    draw(surf, f, area)
    hints            [(button, label)] for the bottom bar

Rows and keys say where they are as they draw (gfx.spot), which is all the
pointer needs to press them.
"""
import pygame

from . import gfx as G
from . import theme as T


class Screen:
    title = ""
    hints = []
    wants_keys = False      # True: text typed on a real keyboard goes to text_input()
    live = False            # True: poll() is called many times a second

    def __init__(self, app):
        self.app = app

    def handle(self, action):
        if action == "b":
            self.app.pop()

    def text_input(self, s):
        pass

    def tick(self):
        """Called about once a second while the screen is shown."""

    def poll(self):
        """Called on every turn of the main loop while the screen is shown."""

    def draw(self, surf, f, area):
        pass


class ListView:
    """A scrolling list of rows with one selected. Rows are drawn by a callback."""

    def __init__(self, row_lines=1):
        self.items, self.sel, self.row_lines = [], 0, row_lines

    def set(self, items, keep=True):
        self.items = items
        self.sel = min(self.sel, max(0, len(items) - 1)) if keep else 0

    @property
    def current(self):
        return self.items[self.sel] if self.items else None

    def move(self, action, selectable=lambda it: True):
        n = len(self.items)
        if not n or action not in ("up", "down"):
            return False
        step = -1 if action == "up" else 1
        for _ in range(n):
            self.sel = (self.sel + step) % n
            if selectable(self.items[self.sel]):
                break
        return True

    def draw(self, surf, f, area, draw_row):
        row_h = f.line * self.row_lines + 10
        visible = max(1, area.h // row_h)
        top = max(0, min(self.sel - visible // 2, len(self.items) - visible))
        y = area.y
        for i, it in enumerate(self.items[top:top + visible], start=top):
            r = pygame.Rect(area.x, y, area.w, row_h - 4)
            if i == self.sel:
                G.box(surf, r, T.ROW, 6, T.BORDER)
            draw_row(surf, f, r, it, i == self.sel)
            G.spot(r, lambda i=i: setattr(self, "sel", i))
            y += row_h
        if top > 0:
            G.text(surf, f.small, "▲", (area.right - 4, area.y - f.small_line + 2), T.DIM, right=True)
        if top + visible < len(self.items):
            G.text(surf, f.small, "▼", (area.right - 4, area.bottom - 4), T.DIM, right=True)


class Menu(Screen):
    """A boxed list of (label, callback) choices over the current page."""
    hints = [("A", "choose"), ("B", "back")]

    def __init__(self, app, title, items, detail=None):
        super().__init__(app)
        self.title, self.items, self.detail, self.sel = title, items, detail, 0

    def handle(self, action):
        if action in ("up", "down") and self.items:
            self.sel = (self.sel + (-1 if action == "up" else 1)) % len(self.items)
        elif action == "a" and self.items:
            cb = self.items[self.sel][1]
            self.app.pop()
            if cb:
                cb()
        elif action == "b":
            self.app.pop()

    def draw(self, surf, f, area):
        w = min(area.w - 40, f.base * 24)
        lines = G.wrap(f.small, self.detail, w - 28) if self.detail else []
        # the title and each choice take a second line when they need it, not an ellipsis
        title = G.wrap(f.big, self.title, w - 28)[:2]
        labels = [G.wrap(f.mono, label, w - 44)[:2] for label, _ in self.items]
        rows_h = [len(ls) * f.line + 8 for ls in labels]
        fixed = len(title) * f.line + 16 + 24
        room = area.h - 8
        # A long menu on a small screen: the explanation gives way first, then
        # the choices scroll around the chosen one. Nothing is drawn outside.
        if fixed + len(lines) * f.small_line + sum(rows_h) > room:
            lines = []
        first, last = 0, len(labels)
        if fixed + sum(rows_h) > room:
            first = last = self.sel
            used = 0
            while True:
                grew = False
                if last < len(labels) and used + rows_h[last] <= room - fixed:
                    used += rows_h[last]; last += 1; grew = True
                if first > 0 and used + rows_h[first - 1] <= room - fixed:
                    first -= 1; used += rows_h[first]; grew = True
                if not grew:
                    break
            last = max(last, first + 1)
        h = fixed + len(lines) * f.small_line + sum(rows_h[first:last])
        r = self.rect = pygame.Rect(area.centerx - w // 2, area.centery - h // 2, w, h)
        G.box(surf, r, T.PANEL, 8, T.EMBER)
        y = r.y + 12
        for k, ln in enumerate(title):
            G.text(surf, f.big, ln if k == 0 or len(title) < 2 else G.fit(f.big, ln, w - 28), (r.x + 14, y), T.EMBER_BRIGHT)
            y += f.line
        y += 10
        for ln in lines:
            G.text(surf, f.small, ln, (r.x + 14, y), T.MUTED)
            y += f.small_line
        y += 8 if lines else 0
        if first > 0:
            G.text(surf, f.small, "▲", (r.right - 14, r.y + 12), T.MUTED, right=True)
        if last < len(labels):
            G.text(surf, f.small, "▼", (r.right - 14, r.bottom - f.small_line - 6), T.MUTED, right=True)
        for i, ls in enumerate(labels):
            if not first <= i < last:
                continue
            row = pygame.Rect(r.x + 8, y, w - 16, len(ls) * f.line + 4)
            if i == self.sel:
                G.box(surf, row, T.ROW, 5, T.BORDER)
            for k, ln in enumerate(ls):
                G.text(surf, f.mono, G.fit(f.mono, ln, w - 44), (row.x + 10, row.y + 2 + k * f.line),
                       T.EMBER_BRIGHT if i == self.sel else T.TEXT)
            G.spot(row, lambda i=i: setattr(self, "sel", i))
            y += row.h + 4


class Keyboard(Screen):
    """On-screen keyboard, the same controls as FireFly's: A types, B deletes,
    X space, Y shift, L1/R1 change the page of keys, START confirms. A real
    keyboard types straight in."""
    hints = [("A", "type"), ("B", "delete"), ("X", "space"), ("Y", "shift"), ("L1/R1", "keys"), ("START", "done")]
    wants_keys = True
    PAGES = [["1234567890", "qwertyuiop", "asdfghjkl-", "zxcvbnm_.@"],
             ["!\"#$%&'()*", "+,-./:;<=>", "?@[\\]^_`{|", "}~€£¥•°§¶ "]]

    def __init__(self, app, title, on_done, secret=False, initial=""):
        super().__init__(app)
        self.title, self.on_done, self.secret, self.value = title, on_done, secret, initial
        self.page, self.row, self.col, self.shift, self.show = 0, 1, 0, False, not secret

    def key(self):
        ch = self.PAGES[self.page][self.row][self.col]
        return ch.upper() if self.shift else ch

    def handle(self, action):
        rows = self.PAGES[self.page]
        if action in ("up", "down"):
            self.row = (self.row + (-1 if action == "up" else 1)) % len(rows)
        elif action in ("left", "right"):
            self.col = (self.col + (-1 if action == "left" else 1)) % len(rows[self.row])
        elif action == "a":
            self.value += self.key()
        elif action == "b":
            if self.value:
                self.value = self.value[:-1]
            else:
                self.app.pop()
        elif action == "x":
            self.value += " "
        elif action == "y":
            self.shift = not self.shift
        elif action in ("l1", "r1"):
            self.page = (self.page + 1) % len(self.PAGES)
        elif action == "select" and self.secret:
            self.show = not self.show
        elif action == "start":
            self.app.pop()
            self.on_done(self.value)

    def text_input(self, s):
        if s == "\x1b":                 # Escape on a real keyboard
            return self.app.pop()
        if s.startswith("\x1b"):        # arrow keys and the like mean nothing here
            return
        for ch in s:
            if ch in ("\r", "\n"):
                self.app.pop()
                self.on_done(self.value)
                return
            if ch in ("\x08", "\x7f"):
                self.value = self.value[:-1]
            elif ch.isprintable():
                self.value += ch

    def draw(self, surf, f, area):
        r = pygame.Rect(area.x + 16, area.y + 16, area.w - 32, area.h - 32)
        G.box(surf, r, T.PANEL, 8, T.EMBER)
        # the question is read whole: in smaller letters when the large ones do not fit
        font = next((ft for ft in (f.big, f.mono, f.small) if ft.size(self.title)[0] <= r.w - 28), f.small)
        G.text(surf, font, G.fit(font, self.title, r.w - 28), (r.x + 14, r.y + 12), T.EMBER_BRIGHT)
        field = pygame.Rect(r.x + 14, r.y + 22 + f.line, r.w - 28, f.line + 14)
        G.box(surf, field, T.BG, 6, T.BORDER)
        shown = self.value if self.show else "•" * len(self.value)
        while f.mono.size(shown + "▏")[0] > field.w - 16 and shown:
            shown = shown[1:]
        G.text(surf, f.mono, shown + "▏", (field.x + 8, field.y + 6), T.TEXT)
        if self.secret:
            G.text(surf, f.small, "SELECT shows or hides it", (r.x + 14, field.bottom + 6), T.DIM)
        rows = self.PAGES[self.page]
        cell = min((r.w - 28) // 10, (r.bottom - field.bottom - 50) // len(rows))
        x0 = r.centerx - cell * 5
        y0 = r.bottom - cell * len(rows) - 14
        for ri, line in enumerate(rows):
            for ci, ch in enumerate(line):
                c = pygame.Rect(x0 + ci * cell + 3, y0 + ri * cell + 3, cell - 6, cell - 6)
                on = ri == self.row and ci == self.col
                G.box(surf, c, T.EMBER if on else T.ROW, 6, T.BORDER)
                G.text(surf, f.big, ch.upper() if self.shift else ch, (c.centerx, c.centery - f.line // 2 - 2),
                       T.BG if on else T.TEXT, center=True)
                G.spot(c, lambda ri=ri, ci=ci: (setattr(self, "row", ri), setattr(self, "col", ci)))


class TextView(Screen):
    """A page of text to read, scrolled with up and down."""
    hints = [("↑↓", "scroll"), ("B", "back")]

    def __init__(self, app, title, text):
        super().__init__(app)
        self.title, self.text, self.top, self.lines = title, text, 0, None

    def handle(self, action):
        if action == "b":
            self.app.pop()
        elif action in ("up", "down") and self.lines:
            self.top = max(0, min(len(self.lines) - 1, self.top + (-3 if action == "up" else 3)))

    def draw(self, surf, f, area):
        r = pygame.Rect(area.x + 12, area.y + 12, area.w - 24, area.h - 24)
        G.box(surf, r, T.PANEL, 8, T.BORDER)
        G.text(surf, f.big, G.fit(f.big, self.title, r.w - 28), (r.x + 14, r.y + 10), T.EMBER_BRIGHT)
        if self.lines is None:
            self.lines = G.wrap(f.small, self.text.expandtabs(4), r.w - 28)
        y = r.y + 18 + f.line
        for ln in self.lines[self.top:]:
            if y + f.small_line > r.bottom - 8:
                break
            G.text(surf, f.small, ln, (r.x + 14, y), T.TEXT)
            y += f.small_line
