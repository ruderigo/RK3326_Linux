"""Games: the owner's own games, found by the system and started with A.

Opening the window looks through the games folder (roms/<machine>/ on the
part of the card a computer reads) and shows one tile per machine that has
games, with how many. A on a tile lists its games; A on a game starts it,
with the emulator for that machine already chosen. Nothing is set up by
hand, and a game copied onto the card is there the next time Games opens.

X is the options: how the tiles and the lists are sorted, looking again, and
RetroArch's own menu for whoever wants its settings. In a game, SELECT+START
comes back here, and SELECT+X opens RetroArch's menu.
"""
import threading
import time

import pygame

from .. import games as L
from .. import gfx as G
from .. import theme as T
from ..widgets import ListView, Menu
from .base import Page

TILE_SORTS = [("name", "by name"), ("count", "most games first"), ("played", "last played first")]
GAME_SORTS = [("name", "by name"), ("played", "last played first")]
RECENT = "recent"               # the tile that is not a machine: what was played lately


class GamesPage(Page):
    title, icon = "Games", "games"

    def __init__(self, app):
        super().__init__(app)
        self.view, self.machine = "scanning", None
        self.games, self.shelves, self.tiles = [], {}, []
        self.sel, self.top, self.cols = 0, 0, 3
        self.list = ListView()
        self.found = None           # the scan's answer, handed over by its thread
        self.shown_at = 0.0
        self.history = app.system.games_history()
        self.started = None         # the game just handed to RetroArch

    # ----------------------------------------------------------- the library
    def enter(self):
        self.rescan()

    def rescan(self):
        """Look again. The "looking" screen is drawn first and stays long
        enough to be read: on a card with few games the looking is instant."""
        self.view, self.found, self.shown_at = "scanning", None, time.time()
        threading.Thread(target=lambda: setattr(self, "found", self.app.system.games_scan()), daemon=True).start()

    @property
    def live(self):
        return self.view == "scanning"

    def poll(self):
        if self.started and self.app.last_run is not None:
            # back from RetroArch. It ended at once, or badly: the game never
            # ran, and RetroArch's own words for it went by too fast to read
            game, run, self.started = self.started, self.app.last_run, None
            if run["code"] not in (0, None) or run["secs"] < 3:
                name = L.BY_FOLDER[game["machine"]][2]
                self.app.toast(f"{game['name']} did not start. The {name} emulator could not run it: "
                               "the file may be damaged, or of a kind it does not read.", 10, error=True)
        if self.view == "scanning" and self.found is not None and time.time() - self.shown_at >= 0.6:
            self.games, self.found = self.found, None
            self.shelves = L.by_machine(self.games)
            self.history.forget_missing(self.games)
            self.build()
            self.view = "home" if self.machine is None else "list"
            if self.machine is not None:
                self.open_tile(self.machine)
            self.app.dirty = True

    def setting(self, key, choices):
        value = self.app.system.setting(key, choices[0][0])
        return value if value in [c[0] for c in choices] else choices[0][0]

    def recent(self):
        played = [g for g in self.games if self.history.last(g["path"])]
        return sorted(played, key=lambda g: -self.history.last(g["path"]))[:12]

    def games_of(self, tile):
        return self.recent() if tile == RECENT else self.shelves.get(tile, [])

    def build(self):
        """The tiles, in the chosen order; "Recently played" first when there is anything in it."""
        order = self.setting("games_tiles", TILE_SORTS)
        tiles = list(self.shelves)
        if order == "name":
            tiles.sort(key=lambda m: L.BY_FOLDER[m][2].lower())
        elif order == "count":
            tiles.sort(key=lambda m: -len(self.shelves[m]))
        else:
            tiles.sort(key=lambda m: -max(self.history.last(g["path"]) for g in self.shelves[m]))
        keep = self.tiles[self.sel] if self.tiles and self.sel < len(self.tiles) else None
        self.tiles = ([RECENT] if self.recent() else []) + tiles
        self.sel = self.tiles.index(keep) if keep in self.tiles else 0

    def open_tile(self, tile):
        games = list(self.games_of(tile))
        if not games:
            self.view, self.machine = "home", None
            return
        if tile != RECENT and self.setting("games_list", GAME_SORTS) == "played":
            games.sort(key=lambda g: (-self.history.last(g["path"]), g["name"].lower()))
        keep = self.list.current["path"] if self.machine == tile and self.list.current else None
        self.machine, self.view = tile, "list"
        self.list.set(games, keep=False)
        if keep:
            self.list.sel = next((i for i, g in enumerate(games) if g["path"] == keep), 0)

    # ----------------------------------------------------------------- input
    @property
    def hints(self):
        if self.view == "scanning":
            return [("B", "close")]
        if self.view == "list":
            return [("A", "play"), ("X", "options"), ("B", "back")]
        return ([("A", "open")] if self.tiles else []) + [("X", "options"), ("B", "close")]

    def wants_back(self):
        return self.view == "list"

    def handle(self, action):
        if self.view == "scanning":
            return
        if action == "x":
            return self.options()
        if self.view == "list":
            if self.list.move(action):
                return
            if action == "b":
                self.view, self.machine = "home", None
                self.build()
            elif action == "a" and self.list.current:
                self.play(self.list.current)
            return
        n = len(self.tiles)
        if not n:
            return
        step = {"left": -1, "right": 1, "up": -self.cols, "down": self.cols}.get(action)
        if step is not None:
            to = self.sel + step
            if 0 <= to < n:
                self.sel = to
            elif action == "down" and self.sel // self.cols < (n - 1) // self.cols:
                self.sel = n - 1                # the last row is shorter: land on its end
        elif action == "a":
            self.open_tile(self.tiles[self.sel])

    def options(self):
        tiles, games = self.setting("games_tiles", TILE_SORTS), self.setting("games_list", GAME_SORTS)
        nxt_t = TILE_SORTS[([c[0] for c in TILE_SORTS].index(tiles) + 1) % len(TILE_SORTS)]
        nxt_g = GAME_SORTS[([c[0] for c in GAME_SORTS].index(games) + 1) % len(GAME_SORTS)]

        def set_tiles():
            self.app.system.set_setting("games_tiles", nxt_t[0])
            self.build()

        def set_games():
            self.app.system.set_setting("games_list", nxt_g[0])
            if self.view == "list":
                self.open_tile(self.machine)

        rows = [("Close", None),
                (f"Sort machines {nxt_t[1]}", set_tiles),
                (f"Sort games {nxt_g[1]}", set_games)]
        detail = f"Machines are sorted {dict(TILE_SORTS)[tiles]}, games {dict(GAME_SORTS)[games]}."
        for folder, cores in L.CHOICES.items():         # a machine with two emulators: change to the other
            if folder not in self.shelves:
                continue
            ids = [c for c, _ in cores]
            now = self.app.system.setting("games_core_" + folder)
            now = now if now in ids else ids[0]
            other = cores[(ids.index(now) + 1) % len(cores)]
            short = L.BY_FOLDER[folder][1]
            rows.append((f"{short} emulator: use {other[1]}",
                         lambda folder=folder, other=other, short=short: (
                             self.app.system.set_setting("games_core_" + folder, other[0]),
                             self.app.toast(f"{short} games now start with {other[1]}", 4))))
            detail += f" {short} games start with {dict(cores)[now]}: when a game is slow or looks wrong, try the other."
        rows += [("Look for new games", self.rescan), ("RetroArch's own menu", self.retroarch_menu)]
        self.app.push(Menu(self.app, "Games: options", rows, detail))

    def play(self, game):
        cmd = self.app.system.games_command(game)
        if not cmd:
            self.app.toast("The emulators are not on this card. Open Video and press Y, on Wi-Fi: it installs them.", 8, error=True)
            return
        self.history.mark(game["path"])
        self.started, self.app.last_run = game, None
        self.app.launch, self.app.launch_item = cmd, self.app.system.games_entry()

    def retroarch_menu(self):
        cmd = self.app.system.games_command(None)
        if not cmd:
            self.app.toast("The emulators are not on this card. Open Video and press Y, on Wi-Fi: it installs them.", 8, error=True)
            return
        self.app.launch, self.app.launch_item = cmd, self.app.system.games_entry()

    # ------------------------------------------------------------------ draw
    def draw(self, surf, f, area):
        x, y = area.x + 16, area.y + 12
        if self.view == "scanning":
            G.text(surf, f.big, "Looking for games…", (area.centerx, area.centery - f.line), T.EMBER_BRIGHT, center=True)
            G.text(surf, f.small, self.app.system.games_folder(), (area.centerx, area.centery + 6), T.MUTED, center=True)
            return
        if not self.games:
            return self.draw_empty(surf, f, area)
        if self.view == "list":
            return self.draw_list(surf, f, area)
        total, machines = len(self.games), len(self.shelves)
        G.text(surf, f.mono, f"{L.count(total)} on {machines} machine{'s' if machines != 1 else ''}", (x, y), T.OK)
        G.text(surf, f.small, "sorted " + dict(TILE_SORTS)[self.setting("games_tiles", TILE_SORTS)],
               (area.right - 16, y + 3), T.DIM, right=True)
        y += f.line + 8
        self.draw_tiles(surf, f, pygame.Rect(area.x + 12, y, area.w - 24, area.bottom - y - 4))

    def draw_tiles(self, surf, f, box):
        gap = max(8, box.w // 60)
        self.cols = 3 if box.w >= 520 else 2
        tw = (box.w - gap * (self.cols - 1)) // self.cols
        th = max(f.line * 2 + f.small_line * 2 + 30, min(tw * 2 // 3, box.h // 2 - gap))
        rows_fit = max(1, (box.h + gap) // (th + gap))
        row = self.sel // self.cols
        self.top = max(0, min(self.top, row), row - rows_fit + 1)
        clip = surf.get_clip()
        surf.set_clip(box)
        for i, tile in enumerate(self.tiles):
            r, c = divmod(i, self.cols)
            if r < self.top or r >= self.top + rows_fit + 1:
                continue
            rect = pygame.Rect(box.x + c * (tw + gap), box.y + (r - self.top) * (th + gap), tw, th)
            on = i == self.sel
            G.box(surf, rect, T.ROW if on else T.PANEL, 12, T.EMBER if on else T.BORDER)
            games = self.games_of(tile)
            label, name = ("★", "Recently played") if tile == RECENT else L.BY_FOLDER[tile][1:3]
            G.text(surf, f.big, label, (rect.x + 14, rect.y + 10), T.EMBER_BRIGHT if on else T.EMBER)
            G.para(surf, f.small, name, (rect.x + 14, rect.y + 12 + f.line), rect.w - 24, T.TEXT if on else T.MUTED, max_lines=2)
            G.text(surf, f.mono, L.count(len(games)), (rect.x + 14, rect.bottom - f.line - 8), T.OK)
            if r < self.top + rows_fit:
                G.spot(rect.clip(box), lambda i=i: self.pick_tile(i))
        surf.set_clip(clip)

    def pick_tile(self, i):
        if self.sel == i:
            self.open_tile(self.tiles[i])
        self.sel = i

    def draw_list(self, surf, f, area):
        x, y = area.x + 16, area.y + 12
        name = "Recently played" if self.machine == RECENT else L.BY_FOLDER[self.machine][2]
        G.text(surf, f.mono, G.fit(f.mono, name, area.w // 2), (x, y), T.EMBER_BRIGHT)
        G.text(surf, f.small, L.count(len(self.list.items)) + ("" if self.machine == RECENT else
               "  ·  " + dict(GAME_SORTS)[self.setting("games_list", GAME_SORTS)]), (area.right - 16, y + 3), T.DIM, right=True)
        y += f.line + 8
        self.list.draw(surf, f, pygame.Rect(area.x + 12, y, area.w - 24, area.bottom - y - 4), self.draw_game)

    def draw_game(self, surf, f, r, game, selected):
        when = L.ago(self.history.last(game["path"]))
        tag = (L.BY_FOLDER[game["machine"]][1] + ("  " + when if when else "")) if self.machine == RECENT else when
        room = r.w - 24 - (f.small.size(tag)[0] + 16 if tag else 0)
        G.text(surf, f.mono, G.fit(f.mono, game["name"], room), (r.x + 10, r.y + 5), T.EMBER_BRIGHT if selected else T.TEXT)
        if tag:
            G.text(surf, f.small, tag, (r.right - 12, r.y + 8), T.MUTED, right=True)

    def draw_empty(self, surf, f, area):
        y = area.y + 16
        G.text(surf, f.big, "No games yet", (area.x + 16, y), T.EMBER_BRIGHT)
        y += f.line + 10
        folders = "  ".join(m[0] for m in L.MACHINES)
        for para, colour in (
                ("No game comes with the system: you bring your own. Put the card in a computer, open RKSHARE, "
                 "and copy each game into the folder for its machine inside roms.", T.TEXT),
                (folders, T.OK),
                ("Then open Games again: they are found by themselves. Files can also arrive over SSH, or from "
                 "a USB stick in Files.", T.MUTED),
                ("Looked in " + self.app.system.games_folder(), T.DIM)):
            y += G.para(surf, f.small, para, (area.x + 16, y), area.w - 32, colour, max_lines=6) + 8
