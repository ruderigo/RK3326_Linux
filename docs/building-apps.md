# Building apps for RK3326 Linux

This is the contract for Team r36max and anyone putting an app on the
handheld's dock — FireFly, Stump and Ember follow it, and so does any app you
add on top of this image or another build of it. It describes how an app
announces itself, how it gets the screen and the controls, how sound reaches
it, how two apps stay out of each other's way, and how updates are delivered.
Nothing here is specific to one app: if a program obeys this contract it runs.

The short version: **an app is any program on the handheld, plus one small
JSON file that puts it on the dock.** Everything else is about drawing on
this particular screen and sharing this particular hardware.

- [The dock entry](#the-dock-entry)
- [Getting the screen (the GPU/SDL contract)](#getting-the-screen)
- [Controls](#controls)
- [Sound](#sound)
- [Two apps at once, and taking turns](#coexistence)
- [Setup flows and "needs"](#setup-and-needs)
- [Icons](#icons)
- [Shipping updates through rk-apps](#updates)
- [Where files live](#where-files-live)
- [Baking an app into the image](#baking-in)
- [Checklist](#checklist)

<a name="the-dock-entry"></a>
## The dock entry

The desktop reads every `*.json` file in these two folders and makes one dock
icon per file:

- `/usr/share/rk/apps/` — baked into the image (this repo's
  `overlay/usr/share/rk/apps/`).
- `/data/ark/apps/` — on the data partition, so an app can drop its own entry
  at install time without a rebuild.

A minimal entry is a name and a program:

```json
{"name": "FireFly", "icon": "firefly", "group": "Comms",
 "about": "Messages over LoRa and Wi-Fi",
 "exec": ["/home/ark/firefly/deploy/FireFly.sh"]}
```

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | Shown on the dock and in windows. |
| `exec` | yes | The program and its arguments, as a list. The desktop runs it directly (no shell), waits for it, and returns to the dock when it exits. `exec[0]` is an absolute path or a command on `PATH`. |
| `icon` | no | One of the built-in [glyphs](#icons). Anything else (or omitted) shows the first letter of the name. |
| `group` | no | Groups and sorts the dock (`"Comms"`, `"Audio"`, …). |
| `about` | no | One line, shown with the entry. |
| `before` / `after` | no | A command (as a list) run just before the app starts and just after it exits. See [coexistence](#coexistence). |
| `setup` / `needs` | no | A first-run setup flow. See [setup and "needs"](#setup-and-needs). |

**Readiness.** If `exec[0]` is not found on the handheld, the icon is dimmed
and labelled *not installed* — so an entry can ship in the image before the
program does, and light up once it is installed. The build (`build-image.sh`)
checks that every baked-in JSON is valid and has a `name` and an `exec`.

That's the whole dock contract. The rest of this document is about making the
program itself behave on the hardware.

<a name="getting-the-screen"></a>
## Getting the screen

The panel only shows what goes through the Mali GPU driver. The desktop draws
its own way (into memory, then to `/dev/fb0`), but **an app the dock launches
must render with dArkOS's Mali driver and the SDL2 built against it.** The
desktop sets the environment up for you before it runs `exec`:

- `LD_LIBRARY_PATH` starts with `/usr/lib/rk-gpu`, which holds `libmali.so`
  (this G31 GPU's driver), the matching `libSDL2-2.0.so.0`, and
  `libEGL.so.1` / `libGLESv2.so.2` / `libgbm.so.1` symlinked onto libmali.
- `SDL_VIDEODRIVER=kmsdrm`.
- `SDL_GAMECONTROLLERCONFIG_FILE=/usr/share/gamecontrollerdb.txt` (puts SELECT
  and START where they are on this pad).
- The desktop's **own** `SDL_*` variables are stripped first, so its headless
  "dummy" driver can't leak in and give your app a black screen.

What this means for your app:

- **Use SDL2 (or pygame/anything on SDL2).** Link the system SDL2; at launch
  `LD_LIBRARY_PATH` makes it dArkOS's build. Do not bundle your own `libSDL2`
  or your own `libEGL`/`libGLES`/`libgbm` — they will not scan out to this
  panel. Ember is a C/SDL2 app; FireFly and Stump are pygame.
- **Don't set `SDL_VIDEODRIVER` yourself.** Inherit `kmsdrm` from the
  environment. Forcing `dummy`, `x11`, `wayland`, `fbcon` or `directfb` gives
  a black screen or a crash.
- The screen is **720×720**. Draw for a square.
- A udev rule (`70-mali-dma-heap.rules`) lets the `video` group reach the GPU
  memory heap; without it SDL fails with *EGL not initialized*. It is in the
  image already — only relevant if you build your own.

If your app crashes on the way out it can leave the panel blanked; the desktop
turns it back on when it regains control (`FBIOBLANK 0`), so a clean or a
crashed exit both return to the dock.

You can develop the app anywhere SDL2 runs (a desktop Linux box, X or
Wayland) and only need the handheld to test it against the real panel.

<a name="controls"></a>
## Controls

The gamepad is a standard SDL game controller through the bundled
`gamecontrollerdb.txt`, so SDL's `SDL_GameController` API gives you A/B/X/Y,
the d-pad, the sticks, the shoulder buttons, and SELECT/START in the usual
places.

Two conventions the desktop relies on:

- **SELECT+START quits.** There is no window manager; the app owns the screen
  while it runs. Handle SELECT+START (or let your framework do it) as "quit
  and return to the dock". FireFly and Stump do; Ember uses SELECT+START too.
- **The volume keys are not yours.** While an app runs the desktop is paused
  but still watches the two volume keys (evdev codes 114 and 115) and adjusts
  the system volume itself. Every other key is the app's. You don't need to
  handle volume, and shouldn't grab those keys exclusively.

A USB keyboard also works and is the easy way to develop and debug.

<a name="sound"></a>
## Sound

Routing is handled for the whole system by a small service, `rk-audiod`, so an
app should **open the ALSA `default` device and nothing else**:

- `default` is wired (via `/etc/asound.conf`, rewritten by `rk-audiod`) to the
  USB headset or microphone while one is plugged in, and to the built-in chip
  otherwise. The built-in chip is shared through `dmix`/`dsnoop` at 44100 Hz,
  so two programs can play at once and the volume keys keep working.
- The 3.5 mm jack is switched between speaker and headphones by the service.
- **Do not hardcode `hw:0,0` or `plughw:0,0`.** That bypasses routing: it
  pins you to the built-in chip, ignores the headset, can't share, and makes
  the jack behave wrongly. Ember historically forced `plughw:0,0` and so does
  not follow a USB mic — that is the bug this rule avoids.
- For a microphone, open the `default` capture device. The **Sound** window on
  the dock is the reference: if it records your mic and your app doesn't, your
  app is opening its own device instead of `default`.
- If you genuinely must target a specific device (a diagnostic), read
  `/run/rk-audio/status` (JSON) to see what `rk-audiod` chose, rather than
  guessing a card number.

<a name="coexistence"></a>
## Two apps at once, and taking turns

Some hardware can only belong to one program at a time. The clearest case:
FireFly and Stump both use Reticulum's AutoInterface, which binds **UDP port
29716**, and only one process can hold it. So they must not run at once.

The mechanism is the `before`/`after` hooks on the dock entry. FireFly's entry
pauses the Stump before it starts and resumes it after it quits:

```json
"before": ["/usr/local/bin/rk-stump-pause", "pause"],
"after":  ["/usr/local/bin/rk-stump-pause", "resume"]
```

`rk-stump-pause` stops and restarts the Stump's background service. Opening
the Stump's own window needs no hook, because FireFly is closed by then.

The pattern generalises: if your app needs sole use of something another app
holds, stop that thing in `before` and restart it in `after`. The hooks are
command lists, run with a 30-second timeout; a missing or failing hook is
skipped quietly, so never rely on a hook for correctness inside your app —
it's for being a good neighbour.

<a name="setup-and-needs"></a>
## Setup flows and "needs"

An app that needs first-run configuration can declare it:

- `needs` is a file, or a list of files, that exist only once the app's setup
  has completed (`~` is expanded). While any is missing, the dock shows the
  entry as needing setup.
- `setup` names a setup screen built into the desktop. Today the only one is
  `"stump"` (the Stump's provisioning wizard: chain, secret, radio, storage
  size, and the handheld's password). The Stump entry uses both:

```json
"setup": "stump",
"needs": ["~/Stump/stump_pc.py", "~/stump_r36max/stump_r36max_engine"]
```

Setup screens live in the desktop code (`shell/rkshell/pages/`, registered in
`app.py`'s `SETUPS`), so adding a *new* one is a change to this repo, not
something a third-party app drops in. If your app can configure itself on
first launch instead, prefer that and skip `setup`. `needs` on its own is
still useful: it keeps the icon honestly labelled until the app's files are
actually in place.

<a name="icons"></a>
## Icons

`icon` picks a vector glyph drawn by the desktop. The ones that suit apps are
`firefly`, `stump`, `ember`, `sound` and `chip` (a generic one); the rest
(`radar`, `survey`, `files`, `network`, `devices`, `settings`, `terminal`,
`update`) belong to the built-in windows. Any unknown name falls back to the
first letter of the app's name, which is a fine placeholder.

A new glyph is a small function in `shell/rkshell/desktop.py` (added to the
`GLYPHS` table) that draws into a 192×192 surface in one colour — a pull
request to this repo. Until then, use `chip` or the letter fallback.

<a name="updates"></a>
## Shipping updates through rk-apps

`rk-apps` installs, versions and updates the three apps, over Wi-Fi, into
`/home/ark`. It is also how the image bakes them in at build time. Supporting
it is optional for a brand-new app, but it's how FireFly, Stump and Ember stay
current, and the pattern is worth matching.

Two pieces make an app updatable:

**1. A readable version.** `rk-apps versions` compares an installed version
against the newest published one. The three apps expose "newest" differently:

- **FireFly** — `__version__` in `firefly/firefly/__init__.py` on the repo's
  `main` branch. (FireFly also has a **sandbox** source — the
  `SandBox_FireFly_RK3326` repo, where a version lands first; `rk-apps source
  firefly stable|sandbox`, or **Y** on FireFly's row in the Apps window,
  switches.)
- **Stump** — a `handheld/VERSION` file on `main`.
- **Ember** — the tag of its latest GitHub release (its binary is only built
  for releases); the installed version is recorded in `~/ports/ember/.rk-version`.

Pick whichever fits how you release, and keep it somewhere `rk-apps` can read
without cloning the whole repo.

**2. An installer that keeps data.** `rk-apps install`/`update` runs the app's
own installer so the app decides what to preserve. The shared conventions:

- A **`deploy/install.sh`** (FireFly) or an **`install.sh`** (Stump) at a
  predictable place in the release, re-runnable without wiping user data.
- Root steps go through **sudo's askpass helper**: when there's no terminal
  (launched from the desktop), the password arrives via `SUDO_ASKPASS` and
  `sudo -A`. **Never read the password from stdin (`sudo -S`)** — the desktop
  can't answer that. Over SSH, sudo just prompts normally.
- A wizard-style installer should accept **non-interactive answers** —
  Stump's takes `install.sh --answers FILE.json`, keyed by each question's
  text up to the `?` — so the desktop's setup screen can drive it. A plain
  app that needs no questions can ignore this.

If an app does none of this, it still runs from the dock; it just won't appear
in the Apps window's version list, and it's updated by re-running its own
installer by hand.

<a name="where-files-live"></a>
## Where files live

| Path | For |
|---|---|
| `/home/ark/<App>/` | the app itself (owned by `ark`). FireFly: `/home/ark/firefly`. Stump: `/home/ark/R36MAX-Stump`. |
| `/home/ark/ports/` | ports-style apps (Ember: `/home/ark/ports/Ember.sh`). |
| `/roms/ports/<app>/` | a port's working/drop folders. |
| `/data/ark/` | user data on the data partition (survives reflashing). `/data/ark/apps/` for a dock entry added at install time. |
| `/data/opt/` | large optional payloads (Exploit-DB lives here). |
| `/usr/lib/rk-gpu/` | the GPU driver and SDL2 the launcher puts on `LD_LIBRARY_PATH`. Read-only; don't ship your own copies. |

The handheld runs as user **`ark`**. Install into `ark`'s home, not root's.

<a name="baking-in"></a>
## Baking an app into the image

To ship an app on the card (as FireFly, Stump and Ember are):

1. Put its dock JSON in `overlay/usr/share/rk/apps/`.
2. Make `rk-apps install <app>` fetch and install it (add an `install_<app>`
   path in `overlay/usr/local/sbin/rk-apps`).
3. In `build/build-image.sh`, call `rk-apps install <app>` in the "dock apps"
   step (it runs as `ark`), and add any folders the app needs.
4. If first-boot state matters, remember the fresh card's `ark` account starts
   with an **expired** password: user services (`systemd --user`) won't run
   until the password is changed, so don't rely on a user service at first
   boot — the app's own setup turns things on after the password is set.

An app that is only *offered* (fetched later over Wi-Fi) needs just step 1 and
a working `rk-apps install`.

<a name="checklist"></a>
## Checklist

- [ ] A JSON dock entry with `name` and `exec`; valid JSON.
- [ ] Renders with SDL2; inherits `kmsdrm` and `LD_LIBRARY_PATH`; bundles no
      GPU/SDL libraries; draws for 720×720.
- [ ] Quits on SELECT+START; doesn't grab the volume keys.
- [ ] Opens the ALSA `default` device; no `hw:0,0`.
- [ ] If it shares a single-owner resource, a `before`/`after` hook stops and
      restarts the other user.
- [ ] Installs under `/home/ark` as `ark`; data under `/data`.
- [ ] (Optional) a readable version and a re-runnable installer that honours
      `SUDO_ASKPASS`, so `rk-apps` can update it.

Questions, or a glyph/setup-screen you need added to the desktop, are a pull
request or an issue on this repo.
