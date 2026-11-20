"""Draw every page, and a few of the screens they open, into PNG files."""
import os

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
        app.draw()
        pygame.image.save(surf, os.path.join(out_dir, f"{n:02d}-{name}.png"))

    for i, page in enumerate(app.pages):
        app.page = i
        page.enter()
        shot(page.title.lower())
    app.page = 1                                    # FILES: inside the home folder
    app.pages[1].handle("a")
    shot("files-folder")
    app.page = 2                                    # NETWORK: the list of networks, then a password
    app.pages[2].handle("a")
    import time
    time.sleep(0.2)
    shot("network-join")
    app.push(Keyboard(app, "Password for Guest", lambda pw: None, secret=True, initial="hunter2"))
    shot("keyboard")
    app.stack.clear()
    app.page = 4                                    # SYSTEM: about, then the power-off question
    app.pages[4].about()
    shot("system-about")
    app.stack.clear()
    app.confirm("Power off?", "Press the power button to start it again.", "Power off", lambda: None)
    shot("confirm")
    print(f"{n} pictures in {out_dir}")
    return 0
