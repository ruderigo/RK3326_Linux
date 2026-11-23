# Changes

What changed in each release, newest first. A handheld takes a new release
from **Settings → Update this handheld**; what an update can and cannot
replace is in [`docs/updates.md`](docs/updates.md).

## Unreleased

Not yet tried on a handheld; see [`docs/media.md`](docs/media.md).

- **Video.** A window on the dock that searches YouTube and plays the result
  with mpv, driven by the pad. yt-dlp comes from its own releases and is
  updated from the window.
- **Games.** RetroArch on the dock with Debian's cores for the 8- and 16-bit
  machines and the Game Boy Advance, for the owner's own game files in
  `/data/ark/roms`.
- `rk-tools install-media` installs both on a card flashed before they were
  part of the image; the Video window runs it for you.
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
