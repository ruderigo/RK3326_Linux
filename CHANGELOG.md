# Changes

What changed in each release, newest first. A handheld takes a new release
from **Settings → Update this handheld**; what an update can and cannot
replace is in [`docs/updates.md`](docs/updates.md).

## Unreleased

From a builder's notes on 1.1.0 (25 November):

- **The first start no longer prints failures for `/data`.** The image's
  `/etc/fstab` waited 8 seconds for the data partition before the first start
  had made it, and showed TIME and DEPEND failures that were not failures.
  The image now has no line for `/data`; `rk-firstboot` adds it once the
  partition is there. Cards already in use keep their line and are not
  touched.
- **A CH340 board gets a serial port.** arkos4clone's 5.10 kernel is built
  without the driver for the CH340/CH341 USB-serial chip, so a Freenove
  ESP32-WROVER, like most ESP32 boards, got no `/dev/ttyUSB*`: only the
  Provisioner reached it, and esptool or a serial terminal saw nothing. The
  build now makes that one module (`ch341`) from the kernel's own source and
  configuration and adds it to the image; it loads when the board is plugged
  in. A card that is updated and not flashed again gets it too: each
  release carries the module as a file, and after **Update this handheld**
  the card takes it from there (`rk-tools kernel-modules`, also by hand and
  from a file). An update still never replaces a kernel file: the module
  must be built for the very kernel it goes to, a file the kernel's build
  put there is left alone, and only the lists of modules are rewritten. The
  4.4 fallback kernel is not covered.
- **The Provisioner is a dock app like the others.** It is in the image
  (Workshop → Provisioner), `rk-apps install|update provisioner` fetches its
  newest release and checks it against the release's SHA-256, and the Apps
  window shows its version, updates it, and installs it on a card that does
  not have it. Its installer's dock entry on `/data` no longer shows a second
  icon beside the image's own. Only its sandbox repository exists, so there
  is no stable/sandbox switch for it yet.
- **Guides brought in line with 1.1.0**: `docs/apps.md` says the three dock
  apps are in the image; `docs/building-apps.md` says the microphone is for
  one program at a time (capture is not shared), and that `/data/ark` is the
  place for an app's files, with `/roms/ports` kept for arkos4clone and
  dArkOS.

## 1.1.0 — 2026-11-24

- **Every RK3326 handheld arkos4clone supports, from one image**: 93 of them,
  listed in [`docs/devices.md`](docs/devices.md). The card holds the boot
  files of all of them; `Choose handheld.command` on the boot partition (Mac,
  Linux), three files copied by hand, or `rk-boot-select` on the handheld
  picks one. Panels mounted on their side or upside down are turned: the
  desktop turns its own picture, dock apps and Video load arkos4clone's SDL2
  for that turn, and Games (emulator bundle 2) is built with RetroArch's
  driver for turned RK3326 panels. A direction pad
  that reports as a hat (RG351P, RG351V, USB pads) is read. Only the R36MAX
  has been started by a person: the others are checked by the build, from
  their device trees, and drawn at their screen sizes.
- **Nothing is installed without looking first.** The tools, the dock apps
  and the OS update each check the room where their files go and the memory
  to spare before anything is fetched, from the packages' own sizes where
  apt knows them, and stop with what is short and by how much. The desktop
  says so when the system partition, the data partition or memory runs low,
  and Settings → About shows what is free.
- **Lighter in the background.** No daily package refresh or upgrade behind
  the owner's back, a log capped at 16 MB, swap tuned for compressed memory,
  downloads kept on the card and off `/tmp` (which is memory), package
  downloads on the data partition, package lists kept compressed, and no
  change logs or unused translations unpacked from packages. Old update
  backups no longer pile up: the newest three are kept. A card already
  flashed gets these with the update (new packages only, for the last one).
- Metasploit goes to the data partition when the system partition cannot
  hold it (not yet tried on a handheld).

Not yet tried on a handheld; see [`docs/media.md`](docs/media.md).

- **Video.** A window on the dock that searches YouTube and plays the result
  with mpv, driven by the pad. yt-dlp comes from its own releases and is
  updated from the window.
- **Games.** RetroArch on the dock, built for this GPU, with dArkOS's cores
  for PlayStation, Nintendo 64, PSP, the 8- and 16-bit machines and the Game
  Boys, for the owner's own game files in `/data/ark/roms`. It comes as the
  emulator bundle (`build/build-emulators.sh`), in new images and fetched on
  cards already flashed.
- `rk-tools install-media` installs both on a card flashed before they were
  part of the image; the Video window runs it for you.
- `rk-tools` finishes an install that was cut short before starting a new
  one, and no longer counts a half-installed package as installed.
- `rk-tools` checks the room on the system partition before it installs, and
  says how much is missing instead of failing half-way.
- The emulator bundle is unpacked without the `xz` program, which the image
  does not have.
- `rk-tools` waits for another install or update that is running (Debian's
  own background refresh, for one) instead of failing on its lock.
- A dock entry's `exec` may be a bare name, looked for on PATH and in
  `/usr/games`.

## 1.0.0 — 2026-11-22

The first full release. Tested on an R36MAX (type 1 board); no other
handheld has been tried.

**New since 0.9.2**

- **A pointer on the desktop.** The left stick moves it, A presses what it is
  on, and it goes away after three seconds of rest or at the first d-pad
  press. On the dock the icon under it grows as the selected one, and the
  screen's left and right edges bring in the icons that did not fit. Every
  window has a × that does what B does. A USB mouse works the same way.
- **The stick is a mouse for apps too** (`rk-mouse`): the triggers click and
  the shoulders are the wheel. A dock entry can say `"mouse": false` to
  switch it off while that app runs.
- **Updates without reflashing.** Settings → Update this handheld replaces
  the desktop and the system's own files, keeps `/home` and `/data`, and
  puts the previous version back by itself if the new desktop does not
  start. Changes to where things are kept are carried forward by numbered
  migrations.
- **Stump** can be switched between its stable and sandbox sources in the
  Apps window, as FireFly already could.
- **More Wi-Fi dongles start.** The image now carries the network adapters'
  firmware from the same place as the kernel drivers, next to Debian's. This
  adds the AIC8800 dongles among others.
- **Ethernet shows on the desktop.** A USB Ethernet adapter, or a hub or dock
  with a network socket, connected by itself before; now the menu bar says
  so, the desktop shows the address, and the Network window has a row for it.
- **A guide for app builders** ([`docs/building-apps.md`](docs/building-apps.md)):
  the dock entry, the screen, the controls, the pointer, sound, taking turns,
  and updates.

**Not yet tried on a handheld**

- Wi-Fi dongles other than the RT3070, USB Ethernet, and a USB mouse.

**Known problems**

- Ember makes no sound yet.
- An app can leave the display's hardware cursor frozen over the desktop
  after it quits. A restart clears it.
- No driver for the MediaTek MT7921AU or the Realtek RTL8852AU / RTL8832AU
  Wi-Fi 6 dongles.
- Firmware is outside what an update replaces: a card that was flashed before
  this release needs a reflash to get the added dongle firmware.

## 0.9.2 and earlier — 2026-11-20 to 2026-11-22

The road to the first release, on an R36MAX:

- The image boots, makes its data partition at the first start, joins Wi-Fi
  and answers SSH; the speaker, the charging limits and restart were fixed
  for the R36MAX type 1 board.
- The desktop: a gamepad-driven shell with a dock, and windows for Files,
  Terminal, Scan (nmap as a loadout), Arsenal (the security toolset), Survey,
  Network, Devices, Sound, Apps and Settings.
- FireFly, the Stump and Ember in the image, the Stump's setup from the dock,
  and app updates from the Apps window.
- Sound routing between the speaker, the 3.5 mm jack and USB audio; volume
  keys everywhere, including inside apps.
- A readiness line in Arsenal for the plugged-in Wi-Fi adapter.
