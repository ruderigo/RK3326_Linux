"""Safe defaults, without a handheld: remote access stays shut on the first
password, and a nearly empty battery is noticed in time.

    python3 tests/test_power.py
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
from rkshell.pages.network import NetworkPage
from rkshell.system import DemoSystem
from rkshell.widgets import Keyboard, Menu

pygame.display.init()
pygame.font.init()
pygame.display.set_mode((1, 1))

OVERLAY = os.path.join(HERE, "..", "..", "overlay")
REMOTE = os.path.join(OVERLAY, "usr", "local", "sbin", "rk-remote")
BATTERY = os.path.join(OVERLAY, "usr", "local", "sbin", "rk-battery")


def sh(cmd, **env):
    return subprocess.run(cmd, env=dict(os.environ, **env), capture_output=True, text=True)


# ------------------------------------------------------------ remote access
def shadow(t, day):
    path = os.path.join(t, "shadow")
    open(path, "w").write(f"root:!:20000:0:99999:7:::\nark:$y$j9T$abc:{day}:0:99999:7:::\n")
    return path


def fake_systemctl(t):
    """Stands in for systemctl: writes what it was asked to a file."""
    path, log = os.path.join(t, "systemctl"), os.path.join(t, "asked")
    open(path, "w").write(f'#!/bin/sh\necho "$@" >> "{log}"\n')
    os.chmod(path, 0o755)
    return path, log


def test_remote_refuses_on_the_first_password():
    with tempfile.TemporaryDirectory() as t:
        ctl, log = fake_systemctl(t)
        env = {"RK_SHADOW": shadow(t, 0), "RK_SYSTEMCTL": ctl}
        assert sh(["bash", REMOTE, "first"], **env).returncode == 0
        p = sh(["bash", REMOTE, "on"], **env)
        assert p.returncode == 3 and "first password" in p.stderr
        assert not os.path.exists(log)                      # SSH was never touched
        assert sh(["bash", REMOTE, "off"], **env).returncode == 0   # off is always allowed
        assert open(log).read().strip() == "disable --now ssh"


def test_remote_turns_on_with_an_own_password():
    with tempfile.TemporaryDirectory() as t:
        ctl, log = fake_systemctl(t)
        env = {"RK_SHADOW": shadow(t, 20419), "RK_SYSTEMCTL": ctl}
        assert sh(["bash", REMOTE, "first"], **env).returncode != 0
        assert sh(["bash", REMOTE, "on"], **env).returncode == 0
        assert open(log).read().strip() == "enable --now ssh"


def test_sudoers_only_lets_the_desktop_through_rk_remote():
    text = open(os.path.join(OVERLAY, "etc", "sudoers.d", "rkshell")).read()
    assert "systemctl enable --now ssh" not in text
    assert "/usr/local/sbin/rk-remote on" in text and "/usr/local/sbin/rk-remote off" in text


def wait_for(cond, secs=5):
    end = time.time() + secs
    while time.time() < end and not cond():
        time.sleep(0.02)
    return cond()


def test_desktop_asks_for_a_password_before_turning_ssh_on():
    system = DemoSystem()
    app = A.App(system, pygame.Surface((720, 720)))
    page = NetworkPage(app)
    app.window = page
    assert not system.ssh_enabled() and system.password_expired()
    page.toggle_ssh()
    menu = app.stack[-1]
    assert isinstance(menu, Menu) and menu.title == "Choose a password first"
    assert not system.ssh_enabled()                         # nothing yet: Cancel comes first
    # too short, or the first password again: refused, SSH stays off
    for bad in ("short", "ark"):
        page.new_password(bad, lambda: system.set_ssh(True))
        assert not system.ssh_enabled() and system.password_expired()
    done = []
    page.new_password("a-longer-one", lambda: done.append(system.set_ssh(True)))
    assert wait_for(lambda: done) and done[0][0]
    assert system.ssh_enabled() and not system.password_expired()
    # with its own password, turning it on again asks nothing
    system.set_ssh(False)
    del app.stack[:]
    page.toggle_ssh()
    assert system.ssh_enabled() and not app.stack


def test_demo_refuses_ssh_on_the_first_password():
    system = DemoSystem()
    ok, why = system.set_ssh(True)
    assert not ok and "first password" in why and not system.ssh_enabled()


# ----------------------------------------------------------------- battery
def supply(t, pct=None, status="Discharging", volts=None):
    d = os.path.join(t, "supply")
    os.makedirs(os.path.join(d, "ac"), exist_ok=True)
    open(os.path.join(d, "ac", "type"), "w").write("Mains\n")
    if pct is not None:
        b = os.path.join(d, "battery")
        os.makedirs(b, exist_ok=True)
        for name, value in (("type", "Battery"), ("capacity", pct), ("status", status), ("voltage_now", volts)):
            if value is not None:
                open(os.path.join(b, name), "w").write(f"{value}\n")
    return d


def once(**kw):
    with tempfile.TemporaryDirectory() as t:
        return sh(["bash", BATTERY, "once"], RK_POWER_SUPPLY=supply(t, **kw)).stdout.strip()


def test_battery_reading():
    assert once() == "none"                                         # a board with no gauge
    assert once(pct="") == "none"                                   # a gauge that says nothing
    assert once(pct=50) == "ok 50"
    assert once(pct=4) == "ok 4"
    assert once(pct=3) == "low 3"
    assert once(pct=0, volts=3300000) == "low 0"
    assert once(pct=2, status="Charging") == "ok 2"                 # on the charger: never
    assert once(pct=2, status="Full") == "ok 2"
    assert once(pct=0, volts=4100000) == "doubt 0"                  # a gauge that lost count on a full cell


def watch(secs, quiet="0", **kw):
    """Run the service for a moment with a stand-in systemctl; what it was asked."""
    with tempfile.TemporaryDirectory() as t:
        ctl, log = fake_systemctl(t)
        p = subprocess.Popen(["bash", BATTERY], env=dict(os.environ, PATH=t + os.pathsep + os.environ["PATH"],
                             RK_POWER_SUPPLY=supply(t, **kw), RK_BATTERY_EVERY="0.1", RK_BATTERY_QUIET=quiet),
                             stdout=subprocess.PIPE, text=True)
        try:
            p.wait(timeout=secs)
        except subprocess.TimeoutExpired:
            p.kill()
        return open(log).read().strip() if os.path.exists(log) else "", p.stdout.read()


def test_battery_service_powers_off_only_when_sure():
    asked, said = watch(5, pct=2, volts=3300000)
    assert asked == "poweroff" and "powering off" in said
    assert watch(1, pct=2, status="Charging")[0] == ""
    assert watch(1, pct=30)[0] == ""
    assert watch(1)[0] == ""                                        # no gauge
    asked, said = watch(1, pct=0, volts=4100000)
    assert asked == "" and said.count("not powering off") == 1      # said once, not every reading
    # just after the start it waits, however low the reading
    assert watch(1, quiet="999999999", pct=1)[0] == ""


class Bat(DemoSystem):
    def __init__(self):
        super().__init__()
        self.pct, self.status = 78, "Discharging"

    def battery(self):
        return {"percent": self.pct, "status": self.status}


def test_desktop_warns_twice_and_only_once_each():
    system = Bat()
    app = A.App(system, pygame.Surface((720, 720)))

    def at(pct, status="Discharging"):
        system.pct, system.status = pct, status
        app.toast_text = ""
        app.check_battery()
        return app.toast_text

    assert at(78) == "" and at(11) == ""
    assert "10%" in at(10) and "charger" in app.toast_text and app.toast_error
    assert at(9) == "" and at(6) == ""                              # said once
    assert "5%" in at(5) and "powers off at 3%" in app.toast_text
    assert at(4) == "" and at(3) == ""
    assert at(4, "Charging") == ""                                  # plugged in: quiet, and it starts over
    assert at(40) == ""
    assert "8%" in at(8)
    system.battery = lambda: None                                   # no gauge: nothing, no error
    app.check_battery()
    system.battery = lambda: {"percent": -1, "status": "Unknown"}
    app.check_battery()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
