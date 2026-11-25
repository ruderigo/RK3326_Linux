#!/usr/bin/env python3
"""Every handheld on the card, checked without having one in hand.

    build/check-consoles.py <consoles dir> [--table FILE] [--sizes]

<consoles dir> is arkos4clone's boot/dArkOS/consoles at the commit pinned in
build/upstream.env: one folder per handheld, with its boot.ini and its device
tree for each kernel. The image carries all of them and one system; this
reads each device tree and boot.ini and checks what that one system takes
for granted on every handheld:

  boot    the system is partition 2 of the card, the files load from
          partition 1, and rk-boot-select can make a boot.ini that starts it
  screen  the panel's size is known, and the desktop is drawn at that size
          (after the quarter turns a panel on its side needs) in the build
  pad     the built-in pad has the name RetroArch and SDL are set up for,
          every button the desktop reads, and a direction pad it can read
  power   the power chip is the one the battery and sound code expect

It fails when one of these does not hold, so raising the pinned commit to an
arkos4clone that supports a new, different handheld is noticed here and not
by its owner. --table writes the list as a Markdown table (docs/devices.md);
--sizes prints the sizes the desktop has to be drawn at.

Standard library only: it runs anywhere, before anything is built.
"""
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SELECT = os.path.join(HERE, "..", "overlay", "usr", "local", "sbin", "rk-boot-select")
PAD_NAME = "GO-Super Gamepad"
BUTTONS = {305: "A", 304: "B", 307: "X", 308: "Y", 310: "L1", 311: "R1", 312: "L2", 313: "R2", 704: "SELECT", 705: "START"}
DPAD = {544, 545, 546, 547}
POWER = {"rockchip,rk817", "rockchip,rk809"}
# handhelds the image has been started on, by a person: folder -> note
ON_HARDWARE = {"r36max type1": "yes (R36MAX)"}


def parse(blob):
    """A device tree file as nested dicts: {"props": {name: bytes}, "kids": {name: node}}."""
    magic, _, off_struct, off_strings = struct.unpack_from(">IIII", blob, 0)
    if magic != 0xD00DFEED:
        raise ValueError("not a device tree")
    p, stack, root = off_struct, [], None
    while True:
        token = struct.unpack_from(">I", blob, p)[0]
        p += 4
        if token == 1:                                  # a node begins
            end = blob.index(b"\0", p)
            node = {"props": {}, "kids": {}}
            if stack:
                stack[-1]["kids"][blob[p:end].decode()] = node
            else:
                root = node
            stack.append(node)
            p = (end + 4) & ~3
        elif token == 2:                                # a node ends
            stack.pop()
            if not stack:
                return root
        elif token == 3:                                # a property
            size, name = struct.unpack_from(">II", blob, p)
            p += 8
            end = blob.index(b"\0", off_strings + name)
            stack[-1]["props"][blob[off_strings + name:end].decode()] = blob[p:p + size]
            p = (p + size + 3) & ~3
        elif token == 9:
            return root


def walk(node):
    yield node
    for kid in node["kids"].values():
        yield from walk(kid)


def text(v):
    return v.rstrip(b"\0").decode(errors="replace") if v is not None else ""


def cell(v):
    return struct.unpack(">I", v[:4])[0] if v and len(v) >= 4 else None


def read_tree(path):
    """What the system needs to know from one device tree."""
    tree = parse(open(path, "rb").read())
    info = {"model": text(tree["props"].get("model")), "sizes": set(), "pads": [], "codes": set(), "hat": False, "power": set()}
    for node in walk(tree):
        compatible = set(text(node["props"].get("compatible")).split("\0"))
        if any("joypad" in c for c in compatible):
            info["pads"].append(text(node["props"].get("joypad-name")))
            info["hat"] = info["hat"] or any("hid" in c for c in compatible)
            for kid in node["kids"].values():
                code = cell(kid["props"].get("linux,code"))
                if code is not None:
                    info["codes"].add(code)
        if "hactive" in node["props"] and "vactive" in node["props"]:
            info["sizes"].add((cell(node["props"]["hactive"]), cell(node["props"]["vactive"])))
        info["power"] |= compatible & POWER
    return info


def check(consoles):
    rows, problems = [], []
    for kernel, image in (("5.10", "kernel/5.10/Image"), ("4.4", "kernel/original/Image")):
        if not os.path.isfile(os.path.join(consoles, image)):
            problems.append(f"no {kernel} kernel: {image}")
    names = sorted(n for n in os.listdir(consoles) if os.path.isfile(os.path.join(consoles, n, "boot.ini")))
    with tempfile.TemporaryDirectory() as scratch:
        # the selector works on a boot partition: a folder with "consoles" in it
        os.symlink(os.path.abspath(consoles), os.path.join(scratch, "consoles"))
        for name in names:
            folder = os.path.join(consoles, name)
            bad = lambda what: problems.append(f"{name}: {what}")
            ini = open(os.path.join(folder, "boot.ini"), errors="replace").read()
            dtbs = sorted(f for f in os.listdir(folder) if f.endswith(".dtb") and not f.startswith("._"))
            if len(dtbs) != 1:
                bad(f"{len(dtbs)} device trees, expected 1")
                continue
            dtb = dtbs[0]
            if "root=/dev/mmcblk0p2" not in ini:
                bad("boot.ini does not start the system from /dev/mmcblk0p2")
            if set(re.findall(r"^load mmc (\S+)", ini, re.M)) != {"1:1"}:
                bad("boot.ini does not load its files from mmc 1:1")
            turn = re.search(r"fbcon=rotate:(\d)", ini)
            turn = int(turn.group(1)) if turn else 0
            row = {"console": name, "turn": turn, "kernels": []}
            for kernel, path in (("5.10", os.path.join(folder, "5.10", dtb)), ("4.4", os.path.join(folder, dtb))):
                if not os.path.isfile(path):
                    bad(f"no {kernel} device tree")
                    continue
                try:
                    info = read_tree(path)
                except (ValueError, struct.error, IndexError) as e:
                    bad(f"{kernel} device tree cannot be read: {e}")
                    continue
                if len(info["sizes"]) != 1:
                    bad(f"{kernel}: {len(info['sizes'])} panel sizes in the device tree, expected 1")
                    continue
                if info["pads"] != [PAD_NAME]:
                    bad(f"{kernel}: built-in pad is {info['pads']}, not [{PAD_NAME!r}]")
                missing = [label for code, label in BUTTONS.items() if code not in info["codes"]]
                if missing:
                    bad(f"{kernel}: the pad has no {', '.join(missing)}")
                if not DPAD <= info["codes"] and not info["hat"]:
                    bad(f"{kernel}: the direction pad is neither four keys nor a hat")
                if not info["power"]:
                    bad(f"{kernel}: no RK817 or RK809 power chip")
                # the selector must make, from this folder, a boot.ini that starts this system
                p = subprocess.run(["bash", SELECT, "-b", scratch, "set", name, kernel], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                made = open(os.path.join(scratch, "boot.ini")).read() if p.returncode == 0 else ""
                if p.returncode != 0:
                    bad(f"{kernel}: rk-boot-select: {p.stdout.strip()}")
                elif "uInitrd" in made or f"load mmc 1:1 ${{dtb_loadaddr}} {dtb}" not in made or "booti ${loadaddr} - ${dtb_loadaddr}" not in made:
                    bad(f"{kernel}: the boot.ini rk-boot-select made would not start")
                w, h = next(iter(info["sizes"]))
                row.update(model=info["model"], panel=(w, h), size=(h, w) if turn in (1, 3) else (w, h),
                           dpad="keys" if DPAD <= info["codes"] else "hat", power=sorted(info["power"])[0].split(",")[1].upper())
                row["kernels"].append(kernel)
                for f in os.listdir(scratch):
                    if f != "consoles":
                        os.remove(os.path.join(scratch, f))
            if "size" in row:
                rows.append(row)
    return rows, problems


def table(rows, commit):
    sizes = sorted({r["size"] for r in rows}, key=lambda s: (-s[0] * s[1], s))
    out = ["# Handhelds", "",
           "One image, every RK3326 handheld [arkos4clone](https://github.com/lcdyk0517/arkos4clone) supports: "
           f"{len(rows)} of them. The card holds the boot files of all of them; which one it starts on is chosen on the "
           "boot partition (`Choose handheld.command`, or three files copied by hand: see `README.txt` there), "
           "or on the handheld with `sudo rk-boot-select set \"<folder>\" 5.10`.", "",
           "This table is written by `build/check-consoles.py` from the device trees at the pinned arkos4clone commit"
           + (f" (`{commit[:7]}`)" if commit else "") + ". The build runs the same check on every push: each handheld's "
           "boot files, screen, pad and power chip are read and held against what the system expects, and the desktop is "
           "drawn at every screen size in the list (" + ", ".join(f"{w}×{h}" for w, h in sizes) + ").", "",
           "**Checked is not the same as started.** \"On hardware\" says where a person has started the image and used it. "
           "Everywhere else the files have been checked and nothing more: expect to be the first, and please report.", "",
           "| Folder | Handheld | Screen | Panel turned | Direction pad | Power chip | Kernels | On hardware |",
           "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        turned = "no" if not r["turn"] else f"{r['turn'] * 90}° ({r['panel'][0]}×{r['panel'][1]} panel)"
        out.append(f"| `{r['console']}` | {r['model']} | {r['size'][0]}×{r['size'][1]} | {turned} | {r['dpad']} | {r['power']} | "
                   f"{', '.join(r['kernels'])} | {ON_HARDWARE.get(r['console'], 'not yet')} |")
    out += ["", "## What is the same on all of them, and what is not", "",
            "- **Desktop, tools, Terminal, Wi-Fi, updates**: one system, laid out for the screen it finds. A panel mounted on "
            "its side is turned the way the kernel is told to turn the text console; if a picture still comes out sideways, "
            "a file `rotate.txt` on the boot partition holding 0, 1, 2 or 3 sets it by hand.",
            "- **Buttons**: every handheld in the list reports the same pad with the same button codes. The RG351P and RG351V "
            "send their direction pad as a hat; the desktop reads both.",
            "- **Dock apps, Video and Games** draw through the GPU, not through the desktop, and are turned there, the way "
            "arkos4clone and dArkOS do it: SDL programs (the dock apps, Video's player) load the SDL2 built for the panel's "
            "turn, and Games uses RetroArch's driver for turned RK3326 panels. Both turn the picture with the Rockchip 2D "
            "chip (librga). `rotate.txt` sets these too.",
            "- **Sound, charging, brightness**: the fixes in `build/dtb-fixes.txt` are for the R36MAX (type 1) only, found on "
            "one. Other handhelds run arkos4clone's device tree as it is.",
            "- **Left-stick pointer**: needs a left stick. Without one the direction pad does everything.",
            "- **Boards on USB serial (ESP32 and the like)**: on kernel 5.10, the chips these boards use all get a serial port (`/dev/ttyUSB0`, or `/dev/ttyACM0`): CP210x, FTDI, PL2303, and the CH340/CH341 of most ESP32 boards (a Freenove ESP32-WROVER, for one). arkos4clone's 5.10 kernel is built without the CH340 driver (`ch341`), so the image adds it, built from that kernel's source (`build/kernel-modules.env`). It comes with a flashed image, not with **Update this handheld**, which leaves the kernel's files alone. On the 4.4 fallback kernel a CH340 board gets no serial port; the Provisioner still reaches it there, driving the chip itself.", ""]
    return "\n".join(out)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    rows, problems = check(args[0])
    if "--sizes" in sys.argv:
        for w, h in sorted({r["size"] for r in rows}):
            print(f"{w}x{h}")
        return 1 if problems else 0
    if "--table" in sys.argv:
        commit = ""
        env = os.path.join(HERE, "upstream.env")
        if os.path.isfile(env):
            m = re.search(r"^UPSTREAM_COMMIT=(\w+)", open(env).read(), re.M)
            commit = m.group(1) if m else ""
        open(sys.argv[sys.argv.index("--table") + 1], "w").write(table(rows, commit))
    turned = sum(1 for r in rows if r["turn"])
    print(f"{len(rows)} handhelds, {sum(len(r['kernels']) for r in rows)} boot selections, "
          f"{len({r['size'] for r in rows})} screen sizes, {turned} with the panel turned, "
          f"{sum(1 for r in rows if r['dpad'] == 'hat')} with a hat for a direction pad")
    for p in problems:
        print("PROBLEM:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
