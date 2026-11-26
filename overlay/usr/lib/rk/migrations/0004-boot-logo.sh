#!/bin/bash
# Step 4: our picture at switch-on, on a card flashed before the image had
# it. An update does not replace the boot partition, so its logo stayed
# arkos4clone's. This writes ours once, for the handheld the card starts and
# for every other one in consoles/logo. After this step the logo.bmp on BOOT
# is the owner's: no later update writes over it.
[ -z "${RK_ARK:-}${RK_DATA:-}${RK_MIG_DIR:-}" ] || exit 0      # under test: not this machine's boot partition
BOOT="${RK_BOOT:-/boot}"
# not mounted (the card's first partition did not answer): try again at the next start
mountpoint -q "$BOOT" || { echo "rk-migrate 0004: $BOOT is not mounted"; exit 1; }
# no logo folders: a boot partition that is not ours. Nothing to do, and no reason to stop later steps.
[ -d "$BOOT/consoles/logo" ] || exit 0
# a card flashed with an image that has our logo: nothing to write
[ -e "$BOOT/consoles/logo/ours.txt" ] && exit 0
python3 /usr/lib/rk/bootlogo.py boot "$BOOT" || echo "rk-migrate 0004: the boot logo was not replaced"
exit 0
