"""The games library: what is in the games folder, by machine.

No game comes with the system. The owner copies files into one folder per
machine (roms/n64, roms/psx, ...), and the Games window shows what it finds
there each time it opens: nothing to configure, nothing to refresh by hand.

This file is the looking, with no screen and no RetroArch in it, so it can
be tested on any folder.
"""
import json
import os
import time

# folder, short label for the tile, full name, RetroArch core, file endings
MACHINES = [
    ("n64", "N64", "Nintendo 64", "mupen64plus_next", (".z64", ".n64", ".v64", ".zip")),
    ("psx", "PS1", "PlayStation", "pcsx_rearmed", (".cue", ".chd", ".pbp", ".m3u", ".iso", ".img", ".bin")),
    ("psp", "PSP", "PlayStation Portable", "ppsspp", (".iso", ".cso", ".pbp")),
    ("snes", "SNES", "Super Nintendo", "snes9x", (".sfc", ".smc", ".zip")),
    ("nes", "NES", "Nintendo", "nestopia", (".nes", ".fds", ".zip")),
    ("gba", "GBA", "Game Boy Advance", "mgba", (".gba", ".zip")),
    ("gbc", "GBC", "Game Boy Color", "gambatte", (".gbc", ".gb", ".zip")),
    ("gb", "GB", "Game Boy", "gambatte", (".gb", ".zip")),
    ("megadrive", "MD", "Mega Drive / Genesis", "genesis_plus_gx", (".md", ".gen", ".smd", ".bin", ".zip")),
    ("mastersystem", "SMS", "Master System", "genesis_plus_gx", (".sms", ".zip")),
    ("gamegear", "GG", "Game Gear", "genesis_plus_gx", (".gg", ".zip")),
    ("pcengine", "PCE", "PC Engine", "mednafen_pce_fast", (".pce", ".cue", ".chd", ".zip")),
]
BY_FOLDER = {m[0]: m for m in MACHINES}
CORES_DIR = "/opt/rk-emulators/cores"
# a disc is its .cue or .m3u: the tracks and the single discs beside them are not games of their own
DISC_PARTS = (".bin", ".img", ".iso")


def core_path(folder):
    return os.path.join(CORES_DIR, BY_FOLDER[folder][3] + "_libretro.so")


def listed_in_m3u(path):
    """The file names a .m3u playlist names (a game on several discs)."""
    try:
        with open(path, errors="replace") as f:
            return {os.path.basename(ln.strip()) for ln in f if ln.strip() and not ln.startswith("#")}
    except OSError:
        return set()


def scan(root):
    """Every game under root: [{"machine", "name", "path"}], by machine in
    MACHINES' order, then by name. Folders inside a machine's folder are
    looked into. Left out: hidden files (a Mac leaves "._name" copies on the
    card), a disc's tracks when its .cue is there, and the discs a .m3u lists."""
    found = []
    for folder, _, _, _, endings in MACHINES:
        base = os.path.join(root, folder)
        games = []
        for here, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            files = [f for f in files if not f.startswith(".")]
            lower = {f.lower() for f in files}
            has_cue = any(f.endswith(".cue") for f in lower)
            in_lists = set()
            for f in files:
                if f.lower().endswith(".m3u"):
                    in_lists |= listed_in_m3u(os.path.join(here, f))
            for f in files:
                stem, end = os.path.splitext(f)
                end = end.lower()
                if end not in endings or f in in_lists:
                    continue
                if end in DISC_PARTS and has_cue and ".cue" in endings:
                    continue
                games.append({"machine": folder, "name": stem, "path": os.path.join(here, f)})
        found += sorted(games, key=lambda g: g["name"].lower())
    return found


def by_machine(games):
    """{folder: [games]} for the machines that have any, in MACHINES' order."""
    out = {}
    for g in games:
        out.setdefault(g["machine"], []).append(g)
    return out


class History:
    """When each game was last played: {path: time}, in a small file on the
    data partition (so a reflash keeps it)."""

    def __init__(self, path):
        self.path = path
        try:
            with open(path) as f:
                d = json.load(f)
            self.played = {k: v for k, v in d.items() if isinstance(v, (int, float))} if isinstance(d, dict) else {}
        except (OSError, ValueError):
            self.played = {}

    def last(self, game_path):
        return self.played.get(game_path, 0)

    def mark(self, game_path, when=None):
        self.played[game_path] = when or time.time()
        try:
            with open(self.path + ".new", "w") as f:
                json.dump(self.played, f)
            os.replace(self.path + ".new", self.path)
        except OSError:
            pass

    def forget_missing(self, games):
        """Drop the games that are no longer on the card."""
        here = {g["path"] for g in games}
        self.played = {k: v for k, v in self.played.items() if k in here}


def ago(when, now=None):
    """"today", "yesterday", "3 days ago", "26 Nov": when a game was last played."""
    if not when:
        return ""
    now = now or time.time()
    days = (time.localtime(now).tm_yday - time.localtime(when).tm_yday) if time.localtime(now).tm_year == time.localtime(when).tm_year \
        else int((now - when) // 86400)
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    return time.strftime("%-d %b", time.localtime(when)) + ("" if time.localtime(now).tm_year == time.localtime(when).tm_year
                                                           else time.strftime(" %Y", time.localtime(when)))


def count(n):
    return "1 game" if n == 1 else f"{n} games"
