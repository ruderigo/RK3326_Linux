"""Debian's security updates as part of "Update this handheld", without a
handheld: apt-get and dpkg are stand-ins that write down what they were asked.

    python3 tests/test_packages.py
"""
import os
import subprocess
import sys
import tempfile
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pygame

from rkshell import app as A
from rkshell import system as S
from rkshell.pages.osupdate import OsUpdatePage
from rkshell.widgets import Keyboard, Menu

pygame.display.init()
pygame.font.init()
pygame.display.set_mode((1, 1))

HERE = os.path.dirname(os.path.abspath(__file__))
RK_UPDATE = os.path.join(HERE, "..", "..", "overlay", "usr", "local", "sbin", "rk-update")

APT = r'''#!/bin/bash
echo "apt-get $*" >> "$LOG"
case " $* " in
    *" update "*)       exit "${APT_UPDATE_RC:-0}" ;;
    *" -s "*)           for i in $(seq 1 "${PENDING:-0}"); do echo "Inst pkg$i [1.0] (1.1 Debian-Security:13/stable-security [arm64])"; done ;;
    *" --print-uris "*) for i in $(seq 1 "${PENDING:-0}"); do echo "'http://security.debian.org/pkg$i.deb' pkg${i}_1.1_arm64.deb 2097152 SHA256:x"; done ;;
    *" clean "*)        ;;
    *" upgrade "*)      for i in $(seq 1 "${PENDING:-0}"); do echo "Unpacking pkg$i (1.1) over (1.0) ..."; echo "Setting up pkg$i (1.1) ..."; done
                        exit "${APT_UPGRADE_RC:-0}" ;;
esac
'''


def packages(pending=0, online=True, free=None, battery=None, **env):
    """Run rk-update's packages step; (exit code, what it said, what apt and dpkg were asked)."""
    with tempfile.TemporaryDirectory() as t:
        log = os.path.join(t, "asked")
        for name, text in (("apt-get", APT), ("dpkg", '#!/bin/bash\necho "dpkg $*" >> "$LOG"\n')):
            open(os.path.join(t, name), "w").write(text)
            os.chmod(os.path.join(t, name), 0o755)
        os.makedirs(os.path.join(t, "var/lib/apt/lists"))
        open(os.path.join(t, "var/lib/apt/lists/a_list"), "w").write("x")
        supply = os.path.join(t, "supply")
        if battery:
            os.makedirs(os.path.join(supply, "battery"))
            for k, v in zip(("type", "capacity", "status"), ("Battery",) + battery):
                open(os.path.join(supply, "battery", k), "w").write(f"{v}\n")
        body = (f'RK_UPDATE_SOURCE=1 RK_ROOT="{t}" source "{RK_UPDATE}"\n'
                f'need_root() {{ :; }}\nonline() {{ {"true" if online else "false"}; }}\n'
                f'rk_apt_cache() {{ echo "{t}/cache"; }}\npackages\n')
        e = dict(os.environ, PATH=t + os.pathsep + os.environ["PATH"], LOG=log, PENDING=str(pending),
                 RK_PACKAGES_TEST="1", RK_POWER_SUPPLY=supply, **env)
        if free is not None:
            e["RK_PREFLIGHT_FREE_MB"] = str(free)
        p = subprocess.run(["bash", "-c", body], env=e, capture_output=True, text=True)
        asked = open(log).read() if os.path.exists(log) else ""
        return p.returncode, p.stdout + p.stderr, asked, os.listdir(os.path.join(t, "var/lib/apt/lists"))


def upgraded(asked):
    return any(" upgrade -y -q" in ln for ln in asked.splitlines())


def test_nothing_pending():
    rc, said, asked, lists = packages(0)
    assert rc == 0 and "up to date" in said and not upgraded(asked)
    assert "dpkg --configure -a" in asked                       # an update cut short earlier is finished first
    assert lists == []                                          # the lists are not left on the card


def test_updates_go_in_and_are_named():
    rc, said, asked, lists = packages(3, free=4000)
    assert rc == 0 and upgraded(asked), said
    assert "3 Debian packages to update, 6 MB to download" in said
    assert "rk-update:   pkg2 1.1" in said and "Unpacking" not in said
    assert "Debian's packages are updated (3)" in said
    line = next(ln for ln in asked.splitlines() if " upgrade -y -q" in ln)
    assert "--force-confold" in line and "dist-upgrade" not in asked and "full-upgrade" not in asked
    assert "install" not in asked and "remove" not in asked     # never adds or removes a package
    assert asked.rstrip().splitlines()[-1].endswith("clean") and lists == []


def test_offline_or_no_lists_changes_nothing():
    rc, said, asked, _ = packages(3, online=False)
    assert rc != 0 and "no network" in said and asked == ""
    rc, said, asked, _ = packages(3, APT_UPDATE_RC="100")
    assert rc != 0 and "could not be refreshed" in said and not upgraded(asked)


def test_not_on_a_low_battery():
    rc, said, asked, _ = packages(3, free=4000, battery=(20, "Discharging"))
    assert rc != 0 and "battery is under 25%" in said and not upgraded(asked)
    assert upgraded(packages(3, free=4000, battery=(20, "Charging"))[2])       # on the charger: go
    assert upgraded(packages(3, free=4000, battery=(60, "Discharging"))[2])


def test_not_without_room():
    rc, said, asked, _ = packages(3, free=10)
    assert rc != 0 and "not enough room" in said and not upgraded(asked)


def test_a_failed_upgrade_is_said_and_tidied():
    rc, said, asked, lists = packages(2, free=4000, APT_UPGRADE_RC="100")
    assert rc != 0 and "did not all go in" in said and lists == []


def test_switched_off_and_under_other_tests():
    rc, said, asked, _ = packages(3, RK_NO_PACKAGES="1")
    assert rc == 0 and asked == ""


def test_apply_runs_it_and_cannot_be_failed_by_it():
    text = open(RK_UPDATE).read()
    assert text.count("packages || true") == 2                  # after an update, and when already current
    assert "    packages) packages ;;" in text


# ------------------------------------------ the two versions in the window
def test_versions_are_read_and_compared():
    assert S.os_release_version('RK_NAME="RK3326 Linux"\nRK_VERSION="1.3.1"\nRK_CONSOLE="r36max"\n') == "1.3.1"
    assert S.os_release_version("RK_VERSION=dev-ef1aca8\n") == "dev-ef1aca8"
    assert S.os_release_version("") == ""
    assert S.same_version("1.3.1", "v1.3.1") and S.same_version("v1.4.0", "v1.4.0")
    assert not S.same_version("1.3.1", "v1.4.0") and not S.same_version("", "") and not S.same_version("1.3.1", "")


def test_status_local_does_not_ask_the_network():
    with tempfile.TemporaryDirectory() as t:
        os.makedirs(f"{t}/etc")
        open(f"{t}/etc/os-release.rk", "w").write('RK_VERSION="1.3.1"\n')
        git = os.path.join(t, "git")
        open(git, "w").write(f'#!/bin/sh\necho asked >> "{t}/git-asked"\n')
        os.chmod(git, 0o755)
        env = dict(os.environ, RK_ROOT=t, PATH=t + os.pathsep + os.environ["PATH"])
        out = subprocess.run(["bash", RK_UPDATE, "status", "--local"], env=env, capture_output=True, text=True).stdout
        assert "installed : 1.3.1" in out and "newest" not in out
        assert not os.path.exists(f"{t}/git-asked")


class Slow(S.DemoSystem):
    """The network answers late, or not at all."""
    answer, wait = "v1.4.0", 0.3

    def os_status(self):
        return dict(super().os_status(), installed="1.3.1")

    def os_newest(self):
        time.sleep(self.wait)
        return self.answer


def window(system):
    app = A.App(system, pygame.Surface((720, 720)))
    page = OsUpdatePage(app)
    app.push(page)
    page.enter()
    return app, page


def shown(app):
    """Every piece of text the window draws."""
    from rkshell import gfx as G
    drawn, real = [], G.text
    G.text = lambda surf, font, s, *a, **k: (drawn.append(s), real(surf, font, s, *a, **k))[1]
    try:
        app.window = app.window or type("W", (), {"title": "Settings", "draw": lambda *a: None, "hints": []})()
        app.draw()
    finally:
        G.text = real
    return drawn


def settle(page, secs=3):
    end = time.time() + secs
    while page.looking and time.time() < end:
        time.sleep(0.02)


def test_installed_shows_at_once_and_newest_when_it_answers():
    OsUpdatePage.job = None
    app, page = window(Slow())
    text = shown(app)
    assert "1.3.1" in text and "looking…" in text and "unknown" not in text     # no waiting on the network
    settle(page)
    text = shown(app)
    assert "1.4.0" in text and "looking…" not in text
    assert ("A", "update now") in page.hints


def test_no_answer_is_said_and_the_installed_version_still_shows():
    OsUpdatePage.job = None
    system = Slow()
    system.answer, system.wait = "", 0
    app, page = window(system)
    settle(page)
    text = shown(app)
    assert "1.3.1" in text and any("could not look it up" in s for s in text)


def test_a_says_from_which_version_to_which_before_the_password():
    OsUpdatePage.job = None
    app, page = window(Slow())
    settle(page)
    app.handle("a")
    menu = app.stack[-1]
    assert isinstance(menu, Menu) and menu.title == "Update to 1.4.0?"
    assert "is on 1.3.1" in menu.detail and "goes to 1.4.0" in menu.detail and "security updates" in menu.detail
    assert menu.items[0][0] == "Cancel" and OsUpdatePage.job is None
    app.handle("down")
    app.handle("a")
    assert isinstance(app.stack[-1], Keyboard) and OsUpdatePage.job is None     # then the password


def test_up_to_date_still_offers_the_security_updates():
    OsUpdatePage.job = None
    system = Slow()
    system.answer, system.wait = "v1.3.1", 0
    app, page = window(system)
    settle(page)
    assert page.same and ("A", "security updates") in page.hints
    assert any("up to date" in s for s in shown(app))
    app.handle("a")
    menu = app.stack[-1]
    assert menu.title == "Look for security updates?" and "newest version" in menu.detail


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
