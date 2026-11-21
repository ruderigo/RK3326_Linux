"""Draw the desktop and every window into PNG files."""
import os
import time

import pygame

from .app import App
from .widgets import Keyboard


def write_all(system, size, out_dir):
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_mode((1, 1))
    os.makedirs(out_dir, exist_ok=True)
    surf = pygame.Surface(size)
    app = App(system, surf)
    from .pages.arsenal import ArsenalPage
    def ArsenalPage_reset():
        ArsenalPage.install = None
    n = 0

    def shot(name):
        nonlocal n
        n += 1
        for _ in range(30):                     # let the dock settle on its icon
            app.draw()
        pygame.image.save(surf, os.path.join(out_dir, f"{n:02d}-{name}.png"))

    shot("desktop")
    for _ in range(4):
        app.handle("right")
    shot("desktop-app")
    for i, item in enumerate(app.dock.items):       # the Stump's setup window, opened from its dock entry
        if item.get("setup") == "stump":
            from .pages.stumpsetup import StumpSetupPage
            app.dock.sel = i
            app.handle("a")
            StumpSetupPage.form.update(pw="oak-and-moss", chain="member", secret="b1rch")
            app.handle("down"); app.handle("down"); app.handle("down")
            app.handle("a")                      # look for Stumps on the network
            app.tick()
            shot("stump-setup-found")
            app.handle("a")                      # the first one found
            shot("stump-setup")
            StumpSetupPage.form["sudo"] = "x"
            app.handle("start")
            shot("stump-setup-running")
            StumpSetupPage.job, StumpSetupPage.form = None, None
            app.window = None
    app.dock.sel = 0
    for i, item in enumerate(app.dock.items):
        if "window" not in item:
            continue
        app.dock.sel = i
        app.handle("a")
        shot(item["name"].lower())
        if item["name"] == "Files":
            app.handle("a")
            shot("files-folder")
            app.handle("b")
        if item["name"] == "Network":
            app.handle("a")
            time.sleep(0.2)
            shot("network-join")
            app.push(Keyboard(app, "Password for Guest", lambda pw: None, secret=True, initial="hunter2"))
            shot("keyboard")
            app.stack.clear()
        if item["name"] == "Terminal":
            from .pages.terminal import TerminalPage
            sess = TerminalPage.session
            for line in ("export PS1='ark@r36max:~$ '; clear", "echo a real shell, on the handheld", "echo scans are saved in /data/ark/scans"):
                app.text_input(line + "\r")
                end = time.time() + 0.5
                while time.time() < end:
                    app.tick()
                    time.sleep(0.02)
            shot("terminal")
            app.handle("x")
            shot("terminal-keyboard")
            app.handle("select")
            if sess:
                sess.close()
            TerminalPage.session = None
        if item["name"] == "Scan":
            from .pages.scan import ScanPage
            shot("scan-loadout")
            app.handle("down")
            app.handle("right")
            app.handle("right")                 # the Identify loadout
            shot("scan-identify")
            app.handle("x")
            app.window.view = "running"
            shot("scan-running")
            app.tick()
            shot("scan-results")
            app.handle("down")
            app.handle("a")
            shot("scan-host")
            app.stack.clear()
            app.window.view = "loadout"
            ScanPage.scan, ScanPage.hosts = None, []
        if item["name"] == "Arsenal":
            app.handle("down"); app.handle("down"); app.handle("down")
            app.handle("a")
            shot("arsenal-about")
            app.handle("b")
            app.handle("x")                     # fetch the heavy tools
            shot("arsenal-install")
            app.stack.clear()
            app.window.view = "list"
            ArsenalPage_reset()
        if item["name"] == "Survey":
            time.sleep(0.3)
            shot("survey-list")
        if item["name"] == "Settings":
            app.window.about()
            shot("settings-about")
            app.stack.clear()
            app.confirm("Power off?", "Press the power button to start it again.", "Power off", lambda: None)
            shot("confirm")
            app.stack.clear()
        app.handle("b")
    print(f"{n} pictures in {out_dir}")
    return 0
