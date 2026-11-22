#!/bin/bash
# Migration 0002: FireFly's identity folder (~/.firefly) onto /data.
#
# 0001 moved the FireFly *code* (~/firefly), but FireFly keeps its identity,
# message database and settings under ~/.firefly (a hidden folder). That is
# the node's address on the mesh, and it was still on the root partition — a
# reflash would have wiped it. This moves it onto /data and symlinks it back,
# like 0001. Idempotent; the adopter's /data copy wins over a baked default.
#
# FireFly requires this folder on a filesystem that keeps permissions; /data
# is ext4, so that holds (unlike exFAT /roms).
set -u

ARK="${RK_ARK:-/home/ark}"
DATA="${RK_DATA:-/data/ark}"
src="$ARK/.firefly"
dst="$DATA/.firefly"

[ -d "$DATA" ] || { mkdir -p "$DATA"; chown ark:ark "$DATA" 2>/dev/null || true; }

if [ -L "$src" ]; then
    exit 0                              # already done on a past run
fi
if [ -e "$dst" ]; then
    [ -e "$src" ] && rm -rf "$src"      # the adopter's copy on /data wins
elif [ -e "$src" ]; then
    mv "$src" "$dst"
else
    # FireFly not set up yet: pre-create and link so the identity is born on
    # /data when FireFly first runs
    mkdir -p "$dst"
fi
ln -s "$dst" "$src"
chown -h ark:ark "$src" 2>/dev/null || true
chown -R ark:ark "$dst" 2>/dev/null || true
echo "rk-migrate 0002: $src -> $dst"
exit 0
