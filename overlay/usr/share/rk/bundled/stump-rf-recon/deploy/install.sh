#!/usr/bin/env bash
# deploy/install.sh — Re-runnable RK3326_Linux 1.2.0+ installer for STUMP RF Recon
# Follows RK3326_Linux/docs/building-apps.md:
#   - Installs under /home/ark/stump-rf-recon (owned by ark)
#   - Installs root-owned /usr/local/sbin/rk-stump-wifi (0755) + sudoers rule for ALL monitor-capable
#     USB Wi-Fi adapters (RT3070/rt2800usb, AR9271/ath9k_htc, MT76*, Realtek 88xx/8188/8852) and
#     consumer client-only dongles (read-only managed AP scan fallback)
#   - Preserves persistent exports/logs under /data/ark/stump-recon
#   - Drops /data/ark/apps/stump-recon.json only if not already baked into /usr/share/rk/apps/
#   - Honors SUDO_ASKPASS (sudo -A) when launched without a TTY; never uses sudo -S

set -euo pipefail

say() { printf 'stump-rf-recon: %s\n' "$*"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOME_DIR="${HOME:-/home/ark}"
APP_DIR="$HOME_DIR/stump-rf-recon"
DATA_DIR="/data/ark/stump-recon"
DOCK_DIR="/data/ark/apps"
BAKED_DOCK="/usr/share/rk/apps/stump-recon.json"
WIFI_HELPER="/usr/local/sbin/rk-stump-wifi"
WIFI_SUDOERS="/etc/sudoers.d/stump-recon-wifi"

if [ "$(id -u)" -eq 0 ] && [ "${USER:-}" != "ark" ]; then
    say "Run as user 'ark' (not root) so files live under /home/ark with ark ownership." >&2
    exit 1
fi

run_sudo() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif [ -n "${SUDO_ASKPASS:-}" ]; then
        sudo -A "$@"
    else
        sudo "$@"
    fi
}

say "Installing STUMP RF Recon into $APP_DIR ..."
mkdir -p "$APP_DIR/stump-recon"
cp -f "$SRC_ROOT/host/STUMP-Recon.sh" "$APP_DIR/STUMP-Recon.sh"
cp -f "$SRC_ROOT/host/stump-recon/stump_gui.py" "$APP_DIR/stump-recon/stump_gui.py"
cp -f "$SRC_ROOT/host/stump-recon/stump_cli.py" "$APP_DIR/stump-recon/stump_cli.py"
cp -f "$SRC_ROOT/host/stump-recon/wifi_mon.py" "$APP_DIR/stump-recon/wifi_mon.py"
[ -f "$SRC_ROOT/VERSION" ] && cp -f "$SRC_ROOT/VERSION" "$APP_DIR/VERSION"
[ -f "$SRC_ROOT/README-RK3326.md" ] && cp -f "$SRC_ROOT/README-RK3326.md" "$APP_DIR/README-RK3326.md"
chmod +x "$APP_DIR/STUMP-Recon.sh" "$APP_DIR/stump-recon/stump_gui.py" \
         "$APP_DIR/stump-recon/stump_cli.py" "$APP_DIR/stump-recon/wifi_mon.py"

# Persistent capture directory on /data (survives OS reflashing and shows in Files)
if [ -d "/data/ark" ] && [ -w "/data/ark" ]; then
    mkdir -p "$DATA_DIR/exports" "$DOCK_DIR"
    if [ -f "$BAKED_DOCK" ]; then
        say "Using baked-in dock entry at $BAKED_DOCK"
    else
        cp -f "$SRC_ROOT/deploy/stump-recon.json" "$DOCK_DIR/stump-recon.json"
        say "Dock entry installed at $DOCK_DIR/stump-recon.json"
    fi
    say "Captures & logs will be saved to $DATA_DIR/exports (preserved across reflashes)."
else
    say "Notice: /data/ark not mounted yet (normal during image build); captures will use /data/ark at runtime."
    mkdir -p "$HOME_DIR/stump-recon/exports"
fi

# Verify runtime Python packages & iw (preinstalled on RK3326_Linux)
MISSING=()
python3 -c "import pygame" 2>/dev/null || MISSING+=("python3-pygame")
python3 -c "import serial" 2>/dev/null || MISSING+=("python3-serial")
command -v iw >/dev/null 2>&1 || MISSING+=("iw")

if [ "${#MISSING[@]}" -gt 0 ]; then
    say "Installing missing system packages: ${MISSING[*]}"
    run_sudo apt-get update -qq
    run_sudo apt-get install -y "${MISSING[@]}"
fi

# Install root-owned universal USB Wi-Fi monitor/scan helper and narrowly scoped sudoers rule
# Mirrors RK3326_Linux's rk-scan pattern: ark may invoke only /usr/local/sbin/rk-stump-wifi,
# which strictly validates wireless interfaces via /sys/class/ieee80211 and restores NetworkManager on exit.
say "Installing universal Wi-Fi capture helper at $WIFI_HELPER ..."
run_sudo install -o root -g root -m 0755 "$SRC_ROOT/host/stump-recon/wifi_mon.py" "$WIFI_HELPER"
SUDO_TMP="$(mktemp)"
cat > "$SUDO_TMP" <<'EOF'
# Allow STUMP RF Recon (user ark) to drive USB Wi-Fi monitor/scan capture cleanly
ark ALL=(root) NOPASSWD: /usr/local/sbin/rk-stump-wifi
EOF
if command -v visudo >/dev/null 2>&1; then
    visudo -cf "$SUDO_TMP" >/dev/null
fi
run_sudo install -o root -g root -m 0440 "$SUDO_TMP" "$WIFI_SUDOERS"
rm -f "$SUDO_TMP"

# Check common USB Wi-Fi firmware packs (all shipped in RK3326_Linux)
FW_COUNT=0
for fw in rt2870.bin mt7601u.bin ath9k_htc/htc_9271-1.4.0.fw rtw88/rtw8821c_fw.bin rtw88/rtw8822b_fw.bin; do
    if [ -f "/usr/lib/firmware/$fw" ] || [ -f "/lib/firmware/$fw" ]; then
        FW_COUNT=$((FW_COUNT + 1))
    fi
done
say "USB Wi-Fi firmware check: $FW_COUNT/5 major dongle firmware sets present (RT3070, MT7601U, AR9271, Realtek rtw88)."

# Verify dialout membership on a live handheld (already set by RK3326_Linux build-image.sh)
if [ "$(id -u)" -ne 0 ] && ! id -nG | grep -qw dialout; then
    say "Adding $(id -un) to dialout group for USB OTG serial access..."
    run_sudo usermod -aG dialout "$(id -un)" || true
fi

# Validate whichever dock JSON is active
ACTIVE_DOCK="$DOCK_DIR/stump-recon.json"
[ -f "$BAKED_DOCK" ] && ACTIVE_DOCK="$BAKED_DOCK"
if [ -f "$ACTIVE_DOCK" ]; then
    python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert d.get('name') and d.get('exec')" \
        "$ACTIVE_DOCK"
fi

say "Done. Open 'STUMP Recon' from the RK3326 desktop dock (quit with SELECT+START)."
