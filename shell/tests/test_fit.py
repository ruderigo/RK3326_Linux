"""Nothing the system says is cut with an ellipsis: sentences of ours wrap,
on every screen size. Only data of unknown length (a video's title, a file
name, a network's name) may be cut to its row.

    python3 tests/test_fit.py
"""
import os
import sys
import tempfile
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pygame

from rkshell import app as A
from rkshell import gfx as G
from rkshell import shots
from rkshell import system as S
from rkshell.pages.network import NetworkPage
from rkshell.pages.osupdate import OsUpdatePage, source_name
from rkshell.pages.system import SystemPage
from rkshell.widgets import Keyboard, Menu

pygame.display.init()
pygame.font.init()
pygame.display.set_mode((1, 1))

SIZES = ((720, 720), (640, 480), (480, 320))
# what may be cut: data that comes from outside and has a row of its own
DATA = ("LoRa antennas, measured",)


class Cuts:
    """Every string gfx.fit shortened while this was on."""
    def __enter__(self):
        self.real, self.found = G.fit, []

        def fit(font, text, width):
            out = self.real(font, text, width)
            if out != text:
                self.found.append(text)
            return out
        G.fit = fit
        return self

    def __exit__(self, *exc):
        G.fit = self.real

    def ours(self):
        return sorted({t for t in self.found if not t.startswith(DATA)})


def test_every_page_at_every_size():
    for size in SIZES:
        with tempfile.TemporaryDirectory() as t, Cuts() as cuts:
            devnull = open(os.devnull, "w")
            out, sys.stdout = sys.stdout, devnull
            try:
                shots.write_all(S.DemoSystem(), size, t)
            finally:
                sys.stdout = out
                devnull.close()
        assert cuts.ours() == [], (size, cuts.ours())


def test_the_windows_the_pictures_do_not_show():
    for size in SIZES:
        with Cuts() as cuts:
            s = S.DemoSystem()
            app = A.App(s, pygame.Surface(size))
            app.window = SystemPage(app)
            OsUpdatePage.job = None
            page = OsUpdatePage(app)
            app.push(page)
            end = time.time() + 3
            while page.looking and time.time() < end:
                time.sleep(0.02)
            app.draw()
            app.handle("a")                                     # "Update to 1.0.0?"
            app.draw()
            app.stack.clear()
            page = OsUpdatePage(app)
            OsUpdatePage.job, page.view = s.os_update("x"), "running"
            app.push(page)
            app.draw()
            app.stack.clear()
            OsUpdatePage.job = None
            app.window = NetworkPage(app)
            app.draw()
            app.window.toggle_ssh()                             # "Choose a password first"
            app.draw()
            app.stack.clear()
            s.set_password("a-longer-one")
            s.set_ssh(True)
            app.window.enter()
            app.draw()
            for prompt in ("Choose a password (8 or more)", "This handheld's password", "Password for Bob's Glitch",
                           "Password for a network with a 32 letter name!"):
                app.push(Keyboard(app, prompt, lambda v: None, secret=True))
                app.draw()
                app.stack.clear()
            app.window = SystemPage(app)
            app.draw()
            for kind in ("light", "full"):
                app.window.ask_reset()
                app.draw()
                app.stack.clear()
                app.window.confirm_reset(kind)
                app.draw()
                app.stack.clear()
            app.push(Menu(app, "A question long enough to need a second line here?",
                          [("Cancel", None), ("A choice whose words do not fit on one line of the box", None)]))
            app.draw()
            app.stack.clear()
            for text in ("Remote access could not start. Restart the handheld and try again.",
                         "Battery at 5%: it powers off at 3%. Plug in the charger.",
                         "That is not this handheld's password. Nothing was reset.",
                         "Preparing the card. Wait, do not restart yet. checking /data"):
                app.toast(text, 5)
                app.draw()
        assert cuts.ours() == [], (size, cuts.ours())


def test_a_long_message_is_drawn_on_several_lines():
    app = A.App(S.DemoSystem(), pygame.Surface((480, 320)))
    drawn, real = [], G.text
    G.text = lambda surf, font, s, *a, **k: (drawn.append(s), real(surf, font, s, *a, **k))[1]
    try:
        text = "Remote access could not start. Restart the handheld and try again."
        app.toast(text, 5, error=True)
        app.draw()
    finally:
        G.text = real
    pieces = [s for s in drawn if s and s in text and s != text]
    assert len(pieces) >= 2 and " ".join(pieces) == text, pieces


def test_log_lines_wrap_and_keep_their_end():
    font = pygame.font.Font(None, 20)
    lines = ["short", 'Job for ssh.service failed. See "systemctl status ssh.service" and "journalctl -xeu ssh.service" for details.']
    got = G.tail(font, lines, 200, 10)
    assert got[0] == ("short", 0) and len(got) > 2
    assert all(i == 1 for _, i in got[1:]) and all(font.size(p)[0] <= 200 for p, _ in got)
    assert " ".join(p for p, i in got if i == 1) == lines[1]                # nothing lost, the end included
    assert G.tail(font, lines, 200, 2) == got[-2:]                         # only the room there is
    word = "x" * 200                                                        # one word wider than the box
    assert "".join(p for p, _ in G.tail(font, [word], 200, 50)) == word


def test_remote_access_failure_is_a_sentence():
    real = S.run
    try:
        S.run = lambda *a, **k: (False, 'Job for ssh.service failed.\nSee "systemctl status ssh.service" and "journalctl -xeu ssh.service" for details.')
        ok, msg = S.System().set_ssh(True)
        assert not ok and msg == "Remote access could not start. Restart the handheld and try again."
        assert not S.System().set_ssh(False)[0] and "systemctl" not in S.System().set_ssh(False)[1]
        S.run = lambda *a, **k: (False, "rk-remote: this handheld still has its first password; choose your own first")
        assert "first password" in S.System().set_ssh(True)[1]
    finally:
        S.run = real


def test_update_source_is_short():
    assert source_name("official (https://github.com/ruderigo/RK3326_Linux)") == "official"
    assert source_name("fork (https://github.com/someone/RK3326_Linux)") == "fork: someone/RK3326_Linux"
    assert source_name("url (https://github.com/ruderigo/RK3326_Linux)") == "url" and source_name("") == "official"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
