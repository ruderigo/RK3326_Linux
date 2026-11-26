#!/usr/bin/env python3
"""The picture shown at switch-on, made for every panel. Not a command for
the owner: the image build and one update step run it, nothing else.

    bootlogo.py make LOGO_DIR     (the build) write our logo over each LOGO_DIR/<folder>/logo.bmp
    bootlogo.py boot [BOOT]       (the update step) the same on a boot partition, then the
                                  logo.bmp that the handheld chosen there starts with

u-boot shows one kind of file only: a BMP that is not compressed, 24 bits a
pixel, of exactly the panel's size, and it draws the file as it is, so for a
panel mounted on its side the picture is stored turned. /usr/share/rk/boot-logo
holds the picture (logo.jpg) and, for each of arkos4clone's logo folders, how
far it is turned counter-clockwise (turns.txt). Each folder's logo.bmp is
replaced by the picture in that folder's size, whole (nothing is cut off),
with the colour of the picture's top corners around it. A folder that is not
in turns.txt keeps the logo it has, and that is said.

An update does not replace the boot partition, so a card flashed before our
logo existed kept arkos4clone's. Migration 0004 runs "boot" once on such a
card. After that the logo.bmp on BOOT is the owner's: they replace the file
themselves, and no later update writes over it.
"""
import os
import struct
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402

SHARE = os.environ.get("RK_BOOTLOGO_DIR", "/usr/share/rk/boot-logo")     # RK_BOOTLOGO_DIR: the build and the tests


def say(text):
    print(f"bootlogo: {text}")


def bmp_size(path):
    with open(path, "rb") as f:
        head = f.read(26)
    if head[:2] != b"BM" or len(head) < 26:
        raise ValueError("not a BMP")
    w, h = struct.unpack("<ii", head[18:26])
    return w, abs(h)


def turns():
    out = {}
    with open(os.path.join(SHARE, "turns.txt"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                name, deg = line.split("|")
                out[name] = int(deg)
    return out


def edge_colour(pic):
    """The average colour of the picture's two top corners (a twentieth of its side each)."""
    w, h = pic.get_size()
    k = max(1, min(w, h) // 20)
    pts = [pic.get_at((x, y)) for x in list(range(k)) + list(range(w - k, w)) for y in range(k)]
    return tuple(sum(p[i] for p in pts) // len(pts) for i in range(3))


def logo(pic, size, turn):
    w, h = size if turn in (0, 180) else (size[1], size[0])     # the panel as it is looked at
    side = min(w, h)
    canvas = pygame.Surface((w, h), depth=24)
    canvas.fill(edge_colour(pic))
    canvas.blit(pygame.transform.smoothscale(pic, (side, side)), ((w - side) // 2, (h - side) // 2))
    out = pygame.transform.rotate(canvas, turn) if turn else canvas     # counter-clockwise, as turns.txt counts
    if out.get_size() != tuple(size):
        raise ValueError(f"made {out.get_size()}, wanted {size}")
    return out.convert(24) if out.get_bitsize() != 24 else out


def write(surface, path):
    """Beside the file, then over it: a card pulled mid-write keeps the old logo."""
    new = os.path.join(os.path.dirname(path), ".logo-new.bmp")      # the name ends in .bmp: pygame goes by it
    pygame.image.save(surface, new)
    os.replace(new, path)


def make(logo_dir):
    """-> {folder: its new logo's path}"""
    table = turns()
    pic = pygame.image.load(os.path.join(SHARE, "logo.jpg"))
    made = {}
    for name in sorted(os.listdir(logo_dir)):
        path = os.path.join(logo_dir, name, "logo.bmp")
        if not os.path.isfile(path):
            continue
        if name not in table:
            say(f"WARNING: {name} is not in turns.txt: the logo it has is kept")
            continue
        try:
            write(logo(pic, bmp_size(path), table[name]), path)
        except (OSError, ValueError, pygame.error) as e:
            say(f"{name}: {e}: the logo it has is kept")
            continue
        made[name] = path
    if made:
        # so the update step can tell a boot partition that has ours already
        with open(os.path.join(logo_dir, "ours.txt"), "w", encoding="utf-8") as f:
            f.write("These logos are RK3326 Linux's own. Replace logo.bmp at the top of BOOT with yours.\r\n")
    say(f"{len(made)} boot logos made")
    return made


def chosen_folder(boot):
    """The logo folder of the handheld this boot partition starts: rk-device.txt -> consoles/logos.txt."""
    try:
        console = ""
        with open(os.path.join(boot, "rk-device.txt"), encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("console="):
                    console = line.split("=", 1)[1].strip()
        with open(os.path.join(boot, "consoles", "logos.txt"), encoding="utf-8", errors="replace") as f:
            for line in f:
                name, _, folder = line.strip().partition("|")
                if name == console and folder:
                    return os.path.basename(folder.strip("/"))
    except OSError:
        pass
    return ""


def boot(boot_dir):
    logo_dir = os.path.join(boot_dir, "consoles", "logo")
    if not os.path.isdir(logo_dir):
        say(f"no consoles/logo in {boot_dir}: nothing done")
        return 1
    made = make(logo_dir)
    folder = chosen_folder(boot_dir)
    if folder in made:
        with open(made[folder], "rb") as src:
            data = src.read()
        new = os.path.join(boot_dir, ".logo-new.bmp")
        with open(new, "wb") as dst:
            dst.write(data)
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(new, os.path.join(boot_dir, "logo.bmp"))
        say(f"logo.bmp is now ours, for {folder}")
    else:
        say("could not tell which handheld this card starts: logo.bmp is left as it is")
    os.sync()
    return 0 if made else 1


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "make":
        return 0 if make(args[1]) else 1
    if args and args[0] == "boot" and len(args) <= 2:
        return boot(args[1] if len(args) == 2 else "/boot")
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
