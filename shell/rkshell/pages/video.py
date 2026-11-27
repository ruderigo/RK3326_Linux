"""Video: search YouTube and watch, with the pad.

X asks what to look for, A plays the chosen result. Playing is mpv's work
(through rk-video): the desktop steps aside and comes back when the video
ends or is stopped. In the player A pauses, left and right move ten seconds,
up and down a minute, L1 and R1 five minutes, B stops, and SELECT+START
stops as in every dock app.

The first time, and on a card flashed before Video was part of the image,
the window offers to set itself up: the player from Debian, the emulators
for Games, and
yt-dlp from its own releases, because only a recent one keeps up with
YouTube. Y fetches the newest yt-dlp at any time; that is the first thing to
try when videos stop playing; it also installs RetroArch for Games when that
is missing.
"""
import time

import pygame

from .. import gfx as G
from .. import theme as T
from ..widgets import Keyboard, ListView
from .base import Page


class VideoPage(Page):
    title, icon = "Video", "video"
    setup = None                    # a running setup outlives the window
    results, words = [], ""         # the last search stays when the window is closed

    def __init__(self, app):
        super().__init__(app)
        self.list = ListView(row_lines=2)
        self.status, self.search, self.told = None, None, False
        self.loading = None             # the video being started: shown for one frame, then handed to the player
        self.view = "list"

    def enter(self):
        self.status = self.app.system.video_status()
        self.list.set(VideoPage.results)
        if VideoPage.setup is not None:
            self.view = "setup"

    @property
    def ready(self):
        return bool(self.status and self.status["mpv"] and self.status["ytdlp"])

    @property
    def live(self):
        return self.view == "setup" or self.search is not None or self.loading is not None

    @property
    def hints(self):
        if self.view == "setup":
            job = VideoPage.setup
            return [("B", "back")] if job and job.done else [("B", "hide")]
        if not self.ready:
            return [("A", "set up"), ("B", "close")]
        hints = [("X", "search")]
        if self.list.items:
            hints.insert(0, ("A", "play"))
        return hints + [("Y", "update"), ("B", "close")]

    def wants_back(self):
        return self.view == "setup" and bool(VideoPage.setup and VideoPage.setup.done)

    # --------------------------------------------------------------- input
    def packages_missing(self):
        """True when Debian packages are to be installed too (the player, or RetroArch for Games)."""
        return not (self.status and self.status["mpv"]) or not self.app.system.games_installed()

    def start_setup(self, packages):
        if not self.app.system.online():
            self.app.toast("Join Wi-Fi first", 4, error=True)
            return
        VideoPage.setup = self.app.system.video_setup(packages)
        self.view, self.told = "setup", False

    def ask(self):
        def go(words):
            words = words.strip()
            if not words:
                return
            if not self.app.system.online():
                self.app.toast("Join Wi-Fi first", 4, error=True)
                return
            VideoPage.words = words
            self.search = self.app.system.video_search(words)
        self.app.push(Keyboard(self.app, "Search YouTube", go, initial=VideoPage.words))

    def play(self, video):
        """Say so first: the screen keeps this frame while the player gets the
        video's address, which can take a minute. poll() starts the player
        once the frame is drawn."""
        self.loading = {"video": video, "shown": False, "started": 0}

    def handle(self, action):
        if self.view == "setup":
            if action == "b" and VideoPage.setup and VideoPage.setup.done:
                VideoPage.setup, self.view = None, "list"
                self.status = self.app.system.video_status()
            return
        if not self.ready:
            if action == "a":
                self.start_setup(packages=self.packages_missing())
            return
        if self.search is not None or self.loading is not None:
            return                              # one thing at a time
        if self.list.move(action):
            return
        if action == "a" and self.list.current:
            self.play(self.list.current)
        elif action == "x":
            self.ask()
        elif action == "y":
            self.start_setup(packages=self.packages_missing())

    def poll(self):
        if self.loading is not None:
            self.app.dirty = True
            if self.loading["started"]:         # back from the player
                why = self.app.system.video_error(self.loading["started"])
                self.loading = None
                if why:
                    self.app.toast(why, 8, error=True)
            elif self.loading["shown"]:
                self.loading["started"] = time.time()
                self.app.launch = self.app.system.video_command(self.loading["video"]["id"])
                self.app.launch_item = {"name": "Video", "mouse": False}
        if self.search is not None:
            self.app.dirty = True
            if self.search.done:
                job, self.search = self.search, None
                if job.results:
                    VideoPage.results = job.results
                    self.list.set(job.results, keep=False)
                else:
                    self.app.toast(job.error or "Nothing found", 5, error=True)
        job = VideoPage.setup
        if self.view == "setup" and job:
            self.app.dirty = True
            if job.done and not self.told:
                self.told = True
                self.app.toast("Video is ready" if job.ok else "The setup stopped", 5, error=not job.ok)
                self.app.fill_dock()            # Games arrives with the same packages

    # ---------------------------------------------------------------- draw
    def draw(self, surf, f, area):
        if self.view == "setup":
            return self.draw_setup(surf, f, area)
        x, y = area.x + 16, area.y + 10
        if not self.ready:
            missing = [n for n, here in (("the player (mpv)", self.status and self.status["mpv"]),
                                         ("yt-dlp", self.status and self.status["ytdlp"])) if not here]
            G.text(surf, f.big, "Video is not set up yet", (x, y), T.EMBER_BRIGHT)
            y += f.line + 8
            text = ("Missing: " + " and ".join(missing) + ". A fetches what is missing over Wi-Fi: the player and "
                    "the emulators for Games (a few minutes), and yt-dlp from its own releases.")
            for ln in G.wrap(f.small, text, area.w - 32):
                G.text(surf, f.small, ln, (x, y), T.TEXT)
                y += f.small_line
            return
        if self.loading is not None:
            self.loading["shown"] = True
            G.text(surf, f.big, "Loading…", (x, y), T.EMBER_BRIGHT)
            y += f.line + 8
            for ln in G.wrap(f.mono, self.loading["video"]["title"], area.w - 32)[:3]:
                G.text(surf, f.mono, ln, (x, y), T.TEXT)
                y += f.line
            for ln in G.wrap(f.small, "Getting the video from YouTube. This can take up to a minute; the screen "
                                      "stays like this until it starts. SELECT+START gives up.", area.w - 32):
                y += f.small_line
                G.text(surf, f.small, ln, (x, y), T.DIM)
            return
        head = (f"Searching for “{VideoPage.words}”…" if self.search is not None
                else f"“{VideoPage.words}”" if self.list.items else "X: search YouTube")
        G.text(surf, f.mono, G.fit(f.mono, head, area.w - 32), (x, y), T.EMBER_BRIGHT if self.list.items else T.MUTED)
        y += f.line + 8
        pygame.draw.line(surf, T.BORDER, (area.x + 12, y - 4), (area.right - 12, y - 4))
        notes = [f"yt-dlp {self.status['ytdlp']}" + ("" if self.status["js"] else "  ·  no JavaScript runtime: YouTube may refuse"),
                 "If videos stop playing, press Y: YouTube changes often and yt-dlp follows."]
        wrapped = [(ln, k) for k, note in enumerate(notes) for ln in G.wrap(f.small, note, area.w - 32)]
        foot = len(wrapped) * f.small_line + 8
        rows = pygame.Rect(area.x + 12, y, area.w - 24, area.bottom - y - foot)
        if self.list.items:
            self.list.draw(surf, f, rows, self.draw_row)
        for i, (ln, k) in enumerate(wrapped):
            G.text(surf, f.small, ln, (x, area.bottom - foot + 4 + i * f.small_line),
                   T.DIM if self.status["js"] or k else T.ERROR)

    def draw_row(self, surf, f, r, v, sel):
        length = v["length"] or "live"
        w = f.small.size(length)[0]
        G.text(surf, f.mono, G.fit(f.mono, v["title"], r.w - 28), (r.x + 12, r.y + 4), T.EMBER_BRIGHT if sel else T.TEXT)
        G.text(surf, f.small, G.fit(f.small, v["channel"], r.w - 44 - w), (r.x + 12, r.y + 6 + f.line), T.MUTED)
        G.text(surf, f.small, length, (r.right - 12, r.y + 6 + f.line), T.MUTED, right=True)

    def draw_setup(self, surf, f, area):
        job = VideoPage.setup
        x, y = area.x + 16, area.y + 10
        done, ok = bool(job and job.done), bool(job and job.ok)
        head = "Video is ready" if ok else "The setup stopped" if done else "Setting up Video"
        G.text(surf, f.big, head, (x, y), T.OK if ok else T.ERROR if done else T.EMBER_BRIGHT)
        y += f.line + 6
        sub = ("B goes back." if ok else "The reason is in the last lines." if done
               else "This takes a few minutes. It keeps running if you close the window.")
        y += max(f.small_line, G.para(surf, f.small, sub, (x, y), area.w - 32, T.TEXT if done else T.DIM)) + 10
        box = pygame.Rect(area.x + 12, y, area.w - 24, area.bottom - y - 6)
        G.box(surf, box, T.PANEL, 6, T.BORDER)
        lines = job.lines if job else []
        fit = max(1, (box.h - 16) // f.small_line)
        shown = [ln.replace("rk-tools: ", "").replace("rk-video: ", "") for ln in lines]
        for i, (piece, k) in enumerate(G.tail(f.small, shown, box.w - 24, fit)):
            colour = T.EMBER if lines[k].startswith(("rk-tools:", "rk-video:")) else T.TEXT
            G.text(surf, f.small, piece, (box.x + 12, box.y + 10 + i * f.small_line), colour)
