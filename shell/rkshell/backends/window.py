"""A desktop window, for working on the shell without a handheld.

Arrows move, Z or Enter is A, X or Escape is B, S is X, A is Y, Q/W are L1/R1,
1/2 are L2/R2, Space is START, Tab is SELECT. In a screen that takes typing
(the on-screen keyboard, the terminal) the keyboard types, and Alt with one
of those keys is the gamepad button. The computer's mouse is the pointer: a
click presses what it is on, the right button is B.
"""
import pygame

from ..app import App

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
    special = {pygame.K_RETURN: "\r", pygame.K_BACKSPACE: "\x7f", pygame.K_TAB: "\t", pygame.K_ESCAPE: "\x1b",
               pygame.K_UP: "\x1b[A", pygame.K_DOWN: "\x1b[B", pygame.K_RIGHT: "\x1b[C", pygame.K_LEFT: "\x1b[D"}
    while app.running:
        for e in pygame.event.get():
            typing = bool(app.current and app.current.wants_keys)
            if e.type == pygame.QUIT:
                app.running = False
            elif e.type == pygame.TEXTINPUT and typing:
                app.text_input(e.text)
            elif e.type == pygame.KEYDOWN and typing:
                if e.mod & pygame.KMOD_ALT and e.key in KEYS:          # Alt + key: the gamepad button
                    app.handle(KEYS[e.key])
                elif e.mod & pygame.KMOD_CTRL and pygame.K_a <= e.key <= pygame.K_z:
                    app.text_input(chr(e.key & 0x1f))
                elif e.key in special:
                    app.text_input(special[e.key])
            elif e.type == pygame.KEYDOWN and e.key in KEYS:
                app.press(KEYS[e.key])
            elif e.type == pygame.MOUSEMOTION:
                app.move_pointer(e.pos[0] - app.pointer[0], e.pos[1] - app.pointer[1])
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                app.move_pointer(e.pos[0] - app.pointer[0], e.pos[1] - app.pointer[1])
                app.click()
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 3:
                app.press("b")
        app.tick()
        if app.launch:
            app.toast("Starting an app needs the handheld")
            app.launch = None
        if app.dirty or app.animating:
            app.draw()
            pygame.display.flip()
        clock.tick(30 if app.dock.moving or app.live else 12)      # smooth while the dock moves, slow for the fireflies
    return 0
