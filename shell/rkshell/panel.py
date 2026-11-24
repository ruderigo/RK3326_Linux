"""How the panel is mounted, and what turns the picture for each kind of program.

Some RK3326 handhelds have their panel on its side or upside down. The
kernel is told on its command line (fbcon=rotate:N, quarter turns clockwise),
and three things have to follow it:

  the desktop        turns its own frames (backends/device.py)
  SDL programs       dock apps, and Video's player: arkos4clone's builds of
                     SDL2, one per turn, which turn the picture with the
                     Rockchip 2D chip (librga) as it goes to the screen
  Games (RetroArch)  its own driver for turned RK3326 panels, told the turn
                     in RK_ROTATE

Standard library only: rk-video uses this too, without the desktop.
"""
import glob
import os

ROTATE_FILE = "/boot/rotate.txt"        # the owner's own answer, when the kernel's is wrong for a panel
GPU_DIR = "/usr/lib/rk-gpu"             # dArkOS's Mali driver and SDL2 (build-image.sh); turn1..3: the turned SDL2s
RGA = "/usr/lib/*/librga.so.2"          # what the turned SDL2s and RetroArch's driver turn the picture with


def _read(path):
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def screen_rotation(cmdline, override=""):
    """Quarter turns clockwise the picture needs (0 to 3), as the text console
    is told: fbcon=rotate:N on the kernel command line. A digit in `override`
    (the text of /boot/rotate.txt) comes first."""
    for word in override.split()[:1]:
        if word in ("0", "1", "2", "3"):
            return int(word)
    for word in cmdline.split():
        if word.startswith("fbcon=rotate:") and word[13:14] in ("0", "1", "2", "3"):
            return int(word[13])
    return 0


def turn():
    """This handheld's quarter turns clockwise."""
    return screen_rotation(_read("/proc/cmdline"), _read(ROTATE_FILE))


def library_path(quarter_turns=None, gpu_dir=GPU_DIR, rga=RGA):
    """The folders a program that draws through the GPU loads its libraries
    from, first one first: the SDL2 for this panel's turn, then dArkOS's Mali
    driver. A turned SDL2 is only named when it can load (it needs librga):
    a picture on its side is better than a program that does not start."""
    if not os.path.isdir(gpu_dir):
        return []
    n = turn() if quarter_turns is None else quarter_turns
    turned = os.path.join(gpu_dir, f"turn{n}")
    if n and os.path.isfile(os.path.join(turned, "libSDL2-2.0.so.0")) and glob.glob(rga):
        return [turned, gpu_dir]
    return [gpu_dir]


def app_environment(env, quarter_turns=None, gpu_dir=GPU_DIR, rga=RGA):
    """`env` with what a GPU program needs for this panel added: the library
    folders in front of LD_LIBRARY_PATH, and the turn for RetroArch."""
    n = turn() if quarter_turns is None else quarter_turns
    ours = library_path(n, gpu_dir, rga)
    if ours:
        rest = [p for p in env.get("LD_LIBRARY_PATH", "").split(":") if p and p not in ours and not p.startswith(gpu_dir)]
        env["LD_LIBRARY_PATH"] = ":".join(ours + rest)
    env["RK_ROTATE"] = str(n)
    return env
