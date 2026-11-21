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

Stump is only **cloned** by `rk-apps install stump`, to `/home/ark/R36MAX-Stump`.
Its installer does more than a normal app: it runs a Stump server in the
background from boot, binds ports 80 and 53, and sets up a captive DNS for its
own hotspot. That is invasive enough that you should run it yourself, once you
have decided it suits this machine:

    bash ~/R36MAX-Stump/handheld/install.sh

It was written for dArkOS with EmulationStation; on this OS expect to adjust
paths (it uses `/roms/ports`) and the launcher. This is the one that will need
the most hands-on work.

## Caveat

None of this is tested on the handheld yet. The dock entries, the shared
packages, and the Ember and FireFly fetches are wired and ready to try; how
each program's own screen and input behave through the desktop's hand-off, and
Stump's setup on this OS, are what to check on the device.
