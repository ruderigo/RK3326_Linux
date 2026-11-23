"""Video and Games, without a handheld: what rk-video tells mpv and yt-dlp,
how the pad drives the player, and what the desktop reads back.

Playing itself needs the panel; this covers everything decided before that.
"""
import importlib.machinery
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(HERE, ".."))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

loader = importlib.machinery.SourceFileLoader("rk_video", os.path.join(REPO, "overlay/usr/local/bin/rk-video"))
rv = importlib.util.module_from_spec(importlib.util.spec_from_loader("rk_video", loader))
sys.dont_write_bytecode = True
loader.exec_module(rv)

from rkshell import system

# the checksum list of a release: only the exact name counts
sums = "a" * 64 + "  yt-dlp.exe\n" + "b" * 64 + "  yt-dlp\n" + "c" * 64 + " *yt-dlp_linux\nshort  yt-dlp\n"
assert rv.sha_in(sums, "yt-dlp") == "b" * 64
assert rv.sha_in(sums, "yt-dlp_linux") == "c" * 64
assert rv.sha_in(sums, "nothing") is None

# H.264 is asked for first, and never taller than the limit
fmt = rv.ytdl_format(480)
assert fmt.startswith("bv*[height<=480][vcodec^=avc1]") and fmt.endswith("/b")

# mpv: our settings, the control socket, and the target after "--" so it is never an option
rv.ytdlp = lambda: [sys.executable, rv.YTDLP_OWN]
rv.js_runtime = lambda: "quickjs"
cmd = rv.mpv_command("--not-an-option", "/tmp/s", {}, height=360)
assert cmd[-2:] == ["--", "--not-an-option"]
assert "--vo=sdl" in cmd and "--input-ipc-server=/tmp/s" in cmd
assert f"--script-opts=ytdl_hook-ytdl_path={rv.YTDLP_OWN}" in cmd
assert "--ytdl-raw-options=js-runtimes=quickjs" in cmd
assert any(a.startswith("--ytdl-format=bv*[height<=360]") for a in cmd)
cmd = rv.mpv_command("x", "/tmp/s", {"VO": "drm", "HEIGHT": "240"})
assert "--vo=drm" in cmd and any("height<=240" in a for a in cmd)
rv.js_runtime = lambda: "deno"                  # yt-dlp's own default: nothing to say
assert not any("js-runtimes" in a for a in rv.mpv_command("x", "/tmp/s", {}, height=360))

# the pad: SELECT+START stops, either one alone does nothing
assert rv.pad_command("start", {"start"}) is None
assert rv.pad_command("select", {"select", "start"}) == ["quit"]
assert rv.pad_command("start", {"select", "start"}) == ["quit"]
assert rv.pad_command("a", {"a"}) == ["cycle", "pause"]
assert rv.pad_command("b", {"b"}) == ["quit"]
assert rv.pad_command("left", {"left"}) == ["seek", -10]
assert rv.pad_command("y", {"y"}) is None

# play refuses what is neither a web address nor a file (before it would reach mpv)
import shutil
shutil_which, shutil.which = shutil.which, lambda name, **k: "/usr/bin/" + name
assert rv.play("--script=/tmp/evil.lua") == 2
shutil.which = shutil_which

# settings file
import tempfile
with tempfile.NamedTemporaryFile("w", suffix=".conf") as f:
    f.write("# mine\nvo = drm\nHEIGHT=360\nnonsense\n")
    f.flush()
    assert rv.settings(f.name) == {"VO": "drm", "HEIGHT": "360"}

# what the desktop reads back
assert system.parse_video_status("mpv yes\nytdlp 2026.11.18\njs quickjs") == {"mpv": True, "ytdlp": "2026.11.18", "js": "quickjs"}
assert system.parse_video_status("mpv no\nytdlp absent\njs none") == {"mpv": False, "ytdlp": None, "js": None}
assert system.parse_video_status("") == {"mpv": False, "ytdlp": None, "js": None}
out = "dQw4w9WgXcQ\t3:33\tSome Channel\tA title\twith a tab\nabcdefghijk\t\t\tLive now\nWARNING: something\nrk-video: note\n-bad id!\t1\tc\tt"
got = system.parse_video_results(out)
assert got == [{"id": "abcdefghijk", "length": "", "channel": "", "title": "Live now"}], got
assert system.System().video_command("abcdefghijk") == ["/usr/local/bin/rk-video", "play", "https://www.youtube.com/watch?v=abcdefghijk"]

# Debian keeps RetroArch in /usr/games: the dock looks there too, once
assert system.with_games("/usr/bin:/bin") == "/usr/bin:/bin:/usr/games:/usr/local/games"
assert system.with_games("/usr/games:/bin").count("/usr/games") == 1

# Games: the dock entry starts RetroArch with our settings, and those keep the dock's rule (SELECT+START leaves)
entry = json.load(open(os.path.join(REPO, "overlay/usr/share/rk/apps/games.json")))
assert entry["exec"][0] == "retroarch" and entry["exec"][1] == "--appendconfig"
cfg = dict((k.strip(), v.strip().strip('"')) for k, _, v in
           (ln.partition("=") for ln in open(os.path.join(REPO, "overlay" + entry["exec"][2])) if "=" in ln and not ln.startswith("#")))
assert cfg["video_driver"] == "sdl2" and cfg["input_joypad_driver"] == "sdl2"
assert cfg["input_quit_gamepad_combo"] == "4"          # INPUT_COMBO_START_SELECT
assert cfg["input_menu_toggle_gamepad_combo"] != cfg["input_quit_gamepad_combo"]

# the two package lists name the same set
want = [ln.strip() for ln in open(os.path.join(REPO, "build/packages-media.txt")) if ln.strip() and not ln.startswith("#")]
tools = open(os.path.join(REPO, "overlay/usr/local/sbin/rk-tools")).read()
have = tools.split('MEDIA_PKGS="', 1)[1].split('"', 1)[0].split()
assert sorted(want) == sorted(have), (want, have)

# the window: not set up -> A starts the setup; set up -> a search fills the list and A launches the player
import pygame
from rkshell.app import App
from rkshell.pages.video import VideoPage
pygame.display.init(); pygame.font.init(); pygame.display.set_mode((1, 1))
demo = system.DemoSystem()
app = App(demo, pygame.Surface((720, 720)))
demo._video = {"mpv": False, "ytdlp": None, "js": None}
app.window = VideoPage(app); app.window.enter()
assert not app.window.ready
app.handle("a")
assert app.window.view == "setup" and VideoPage.setup is not None
app.draw()
VideoPage.setup = None
del demo._video
app.window = VideoPage(app); app.window.enter()
assert app.window.ready
app.window.search = demo.video_search("x")
app.tick()
assert len(app.window.list.items) == 4
app.handle("down"); app.handle("a")
assert app.launch == ["/usr/local/bin/rk-video", "play", "https://www.youtube.com/watch?v=demo0000002"]
assert app.launch_item.get("mouse") is False
app.draw()
print("video: ok")
