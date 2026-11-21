# The dock apps: FireFly, Stump, Ember

These three are your own programs ported onto the desktop. They are not baked
into the image (each is large and wants its own setup), so they show on the
dock as **(not installed)** until you fetch them. Each is a full-screen app:
when you open it the desktop steps aside and comes back when you quit it (for
FireFly and Stump, SELECT+START returns).

Fetch them over Wi-Fi from the Terminal:

    rk-apps install all        # or: ember | firefly | stump
    rk-apps status

They install under `/home/ark`, where the dock's launchers look, so the icons
light up once each is in place. A USB keyboard helps with all three.

## Ember — analog pads and a vocoder

A prebuilt arm64 binary, so this is the simplest: `rk-apps install ember`
unpacks it into `/home/ark/ports`. It uses SDL2 and ALSA, which are in the
image. Audio comes out of the USB-C port (the jack's left channel is a
hardware fault on this handheld). To rebuild from source instead:
`sudo apt install build-essential libsdl2-dev libsdl2-ttf-dev libasound2-dev`
then run its `Ember.sh`, which compiles once.

## FireFly — messages over LoRa and Wi-Fi

`rk-apps install firefly` downloads the latest release and runs FireFly's own
installer, which makes a Python virtual environment in `/home/ark/firefly` and
pulls Reticulum (`rns`/`lxmf`) from pip — so the first install needs internet.
The packages it depends on (python3-venv, python3-serial, python3-cryptography,
opus-tools, codec2) are already in the image. Plug an RNode LoRa board into USB
for the radio; it also works over Wi-Fi/LAN without one.

## Stump — this handheld as a mesh node

The Stump's files are in the image, but its setup is yours to answer: its
name, its password, whether it is part of a chain, and its radio. Until that
is done, the dock shows it as **Stump (set up)** and opens a setup window in
place of the cockpit:

![Stump setup](stump-setup.png)

Fill it in with the gamepad and press START. The window hands the answers to
the Stump's own installer (`R36MAX-Stump/handheld/install.sh --answers`, the
same way the RK3326 Provisioner drives it) and shows its progress. It needs
Wi-Fi, takes a few minutes, and asks for this handheld's password because the
installer needs root for a few steps. The password goes to `sudo` and is not
kept; the answers file is removed when the installer ends.

The window covers a Stump on its own, the first Stump of a chain, or one
that joins another Stump on the Wi-Fi the handheld is on. For anything else
(Bluetooth radio, joining a Stump's own hotspot), run the installer in the
Terminal: `bash ~/R36MAX-Stump/handheld/install.sh`.

## How they get the screen

The panel only shows what goes through the Mali GPU driver, so the image
carries dArkOS's own graphics: its Mali driver (`libmali`, for this G31 GPU)
and the SDL2 it builds against it, in `/usr/lib/rk-gpu`, plus its controller
database in `/usr/share/gamecontrollerdb.txt` (SELECT and START in the right
place on this pad). The desktop gives these to every app it opens; the
desktop itself keeps drawing its own way. A udev rule lets the `video` group
reach the GPU's memory heap, without which apps fail with
"EGL not initialized".

While an app runs it owns the screen, as a port does under EmulationStation,
and the desktop comes back when it quits. If an app crashes on its way out,
the desktop turns the panel back on itself. By hand, the same is
`echo 0 | sudo tee /sys/class/graphics/fb0/blank`.

## FireFly and Stump take turns

Both run Reticulum, and Reticulum's local-network discovery (UDP port 29716)
can belong to only one program on a machine. So while FireFly is open, the
Stump pauses (`rk-stump-pause`, run by the dock before and after FireFly),
and it comes back when you quit FireFly. Opening Stump's cockpit needs
nothing: FireFly is closed then.

## Tested

On an R36MAX, all three open from the dock, draw, take the gamepad, and quit
back to the desktop with SELECT+START; Stump pauses for FireFly and resumes.
Still open: Ember makes no sound yet, and an app can leave the display's
hardware cursor frozen over the desktop after it quits (a reboot clears it).
