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
