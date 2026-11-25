# STUMP RF Recon — RK3326_Linux v1.2.0 Compatibility Port

Version: `0.4.1-rk3326`  
Target OS: `ruderigo/RK3326_Linux` v1.2.0+ (Debian 13 arm64 · `rkshell` dock · dArkOS Mali/SDL2 · 93 RK3326 handhelds)  
Target Hardware: XiFan R36MAX (720×720) + R36S / RG351P / RG351V / other RK3326 handhelds · USB OTG Heltec V3 (CP2102) or CH340/CH341 ESP32 boards

## Summary of Porting Changes (aligned with `RK3326_Linux` v1.2.0 & `docs/building-apps.md`)

1. **Dock Entry (`deploy/stump-recon.json`)**
   - Registers `STUMP Recon` under `Comms` using the `chip` glyph.
   - Sets `"mouse": false` so `rkshell` pauses `rk-mouse` while STUMP Recon owns the left stick, triggers, and shoulder buttons, then re-enables it on exit.
   - Wires `"before": ["/usr/local/bin/rk-stump-pause", "pause"]` and `"after": ["/usr/local/bin/rk-stump-pause", "resume"]` so STUMP Recon cleanly shares the USB OTG serial port with a running background Stump node.
   - Matches exact filename `stump-recon.json` so `rkshell` 1.2.0 automatically deduplicates `/usr/share/rk/apps/stump-recon.json` vs `/data/ark/apps/stump-recon.json`.
2. **Display, Panel Rotation & Multi-Resolution Scaling (`host/STUMP-Recon.sh` & `host/stump-recon/stump_gui.py`)**
   - Inherits `LD_LIBRARY_PATH` (`/usr/lib/rk-gpu/turn{1..3}` + `/usr/lib/rk-gpu`), `RK_ROTATE`, `SDL_VIDEODRIVER=kmsdrm`, and `SDL_GAMECONTROLLERCONFIG_FILE=/usr/share/gamecontrollerdb.txt` from `rkshell`.
   - Renders 1:1 natively on 720×720 panels (R36MAX) and automatically scales the 720×720 HUD cleanly onto any of the other 92 RK3326_Linux 1.2.0 handheld panels (640×480, 480×320, rotated panels).
   - Never overwrites `SDL_VIDEODRIVER`, removes legacy `/dev/tty1` resets, hides the SDL cursor, and blocks mouse events.
3. **Standard Gamepad, HAT D-Pad & `SELECT+START` Exit Contract (`stump_gui.py`)**
   - Uses SDL2's `pygame._sdl2.controller.Controller` API (reading `/usr/share/gamecontrollerdb.txt`) with `JOYHATMOTION` and `pygame.joystick` fallback (works on RG351P/RG351V/USB pads).
   - Changes quit chord from single-press `SELECT` / `L1+R1` to **`SELECT+START`** (matching FireFly, Stump, Ember, and Provisioner).
   - Leaves hardware volume keys (`evdev 114/115`) untouched for `rkshell`.
4. **Persistent `/data/ark` Storage, CH340/CP2102 Discovery & Permissions (`STUMP-Recon.sh`, `stump_gui.py`, `stump_cli.py`)**
   - Removes `echo ark | sudo -S chmod ...` (`ark` already belongs to `dialout`, `video`, `input`, and `render`).
   - Saves exports (`.pcap`, `.chlsj`, `.json`, `.jsonl`) and `debug.log` to `/data/ark/stump-recon/exports` so captures survive OS reflashing and appear directly in the desktop **Files** window.
   - Scans `/dev/ttyUSB0`, `/dev/ttyACM0`, `/dev/ttyUSB1`, `/dev/ttyACM1`, and `/dev/serial/by-id/*` (compatible with both Heltec V3 CP2102 and RK3326_Linux 1.2.0's newly added `ch341` driver for CH340/CH341 ESP32 boards).
5. **Re-runnable Installer & v1.2.0 `rk-apps` / `build-image.sh` Patches (`deploy/install.sh`, `VERSION`, `rk3326-linux-patch/`)**
   - `rk-apps.patch` includes `room_for()` preflight disk checks (`rk_need_space`), `install_stump_recon`, `update_stump_recon`, `versions`, and `status` cleanly aligned with RK3326_Linux v1.2.0 (`provisioner` + `preflight.sh`).
   - `build-image.patch` applies cleanly against `RK3326_Linux` v1.2.0 `build/build-image.sh`.

## Quick Install on an Existing RK3326_Linux Handheld (keeps downloads off `/tmp` RAM)

```bash
scp stump-rf-recon-rk3326-v0.4.1-rk3326.zip ark@r36max.local:/data/ark/stump-recon-install.zip && \
ssh ark@r36max.local 'mkdir -p /data/ark/.stump-stage && unzip -o /data/ark/stump-recon-install.zip -d /data/ark/.stump-stage && bash /data/ark/.stump-stage/deploy/install.sh && rm -rf /data/ark/.stump-stage /data/ark/stump-recon-install.zip'
```

## Baking Into the `RK3326_Linux` v1.2.0 Image

```bash
cp /path/to/stump-rf-recon-rk3326/deploy/stump-recon.json overlay/usr/share/rk/apps/stump-recon.json
git apply /path/to/stump-rf-recon-rk3326/rk3326-linux-patch/rk-apps.patch
git apply /path/to/stump-rf-recon-rk3326/rk3326-linux-patch/build-image.patch
```
