# STUMP RF Recon — RK3326_Linux Compatibility Port (`v0.6.0-rk3326`)

Port of [`ruderigo/stump-rf-recon`](https://github.com/ruderigo/stump-rf-recon) engineered for [`ruderigo/RK3326_Linux`](https://github.com/ruderigo/RK3326_Linux) (`v1.2.0+` / commit `6590145`) following `docs/building-apps.md`, with **universal USB Wi-Fi compatibility** covering **all monitor-capable chipsets** AND **consumer client-only dongles**.

## Supported Wi-Fi Adapters (`host/stump-recon/wifi_mon.py`)

Uses the exact same `/sys/class/ieee80211/phy*` + `iw phy` capability probe as RK3326_Linux's **Arsenal** window (`rkshell/system.py`):

### Tier 1 — Full Raw 802.11 Monitor + Radiotap Capture (Beacons, Probes, LAA Clients, Data Frames, `.pcap`)
Any USB adapter whose Linux driver reports `* monitor` in `iw phy`:
- **Ralink / MediaTek `rt2x00`**: **RT3070 / RT3071 / RT3072 / RT5370 / RT2870** (`rt2800usb`, `rt2870.bin`), `rt73usb`, `rt2500usb` (Alfa AWUS036NH, Panda PAU05/06/09, generic RT3070/RT5370)
- **Atheros / Qualcomm**: **AR9271** (`ath9k_htc`, Alfa AWUS036NHA, TP-Link TL-WN722N v1), **AR9170** (`carl9170`)
- **MediaTek `mt76`**: **MT7601U** (`mt7601u`, $5 mini-dongles), **MT7610U** (`mt76x0u`, Archer T2U), **MT7612U** (`mt76x2u`, Alfa AWUS036ACM, BrosTrend AC1L/AC3L), **MT7921U** (`mt7921u`, Wi-Fi 6E)
- **Realtek (mainline & RK3326_Linux vendor drivers)**:
  - **RTL8812AU / RTL8814AU / RTL8821AU** (`8812au`/`88XXau`/`8814au`/`8821au`/`rtw88_*`, Alfa AWUS036ACH/AWUS1900, Archer T4U)
  - **RTL8822BU / RTL88x2BU** (`8822bu`/`88x2bu`/`rtw88_8822bu`, TP-Link Archer T3U/T4U v3, Cudy, BrosTrend)
  - **RTL8821CU** (`8821cu`/`rtw88_8821cu`, consumer AC600 dual-band dongles)
  - **RTL8188EU / RTL8188EUS / RTL8192EU** (`8188eu`/`r8188eu`/`8192eu`/`rtl8xxxu`, **TP-Link TL-WN722N v2/v3**, TL-WN725N, TL-WN823N)
  - **RTL8852BU / RTL8852AU** (`8852bu`/`rtw89_8852bu`, Wi-Fi 6 USB dongles)
- **Multi-driver fallback chain**: Handles `iw set monitor otherbss` → `iw set type monitor` → `iwconfig mode monitor` and `iw set channel HT20` → `iw set channel` → `iw set freq` → `iwconfig channel`, respects per-adapter regulatory channels from `iw phy`, and always restores managed mode + NetworkManager on exit.

### Tier 2 — Consumer Client-Only USB Dongles & Onboard Wi-Fi (Managed AP Scan Fallback)
- If you plug in a consumer client-only USB adapter without monitor mode (e.g., **AIC8800 Wi-Fi 6** `aic8800_fdrv_usb`, stock `rtl8188fu`, generic store-bought dongles) or have **no USB adapter plugged in at all**, STUMP Recon automatically falls back to **read-only Managed AP Scan Mode** (`iw dev <iface> scan` / `scan dump`).
- Never disconnects your Wi-Fi or SSH session, still populates 2.4 GHz spectrum bars, Device Cards, Dossier, and exports, and **auto-upgrades seamlessly to full Monitor Mode** the instant a monitor-capable USB dongle is hot-plugged!

### Dual-Radio Operation
- Works **standalone** with any USB/onboard Wi-Fi adapter (no Heltec V3 needed) OR **simultaneously** with a Heltec V3 / CH340 ESP32 board over USB-C hub for Sub-GHz LoRa (`902–928 MHz` Reticulum / Meshtastic) + 2.4 GHz Wi-Fi.

## RK3326_Linux Contract Highlights
- **Privilege isolation**: Root-owned `/usr/local/sbin/rk-stump-wifi` (mirrors `rk-scan`), stdin-EOF auto-teardown, zero `sudo -S`.
- **Display & Rotation**: Inherits `SDL_VIDEODRIVER=kmsdrm` and rotated `/usr/lib/rk-gpu/turn1..3`, scales cleanly across all 93 RK3326 handhelds.
- **Controls & Pointer**: `SDL_GameController` via `/usr/share/gamecontrollerdb.txt`, `SELECT+START` exit chord, `"mouse": false` in dock JSON.
- **Persistence**: App under `/home/ark/stump-rf-recon`, captures under `/data/ark/stump-recon/exports` (survives reflashes).

## Install on a Running RK3326_Linux Handheld (Stages on `/data/ark`, Off RAM `/tmp`)

```bash
ssh ark@r36max.local 'mkdir -p /data/ark/.stump-stage' && \
scp stump-rf-recon-rk3326-v0.6.0-rk3326.zip ark@r36max.local:/data/ark/.stump-stage/ && \
ssh ark@r36max.local 'unzip -o /data/ark/.stump-stage/stump-rf-recon-rk3326-v0.6.0-rk3326.zip -d /data/ark/.stump-stage/pkg && bash /data/ark/.stump-stage/pkg/deploy/install.sh && rm -rf /data/ark/.stump-stage'
```

## Probe Adapters & Headless CLI Usage

```bash
# List all detected USB & onboard Wi-Fi adapters, chipsets, and monitor/scan capabilities (no root required):
python3 /home/ark/stump-rf-recon/stump-recon/wifi_mon.py --probe

# Headless CLI (auto-selects best monitor USB dongle or consumer scan fallback + Heltec V3 if present):
python3 /home/ark/stump-rf-recon/stump-recon/stump_cli.py

# Monitor-only mode on a specific USB adapter and fixed channel 6:
python3 /home/ark/stump-rf-recon/stump-recon/stump_cli.py --no-serial --wifi-iface wlan1 --channel 6 --monitor-only
```

## Update Bundled Copy in `ruderigo/RK3326_Linux` (Post-PR #33 / `6590145+`)

```bash
# Inside your local clone of ruderigo/RK3326_Linux:
cp -r /path/to/stump-rf-recon-rk3326/{host,deploy,VERSION,README-RK3326.md} \
      overlay/usr/share/rk/bundled/stump-rf-recon/
cp /path/to/stump-rf-recon-rk3326/host/stump-recon/wifi_mon.py \
   overlay/usr/local/sbin/rk-stump-wifi
chmod 0755 overlay/usr/local/sbin/rk-stump-wifi
git apply /path/to/stump-rf-recon-rk3326/rk3326-linux-patch/rk3326-universal-wifi.patch
```
