#!/usr/bin/env python3
"""Make the boot logo for every panel from one picture.

    make-logos.py PICTURE LOGO_DIR TURNS_FILE

LOGO_DIR is consoles/logo on the boot partition being built: one folder per
kind of panel, each with a logo.bmp that u-boot shows when the handheld is
switched on. u-boot reads one format only: a BMP that is not compressed, 24
bits per pixel, of exactly the panel's size. Each folder's logo.bmp is
replaced by PICTURE in that folder's size, turned as TURNS_FILE says, whole
(nothing is cut off), with the colour of the picture's top corners around it.
"""
import os
import sys

from PIL import Image


def edge_colour(im):
    """The average colour of the picture's two top corners (a twentieth of its side each)."""
    w, h = im.size
    k = max(1, min(w, h) // 20)
    px = im.load()
    pts = [px[x, y] for x in list(range(k)) + list(range(w - k, w)) for y in range(k)]
    return tuple(sum(p[i] for p in pts) // len(pts) for i in range(3))


def logo(pic, size, turn):
    w, h = size if turn in (0, 180) else (size[1], size[0])     # the panel as it is looked at
    side = min(w, h)
    canvas = Image.new("RGB", (w, h), edge_colour(pic))
    canvas.paste(pic.resize((side, side), Image.LANCZOS), ((w - side) // 2, (h - side) // 2))
    out = canvas.rotate(turn, expand=True) if turn else canvas
    assert out.size == tuple(size), (out.size, size)
    return out


def main():
    picture, logo_dir, turns_file = sys.argv[1:4]
    turns = {}
    for line in open(turns_file, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#"):
            name, deg = line.split("|")
            turns[name] = int(deg)
    pic = Image.open(picture).convert("RGB")
    made = 0
    for name in sorted(os.listdir(logo_dir)):
        path = os.path.join(logo_dir, name, "logo.bmp")
        if not os.path.isfile(path):
            continue
        if name not in turns:
            print(f"make-logos: WARNING: {name} is not in {os.path.basename(turns_file)}: arkos4clone's logo is kept")
            continue
        with Image.open(path) as stock:
            size = stock.size
        logo(pic, size, turns[name]).save(path, format="BMP")       # RGB: 24 bits, not compressed
        made += 1
    print(f"make-logos: {made} boot logos made from {os.path.basename(picture)}")
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
