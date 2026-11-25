#!/bin/bash
# Builds the kernel modules listed in build/kernel-modules.env for the 5.10
# kernel the image starts, from that kernel's own source and configuration.
#
#   build/build-kernel-modules.sh OUT [REFERENCE.ko]
#
# OUT gets <release>/kernel/<path>/<module>.ko, laid out as under
# /usr/lib/modules, and build-image.sh adds it (KMODS=OUT). REFERENCE.ko is a
# module of the shipped kernel (arkos4clone's cp210x.ko): each built module
# must say it is for exactly the same kernel, or the handheld refuses it.
#
# Only the module is built, not the kernel: the configuration is the
# kernel's own with the module switched on, which changes nothing else.
# Needs git, make, gcc (aarch64, or CROSS_COMPILE), flex, bison, bc,
# libssl-dev, libelf-dev, kmod. The 4.4 fallback kernel is not covered.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/kernel-modules.env"
OUT="${1:?usage: build-kernel-modules.sh OUT [REFERENCE.ko]}"
REF="${2:-}"
say() { echo "== $*"; }
die() { echo "build-kernel-modules: $*" >&2; exit 1; }
for t in git make flex bison bc modinfo "${CROSS_COMPILE:-}gcc" "${CROSS_COMPILE:-}strip"; do
    command -v "$t" >/dev/null || die "missing tool: $t"
done
[ "$(uname -m)" = aarch64 ] || [ -n "${CROSS_COMPILE:-}" ] || die "not an arm64 machine: set CROSS_COMPILE (aarch64-linux-gnu-)"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
WORK="${KMOD_WORK:-$OUT/.work}"
SRC="$WORK/src"; B="$WORK/build"

say "Kernel source at ${KERNEL_COMMIT::12}"
if [ "$(git -C "$SRC" rev-parse HEAD 2>/dev/null)" != "$KERNEL_COMMIT" ]; then
    rm -rf "$SRC"; mkdir -p "$SRC"
    git -C "$SRC" init -q
    git -C "$SRC" remote add origin "$KERNEL_REPO"
    git -C "$SRC" fetch -q --depth 1 origin "$KERNEL_COMMIT"
    git -C "$SRC" checkout -q FETCH_HEAD
fi

# As tools/arkos4clone/build.sh builds the kernel: LOCALVERSION set, even
# empty, keeps "+" off the release.
mk() { make -C "$SRC" O="$B" ARCH=arm64 CROSS_COMPILE="${CROSS_COMPILE:-}" LOCALVERSION= "$@"; }
rm -rf "$B"
say "Configuration: $KERNEL_DEFCONFIG, with the extra modules"
mk "$KERNEL_DEFCONFIG" >/dev/null
MODS=()
while read -r opt path; do
    [ -n "$opt" ] || continue
    "$SRC/scripts/config" --file "$B/.config" -m "$opt"
    MODS+=("$opt $path")
done <<< "$EXTRA_MODULES"
mk olddefconfig >/dev/null
for m in "${MODS[@]}"; do
    grep -q "^CONFIG_${m%% *}=m$" "$B/.config" || die "CONFIG_${m%% *} did not become a module (a dependency is off?)"
done
mk -j"$(nproc)" modules_prepare >/dev/null
REL="$(cat "$B/include/config/kernel.release")"
[ "$REL" = "$KERNEL_RELEASE" ] || die "the source builds $REL, the image starts $KERNEL_RELEASE"
magic() { modinfo -F vermagic "$1"; }
[ -z "$REF" ] || [ -f "$REF" ] || die "no such reference module: $REF"

rm -rf "$OUT/$REL"
for m in "${MODS[@]}"; do
    path="${m#* }"
    say "Building $path"
    mk "$path" 2>&1 | grep -v -e 'vmlinux.symvers" is missing' -e 'may not have dependencies' -e 'Symbol info of vmlinux is missing' || true
    [ -f "$B/$path" ] || die "$path was not built"
    if [ -n "$REF" ]; then
        [ "$(magic "$B/$path")" = "$(magic "$REF")" ] ||
            die "$path is for '$(magic "$B/$path")', the shipped kernel's modules are for '$(magic "$REF")'"
    fi
    install -D -m 0644 "$B/$path" "$OUT/$REL/kernel/$path"
    "${CROSS_COMPILE:-}strip" --strip-debug "$OUT/$REL/kernel/$path"
    echo "   $(magic "$OUT/$REL/kernel/$path")   $(du -k "$OUT/$REL/kernel/$path" | cut -f1) KB"
done
[ -n "${KMOD_WORK:-}" ] || rm -rf "$WORK"
say "Done: $OUT/$REL"
