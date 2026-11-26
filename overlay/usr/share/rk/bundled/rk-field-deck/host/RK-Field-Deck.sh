#!/bin/sh
# RK Field Deck launcher for RK3326_Linux (v1.2.0+) and Desktop Linux
# Strictly inherits SDL_VIDEODRIVER (kmsdrm) and rotated Mali LD_LIBRARY_PATH from rkshell.
# Zero sudo -S calls; user ark already holds dialout/video/input/render groups.

set -eu

APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/field-deck" && pwd)"
DATA_DIR="${RK_FIELD_DECK_DATA_DIR:-/data/ark/field-deck}"
if [ ! -d "/data/ark" ] && [ -z "${RK_FIELD_DECK_DATA_DIR:-}" ]; then
    DATA_DIR="${HOME}/.local/share/rk-field-deck"
fi

mkdir -p "$DATA_DIR/reports" "$DATA_DIR/captures"
export RK_FIELD_DECK_DATA_DIR="$DATA_DIR"

exec python3 "$APP_DIR/field_deck.py" "$@" 2>>"$DATA_DIR/debug.log"
