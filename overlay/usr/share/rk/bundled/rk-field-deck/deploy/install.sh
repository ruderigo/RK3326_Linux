#!/usr/bin/env bash
# Re-runnable installer for RK Field Deck on RK3326_Linux (v1.2.0+)
set -euo pipefail

PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARK_HOME="${ARK_HOME:-/home/ark}"
APP_DST="$ARK_HOME/rk-field-deck"
DATA_DIR="${RK_FIELD_DECK_DATA_DIR:-/data/ark/field-deck}"
DOCK_DIR="${RK_DOCK_DIR:-/data/ark/apps}"

mkdir -p "$APP_DST/field-deck" "$DATA_DIR/reports" "$DATA_DIR/captures" "$DOCK_DIR"

cp "$PKG_DIR/VERSION" "$APP_DST/VERSION"
cp "$PKG_DIR/host/RK-Field-Deck.sh" "$APP_DST/RK-Field-Deck.sh"
cp "$PKG_DIR/host/field-deck/field_deck.py" "$APP_DST/field-deck/field_deck.py"
cp "$PKG_DIR/host/field-deck/tool_runner.py" "$APP_DST/field-deck/tool_runner.py"
cp "$PKG_DIR/host/field-deck/wifi_mon.py" "$APP_DST/field-deck/wifi_mon.py"
cp "$PKG_DIR/deploy/rk-field-deck.json" "$DOCK_DIR/rk-field-deck.json"

chmod 0755 "$APP_DST/RK-Field-Deck.sh" \
           "$APP_DST/field-deck/field_deck.py" \
           "$APP_DST/field-deck/tool_runner.py" \
           "$APP_DST/field-deck/wifi_mon.py"

if [ "$(id -u)" -eq 0 ] && id -u ark >/dev/null 2>&1; then
    chown -R ark:ark "$APP_DST" "$DATA_DIR" "$DOCK_DIR/rk-field-deck.json"
fi

# Install root-owned, stdin-controlled privilege helpers matching rk-scan
install_root_helpers() {
    local sudo_prefix=""
    if [ "$(id -u)" -ne 0 ]; then
        sudo_prefix="sudo"
    fi
    $sudo_prefix install -o root -g root -m 0755 "$PKG_DIR/host/field-deck/tool_runner.py" /usr/local/sbin/rk-field-tool
    $sudo_prefix install -o root -g root -m 0755 "$PKG_DIR/host/field-deck/wifi_mon.py" /usr/local/sbin/rk-field-wifi

    local tmp_sudo
    tmp_sudo="$(mktemp)"
    cat >"$tmp_sudo" <<'EOF'
# RK Field Deck root-isolated helpers (allowlisted diagnostic tools + universal Wi-Fi capture)
ark ALL=(root) NOPASSWD: /usr/local/sbin/rk-field-tool run, /usr/local/sbin/rk-field-wifi
EOF
    if command -v visudo >/dev/null 2>&1 && visudo -cf "$tmp_sudo" >/dev/null 2>&1; then
        $sudo_prefix install -o root -g root -m 0440 "$tmp_sudo" /etc/sudoers.d/rk-field-deck
    else
        echo "Warning: visudo validation failed; skipped /etc/sudoers.d/rk-field-deck" >&2
    fi
    rm -f "$tmp_sudo"
}

if [ "$(id -u)" -eq 0 ] || sudo -n true >/dev/null 2>&1; then
    install_root_helpers
else
    echo "Note: run 'sudo bash $0' once to install /usr/local/sbin/rk-field-tool and /usr/local/sbin/rk-field-wifi."
fi

echo "RK Field Deck ($(cat "$APP_DST/VERSION")) installed to $APP_DST"
echo "Dock entry: $DOCK_DIR/rk-field-deck.json"
echo "Reports & captures: $DATA_DIR"
