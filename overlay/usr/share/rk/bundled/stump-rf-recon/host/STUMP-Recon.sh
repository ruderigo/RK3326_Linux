#!/bin/sh
# STUMP-Recon.sh — RK3326_Linux & dArkOS compatible launcher for STUMP RF Recon
#
# RK3326_Linux contract (docs/building-apps.md):
#   - Inherit LD_LIBRARY_PATH (/usr/lib/rk-gpu), SDL_VIDEODRIVER=kmsdrm,
#     and SDL_GAMECONTROLLERCONFIG_FILE from rkshell (never overwrite them).
#   - Never invoke `echo ark | sudo -S` (ark already owns dialout/video/input
#     groups, and the password is changed on first boot).
#   - Never reset /dev/tty1 (rkshell manages console handoff and FBIOBLANK).
#   - Store persistent logs & exports under /data/ark/stump-recon (survives reflash).

set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
APP_DIR="$SCRIPT_DIR/stump-recon"
if [ ! -f "$APP_DIR/stump_gui.py" ] && [ -f "/home/ark/stump-rf-recon/stump-recon/stump_gui.py" ]; then
    APP_DIR="/home/ark/stump-rf-recon/stump-recon"
elif [ ! -f "$APP_DIR/stump_gui.py" ] && [ -f "/roms/ports/stump-recon/stump_gui.py" ]; then
    APP_DIR="/roms/ports/stump-recon"
fi

if [ -n "${STUMP_RECON_DATA_DIR:-}" ]; then
    DATA_DIR="$STUMP_RECON_DATA_DIR"
elif [ -d "/data/ark" ] && [ -w "/data/ark" ]; then
    DATA_DIR="/data/ark/stump-recon"
elif [ -d "/roms/ports" ] && [ -w "/roms/ports" ]; then
    DATA_DIR="/roms/ports/stump-recon"
else
    DATA_DIR="${HOME:-/tmp}/stump-recon"
fi

mkdir -p "$DATA_DIR/exports"
LOG_FILE="$DATA_DIR/debug.log"

export PYTHONUNBUFFERED=1
export STUMP_RECON_DATA_DIR="$DATA_DIR"

# Prefer system python3 (links Debian's python3-pygame against /usr/lib/rk-gpu SDL2)
PY="/usr/bin/python3"
if [ ! -x "$PY" ]; then
    PY="$(command -v python3 || true)"
fi

cd "$APP_DIR" || exit 1
exec "$PY" "$APP_DIR/stump_gui.py" >"$LOG_FILE" 2>&1
