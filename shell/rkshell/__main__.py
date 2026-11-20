"""Start the shell.

  python3 -m rkshell --window              in a window, for working on it
  python3 -m rkshell --demo --shots DIR    draw every page with made-up data into PNG files
"""
import argparse
import os
import sys


def main():
    ap = argparse.ArgumentParser(prog="rkshell")
    ap.add_argument("--window", action="store_true", help="run in a desktop window (keyboard: arrows, z/x/s/a, q/w, Enter)")
    ap.add_argument("--demo", action="store_true", help="made-up data instead of this machine's")
    ap.add_argument("--shots", metavar="DIR", help="write a PNG of every page to DIR and exit")
    ap.add_argument("--size", default="720x720")
    a = ap.parse_args()
    w, h = (int(x) for x in a.size.split("x"))

    if a.shots:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    import pygame
    from .app import App
    from .system import DemoSystem, System
    system = DemoSystem() if a.demo else System()

    if a.shots:
        from .shots import write_all
        return write_all(system, (w, h), a.shots)
    if a.window:
        from .backends.window import run
        return run(system, (w, h))
    print("On the handheld the shell is started by its service; here use --window or --shots.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
