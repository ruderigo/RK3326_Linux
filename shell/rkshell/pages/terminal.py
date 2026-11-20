"""Terminal: a real shell in a window.

A login shell runs on a pseudo-terminal and pyte keeps the picture of its
screen (what a VT100 would show); this page draws that picture and sends
keys. The shell keeps running while the window is closed, so a long command
can be left and looked at again later.

With the gamepad alone: the D-pad is the arrow keys, A is Enter, Y is
Ctrl+C, START is Tab, L1/R1 scroll back, and X opens a keyboard under the
terminal. A USB keyboard types straight in, Ctrl keys and arrows included.
"""
import fcntl
import os
import pty
import signal
import struct
import termios

import pygame
import pyte

from .. import gfx as G
from .. import theme as T
from ..widgets import Keyboard
from .base import Page

ARROWS = {"up": "\x1b[A", "down": "\x1b[B", "right": "\x1b[C", "left": "\x1b[D"}
COLORS = {"default": T.TEXT, "black": (0x3a, 0x30, 0x26), "red": T.ERROR, "green": T.OK, "brown": T.EMBER_BRIGHT,
          "yellow": T.EMBER_BRIGHT, "blue": (0x7a, 0xa2, 0xc8), "magenta": (0xc8, 0xa2, 0xc8), "cyan": (0x8a, 0xc0, 0xb8),
          "white": T.TEXT, "brightblack": T.DIM, "brightred": (0xf0, 0x90, 0x70), "brightgreen": (0xb4, 0xd0, 0x8c),
          "brightbrown": (0xff, 0xc0, 0x70), "brightyellow": (0xff, 0xc0, 0x70), "brightblue": (0x9a, 0xc0, 0xe0),
          "brightmagenta": (0xe0, 0xc0, 0xe0), "brightcyan": (0xa8, 0xd8, 0xd0), "brightwhite": (0xff, 0xf4, 0xe0)}


def colour(name, default):
    if name in COLORS:
        return default if name == "default" else COLORS[name]
    try:
        return tuple(int(name[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, TypeError):
        return default


class Session:
    """A shell on a pseudo-terminal, and the picture of its screen."""

    def __init__(self, cols, rows, argv=None):
        self.cols, self.rows = cols, rows
        self.screen = pyte.HistoryScreen(cols, rows, history=2000, ratio=0.5)
        self.stream = pyte.ByteStream(self.screen)
        self.alive = True
        self.pid, self.fd = pty.fork()
        if self.pid == 0:                                   # the child: become the shell
            home = "/data/ark" if os.path.isdir("/data/ark") else os.path.expanduser("~")
            try:
                os.chdir(home)
            except OSError:
                pass
            os.environ.update(TERM="linux", COLUMNS=str(cols), LINES=str(rows))
            argv = argv or [os.environ.get("SHELL") or "/bin/bash", "-l"]
            try:
                os.execvp(argv[0], argv)
            finally:
                os._exit(127)
        fcntl.fcntl(self.fd, fcntl.F_SETFL, fcntl.fcntl(self.fd, fcntl.F_GETFL) | os.O_NONBLOCK)
        self._winsize()

    def _winsize(self):
        try:
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", self.rows, self.cols, 0, 0))
        except OSError:
            pass

    def resize(self, cols, rows):
        if (cols, rows) != (self.cols, self.rows) and cols > 3 and rows > 1:
            self.cols, self.rows = cols, rows
            self.screen.resize(rows, cols)
            self._winsize()

    def read(self):
        """Take in what the shell printed. True when the picture changed."""
        changed = False
        while self.alive:
            try:
                data = os.read(self.fd, 65536)
            except BlockingIOError:
                break
            except OSError:
                data = b""
            if not data:                                    # the shell ended
                self.alive = False
                try:
                    os.waitpid(self.pid, os.WNOHANG)
                except OSError:
                    pass
                return True
            self.stream.feed(data)
            changed = True
        return changed

    def write(self, s):
        if self.alive:
            try:
                os.write(self.fd, s.encode("utf-8", "replace"))
            except OSError:
                pass

    def close(self):
        if self.alive:
            try:
                os.kill(self.pid, signal.SIGHUP)
            except OSError:
                pass
        try:
            os.close(self.fd)
        except OSError:
            pass
        self.alive = False


class TerminalPage(Page):
    title, icon = "Terminal", "terminal"
    wants_keys = True            # a real keyboard types into it
    live = True                  # look for output often, not once a second
    session = None               # one shell for the whole desktop: it outlives the window

    def __init__(self, app):
        super().__init__(app)
        self.keys, self.page, self.row, self.col, self.shift = False, 0, 1, 0, False

    @property
    def hints(self):
        if self.keys:
            return [("A", "type"), ("B", "del"), ("X", "space"), ("Y", "shift"), ("L1", "keys"),
                    ("START", "enter"), ("SEL", "hide")]        # also: L2 is Tab, R2 is Ctrl+C
        return [("X", "keyboard"), ("A", "enter"), ("Y", "^C"), ("START", "tab"), ("L1/R1", "scroll"), ("B", "close")]

    def poll(self):
        s = TerminalPage.session
        if s and s.read():
            self.app.dirty = True

    def send(self, s):
        sess = TerminalPage.session
        if sess is None or not sess.alive:
            if sess:
                sess.close()
            TerminalPage.session = None          # the next draw starts a new shell
            self.app.dirty = True
            return
        while sess.screen.history.position < sess.screen.history.size:      # typing goes back to the present
            sess.screen.next_page()
        sess.write(s)

    def text_input(self, s):
        self.send(s)

    def handle(self, action):
        sess = TerminalPage.session
        if action in ("l1", "r1") and not self.keys:
            if sess:
                sess.screen.prev_page() if action == "l1" else sess.screen.next_page()
            return
        if not self.keys:
            if action in ARROWS:
                self.send(ARROWS[action])
            elif action == "a":
                self.send("\r")
            elif action == "y":
                self.send("\x03")
            elif action == "start":
                self.send("\t")
            elif action == "x":
                self.keys = True
            return
        rows = Keyboard.PAGES[self.page]
        if action in ("up", "down"):
            self.row = (self.row + (-1 if action == "up" else 1)) % len(rows)
        elif action in ("left", "right"):
            self.col = (self.col + (-1 if action == "left" else 1)) % len(rows[self.row])
        elif action == "a":
            ch = rows[self.row][self.col]
            self.send(ch.upper() if self.shift else ch)
        elif action == "b":
            self.send("\x7f")
        elif action == "x":
            self.send(" ")
        elif action == "y":
            self.shift = not self.shift
        elif action in ("l1", "r1"):
            self.page = (self.page + 1) % len(Keyboard.PAGES)
        elif action == "l2":
            self.send("\t")
        elif action == "r2":
            self.send("\x03")
        elif action == "start":
            self.send("\r")
        elif action == "select":
            self.keys = False

    def wants_back(self):
        return self.keys                 # with the keyboard up, B deletes; otherwise it closes the window

    def draw(self, surf, f, area):
        font = f.small
        cw, ch = font.size("M")[0], f.small_line
        kb_h = 0
        if self.keys:
            rows = Keyboard.PAGES[self.page]
            cell = min((area.w - 16) // 10, area.h // 9)
            kb_h = cell * len(rows) + 10
        # The terminal keeps its full size whether or not the keyboard is up:
        # shrinking it would make the shell redraw and lose what is on screen.
        # With the keyboard up, the part around the cursor is shown.
        full = pygame.Rect(area.x + 8, area.y + 4, area.w - 16, area.h - 8)
        text_area = pygame.Rect(full.x, full.y, full.w, full.h - kb_h)
        cols, nrows = max(20, full.w // cw), max(4, full.h // ch)
        sess = TerminalPage.session
        if sess is None:
            sess = TerminalPage.session = Session(cols, nrows)
        else:
            sess.resize(cols, nrows)
        scr = sess.screen
        shown = max(1, min(nrows, text_area.h // ch))
        first = max(0, min(scr.cursor.y - shown + 1, nrows - shown))
        for y in range(shown):
            line = scr.buffer[first + y]
            x = 0
            while x < cols:
                c = line[x]
                fg, bg = colour(c.fg, T.TEXT), colour(c.bg, None)
                if c.reverse:
                    fg, bg = (bg or T.BG), fg
                run, x0 = "", x
                while x < cols:                             # a run of cells drawn the same way
                    d = line[x]
                    dfg, dbg = colour(d.fg, T.TEXT), colour(d.bg, None)
                    if d.reverse:
                        dfg, dbg = (dbg or T.BG), dfg
                    if (dfg, dbg, d.bold) != (fg, bg, c.bold):
                        break
                    run += d.data or " "
                    x += 1
                px, py = text_area.x + x0 * cw, text_area.y + y * ch
                if bg:
                    pygame.draw.rect(surf, bg, (px, py, len(run) * cw, ch))
                if run.strip():
                    if c.bold and fg == T.TEXT:
                        fg = COLORS["brightwhite"]
                    G.text(surf, font, run.rstrip() if not bg else run, (px, py), fg)
        at_present = scr.history.position >= scr.history.size
        if sess.alive and at_present and not scr.cursor.hidden and first <= scr.cursor.y < first + shown:
            cx, cy = text_area.x + scr.cursor.x * cw, text_area.y + (scr.cursor.y - first) * ch
            pygame.draw.rect(surf, T.EMBER, (cx, cy, cw, ch))
            under = scr.buffer[scr.cursor.y][scr.cursor.x].data
            if under.strip():
                G.text(surf, font, under, (cx, cy), T.BG)
        if not at_present:
            G.text(surf, f.small, "scrolled back  ·  R1 returns", (text_area.right, text_area.y), T.EMBER_BRIGHT, right=True)
        if not sess.alive:
            G.text(surf, f.small, "The shell ended. Press A for a new one.", (text_area.x, text_area.bottom - ch), T.EMBER_BRIGHT)
        if self.keys:
            rows = Keyboard.PAGES[self.page]
            x0, y0 = area.centerx - cell * 5, area.bottom - kb_h + 4
            pygame.draw.line(surf, T.BORDER, (area.x, y0 - 4), (area.right, y0 - 4))
            for ri, keys in enumerate(rows):
                for ci, k in enumerate(keys):
                    c = pygame.Rect(x0 + ci * cell + 2, y0 + ri * cell + 2, cell - 4, cell - 4)
                    on = ri == self.row and ci == self.col
                    G.box(surf, c, T.EMBER if on else T.ROW, 5, T.BORDER)
                    G.text(surf, f.mono, k.upper() if self.shift else k, (c.centerx, c.centery - f.line // 2),
                           T.BG if on else T.TEXT, center=True)
