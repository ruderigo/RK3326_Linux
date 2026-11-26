# RK Field Deck (`1.0.0-rk3326`)

Unified device-card RF & network diagnostic HUD for **RK3326_Linux v1.2.0+** (XiFan R36MAX 720×720 and 93 supported RK3326 handhelds).

## Core Workflow

1. **Live Device Cards (`1:DEVICES`)**: Automatically discovers real devices across:
   - **LAN** (`ip neigh`, `arp-scan`, and `rk-scan` Sweep)
   - **Wi-Fi** (all monitor-capable USB adapters via `wifi_mon.py` + consumer client-only Managed AP Scan fallback)
   - **Sub-GHz LoRa** (Heltec V3 / ESP32 USB serial)
   - Zero simulated or placeholder devices are ever displayed.
2. **Click / Press `A` on any Device Card**: Opens the contextual **Scan & Diagnostic Arsenal Menu** showing every compatible tool for that specific device card, live binary availability, and the exact command preview.
3. **Execute (`A` / Click)**: Streams live stdout/stderr in `3:EXEC CONSOLE`, automatically merges discovered open ports/hosts back into Device Cards, cancels cleanly on `[B]`, and saves reports + `.pcap` captures under `/data/ark/field-deck/`.

## Integrated Tools (from `RK3326_Linux` Scan & Arsenal)

- **Scan (`rk-scan` / `rkshell.nmapspec`)**: Quick Look (`-F`), Identify (`-sV -O`), Quiet (`-T2`), Host Sweep (`-sn`)
- **Traffic Capture (Passive)**: `tcpdump` (`.pcap` saved under `/data/ark/field-deck/captures/`), `tshark`, `ngrep`
- **Network Diagnostics**: `arp-scan`, `fping`, `nbtscan`, `sslscan`, `dig`, `whois`, `snmpwalk`
- **Web Inspection (Read-Only)**: `httpie` (`HEAD`), `whatweb`, `wafw00f`

Offensive exploitation, MITM, and Wi-Fi attack tools from `arsenal.py` (such as `msfconsole`, `sqlmap`, `ettercap`, `mdk4`, `reaver`, `bully`, `wifite`, `hcxdumptool`, `aircrack-ng`) are intentionally excluded.

## Security & RK3326_Linux Compliance

- Strict target validation (`ipaddress.ip_address`, MAC/iface regexes) and `shell=False` argv execution everywhere.
- Root privileges are isolated in `/usr/local/sbin/rk-scan run`, `/usr/local/sbin/rk-field-tool run`, and `/usr/local/sbin/rk-field-wifi` using stdin-controlled cancellation and `visudo -cf` verified sudoers.
- Inherits `SDL_VIDEODRIVER=kmsdrm` & rotated Mali `LD_LIBRARY_PATH`, disables `rk-mouse` (`"mouse": false`), uses `SELECT+START` quit chord, pauses/resumes background Stump via `rk-stump-pause`, and persists all outputs on `/data/ark/field-deck/`.

## Install on a Running RK3326_Linux Handheld

```bash
ssh ark@r36max.local 'mkdir -p /data/ark/.field-stage'
scp rk-field-deck-v1.0.0-rk3326.zip ark@r36max.local:/data/ark/.field-stage/
ssh ark@r36max.local 'unzip -o /data/ark/.field-stage/rk-field-deck-v1.0.0-rk3326.zip -d /data/ark/.field-stage/pkg && sudo bash /data/ark/.field-stage/pkg/deploy/install.sh && rm -rf /data/ark/.field-stage'
```
