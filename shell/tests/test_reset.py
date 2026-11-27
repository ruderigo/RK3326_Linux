"""Reset this handheld, light and full, on a stand-in card: what goes, and
above all what stays.

    python3 tests/test_reset.py
"""
import os
import subprocess
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import pygame

from rkshell import app as A
from rkshell import system as S
from rkshell.pages.system import SystemPage
from rkshell.widgets import Keyboard, Menu

pygame.display.init()
pygame.font.init()
pygame.display.set_mode((1, 1))

RESET = os.path.join(HERE, "..", "..", "overlay", "usr", "local", "sbin", "rk-reset")

SETTINGS = ["etc/NetworkManager/system-connections/Home.nmconnection", "etc/NetworkManager/system-connections/rk-wifi.nmconnection",
            "etc/default/crda", "etc/ssh/ssh_host_ed25519_key", "etc/ssh/ssh_host_ed25519_key.pub",
            "home/ark/.ssh/authorized_keys", "home/ark/.ssh/known_hosts", "data/ark/.rk-desktop.json",
            "data/ark/rk-update.json", "home/ark/.config/rk-apps", "home/ark/.config/rk-video"]
APP_DATA = ["data/ark/.firefly/identity", "data/ark/.firefly/messages.db", "data/ark/.reticulum/config",
            "data/ark/Stump/stump_pc.py", "data/ark/Stump/stop-stump.sh", "home/ark/stump_r36max/stump_r36max_engine",
            "data/ark/roms-stump_r36max/drop/a-file", "data/ark/apps/recon.json", "data/ark/apps/.packages/recon.json",
            "data/ark/scans/home-20261120.txt", "data/ark/inbox/provisioner/fw.bin", "home/ark/.bash_history",
            "home/ark/.cache/rk-video/last.log", "etc/systemd/system/stump-ark.service",
            "home/ark/.config/systemd/user/stump.service"]
KEPT = ["data/ark/firefly/deploy/FireFly.sh", "data/ark/firefly/venv/bin/python", "data/ark/R36MAX-Stump/handheld/install.sh",
        "data/ark/ports/Ember.sh", "data/ark/ports/ember/ember", "home/ark/rk3326_provisioner/VERSION",
        "home/ark/SandBox_Stump_On/provisioner.py", "data/ark/.rk-schema", "data/ark/.rk-backups/20261126T000000Z/version",
        "data/ark/packages/recon-0.6.0.zip", "data/opt/metasploit/msfconsole", "share/roms/n64/a-game.z64",
        "share/roms/saves/a-game.srm", "share/packages/fielddeck.zip", "etc/os-release.rk", "etc/hostname",
        "boot/boot.ini", "boot/wifi.txt", "home/ark/.bashrc", "home/ark/.local/share/rk-video/yt-dlp",
        "usr/share/zoneinfo/America/Toronto", "usr/share/zoneinfo/Europe/Paris", "etc/passwd"]


def card(t):
    """A card that has been lived on: set up the way migrations leave it,
    with links from the home folder to the data partition."""
    for rel in SETTINGS + APP_DATA + KEPT:
        os.makedirs(os.path.dirname(f"{t}/{rel}"), exist_ok=True)
        open(f"{t}/{rel}", "w").write(rel)
    os.makedirs(f"{t}/roms/ports")
    for name in (".firefly", ".reticulum", "firefly", "R36MAX-Stump", "ports", "Stump"):
        os.symlink(f"{t}/data/ark/{name}", f"{t}/home/ark/{name}")
    os.symlink(f"{t}/data/ark/roms-stump_r36max", f"{t}/roms/ports/stump_r36max")
    os.symlink(f"{t}/share/roms", f"{t}/data/ark/roms")
    os.symlink(f"{t}/usr/share/zoneinfo/Europe/Paris", f"{t}/etc/localtime")
    open(f"{t}/etc/timezone", "w").write("Europe/Paris\n")


def reset(t, *args):
    env = dict(os.environ, RK_ROOT=t, RK_ZONEINFO=f"{t}/usr/share/zoneinfo")
    return subprocess.run(["bash", RESET, *args], env=env, capture_output=True, text=True)


def there(t, rel):
    return os.path.lexists(f"{t}/{rel}")


def ran(t):
    return open(f"{t}/ran").read() if os.path.exists(f"{t}/ran") else ""


def test_light_takes_the_settings_and_nothing_else():
    with tempfile.TemporaryDirectory() as t:
        card(t)
        p = reset(t, "light")
        assert p.returncode == 0, p.stdout + p.stderr
        assert [rel for rel in SETTINGS if there(t, rel)] == []
        assert [rel for rel in APP_DATA + KEPT if not there(t, rel)] == []     # every app's data, and the rest
        asked = ran(t)
        assert "rk-remote off" in asked and "echo ark:ark | chpasswd" in asked and "chage -d 0 ark" in asked
        # the card's SSH keys are replaced at once: nothing else makes them after the very first start,
        # and without them remote access cannot be turned on again
        assert "ssh-keygen -A" in asked
        assert "ConditionPathExists=!/var/lib/rk/firstboot-done" in open(os.path.join(
            HERE, "..", "..", "overlay", "etc", "systemd", "system", "rk-firstboot.service")).read()
        assert "rk-pkg" not in asked and "stump" not in asked
        assert open(f"{t}/etc/timezone").read().strip() == "America/Toronto"
        assert os.readlink(f"{t}/etc/localtime").endswith("America/Toronto")
        assert "reboot" not in asked                                            # (under test nothing restarts)


def test_full_takes_app_data_too_and_keeps_the_apps():
    with tempfile.TemporaryDirectory() as t:
        card(t)
        p = reset(t, "full")
        assert p.returncode == 0, p.stdout + p.stderr
        assert [rel for rel in SETTINGS + APP_DATA if there(t, rel)] == []
        assert [rel for rel in KEPT if not there(t, rel)] == []
        # the Stump asks its questions again: what its dock entry "needs" is gone
        assert not there(t, "home/ark/Stump") and not there(t, "data/ark/Stump") and not there(t, "home/ark/stump_r36max")
        # FireFly finds its folders, empty: it makes a new identity
        for name in (".firefly", ".reticulum"):
            assert os.path.islink(f"{t}/home/ark/{name}") and os.listdir(f"{t}/data/ark/{name}") == []
        # the Stump's folder under /roms is as a new card has it
        assert sorted(os.listdir(f"{t}/data/ark/roms-stump_r36max")) == ["drop", "tf_backup"]
        assert os.listdir(f"{t}/data/ark/roms-stump_r36max/drop") == []
        asked = ran(t)
        assert "rk-pkg remove recon" in asked and "systemctl disable --now stump-ark" in asked
        assert "loginctl disable-linger ark" in asked and "stop-stump.sh" in asked
        # the games folder is a link out of the data folder: followed by nothing
        assert os.path.islink(f"{t}/data/ark/roms") and there(t, "share/roms/n64/a-game.z64")


def test_a_second_reset_and_an_empty_card_are_fine():
    with tempfile.TemporaryDirectory() as t:
        card(t)
        assert reset(t, "full").returncode == 0
        assert reset(t, "full").returncode == 0
        assert [rel for rel in KEPT if not there(t, rel)] == []
    with tempfile.TemporaryDirectory() as t:                                    # a card just flashed: almost nothing there
        os.makedirs(f"{t}/home/ark")
        os.makedirs(f"{t}/etc")
        assert reset(t, "full").returncode == 0


def test_a_link_pointing_outside_is_not_followed():
    with tempfile.TemporaryDirectory() as t:
        card(t)
        os.remove(f"{t}/home/ark/Stump")
        os.symlink(f"{t}/share/roms", f"{t}/home/ark/Stump")                    # somebody's odd link, to the games
        os.makedirs(f"{t}/outside")
        open(f"{t}/outside/precious", "w").write("x")
        os.remove(f"{t}/home/ark/.firefly")
        os.symlink(f"{t}/outside", f"{t}/home/ark/.firefly")
        assert reset(t, "full").returncode == 0
        assert there(t, "share/roms/n64/a-game.z64") and there(t, "outside/precious")
        assert not there(t, "home/ark/Stump")                                   # the link itself goes


def test_it_wants_a_kind_and_a_home():
    with tempfile.TemporaryDirectory() as t:
        card(t)
        for args in ((), ("everything",), ("--no-restart",)):
            assert reset(t, *args).returncode == 2
        assert [rel for rel in SETTINGS + APP_DATA + KEPT if not there(t, rel)] == []
    with tempfile.TemporaryDirectory() as t:
        assert reset(t, "light").returncode == 1


def shadow(t, day):
    os.makedirs(f"{t}/etc", exist_ok=True)
    open(f"{t}/etc/shadow", "w").write(f"ark:$y$j9T$abc:{day}:0:99999:7:::\n")


def test_without_the_password_only_while_it_is_the_first_one():
    text = open(os.path.join(HERE, "..", "..", "overlay", "etc", "sudoers.d", "rkshell")).read()
    assert "rk-reset unlocked light" in text and "rk-reset unlocked full" in text
    rules = "".join(ln for ln in text.splitlines() if not ln.startswith("#"))
    assert rules.count("rk-reset") == rules.count("rk-reset unlocked") == 2     # no other way in without the password
    with tempfile.TemporaryDirectory() as t:
        card(t)
        shadow(t, 20419)                                        # the owner chose a password
        p = reset(t, "unlocked", "full")
        assert p.returncode == 1 and "own password" in p.stderr
        assert [rel for rel in SETTINGS + APP_DATA + KEPT if not there(t, rel)] == []
        shadow(t, 0)                                            # still the first one
        assert reset(t, "unlocked", "light").returncode == 0
        assert [rel for rel in SETTINGS if there(t, rel)] == []
        assert reset(t, "unlocked", "everything").returncode == 2


# ------------------------------------------------------------- in Settings
def settings(own_password=True):
    system = S.DemoSystem()
    if own_password:
        system.set_password("a-longer-one")
    app = A.App(system, pygame.Surface((720, 720)))
    app.window = SystemPage(app)
    SystemPage.reset_job = None
    page = app.window
    page.list.sel = next(i for i, it in enumerate(page.list.items) if it["name"] == "Reset this handheld")
    return system, app, page


def choose(app, label):
    menu = app.stack[-1]
    assert isinstance(menu, Menu)
    menu.sel = next(i for i, (text, _) in enumerate(menu.items) if text.startswith(label))
    app.handle("a")


def test_two_confirms_then_the_password():
    system, app, page = settings()
    app.handle("a")
    menu = app.stack[-1]
    assert menu.title == "Reset this handheld" and menu.items[0][0] == "Cancel"
    app.handle("a")                                             # A twice by mistake: Cancel, nothing
    assert not app.stack and not hasattr(system, "reset_done")
    app.handle("a")
    choose(app, "Full")
    confirm = app.stack[-1]
    assert confirm.title == "Full reset?" and "cannot be undone" in confirm.detail and "RKSHARE stay" in confirm.detail
    assert confirm.items[0][0] == "Cancel"
    app.draw()
    choose(app, "Reset")
    kb = app.stack[-1]
    assert isinstance(kb, Keyboard) and not hasattr(system, "reset_done")
    kb.value = "not-the-password"
    app.handle("start")
    page.poll()
    assert not hasattr(system, "reset_done") and "not this handheld's password" in app.toast_text and app.toast_error
    app.handle("a")
    choose(app, "Light")
    assert app.stack[-1].title == "Light reset?"
    choose(app, "Reset")
    app.stack[-1].value = "a-longer-one"
    app.handle("start")
    assert system.reset_done == "light"
    page.poll()
    assert "Restarting" in app.toast_text and SystemPage.reset_job is None


def test_on_the_first_password_nothing_is_asked():
    system, app, page = settings(own_password=False)
    app.handle("a")
    choose(app, "Light")
    choose(app, "Reset")
    assert not app.stack and system.reset_done == "light"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
