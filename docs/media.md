# Video and Games

Two things people expect from a handheld that the security tools do not
cover: watching a video and playing their own games. Both use the same road
to the screen as the other dock apps (SDL2 on dArkOS's Mali driver), and
both leave with **SELECT+START**.

> **Status: new, and not yet proven on a handheld.** The desktop side is
> tested in CI with made-up data. Playing a video and starting RetroArch on
> the panel have to be confirmed on an R36MAX before a release says they work.

## Video

![The Video window](video.png)

**Video** on the dock searches YouTube and plays the result.

| In the window | |
|---|---|
| X | search (the on-screen keyboard, or a USB keyboard) |
| A | play the chosen result |
| Y | update: the newest yt-dlp, and anything missing |

| In the player | |
|---|---|
| A | pause / play |
| LEFT, RIGHT | 10 seconds back / on |
| UP, DOWN | 1 minute on / back |
| L1, R1 | 5 minutes back / on |
| X | show where you are |
| B, or SELECT+START | stop |

The volume keys work as everywhere.

**How it works.** `rk-video` asks [yt-dlp](https://github.com/yt-dlp/yt-dlp)
for the results and hands the chosen one to `mpv`. The picture is asked for
in H.264 at 480 lines at most (360 on a 640x480 panel), because this
processor decodes video in software and H.264 is by far the lightest.

**yt-dlp is not Debian's.** YouTube changes often and only a recent yt-dlp
keeps up, so `rk-video fetch` (Y in the window) takes the official one from
its releases, checks it against the release's SHA-256 list, and keeps it in
`~/.local/share/rk-video`. Since late 2025 yt-dlp also needs a JavaScript
runtime for YouTube; the image carries QuickJS (`qjs`) for that, and deno is
used when you install it yourself. **When videos stop playing, press Y
first.**

**On a card flashed before this was in the image**, open Video and press A:
it installs the player and RetroArch from Debian and fetches yt-dlp. The
same from a terminal:

    sudo rk-tools install-media
    rk-video fetch

**From a terminal:**

    rk-video status
    rk-video search lora antenna
    rk-video play https://www.youtube.com/watch?v=...
    rk-video play ~/clip.mp4

**Settings** (optional), in `~/.config/rk-video`:

    VO=sdl        # mpv's video output: sdl (default), drm, gpu
    HEIGHT=480    # the tallest picture asked from YouTube

What mpv said the last time is in `~/.cache/rk-video/last.log`.

## Games

**Games** on the dock is [RetroArch](https://www.retroarch.com/) with the
cores Debian packages that this processor can carry:

| Machine | Core | Folder |
|---|---|---|
| NES | Nestopia | `nes` |
| Super NES | Snes9x | `snes` |
| Game Boy, Game Boy Color | Gambatte | `gb`, `gbc` |
| Game Boy Advance | mGBA | `gba` |
| Mega Drive, Master System, Game Gear | Genesis Plus GX | `megadrive`, `mastersystem`, `gamegear` |
| PC Engine | Beetle PCE Fast | `pcengine` |

**No game and no BIOS file comes with the system.** Copy your own into
`/data/ark/roms/<folder>` (over SFTP, or from a USB stick with Files). The
folders are made the first time Games is opened, and they are on the data
partition, so a reflash keeps them along with saves and save states.

In RetroArch: **Load Content**, pick the file, then the core when asked.
**SELECT+START leaves. Both sticks pressed in open the menu** (save states,
options).

The handheld's own settings are in `/usr/share/rk/retroarch/rk.cfg` and are
applied over yours at every start (the SDL2 picture and pad, ALSA sound, the
folders, the two button combinations). Everything else you change in
RetroArch is kept in `~/.config/retroarch/retroarch.cfg`.

**Not there yet:** Nintendo 64, Dreamcast, PSP and PlayStation. Those need a
RetroArch and cores built for this GPU's driver, which Debian's are not;
that is a build of our own, for a later release.
