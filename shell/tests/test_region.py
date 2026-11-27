"""The screen's sleep and the time zone, without a handheld.

    python3 tests/test_region.py
"""
import os
import subprocess
import sys
import tempfile
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import pygame

from rkshell import app as A
from rkshell import system as S
from rkshell.backends.device import ScreenSleep
from rkshell.pages.system import SystemPage, ZonePicker, screen_off_text

pygame.display.init()
pygame.font.init()
pygame.display.set_mode((1, 1))

OVERLAY = os.path.join(HERE, "..", "..", "overlay")
REGION = os.path.join(OVERLAY, "usr", "local", "sbin", "rk-region")


# ---------------------------------------------------------------- time zone
def fake_root(t):
    zones = os.path.join(t, "zoneinfo")
    for name in ("America/Toronto", "Europe/Madrid", "America/Argentina/Ushuaia", "UTC"):
        os.makedirs(os.path.dirname(os.path.join(zones, name)), exist_ok=True)
        open(os.path.join(zones, name), "w").write("TZif")
    open(os.path.join(zones, "zone1970.tab"), "w").write(
        "# a comment\nCA\t+4339-07923\tAmerica/Toronto\tEastern\nES\t+4024-00341\tEurope/Madrid\n"
        "AR\t-5448-06818\tAmerica/Argentina/Ushuaia\nXX\t+0000+00000\tMars/Olympus\n")
    os.makedirs(os.path.join(t, "etc"))
    open(os.path.join(t, "outside"), "w").write("not a zone")
    return {"RK_ROOT": t, "RK_ZONEINFO": zones}


def region(env, *args):
    return subprocess.run(["bash", REGION, *args], env=dict(os.environ, **env), capture_output=True, text=True)


def test_rk_region_sets_only_real_zones():
    with tempfile.TemporaryDirectory() as t:
        env = fake_root(t)
        assert region(env, "tz").stdout.strip() == "UTC"                 # nothing set yet
        assert region(env, "tz", "Europe/Madrid").returncode == 0
        assert region(env, "tz").stdout.strip() == "Europe/Madrid"
        assert os.readlink(f"{t}/etc/localtime").endswith("zoneinfo/Europe/Madrid")
        assert region(env, "tz", "America/Argentina/Ushuaia").returncode == 0
        for bad in ("Mars/Olympus", "../outside", "Europe/../../outside", "/etc/passwd", "Europe/", "Europe/Mad rid",
                    "Europe/Madrid;reboot", "$(reboot)", "zone1970.tab/..", "America"):
            p = region(env, "tz", bad)
            assert p.returncode != 0, bad
            assert region(env, "tz").stdout.strip() == "America/Argentina/Ushuaia", bad      # unchanged
        assert region(env, "tz", "Europe/Madrid", "extra").returncode != 0
        assert region(env, "nonsense").returncode == 2


def test_zone_names_come_from_the_table_and_exist():
    with tempfile.TemporaryDirectory() as t:
        zones = fake_root(t)["RK_ZONEINFO"]
        assert S.zone_names(zones) == ["America/Argentina/Ushuaia", "America/Toronto", "Europe/Madrid", "UTC"]
        os.remove(os.path.join(zones, "zone1970.tab"))                   # no table: the files themselves
        assert S.zone_names(zones) == ["America/Toronto", "Europe/Madrid", "UTC"]
    real = S.zone_names("/usr/share/zoneinfo")
    if os.path.isfile("/usr/share/zoneinfo/zone1970.tab"):
        assert "America/Toronto" in real and "Europe/Paris" in real and real[-1] == "UTC" and len(real) > 250


def test_sudoers_lets_the_desktop_set_the_zone():
    text = open(os.path.join(OVERLAY, "etc", "sudoers.d", "rkshell")).read()
    assert "/usr/local/sbin/rk-region tz *" in text


def settings(size=(720, 720)):
    system = S.DemoSystem()
    app = A.App(system, pygame.Surface(size))
    app.window = SystemPage(app)
    return system, app, app.window


def select(page, name):
    page.list.sel = next(i for i, it in enumerate(page.list.items) if it["name"] == name)


def test_choosing_a_zone_in_settings():
    for size in ((720, 720), (640, 480), (480, 320)):
        system, app, page = settings(size)
        select(page, "Time zone")
        app.handle("a")
        picker = app.stack[-1]
        assert isinstance(picker, ZonePicker)
        assert picker.list.current == "America"                         # it opens on where the handheld is
        app.draw()
        app.handle("a")
        assert picker.region == "America" and picker.list.current == "America/Toronto"
        app.draw()
        app.handle("b")                                                 # back to the parts of the world
        assert picker.region is None and picker.list.current == "America"
        picker.list.sel = picker.regions.index("Europe")
        app.handle("a")
        picker.list.sel = picker.list.items.index("Europe/Madrid")
        app.handle("a")
        assert not app.stack and system.timezone() == "Europe/Madrid"
        assert "Europe/Madrid" in app.toast_text and not app.toast_error
        app.draw()
        # UTC has no cities: one press
        select(page, "Time zone")
        app.handle("a")
        picker = app.stack[-1]
        picker.list.sel = picker.regions.index("UTC")
        app.handle("a")
        assert not app.stack and system.timezone() == "UTC"


def test_a_zone_the_system_refuses_is_said():
    system, app, page = settings()
    page.set_zone("Mars/Olympus")
    assert app.toast_error and system.timezone() == "America/Toronto"


def test_a_reflash_gets_the_owners_zone_back():
    system = S.DemoSystem()
    asked = []
    system.timezone = lambda: "America/Toronto"                         # what the fresh image has
    system.set_timezone = lambda zone: asked.append(zone) or (True, "")
    system.restore_timezone()
    assert asked == []                                                  # nothing chosen: nothing to do
    system.set_setting("timezone", "Europe/Paris")
    system.restore_timezone()
    assert asked == ["Europe/Paris"]
    system.timezone = lambda: "Europe/Paris"
    system.restore_timezone()
    assert asked == ["Europe/Paris"]                                    # already there: not asked again


# -------------------------------------------------------------- screen sleep
def test_screen_off_setting_steps_through_its_choices():
    system, app, page = settings()
    assert system.screen_off() == 5 and screen_off_text(5) == "5 min" and screen_off_text(0) == "Never"
    select(page, "Screen off after")
    seen = []
    for _ in range(6):
        app.handle("right")
        seen.append(system.screen_off())
    assert seen == [10, 30, 0, 1, 2, 5]
    app.handle("left")
    assert system.screen_off() == 2
    system.set_setting("screen_off", "nonsense")                        # a damaged file: the default
    assert system.screen_off() == 5
    app.draw()


class Idle:
    live = False


def test_screen_sleeps_when_idle_and_wakes_as_it_was():
    system = S.DemoSystem()
    system.set_brightness(65)
    sleeper = ScreenSleep(system)
    app = Idle()
    assert not sleeper.due(app)
    sleeper.last = time.time() - 5 * 60 - 1
    assert sleeper.due(app)
    app.live = True                                                     # a scan or an install is running
    assert not sleeper.due(app)
    app.live = False
    assert sleeper.sleep() and sleeper.asleep and system.brightness() == 0
    assert not sleeper.due(app)                                         # already asleep
    sleeper.wake()
    assert not sleeper.asleep and system.brightness() == 65
    assert not sleeper.due(app)                                         # the wait starts again
    system.set_screen_off(0)                                            # never
    sleeper.last = 0
    assert not sleeper.due(app)
    system.set_screen_off(1)
    sleeper.last = time.time() - 59
    assert not sleeper.due(app)
    sleeper.last = time.time() - 61
    assert sleeper.due(app)


def test_no_backlight_means_no_sleep():
    system = S.DemoSystem()
    system.backlight_off = lambda: None                                 # a board whose light cannot be switched
    sleeper = ScreenSleep(system)
    assert not sleeper.sleep() and not sleeper.asleep
    system.brightness = lambda: None
    _, _, page = (system, None, SystemPage(A.App(system, pygame.Surface((720, 720)))))
    assert "Screen off after" not in [it["name"] for it in page.list.items]


def test_a_desktop_stopped_asleep_starts_lit():
    system = S.DemoSystem()
    system.set_brightness(40)
    ScreenSleep(system).sleep()
    assert system.brightness() == 0
    system.set_setting("brightness_awake", 40)                          # what the real system notes as it goes dark
    ScreenSleep(system)                                                 # the desktop starts again
    assert system.brightness() == 40


def test_real_backlight_goes_to_zero_and_back():
    with tempfile.TemporaryDirectory() as t:
        open(f"{t}/brightness", "w").write("200")
        open(f"{t}/max_brightness", "w").write("255")
        system = S.System()
        system._backlight = lambda: t
        system.SETTINGS = (f"{t}/nowhere/x.json", f"{t}/desktop.json")
        was = system.backlight_off()
        assert was == 78 and open(f"{t}/brightness").read() == "0"
        assert system.setting("brightness_awake") == 78
        system.backlight_restore()                                      # dark, and no value given: the noted one
        assert system.brightness() == 78
        system.backlight_restore()                                      # lit: left alone
        assert system.brightness() == 78
        system.set_screen_off(10)
        assert S.System.setting(system, "screen_off") == 10 and system.screen_off() == 10
        fresh = S.System()
        fresh.SETTINGS = system.SETTINGS
        assert fresh.screen_off() == 10                                 # it was written down


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
