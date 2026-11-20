"""A desktop window, for working on the shell without a handheld.

Arrows move, Z or Enter is A, X or Escape is B, S is X, A is Y, Q/W are L1/R1,
1/2 are L2/R2, Space is START, Tab is SELECT. Text typed while the on-screen
keyboard is open goes into it.
"""
import pygame

from ..app import App
from ..widgets import Keyboard

KEYS = {pygame.K_UP: "up", pygame.K_DOWN: "down", pygame.K_LEFT: "left", pygame.K_RIGHT: "right",
        pygame.K_z: "a", pygame.K_RETURN: "a", pygame.K_x: "b", pygame.K_ESCAPE: "b", pygame.K_s: "x", pygame.K_a: "y",
        pygame.K_q: "l1", pygame.K_w: "r1", pygame.K_1: "l2", pygame.K_2: "r2", pygame.K_SPACE: "start", pygame.K_TAB: "select"}


def run(system, size):
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode(size)
    pygame.display.set_caption("rkshell")
    app = App(system, screen)
    clock = pygame.time.Clock()
    while app.running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                app.running = False
            elif e.type == pygame.TEXTINPUT and isinstance(app.current, Keyboard):
                app.text_input(e.text)
            elif e.type == pygame.KEYDOWN:
                if isinstance(app.current, Keyboard) and e.key in (pygame.K_RETURN, pygame.K_BACKSPACE):
                    app.text_input("\n" if e.key == pygame.K_RETURN else "\x08")
                elif not isinstance(app.current, Keyboard) or e.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT,
                                                                        pygame.K_RIGHT, pygame.K_ESCAPE, pygame.K_TAB):
                    if e.key in KEYS:
                        app.handle(KEYS[e.key])
        app.tick()
        if app.launch:
            app.toast("Starting an app needs the handheld")
            app.launch = None
        if app.dirty:
            app.draw()
            pygame.display.flip()
        clock.tick(30)
    return 0
