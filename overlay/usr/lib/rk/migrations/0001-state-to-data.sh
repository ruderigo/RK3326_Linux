#!/bin/bash
# Migration 0001: the apps' state lives on /data, not on the root partition.
#
# Why: a reflash replaces the root partition but keeps /data. FireFly and the
# Stump keep a Reticulum identity (the node's address on the mesh) and their
# config under /home/ark, on the root partition — so a reflash would strand
# the adopter as a new node and wipe their setup. This moves each app's folder
# onto /data/ark and leaves a symlink behind, so the apps still find their
# files at the old path, rk-apps still updates them in place, and a reflash
# keeps the identity and the setup.
#
# Idempotent: a folder already moved (its old path is a symlink) is skipped.
# A fresh card keeps the adopter's /data copy over the image's baked default,
# so reflashing to upgrade never loses what they had.
set -u

ARK="${RK_ARK:-/home/ark}"
DATA="${RK_DATA:-/data/ark}"

# the app state worth keeping across a reflash (identity, config, data, and
# the app files themselves, which are large but harmless to carry along)
NAMES=".reticulum firefly R36MAX-Stump stump_r36max Stump ports"

[ -d "$DATA" ] || { mkdir -p "$DATA"; chown ark:ark "$DATA"; }

# The copy on the system partition gives way to the one on /data. An app's
# code is the image's own and is dropped. A settings folder (its name starts
# with a dot) may have been written by the owner since a reflash that did not
# link it: that one is kept beside the other, never deleted.
set_aside_or_drop() {
    local src="$1" name aside
    name=$(basename "$src")
    case "$name" in
        .*) if [ -n "$(ls -A "$src" 2>/dev/null)" ]; then
                aside="$DATA/$name.set-aside-$(date +%Y%m%d)"
                [ -e "$aside" ] && aside="$aside-$$"
                mv "$src" "$aside" && chown -R ark:ark "$aside" 2>/dev/null
                echo "rk-migrate 0001: $src held other files; they are kept in $aside"
                return 0
            fi ;;
    esac
    rm -rf "$src"
}

move_one() {           # $1 = source path, $2 = destination on /data
    local src="$1" dst="$2"
    if [ -L "$src" ]; then
        return 0                       # already a symlink: done on a past run
    fi
    if [ -e "$dst" ]; then
        # the adopter's copy is already on /data (e.g. kept across a reflash);
        # drop the image's default and point at theirs
        [ -e "$src" ] && set_aside_or_drop "$src"
    elif [ -e "$src" ]; then
        mv "$src" "$dst"
    else
        return 0                       # neither exists: the app is not installed
    fi
    ln -s "$dst" "$src"
    chown -h ark:ark "$src" 2>/dev/null || true
    chown -R ark:ark "$dst" 2>/dev/null || true
    echo "rk-migrate 0001: $src -> $dst"
}

for name in $NAMES; do
    move_one "$ARK/$name" "$DATA/$name"
done

# the Stump's cockpit writes under /roms/ports; keep that too
ROMS="${RK_ROMS:-/roms}"
if [ -d "$ROMS/ports/stump_r36max" ] && [ ! -L "$ROMS/ports/stump_r36max" ]; then
    if [ -e "$DATA/roms-stump_r36max" ]; then
        rm -rf "$ROMS/ports/stump_r36max"
    else
        mkdir -p "$DATA"; mv "$ROMS/ports/stump_r36max" "$DATA/roms-stump_r36max"
    fi
    ln -s "$DATA/roms-stump_r36max" "$ROMS/ports/stump_r36max"
    chown -h ark:ark "$ROMS/ports/stump_r36max" 2>/dev/null || true
    chown -R ark:ark "$DATA/roms-stump_r36max" 2>/dev/null || true
    echo "rk-migrate 0001: $ROMS/ports/stump_r36max -> $DATA/roms-stump_r36max"
fi

exit 0
