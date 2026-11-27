#!/bin/bash
# Step 6: the emulator cores that draw in 3D (both Nintendo 64 cores and
# PPSSPP) look for the graphics driver under the names libEGL.so and
# libGLESv2.so, without a version. The image had only libEGL.so.1 and
# libGLESv2.so.2, so those cores did not load. The two missing names are
# links to the same driver; an update cannot bring links (they are made by
# the image build), so they are made here.
[ -z "${RK_ARK:-}${RK_DATA:-}${RK_MIG_DIR:-}" ] || exit 0      # under test: not this machine's libraries
GPU="${RK_GPU_DIR:-/usr/lib/rk-gpu}"
[ -f "$GPU/libmali.so" ] || exit 0
for n in libEGL.so libGLESv2.so; do
    [ -e "$GPU/$n" ] || ln -s libmali.so "$GPU/$n" || echo "rk-migrate 0006: $GPU/$n was not made"
done
exit 0
