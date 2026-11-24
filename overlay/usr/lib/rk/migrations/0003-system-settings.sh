#!/bin/bash
# Step 3: the settings that keep the system light (a small log, no package
# work in the background, swap tuned for compressed memory), on a card that
# was flashed before they were part of the image.
[ -z "${RK_ARK:-}${RK_DATA:-}${RK_MIG_DIR:-}" ] || exit 0      # under test: not this machine's settings
/usr/local/sbin/rk-sysconf
# a log that grew before the limit existed
journalctl --vacuum-size=16M >/dev/null 2>&1 || true
# package files already installed, and lists in the old uncompressed form
apt-get clean >/dev/null 2>&1 || true
rm -rf /var/lib/apt/lists/* 2>/dev/null || true
exit 0
