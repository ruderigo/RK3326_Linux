# Changes

What changed in each release, newest first. A handheld takes a new release
from **Settings → Update this handheld**; what an update can and cannot
replace is in [`docs/updates.md`](docs/updates.md).

## 1.4.0 — 2026-11-27

What an operating system is expected to have, and this one did not.

- **Remote access (SSH) is off on a new card.** Every card starts with the
  same password, so a card that answered SSH from its first start could be
  entered by anybody on the same network before its owner. It is turned on
  in **Network → Remote access (SSH)**, which first asks you to choose the
  handheld's password if it still has `ark`. An updated card keeps SSH as
  it was, unless its password was never changed: then it is turned off
  until you choose one.
- **The battery is looked after.** The desktop warns at 10% and at 5%, and
  the handheld powers off properly at 3%, also while a game or an app has
  the screen: running out in the middle of a write is how cards get damaged.
- **The screen goes dark when nobody is using it**: after 5 minutes without
  a button (**Settings → Screen off after**: 1 to 30 minutes, or never).
  Any button lights it again. The handheld itself keeps running.
- **Time zone** in Settings, by part of the world and city. The choice
  survives a reflash.
- **Reset this handheld**, in Settings: *light* (saved Wi-Fi networks, the
  password, remote access and its keys, the time zone, the desktop's
  settings) or *full* (all of that, and what the apps hold: FireFly's
  identity, the Stump's setup, apps from a package, saved scans). Neither
  touches the system, the apps that come with it, or RKSHARE. The table is
  in the README.
- **Update this handheld also applies Debian's security updates**, after
  the system's own update and when the system is already current. It never
  adds or removes a package, looks at the room and the battery first, and
  cannot fail the update. A new image is built with the fixes of the day.
- **The Update window shows the version you have and the one you would
  get**, and asks "Update to X?" before the password. Both used to say
  "unknown": opened from Settings, the window never looked them up.
- **Nothing the system says is cut with "…".** Messages, the lines under a
  job's heading, job logs, menus, Arsenal's tool descriptions and Video's
  notes wrap; the keyboard's question drops to smaller letters when it is
  long. Names from outside (a video's title, a file, a network) are still
  cut to their row. A failure to start remote access is a sentence now.

To get it: **Settings → Update this handheld**. The update that brings
this release is run by the updater you already have, so Debian's security
updates come with the *next* press of A, not this one.

Seen on an R36MAX on 27 November: SSH off after a flash and the password
step, the screen's sleep, the time zone, both versions in the Update
window, Debian's security updates being applied, both resets. A reset first left SSH unable to start (the card's
keys were removed and nothing made new ones); that was found on the
handheld and fixed before this release. Not seen yet: the battery warnings
and the power-off at 3%.

## 1.3.1 — 2026-11-26

- **An update brings the picture at switch-on.** 1.3.0 had our logo only on
  a newly flashed card: an update does not replace the boot partition, so
  an updated card kept arkos4clone's. Every update now writes the system's
  logo to BOOT, for the handheld the card starts and for every other one on
  the card. Nothing is kept: a `logo.bmp` you put there yourself lasts until
  the next update, and is copied back by hand after it.
- **MIT licence.** The repository had none. What is written here (the
  desktop, the `rk-*` programs, the build scripts, the docs, the logo
  picture) is under the MIT licence, in [`LICENSE`](LICENSE). The README
  says what keeps its own terms: what the image carries (the kernel, u-boot,
  Debian's packages, Wi-Fi firmware, RetroArch), the two RetroArch patches,
  and arkos4clone's files.

The logo step is tested in the build on a stand-in boot partition, for
every panel size, and was seen on an R36MAX on 26 November: a card updated
to 1.3.1 from Settings showed the new picture at its next start.

## 1.3.0 — 2026-11-26

- **A part of the card your computer can read: RKSHARE.** With the card in
  a Mac or a PC only BOOT showed up, because the system and `/data` are
  ext4. The card now has a fourth partition, in exFAT, that every computer
  opens: `roms/` for games and BIOS files, `packages/` for app packages. On
  the handheld it is `/share`. `/data` is 16 GB and RKSHARE takes the rest
  of the card (half each on a small card; a card with under about 2 GB free
  after the system keeps it all for `/data`).
  - A newly flashed card gets it at the first start.
  - A card flashed again keeps it, with `/data`: both are found and put back
    as they were, nothing is formatted.
  - A card set up before this release keeps its layout until you ask:
    **Settings → Show the card on a computer**, on Wi-Fi (the exFAT tools
    are fetched once). Settings says to wait while it prepares, then asks to
    restart. At that start `/data` is made smaller with what is in it kept,
    RKSHARE is made, and the handheld restarts once more. It takes a few
    minutes: plug the charger in and do not switch off. From a terminal:
    `sudo rk-share request`, `rk-share status`. It cannot be undone, and an
    update's rollback does not undo it.
  - Flashing 1.2.8 or older over a card that has RKSHARE loses what is on
    RKSHARE.
- **Games reads from RKSHARE.** `/data/ark/roms` is now a link to
  `/share/roms`; games already there move over.
- **AppManager also finds packages in `/share/packages`**, so an app's
  `.zip` can be copied with the card in a computer. It skips the `._` files
  a Mac leaves on exFAT.
- **`rk-paths`: the one place an app asks where things are.** `rk-paths
  inbox APP` gives an app the folders where it finds files from its owner
  (the one on RKSHARE first), `rk-paths find APP '*.bin'` lists them, and
  `share`, `data`, `roms`, `packages`, `list` and `env` answer the rest. A
  command, not a service. Apps should ask it and not write paths:
  [`docs/building-apps.md`](docs/building-apps.md#where-files-live).
- **Our own picture at switch-on**, in place of arkos4clone's, made for
  every panel's size and turn. It shows on a newly flashed card; an update
  does not touch BOOT. For your own: replace `logo.bmp` on BOOT with a BMP,
  24 bits, not compressed, exactly the screen's size.
- The README and the docs were brought up to date (the system partition's
  size, the card to use, flashing from a Mac's Terminal, what the build
  runs on).

Tried on an R36MAX with kernel 5.10: a new card, a card flashed again, and
a 1.2.8 card changed from Settings; RKSHARE opened on a Mac. Not tried: the
4.4 fallback kernel mounting RKSHARE, and any other handheld.

## 1.2.8 — 2026-11-25

- **Apps is now AppManager, and it installs apps from packages.** An app
  that is not part of the system comes as a package, a `.zip` from whoever
  makes it (its version, its own installer, its dock entry). Copied to
  `/data/ark/packages`, it is listed in AppManager with its name and
  version; A installs it, or a newer one over the one in place; Y removes
  it, with its dock entry and what its installer added for root. The system
  does not change when an app is added, and neither does its version: a new
  app or a new version of one needs no release of the system. Nothing
  checks a package, as nothing checks a program installed on a computer:
  the window says where it comes from, says when its installer has steps
  for root, and asks before running it. From a terminal: `rk-apps packages`,
  `package-install`, `package-remove`. What a package holds is in
  [`docs/building-apps.md`](docs/building-apps.md#packages). FireFly, the
  Stump, Ember and the Provisioner stay in the image and are updated as
  before.
- The AppManager list scrolls on a small screen.

## 1.2.0 — 2026-11-25

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
