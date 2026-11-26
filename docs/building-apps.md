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
- [The pointer (the left stick is a mouse)](#the-pointer)
- [Sound](#sound)
- [Two apps at once, and taking turns](#coexistence)
- [Setup flows and "needs"](#setup-and-needs)
- [Icons](#icons)
- [Shipping updates through rk-apps](#updates)
- [Where files live](#where-files-live)
- [Baking an app into the image](#baking-in)
- [Packages: an app that installs itself](#packages)
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
| `mouse` | no | `false`: the left stick is not a mouse while this app runs. See [the pointer](#the-pointer). |
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

<a name="the-pointer"></a>
## The pointer (the left stick is a mouse)

The handheld has no touchscreen, so the system gives every program a mouse:
a service, `rk-mouse`, reads the left stick and presents a virtual mouse
(a uinput device named **`rk-mouse`**). The desktop draws its own pointer from
it. **Your app receives it too**, as an ordinary mouse, whether you asked for
one or not. Know these four things:

**1. What your app sees.** While the mouse is on (it is by default):

| On the pad | As a mouse | In SDL |
|---|---|---|
| Left stick | relative movement (`REL_X`, `REL_Y`) | `SDL_MOUSEMOTION` |
| R2 | left button (`BTN_LEFT`) | `SDL_MOUSEBUTTONDOWN/UP`, `SDL_BUTTON_LEFT` |
| L2 | right button (`BTN_RIGHT`) | `SDL_BUTTON_RIGHT` |
| R1 / L1 | wheel up / down (`REL_WHEEL`) | `SDL_MOUSEWHEEL` |

A USB mouse plugged into the handheld arrives the same way, as a second
mouse. The user can change the speed and the button map in
`/data/ark/rk-mouse.json`, so don't assume R2 is the click; just handle the
mouse events.

**2. The pad still reports everything.** The mouse is *in addition to* the
gamepad, not instead of it: a push on the left stick is both a
`SDL_CONTROLLERAXISMOTION` and a `SDL_MOUSEMOTION`, and R2 is both a trigger
and a left click. So an app must pick one meaning for each:

- **An app that wants a pointer** (a map, a drawing tool, anything with
  buttons to hit): use the mouse events, and ignore the left stick and the
  triggers as controller input.
- **An app that uses the left stick or the triggers itself** (Ember's pads, a
  game): either ignore mouse events entirely, or put `"mouse": false` in the
  dock entry. With that, the desktop switches the stick's mouse off before it
  starts your app and back on when it quits, and you get the pad alone. This
  is the right choice whenever a stray click could do something in your app.

**3. Draw your own pointer.** Only the desktop's pointer is drawn by the
system, and the desktop is paused while your app has the screen. Under
`kmsdrm` do not count on SDL's cursor being visible on this panel: keep the
position yourself (start from `SDL_GetMouseState`, or add up the `xrel`/`yrel`
of each motion event), draw a small sprite there, and call
`SDL_ShowCursor(SDL_DISABLE)` so a hardware cursor is never left behind on the
screen when you quit. If your app has no use for a pointer, call
`SDL_ShowCursor(SDL_DISABLE)` and ignore the events.

**4. Follow the desktop's manners,** so the handheld feels like one system:
hide the pointer after about three seconds without movement and as soon as
the d-pad is used; keep everything reachable with the d-pad and A as well
(the user may have the mouse switched off); and when the pointer is showing,
act on what it points at, never on something selected elsewhere.

**On or off.** The user switches the mouse in **Settings → Left-stick mouse**,
or with SELECT + a click of the left stick, at any time, including while your
app runs. The state is the file `/run/rk-mouse/on` (`1` or `0`; missing means
on). Read it if you want to show a hint; off means the virtual mouse sends
nothing. Don't write it from your app: use `"mouse": false`. Never grab the
pad or the `rk-mouse` device exclusively (`EVIOCGRAB`), or the pointer and the
volume keys stop working for everyone.

Outside SDL, the mouse is a normal evdev device: find the `/dev/input/event*`
whose name is `rk-mouse` (or read every device that reports `REL_X`), and
under X it is picked up as any mouse is.

<a name="sound"></a>
## Sound

Routing is handled for the whole system by a small service, `rk-audiod`, so an
app should **open the ALSA `default` device and nothing else**:

- `default` is wired (via `/etc/asound.conf`, rewritten by `rk-audiod`) to the
  USB headset or microphone while one is plugged in, and to the built-in chip
  otherwise. Playback on the built-in chip is shared through `dmix` at
  44100 Hz, so two programs can play at once and the volume keys keep working.
  A USB sound device is not shared: one program plays through it at a time.
- The 3.5 mm jack is switched between speaker and headphones by the service.
- **Do not hardcode `hw:0,0` or `plughw:0,0`.** That bypasses routing: it
  pins you to the built-in chip, ignores the headset, can't share, and makes
  the jack behave wrongly. Ember historically forced `plughw:0,0` and so does
  not follow a USB mic — that is the bug this rule avoids.
- For a microphone, open the `default` capture device. The **Sound** window on
  the dock is the reference: if it records your mic and your app doesn't, your
  app is opening its own device instead of `default`.
- **The microphone is for one program at a time.** Capture is not shared
  (there is no `dsnoop`): while one program records, a second one that opens
  the microphone gets "device busy". Open it only while you record and close
  it afterwards, and tell the owner plainly when it is busy. FireFly's voice
  messages and Ember's vocoder meet this when both are open.
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

`rk-apps` installs, versions and updates the dock apps (FireFly, Stump,
Ember, the Provisioner), over Wi-Fi, into `/home/ark`. It is also how the image bakes them in at build time. Supporting
it is optional for a brand-new app, but it's how FireFly, Stump and Ember stay
current, and the pattern is worth matching.

Two pieces make an app updatable:

**1. A readable version.** `rk-apps versions` compares an installed version
against the newest published one. The three apps expose "newest" differently:

- **FireFly** — `__version__` in `firefly/firefly/__init__.py` on the repo's
  `main` branch. (FireFly also has a **sandbox** source — the
  `SandBox_FireFly_RK3326` repo, where a version lands first; `rk-apps source
  firefly stable|sandbox`, or **Y** on FireFly's row in the AppManager window,
  switches.)
- **Stump** — a `handheld/VERSION` file on `main`.
- **Ember** — the tag of its latest GitHub release (its binary is only built
  for releases); the installed version is recorded in `~/ports/ember/.rk-version`.
- **Provisioner** — the newest `vX.Y.Z` tag of its repository, pre-releases
  included (GitHub's "latest release" skips those), ranked as versions are:
  `0.3.0-beta.24` above `0.3.0-beta.8`, and a plain `0.3.0` above both. The
  release's `.tar.gz` is checked against its `SHA256SUMS`; the installed
  version is the `VERSION` file in `~/rk3326_provisioner`.

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

This is for an app the image carries. An app that is not in the image does
not need `rk-apps` to know it: see [Packages](#packages) below.

<a name="where-files-live"></a>
## Where files live

| Path | For |
|---|---|
| `/home/ark/<App>/` | the app itself (owned by `ark`). FireFly: `/home/ark/firefly`. Stump: `/home/ark/R36MAX-Stump`. |
| `/home/ark/ports/` | ports-style apps (Ember: `/home/ark/ports/Ember.sh`). |
| `/data/ark/` | **the place for an app's own files on RK3326 Linux**: user data on the data partition (survives reflashing). `/data/ark/apps/` for a dock entry added at install time. |
| `/roms/ports/<app>/` | a port's working/drop folders, kept for apps that also run on arkos4clone and dArkOS. Don't put new state here. |
| `/data/opt/` | large optional payloads (Exploit-DB lives here). |
| `/share/` | **files the owner copies from a computer.** The `RKSHARE` partition (exFAT), the one a Mac or PC shows when the card is in its reader. `/share/roms` for games, `/share/packages` for app packages, `/share/<your app>/` for files your app takes from the owner. Ask `rk-paths` for these, see below. |
| `/usr/lib/rk-gpu/` | the GPU driver and SDL2 the launcher puts on `LD_LIBRARY_PATH`. Read-only; don't ship your own copies. |

The handheld runs as user **`ark`**. Install into `ark`'s home, not root's.

### Ask `rk-paths`, do not write the path

The card's layout has changed once and can change again. So an app does not
carry `/share` or `/data/ark` in its code: it asks `rk-paths`, the one
place that knows, and follows whatever it answers. It is a small command,
not a service: it answers and ends.

| Command | Answers |
|---|---|
| `rk-paths data` | the folder for your app's own files and state |
| `rk-paths share` | the partition a computer can read, or nothing (exit 1) on a card without one |
| `rk-paths inbox yourapp` | the folders where your app finds files its owner gave it, one a line, the first to look in first; made if missing |
| `rk-paths find yourapp '*.bin'` | the files in those folders, full paths, without what a Mac leaves behind |
| `rk-paths roms`, `rk-paths packages` | the games folder; the folders AppManager reads |
| `rk-paths env` | all of it as `NAME=value` lines for a program; `rk-paths list` for a person |

`yourapp` is your app's id: small letters, digits, `-` and `_`.

```sh
# a shell app: every firmware file the owner has given it
rk-paths find provisioner '*.bin' | while IFS= read -r f; do echo "found $f"; done
```

```python
# a Python app
import subprocess
def inbox(app):
    out = subprocess.run(["rk-paths", "inbox", app], capture_output=True, text=True).stdout
    return out.splitlines()        # look in these, in this order
```

On an older system `rk-paths` is not there: fall back to the folder your
app used before.

### `/share`: files that come from a computer

`/data` is ext4: a Mac or a Windows PC does not show it. An owner who wants
to hand your app a file (a firmware `.bin`, a key, a list) with the card in
a computer can only reach `BOOT` and `RKSHARE`. `rk-paths inbox yourapp`
gives your app a folder there, `/share/yourapp` today, and a second one on
`/data` for files that arrive over SFTP or from a USB stick.

- **It may not be there.** A card set up before `RKSHARE` existed has none
  until its owner asks for it (Settings → Show the card on a computer), and
  a card with under about 2 GB of free room never gets one. The inbox then
  has only its `/data` folder: nothing for your app to handle.
- **It is exFAT.** No owners and no permissions (every file belongs to `ark`
  and `chmod` does nothing), no symlinks, no sockets or FIFOs, and names
  that differ only by letter case are the same file. Do not run programs
  from it and do not keep a database there.
- **Input, not state.** The owner pulls the card and edits this partition on
  a computer. Read what they put there; keep your identity, settings and
  working data under `rk-paths data`, as before.
- **A Mac leaves files behind**: `._name` beside each file it copies,
  `.Spotlight-V100`, `.fseventsd`, `.DS_Store`. `rk-paths find` skips them;
  if you list a folder yourself, skip every name that starts with a dot.

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

<a name="packages"></a>
## Packages: an app that installs itself

The four apps above are in the image and `rk-apps` knows each by name. Any
other app needs none of that. Hand people a **package** and AppManager
installs it, updates it and removes it; this repository does not change and
no release of the system is needed for your app or its next version.

A package is a `.zip` with these at its top (or inside one folder):

| File | What it is |
|---|---|
| `VERSION` | the version, on the first line: `1.0.0`, `0.6.0-rk3326`. |
| `deploy/install.sh` | your installer. Run with `bash`, from the package's top folder, as `ark`. Re-runnable: it is also your update. |
| `deploy/<id>.json` | your dock entry ([the JSON above](#the-dock-entry)). The file name is your app's id: lower case, digits, `.`, `_`, `-`. Exactly one. |
| anything else | your app's files, where your installer expects them. |

What happens when someone presses A on your package:

1. The `.zip` is checked before anything is unpacked: the three files are
   there, the version is a version, the dock entry has `name` and `exec`, the
   id is not one of the system's (`firefly`, `stump`, `ember`,
   `provisioner`, or an entry the image carries), no file points outside the
   package, and there are no symbolic links. At most 300 MB unpacked.
2. The window says where the package comes from and, when your installer
   mentions `sudo`, a sudoers file or `/usr/local/sbin`, that it has steps
   for root. The person confirms and gives the handheld's password.
3. Your installer runs. **Root steps go through `sudo`.** There is no
   terminal: the password comes through sudo's askpass helper, and every
   `sudo` your installer calls is made to ask that way, whether it is
   written `sudo`, `sudo -A` or `sudo -n`. Never `sudo -S`.
4. If your installer did not put the dock entry in `/data/ark/apps`, it is
   put there for you. The program your entry's `exec` names must exist by
   then (an absolute path), or the app is not counted as installed.
5. What your installer added in `/usr/local/sbin`, `/usr/local/bin`,
   `/etc/sudoers.d` and `/etc/udev/rules.d` is noted.

Removing the app (Y) deletes the folder your `exec` program is in (when it
is inside `/home/ark`), the dock entry, and the files noted in step 5.
Anything your installer puts elsewhere is not removed: keep to those
places. Data under `/data/ark/<your-app>/` is left on purpose.

A zip does not keep the executable bit: have your installer `chmod` what
needs it (the `exec` program is made executable for you).

To try one: `rk-apps package-install /path/to/your.zip` over SSH shows your
installer's output; `rk-apps packages` lists what is found and why a zip is
refused.

<a name="checklist"></a>
## Checklist

- [ ] A JSON dock entry with `name` and `exec`; valid JSON.
- [ ] Renders with SDL2; inherits `kmsdrm` and `LD_LIBRARY_PATH`; bundles no
      GPU/SDL libraries; draws for 720×720.
- [ ] Quits on SELECT+START; doesn't grab the volume keys.
- [ ] Knows the left stick is also a mouse: uses the mouse events and draws
      its own pointer, or ignores them, or sets `"mouse": false`. Hides
      SDL's cursor.
- [ ] Opens the ALSA `default` device; no `hw:0,0`.
- [ ] If it shares a single-owner resource, a `before`/`after` hook stops and
      restarts the other user.
- [ ] Installs under `/home/ark` as `ark`; data under `/data`.
- [ ] (Optional) a readable version and a re-runnable installer that honours
      `SUDO_ASKPASS`, so `rk-apps` can update it.

Questions, or a glyph/setup-screen you need added to the desktop, are a pull
request or an issue on this repo.
