"""The Games window and its library, without a handheld or an emulator.

    python3 tests/test_games.py
"""
import os
import sys
import tempfile
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import pygame

from rkshell import app as A
from rkshell import games as L
from rkshell import system as S
from rkshell.pages.games import RECENT, GamesPage
from rkshell.widgets import Menu

pygame.display.init()
pygame.font.init()
pygame.display.set_mode((1, 1))


def card(t, files):
    for rel in files:
        os.makedirs(os.path.dirname(f"{t}/{rel}"), exist_ok=True)
        open(f"{t}/{rel}", "w").write("x")


# ------------------------------------------------------------ the looking
def test_scan_finds_games_by_machine():
    with tempfile.TemporaryDirectory() as t:
        card(t, ["n64/Zelda.z64", "n64/old folder/Mario Kart.N64", "n64/._Zelda.z64", "n64/.hidden/Secret.z64",
                 "n64/notes.txt", "psx/Crash.cue", "psx/Crash.bin", "psx/Loose.bin", "snes/Game.sfc", "snes/Zipped.zip",
                 "dreamcast/Sonic.cdi", "bios/scph1001.bin", "saves/Zelda.srm", "README.txt"])
        games = L.scan(t)
        names = [(g["machine"], g["name"]) for g in games]
        assert names == [("n64", "Mario Kart"), ("n64", "Zelda"), ("psx", "Crash"), ("snes", "Game"), ("snes", "Zipped")], names
        assert games[0]["path"] == f"{t}/n64/old folder/Mario Kart.N64"     # a folder inside the machine's folder
        assert list(L.by_machine(games)) == ["n64", "psx", "snes"]          # empty machines are not there
    with tempfile.TemporaryDirectory() as t:                                # a disc image with no .cue is a game
        card(t, ["psx/Only.bin", "megadrive/Sonic.bin", "megadrive/Other.md"])
        assert [(g["machine"], g["name"]) for g in L.scan(t)] == [("psx", "Only"), ("megadrive", "Other"), ("megadrive", "Sonic")]
    assert L.scan("/nonexistent/roms") == []


def test_a_game_on_several_discs_is_one_game():
    with tempfile.TemporaryDirectory() as t:
        card(t, ["psx/FF7/Final (Disc 1).chd", "psx/FF7/Final (Disc 2).chd", "psx/Solo.chd"])
        open(f"{t}/psx/FF7/Final.m3u", "w").write("# discs\nFinal (Disc 1).chd\nFinal (Disc 2).chd\n")
        assert [g["name"] for g in L.scan(t)] == ["Final", "Solo"]


def test_history_and_words():
    with tempfile.TemporaryDirectory() as t:
        h = L.History(f"{t}/.rk-games.json")
        assert h.last("/a") == 0
        h.mark("/a", 1000)
        h.mark("/b")
        again = L.History(f"{t}/.rk-games.json")                            # it was written down
        assert again.last("/a") == 1000 and again.last("/b") > 1000
        again.forget_missing([{"path": "/b"}])
        assert again.last("/a") == 0 and again.last("/b")
        open(f"{t}/bad.json", "w").write("not json")
        assert L.History(f"{t}/bad.json").played == {}
    now = time.mktime((2026, 11, 27, 14, 0, 0, 0, 0, -1))
    assert L.ago(0) == "" and L.ago(now - 3600, now) == "today" and L.ago(now - 86400, now) == "yesterday"
    assert L.ago(now - 3 * 86400, now) == "3 days ago" and L.ago(now - 20 * 86400, now) == "7 Nov"
    assert L.ago(now - 400 * 86400, now).endswith("2025")
    assert L.count(1) == "1 game" and L.count(0) == "0 games" and L.count(12) == "12 games"
    assert L.core_path("n64").endswith("/parallel_n64_libretro.so")                    # dArkOS's first choice
    assert L.core_path("n64", "mupen64plus_next").endswith("/mupen64plus_next_libretro.so")
    assert L.core_path("n64", "nonsense").endswith("/parallel_n64_libretro.so")        # a damaged setting
    assert L.core_path("psx", "mupen64plus_next").endswith("/pcsx_rearmed_libretro.so")    # no choice there
    assert {m[0] for m in L.MACHINES} == set("psx n64 psp nes snes gb gbc gba megadrive mastersystem gamegear pcengine".split())


def test_the_real_command_is_retroarch_with_the_machines_core():
    with tempfile.TemporaryDirectory() as t:
        os.makedirs(f"{t}/cores")
        open(f"{t}/cores/mupen64plus_next_libretro.so", "w").write("x")
        open(f"{t}/cores/parallel_n64_libretro.so", "w").write("x")
        s = S.System()
        s.SETTINGS = (f"{t}/nowhere/x.json", f"{t}/desktop.json")
        real_options, L.CORE_OPTIONS = L.CORE_OPTIONS, f"{t}/retroarch/rk-core-options.cfg"
        entry = {"name": "Games", "exec": ["/opt/rk-emulators/bin/retroarch", "--appendconfig", "/usr/share/rk/retroarch/rk.cfg"],
                 "ready": True, "before": ["/usr/local/bin/rk-games", "prepare"]}
        s.games_entry = lambda: entry
        real, L.CORES_DIR = L.CORES_DIR, f"{t}/cores"
        try:
            game = {"machine": "n64", "name": "Zelda", "path": "/share/roms/n64/Zelda (USA).z64"}
            assert s.games_command(game) == entry["exec"] + ["-L", f"{t}/cores/parallel_n64_libretro.so", game["path"]]
            s.set_setting("games_core_n64", "mupen64plus_next")             # the owner chose the other N64 emulator
            assert s.games_command(game) == entry["exec"] + ["-L", f"{t}/cores/mupen64plus_next_libretro.so", game["path"]]
            assert s.games_command(None) == entry["exec"]                   # RetroArch's own menu
            assert s.games_command(dict(game, machine="psx")) is None       # that core is not on the card
            entry["ready"] = False
            assert s.games_command(game) is None                            # no emulators at all
            assert 'parallel-n64-screensize = "640x480"' in open(L.CORE_OPTIONS).read()   # written just before the game
        finally:
            L.CORES_DIR, L.CORE_OPTIONS = real, real_options


# ------------------------------------------------------------- the window
def window(size=(720, 720), **attrs):
    system = S.DemoSystem()
    for k, v in attrs.items():
        setattr(system, k, v)
    app = A.App(system, pygame.Surface(size))
    games = next(i for i in app.dock.items if i["name"] == "Games")
    app.open(games)
    page = app.window
    assert isinstance(page, GamesPage) and page.view == "scanning"          # the looking is shown first
    app.draw()
    page.shown_at = 0
    end = time.time() + 3
    while page.view == "scanning" and time.time() < end:
        app.tick()
        time.sleep(0.01)
    return system, app, page


def test_one_games_icon_on_the_dock():
    app = A.App(S.DemoSystem(), pygame.Surface((720, 720)))
    assert [i["name"] for i in app.dock.items].count("Games") == 1
    assert "window" in next(i for i in app.dock.items if i["name"] == "Games")


def test_tiles_counts_and_the_total():
    for size in ((720, 720), (640, 480), (480, 320)):
        system, app, page = window(size)
        assert page.view == "home" and page.tiles[0] == RECENT
        assert page.tiles[1:] == ["gba", "megadrive", "nes", "n64", "psx", "psp", "snes"]       # by name
        assert len(page.games) == 18 and len(page.games_of("psx")) == 5 and len(page.games_of(RECENT)) == 2
        assert "pcengine" not in page.tiles                                 # no game, no tile
        drawn, real = [], A.G.text
        A.G.text = lambda surf, font, s, *a, **k: (drawn.append(s), real(surf, font, s, *a, **k))[1]
        try:
            app.draw()
        finally:
            A.G.text = real
        assert "18 games on 7 machines" in drawn and "GBA" in drawn and "1 game" in drawn
        if size == (720, 720):                                              # every tile fits on this screen
            assert "N64" in drawn and "4 games" in drawn and "SNES" in drawn
        for _ in range(12):                                                 # walking the grid never leaves it
            app.handle("down")
            app.draw()
        assert page.sel // page.cols == (len(page.tiles) - 1) // page.cols      # on the last row
        for _ in range(12):
            app.handle("up")
            app.handle("left")
        assert page.sel == 0


def test_open_a_machine_and_start_a_game():
    system, app, page = window()
    page.sel = page.tiles.index("n64")
    app.handle("a")
    assert page.view == "list" and [g["name"] for g in page.list.items] == ["Bolt Racer", "Goldfinch 007", "Star Kart 64", "Tetra Legends"]
    app.draw()
    app.handle("down")
    app.handle("a")
    game = page.list.current
    assert app.launch == ["retroarch", "-L", "n64_core.so", game["path"]] and app.launch_item["name"] == "Games"
    assert page.history.last(game["path"]) > time.time() - 5                 # noted as played
    app.launch = None
    app.handle("b")                                                         # B goes back to the tiles, not out
    assert app.window is page and page.view == "home"
    assert game in page.games_of(RECENT)
    app.handle("b")
    assert app.window is None


def test_sorting():
    system, app, page = window()
    system.set_setting("games_tiles", "count")
    page.build()
    assert page.tiles[1:3] == ["psx", "n64"]
    system.set_setting("games_tiles", "played")
    page.build()
    assert page.tiles[1:3] == ["n64", "psx"]                                # played an hour ago, three days ago
    page.sel = page.tiles.index("psx")
    app.handle("a")
    assert page.list.items[0]["name"] == "Crash Lander (Disc 1)"
    app.handle("x")
    menu = app.stack[-1]
    assert isinstance(menu, Menu) and menu.items[0][0] == "Close"
    assert ("Games: by name", menu.items[2][1]) == menu.items[2]              # the row says what it is now
    menu.sel = 2
    app.handle("a")
    assert system.setting("games_list") == "played" and page.list.items[0]["name"] == "Final Quest VII"
    assert app.toast_text == "Games: last played"
    system.set_setting("games_tiles", "nonsense")                           # a damaged setting: the first choice
    page.build()
    assert page.tiles[1] == "gba"


def test_options_look_again_and_retroarch_menu():
    system, app, page = window()
    app.handle("x")
    menu = app.stack[-1]
    menu.sel = next(i for i, (t, _) in enumerate(menu.items) if t == "RetroArch's own menu")
    app.handle("a")
    assert app.launch == ["retroarch"]
    app.launch = None
    system.games_scan = lambda: [{"machine": "gb", "name": "New One", "path": "/share/roms/gb/New One.gb"}]
    app.handle("x")
    menu = app.stack[-1]
    menu.sel = next(i for i, (t, _) in enumerate(menu.items) if t == "Look for new games")
    app.handle("a")
    assert page.view == "scanning"
    page.shown_at = 0
    end = time.time() + 3
    while page.view == "scanning" and time.time() < end:
        app.tick()
        time.sleep(0.01)
    assert page.tiles == ["gb"]                                             # what was played is no longer on the card


def test_no_games_says_where_they_go():
    for size in ((720, 720), (480, 320)):
        system, app, page = window(size, _no_games=True)
        assert page.view == "home" and page.tiles == []
        drawn, real = [], A.G.text
        A.G.text = lambda surf, font, s, *a, **k: (drawn.append(s), real(surf, font, s, *a, **k))[1]
        try:
            app.draw()
        finally:
            A.G.text = real
        text = " ".join(drawn)
        assert "No games yet" in text and "RKSHARE" in text and "n64" in text and "/share/roms" in text
        app.handle("a")                                                     # nothing to open: nothing happens
        assert app.launch is None


def test_a_game_that_does_not_start_is_said():
    system, app, page = window()
    page.sel = page.tiles.index("n64")
    app.handle("a")
    app.handle("a")
    assert app.launch and app.last_run is None
    app.launch = None
    app.tick()
    assert not app.toast_text                                               # still in the game: nothing to say
    app.last_run = {"code": 1, "secs": 0.4}                                 # RetroArch gave up at once
    app.tick()
    assert "did not start" in app.toast_text and "Nintendo 64" in app.toast_text and app.toast_error
    app.toast_text = ""
    app.handle("a")
    app.launch = None
    app.last_run = {"code": 0, "secs": 600}                                 # ten minutes of play
    app.tick()
    assert not app.toast_text


def test_the_3d_cores_find_the_graphics_driver():
    """Both N64 cores and PPSSPP ask for libEGL.so and libGLESv2.so by those
    names; the image and the migration for cards already flashed make them."""
    import subprocess
    repo = os.path.join(HERE, "..", "..")
    build = open(os.path.join(repo, "build", "build-image.sh")).read()
    assert 'for n in libEGL.so libGLESv2.so; do ln -sf libmali.so "$GPU/$n"; done' in build
    with tempfile.TemporaryDirectory() as t:
        open(f"{t}/libmali.so", "w").write("x")
        os.symlink("libmali.so", f"{t}/libEGL.so.1")
        step = os.path.join(repo, "overlay", "usr", "lib", "rk", "migrations", "0006-core-libraries.sh")
        for _ in range(2):                                                  # a second run changes nothing
            assert subprocess.run(["bash", step], env=dict(os.environ, RK_GPU_DIR=t)).returncode == 0
            assert os.readlink(f"{t}/libEGL.so") == "libmali.so" and os.readlink(f"{t}/libGLESv2.so") == "libmali.so"
    with tempfile.TemporaryDirectory() as t:                                # no driver there: nothing is made
        subprocess.run(["bash", step], env=dict(os.environ, RK_GPU_DIR=t))
        assert os.listdir(t) == []
    pkgs = open(os.path.join(repo, "build", "packages-media.txt")).read().split()
    tools = open(os.path.join(repo, "overlay", "usr", "local", "sbin", "rk-tools")).read()
    for lib in ("libx11-6", "libxext6", "libsm6", "libice6"):               # what PPSSPP's core also asks for
        assert lib in pkgs and lib in tools


def test_the_n64_picture_is_written_where_retroarch_reads_it():
    repo = os.path.join(HERE, "..", "..")
    cfg = open(os.path.join(repo, "overlay", "usr", "share", "rk", "retroarch", "rk.cfg")).read()
    assert 'global_core_options = "true"' in cfg
    assert 'core_options_path = "/home/ark/.config/retroarch/rk-core-options.cfg"' in cfg
    assert L.CORE_OPTIONS.endswith("/.config/retroarch/rk-core-options.cfg")
    with tempfile.TemporaryDirectory() as t:
        path = f"{t}/retroarch/rk-core-options.cfg"                        # the folder is not there yet
        assert L.write_core_options(path, None)                             # nothing chosen: sharp
        text = open(path).read()
        assert 'parallel-n64-screensize = "640x480"' in text and 'mupen64plus-43screensize = "640x480"' in text
        open(path, "a").write('parallel-n64-gfxplugin = "rice"\npcsx_rearmed_frameskip = "1"\n')     # the owner's own, set in RetroArch
        assert L.write_core_options(path, "fast")
        lines = open(path).read().splitlines()
        assert 'parallel-n64-screensize = "320x240"' in lines and 'mupen64plus-43screensize = "320x240"' in lines
        assert 'parallel-n64-gfxplugin = "rice"' in lines and 'pcsx_rearmed_frameskip = "1"' in lines
        assert len(lines) == 4                                              # changed in place, nothing twice
        assert L.write_core_options(path, "nonsense") and 'parallel-n64-screensize = "640x480"' in open(path).read()
    system, app, page = window()
    app.handle("x")
    menu = app.stack[-1]
    menu.sel = next(i for i, (t, _) in enumerate(menu.items) if t == "N64 picture: sharp")
    app.handle("a")
    assert system.setting("games_n64_picture") == "fast" and app.toast_text == "N64 picture: fast, from the next game"
    app.handle("x")
    assert any(t == "N64 picture: fast" for t, _ in app.stack[-1].items)


def test_the_other_n64_emulator_is_one_press_away():
    system, app, page = window()
    app.handle("x")
    menu = app.stack[-1]
    menu.sel = next(i for i, (t, _) in enumerate(menu.items) if t == "N64 emulator: ParaLLEl")
    app.handle("a")
    assert system.setting("games_core_n64") == "mupen64plus_next" and app.toast_text == "N64 games now start with Mupen64Plus"
    app.handle("x")
    menu = app.stack[-1]
    menu.sel = next(i for i, (t, _) in enumerate(menu.items) if t == "N64 emulator: Mupen64Plus")
    app.handle("a")
    assert system.setting("games_core_n64") == "parallel_n64"                               # and back


def test_full_speed_for_the_length_of_a_game():
    import json
    import subprocess
    repo = os.path.join(HERE, "..", "..")
    perf = os.path.join(repo, "overlay", "usr", "local", "sbin", "rk-perf")
    entry = json.load(open(os.path.join(repo, "overlay", "usr", "share", "rk", "apps", "games.json")))
    assert entry["before"] == ["/usr/local/bin/rk-games", "prepare"] and entry["after"] == ["/usr/local/bin/rk-games", "done"]
    games = open(os.path.join(repo, "overlay", "usr", "local", "bin", "rk-games")).read()
    assert "rk-perf game" in games and "rk-perf normal" in games
    sudoers = open(os.path.join(repo, "overlay", "etc", "sudoers.d", "rkshell")).read()
    assert "/usr/local/sbin/rk-perf game, /usr/local/sbin/rk-perf normal" in sudoers
    with tempfile.TemporaryDirectory() as t:
        knobs = {"devices/system/cpu/cpufreq/policy0/scaling_governor": ("interactive", "scaling_available_governors", "interactive ondemand performance"),
                 "class/devfreq/dmc/governor": ("dmc_ondemand", "available_governors", "dmc_ondemand userspace performance"),
                 "class/devfreq/ff400000.gpu/governor": ("simple_ondemand", "available_governors", "simple_ondemand performance"),
                 "class/devfreq/odd/governor": ("simple_ondemand", "available_governors", "simple_ondemand powersave")}
        for rel, (now, listing, offered) in knobs.items():
            os.makedirs(os.path.dirname(f"{t}/sys/{rel}"), exist_ok=True)
            open(f"{t}/sys/{rel}", "w").write(now + "\n")
            open(os.path.join(os.path.dirname(f"{t}/sys/{rel}"), listing), "w").write(offered + "\n")
        env = dict(os.environ, RK_SYS=f"{t}/sys", RK_PERF_NOTE=f"{t}/note")
        now = lambda rel: open(f"{t}/sys/{rel}").read().strip()
        for _ in range(2):                                                  # asked twice: the first note is kept
            assert subprocess.run(["bash", perf, "game"], env=env).returncode == 0
        assert [now(r) for r in knobs] == ["performance", "performance", "performance", "simple_ondemand"]    # the last does not offer it
        assert subprocess.run(["bash", perf, "normal"], env=env).returncode == 0
        assert [now(r) for r in knobs] == [v[0] for v in knobs.values()]    # each back to what it was
        assert subprocess.run(["bash", perf, "normal"], env=env).returncode == 0   # nothing noted: nothing done
        assert subprocess.run(["bash", perf, "nonsense"], env=env, capture_output=True).returncode == 2


def test_the_options_fit_the_smallest_screen():
    """The longest menu of the desktop: on 480x320 it scrolls instead of running off the screen."""
    for size in ((720, 720), (640, 480), (480, 320)):
        system, app, page = window(size)
        app.handle("x")
        menu = app.stack[-1]
        assert len(menu.items) == 7
        seen = set()
        for _ in range(len(menu.items) + 1):
            texts, real_text = [], A.G.text
            A.G.text = lambda surf, font, s, *a, **k: (texts.append(s), real_text(surf, font, s, *a, **k))[1]
            try:
                app.draw()
            finally:
                A.G.text = real_text
            assert pygame.Rect(0, 0, *size).contains(menu.rect), (size, menu.rect)
            assert menu.items[menu.sel][0] in texts and "Games: options" in texts       # the chosen row is always drawn
            seen |= {t for t, _ in menu.items if t in texts}
            app.handle("down")
        assert seen == {t for t, _ in menu.items}                               # every row can be reached


def test_no_emulators_is_said():
    system, app, page = window()
    system.games_command = lambda game: None
    page.sel = page.tiles.index("n64")
    app.handle("a")
    app.handle("a")
    assert app.launch is None and "emulators are not on this card" in app.toast_text


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
