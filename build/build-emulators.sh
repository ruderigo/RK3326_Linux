#!/bin/bash
# Build the emulator bundle: RetroArch for this GPU, and the cores for the
# machines people play on it (PlayStation, Nintendo 64, PSP, and the 8- and
# 16-bit ones). Debian's RetroArch shows nothing on this panel.
#
#   build/build-emulators.sh <out dir>
#
# Makes <out dir>/rk-emulators-<n>.tar.xz and its .sha256. The archive
# unpacks at / into /opt/rk-emulators:
#   bin/retroarch        RetroArch, drawing with OpenGL ES straight to the
#                        panel (KMS), which on the handheld is dArkOS's Mali
#                        driver in /usr/lib/rk-gpu
#   cores/               the cores and their .info files
#   VERSION              what went in
#
# RetroArch is compiled here; the cores are dArkOS's own builds, fetched at a
# pinned commit (build/emulators.env). Run on arm64 Debian for a bundle the
# handheld can use (the workflow does); on another machine it still builds,
# which is how the recipe is checked.
#
# RetroArch is built the way dArkOS builds it, without its handheld-specific
# patches, and with RetroArch's own driver for RK3326 panels mounted on their
# side (--enable-odroidgo2: it turns the picture with the Rockchip 2D chip,
# librga). As it comes it knows one turn, the ODROID-GO Advance's;
# build/patches/retroarch-0001 lets it take any, from RK_ROTATE, which the
# desktop sets for what it opens. On a panel that is not turned the driver
# steps aside and the plain KMS one draws, as before.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/emulators.env"
OUT=${1:?usage: build-emulators.sh <out dir>}
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
WORK=${WORK:-$(mktemp -d /var/tmp/rkemu.XXXXXX)}
say() { printf '\n=== %s\n' "$*"; }
die() { echo "build-emulators: $*" >&2; exit 1; }

for t in git make gcc g++ pkg-config unzip xz sha256sum patch meson ninja patchelf; do
    command -v $t >/dev/null || die "missing tool: $t"
done
for lib in libdrm gbm egl glesv2 alsa libudev freetype2 zlib libpng; do
    pkg-config --exists "$lib" || die "missing development files: $lib"
done

fetch_at() {    # fetch_at REPO COMMIT DIR [PATH...]: only the named paths of one commit
    local repo="$1" commit="$2" dir="$3"; shift 3
    rm -rf "$dir"; git init -q "$dir"
    git -C "$dir" remote add origin "$repo"
    git -C "$dir" sparse-checkout init --no-cone
    ( set -f; git -C "$dir" sparse-checkout set "$@" )
    git -C "$dir" fetch -q --depth 1 --filter=blob:none origin "$commit"
    git -C "$dir" checkout -q FETCH_HEAD
}

# librga: the library for the Rockchip 2D chip, which turns the picture on a
# panel mounted on its side. Debian does not have it; it is built as dArkOS
# builds it, from the same commit, and goes in the bundle beside RetroArch,
# where the turned SDL2s find it too (rkshell/panel.py).
say "librga (at ${RGA_COMMIT:0:7})"
fetch_at "$RGA_REPO" "$RGA_COMMIT" "$WORK/linux-rga" '/*'
rm -rf "$WORK/rga" "$WORK/linux-rga/build"
meson setup "$WORK/linux-rga/build" "$WORK/linux-rga" --prefix=/usr --libdir=lib --buildtype=release -Dlibdrm=true >/dev/null
meson compile -C "$WORK/linux-rga/build" >/dev/null
DESTDIR="$WORK/rga" meson install -C "$WORK/linux-rga/build" >/dev/null
[ -f "$WORK/rga/usr/lib/librga.so.2" ] && [ -f "$WORK/rga/usr/include/rga/RgaApi.h" ] || die "librga did not build"
export CFLAGS_RGA="-I$WORK/rga/usr/include" LDFLAGS="-L$WORK/rga/usr/lib"

say "RetroArch $RETROARCH_TAG"
[ -d "$WORK/retroarch/.git" ] || git clone -q --depth 1 --branch "$RETROARCH_TAG" "$RETROARCH_REPO" "$WORK/retroarch"
cd "$WORK/retroarch"
for p in "$HERE"/patches/retroarch-*.patch; do
    # a work folder used again already has them
    if patch -Np1 --dry-run -s < "$p" >/dev/null 2>&1; then patch -Np1 -s < "$p"; echo "applied $(basename "$p")"
    elif patch -Rp1 --dry-run -s < "$p" >/dev/null 2>&1; then echo "already applied: $(basename "$p")"
    else die "$(basename "$p") does not apply to RetroArch $RETROARCH_TAG"; fi
done
FLAGS="-O2 -fomit-frame-pointer -DNDEBUG"
[ "$(uname -m)" != aarch64 ] || FLAGS="-Ofast -march=armv8-a -mtune=cortex-a35 -fomit-frame-pointer -DNDEBUG"
FLAGS="$FLAGS $CFLAGS_RGA"
CFLAGS="$FLAGS" ./configure \
    --disable-caca --disable-mali_fbdev --disable-opengl --disable-opengl_core --disable-opengl1 \
    --disable-qt --disable-sdl --disable-sdl2 --disable-vg --disable-vulkan --disable-vulkan_display \
    --disable-wayland --disable-x11 --disable-xrandr --disable-jack --disable-pulse --disable-oss \
    --disable-microphone --disable-ffmpeg --disable-discord --disable-v4l2 --disable-systemd \
    --enable-alsa --enable-egl --enable-freetype --enable-kms --enable-networking --enable-odroidgo2 \
    --enable-opengles --enable-opengles3 --enable-opengles3_1 --enable-opengles3_2 \
    --enable-udev --enable-zlib
make -j"$(nproc)"
strip retroarch
patchelf --set-rpath '$ORIGIN/../lib' retroarch          # its librga is beside it in the bundle
LD_LIBRARY_PATH="$WORK/rga/usr/lib" ./retroarch --features > "$WORK/features.txt" 2>&1 || true
grep -qiE "kms.*yes|KMS" "$WORK/features.txt" || echo "WARNING: could not confirm KMS in --features"
grep -q "GO2 DRM\] RK_ROTATE" retroarch || die "the driver for turned panels is not in this RetroArch"

ROOT="$WORK/root/opt/rk-emulators"
rm -rf "$WORK/root"; mkdir -p "$ROOT/bin" "$ROOT/cores"
install -m 0755 retroarch "$ROOT/bin/retroarch"
mkdir -p "$ROOT/lib"
cp -a "$WORK"/rga/usr/lib/librga.so.2* "$ROOT/lib/"
strip "$ROOT"/lib/librga.so.2.*
"$ROOT/bin/retroarch" --version >/dev/null 2>&1 || die "RetroArch does not start from the bundle (a library it needs is not found)"

say "Cores (dArkOS's RK3326 builds, at ${CORES_COMMIT:0:7})"
paths=(); for c in $CORES; do paths+=("/aarch64/${c}_libretro.so.zip"); done
fetch_at "$CORES_REPO" "$CORES_COMMIT" "$WORK/cores" "${paths[@]}"
rm -rf "$WORK/info"; git clone -q --depth 1 "$INFO_REPO" "$WORK/info"
for c in $CORES; do
    unzip -q -o "$WORK/cores/aarch64/${c}_libretro.so.zip" -d "$ROOT/cores"
    [ -f "$ROOT/cores/${c}_libretro.so" ] || die "the core $c did not unpack as ${c}_libretro.so"
    if [ -f "$WORK/info/${c}_libretro.info" ]; then
        install -m 0644 "$WORK/info/${c}_libretro.info" "$ROOT/cores/"
    else
        echo "WARNING: no .info file for $c"
    fi
done
chmod 0644 "$ROOT"/cores/*

cat > "$ROOT/VERSION" <<TXT
bundle $BUNDLE
retroarch $RETROARCH_TAG ($(git -C "$WORK/retroarch" rev-parse --short HEAD)), built for $(uname -m), with build/patches
librga from $RGA_REPO at $RGA_COMMIT
cores $CORES
cores from $CORES_REPO at $CORES_COMMIT
core info from $INFO_REPO at $(git -C "$WORK/info" rev-parse HEAD)
TXT

say "Archive"
NAME="rk-emulators-$BUNDLE.tar.xz"
tar -C "$WORK/root" --owner=0 --group=0 --sort=name -cJf "$OUT/$NAME" opt
( cd "$OUT" && sha256sum "$NAME" > "$NAME.sha256" )
cat "$ROOT/VERSION"; ls -l "$OUT/$NAME"; du -sh "$ROOT"/*
