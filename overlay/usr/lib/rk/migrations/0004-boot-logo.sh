#!/bin/bash
# Step 4: our picture at switch-on, on a card flashed before the image had
# it. An update does not replace the boot partition, so its logo stayed
# arkos4clone's. From this version on rk-update writes the logo at every
# update; this step does it for the update that brings that rk-update (the
# one running then is the old one, which does not).
[ -z "${RK_ARK:-}${RK_DATA:-}${RK_MIG_DIR:-}" ] || exit 0      # under test: not this machine's boot partition
BOOT="${RK_BOOT:-/boot}"
# not mounted (the card's first partition did not answer): try again at the next start
mountpoint -q "$BOOT" || { echo "rk-migrate 0004: $BOOT is not mounted"; exit 1; }
# no logo folders: a boot partition that is not ours. Nothing to do, and no reason to stop later steps.
[ -d "$BOOT/consoles/logo" ] || exit 0
python3 /usr/lib/rk/bootlogo.py boot "$BOOT" || echo "rk-migrate 0004: the boot logo was not replaced"
exit 0
