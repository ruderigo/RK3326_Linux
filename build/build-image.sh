#!/bin/bash
# Build a flashable SD card image for an RK3326 handheld.
#
#   sudo build/build-image.sh <upstream dir> <out dir>
#
# <upstream dir> is a checkout of arkos4clone at the commit in upstream.env
# (only uboot/, boot/dArkOS/consoles/, dtbTools/ and the kernel modules are
# needed; the workflow makes that checkout).
#
# Environment:
#   CONSOLE   arkos4clone console folder   (default "r36max type1")
#   KERNEL    5.10 or 4.4                  (default 5.10)
#   HOSTNAME_ the system's host name       (default from the console: r36max, r36s)
#   VERSION   shown in /etc/os-release     (default "dev")
#   ROOT_MB   size of the system partition (default 3072)
#   ROOTFS_DIR  a ready-made system folder: skips the Debian install, to test
#               the image assembly on any machine
#
# Must run as root on an arm64 Linux machine: the Debian system is installed
# with debootstrap and finished in a chroot. No loop devices are used: the
# two filesystems are built as files and written into the image at their
# offsets.
#
# Card layout (512-byte sectors), the one the Rockchip boot chain expects:
#   sector    64   idbloader.img
#   sector 16384   uboot.img      (8 MiB)
#   sector 24576   trust.img      (12 MiB)
#   16 MiB         partition 1, FAT32 "BOOT", 256 MiB: kernel, device tree, boot.ini
#   272 MiB        partition 2, ext4 "RKROOT": the system
#   after it       partition 3, ext4 "RKDATA": made at the first start, fills the card
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
. "$HERE/upstream.env"

UP=${1:?usage: build-image.sh <upstream dir> <out dir>}
OUT=${2:?usage: build-image.sh <upstream dir> <out dir>}
CONSOLE=${CONSOLE:-r36max type1}
KERNEL=${KERNEL:-5.10}
VERSION=${VERSION:-dev}
ROOT_MB=${ROOT_MB:-3072}
BOOT_MB=256
case $CONSOLE in
    r36max*) DEF_HOST=r36max ;;
    origin*|clone*|sauce*) DEF_HOST=r36s ;;
    *) DEF_HOST=${CONSOLE%% *} ;;
esac
HOSTNAME_=${HOSTNAME_:-$DEF_HOST}

say() { printf '\n=== %s\n' "$*"; }
die() { echo "build-image: $*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "run as root"
[ -n "${ROOTFS_DIR:-}" ] || [ "$(uname -m)" = aarch64 ] || die "run on an arm64 machine (the workflow uses an arm64 runner)"
[ -n "${ROOTFS_DIR:-}" ] || command -v debootstrap >/dev/null || die "missing tool: debootstrap"
for t in mkfs.vfat mkfs.ext4 mcopy sfdisk xz python3 fdtput fdtget; do
    command -v $t >/dev/null || die "missing tool: $t"
done
CONS="$UP/boot/dArkOS/consoles"
MODS="$UP/rootfs/dArkOS/usr/lib/modules"
for f in "$UP/uboot/idbloader.img" "$UP/uboot/uboot.img" "$UP/uboot/trust.img" \
         "$CONS/$CONSOLE/boot.ini" "$CONS/kernel/5.10/Image" "$CONS/kernel/original/Image"; do
    [ -f "$f" ] || die "missing in the upstream checkout: $f"
done
[ -d "$MODS" ] || die "missing in the upstream checkout: $MODS"

WORK=$(mktemp -d /var/tmp/rkbuild.XXXXXX)
ROOTFS="$WORK/rootfs"; BOOT="$WORK/boot"
cleanup() {
    for m in dev/pts dev proc sys; do mountpoint -q "$ROOTFS/$m" && umount -l "$ROOTFS/$m"; done
    rm -rf "$WORK"
}
trap cleanup EXIT
mkdir -p "$ROOTFS" "$BOOT" "$OUT"

# ---------------------------------------------------------------- system
build_system() {
say "Debian $DEBIAN_SUITE (arm64), base"
BASE=systemd-sysv,systemd-timesyncd,udev,dbus,kmod,sudo,ca-certificates,netbase,tzdata,procps,iproute2,util-linux,fdisk,e2fsprogs,dosfstools
SCRIPT=/usr/share/debootstrap/scripts/$DEBIAN_SUITE
[ -e "$SCRIPT" ] || SCRIPT=/usr/share/debootstrap/scripts/sid
debootstrap --arch=arm64 --variant=minbase --components=main,non-free-firmware \
    --include="$BASE" "$DEBIAN_SUITE" "$ROOTFS" "$DEBIAN_MIRROR" "$SCRIPT"

cat > "$ROOTFS/etc/apt/sources.list" <<SRC
deb $DEBIAN_MIRROR $DEBIAN_SUITE main non-free-firmware
deb $DEBIAN_MIRROR $DEBIAN_SUITE-updates main non-free-firmware
deb http://security.debian.org/debian-security $DEBIAN_SUITE-security main non-free-firmware
SRC

mount -t proc proc "$ROOTFS/proc"
mount -t sysfs sys "$ROOTFS/sys"
mount --bind /dev "$ROOTFS/dev"
mount --bind /dev/pts "$ROOTFS/dev/pts"
# no services start while packages install
printf '#!/bin/sh\nexit 101\n' > "$ROOTFS/usr/sbin/policy-rc.d"; chmod +x "$ROOTFS/usr/sbin/policy-rc.d"
in_root() { chroot "$ROOTFS" env DEBIAN_FRONTEND=noninteractive LC_ALL=C "$@"; }

say "Packages"
in_root apt-get update -q
PKGS=$(grep -vE '^\s*(#|$)' "$HERE/packages.txt" | tr '\n' ' ')
in_root apt-get install -y -q --no-install-recommends $PKGS
# optional packages (dongle firmware, conveniences): a missing one must not stop the build
MISSING=
for p in $(grep -vE '^\s*(#|$)' "$HERE/packages-optional.txt"); do
    in_root apt-get install -y -q --no-install-recommends "$p" || MISSING="$MISSING $p"
done
[ -z "$MISSING" ] || echo "WARNING: optional packages not installed:$MISSING"
in_root apt-get clean
rm -rf "$ROOTFS"/var/lib/apt/lists/*

say "Kernel modules (4.4 and 5.10)"
mkdir -p "$ROOTFS/usr/lib/modules"
cp -a "$MODS"/. "$ROOTFS/usr/lib/modules/"
chown -R 0:0 "$ROOTFS/usr/lib/modules"
ls "$ROOTFS/usr/lib/modules"

say "System files"
cp -a "$REPO/overlay/." "$ROOTFS/"
# everything we add belongs to root, whoever owns the checkout
( cd "$REPO/overlay" && find . -mindepth 1 ) | while read -r f; do chown -h 0:0 "$ROOTFS/$f"; done
chmod 755 "$ROOTFS"/usr/local/sbin/rk-*
echo "$HOSTNAME_" > "$ROOTFS/etc/hostname"
printf '127.0.0.1\tlocalhost\n127.0.1.1\t%s\n::1\tlocalhost ip6-localhost ip6-loopback\n' "$HOSTNAME_" > "$ROOTFS/etc/hosts"
cat > "$ROOTFS/etc/fstab" <<'FSTAB'
/dev/mmcblk0p2  /      ext4  defaults,noatime                                    0 1
/dev/mmcblk0p1  /boot  vfat  defaults,umask=0022,nofail                          0 2
LABEL=RKDATA    /data  ext4  defaults,noatime,nofail,x-systemd.device-timeout=8s 0 2
FSTAB
mkdir -p "$ROOTFS/boot" "$ROOTFS/data"
cat >> "$ROOTFS/etc/os-release.rk" <<REL
RK_NAME="RK3326 Linux"
RK_VERSION="$VERSION"
RK_CONSOLE="$CONSOLE"
RK_UPSTREAM_COMMIT="$UPSTREAM_COMMIT"
REL
printf 'RK3326 Linux %s  (\\n, \\l)\nWi-Fi address: \\4{wlan0}\n\n' "$VERSION" > "$ROOTFS/etc/issue"

# the user: "ark", as on dArkOS, so the same paths and commands work.
# The first password is "ark" and has to be changed at the first login.
in_root useradd -m -s /bin/bash ark
for g in sudo audio video input dialout plugdev netdev render; do
    in_root getent group $g >/dev/null && in_root usermod -aG $g ark
done
echo 'ark:ark' | in_root chpasswd
in_root chage -d 0 ark
in_root passwd -l root >/dev/null

# every card makes its own SSH host keys and machine id at its first start
rm -f "$ROOTFS"/etc/ssh/ssh_host_*
: > "$ROOTFS/etc/machine-id"
rm -f "$ROOTFS/var/lib/dbus/machine-id"

in_root systemctl enable rk-firstboot.service rk-bootcfg.service ssh.service NetworkManager.service \
    avahi-daemon.service systemd-timesyncd.service
# starting does not wait for a network that may not be there
in_root systemctl disable NetworkManager-wait-online.service 2>/dev/null || true
in_root systemctl mask systemd-networkd-wait-online.service 2>/dev/null || true

rm -f "$ROOTFS/usr/sbin/policy-rc.d"
for m in dev/pts dev proc sys; do umount "$ROOTFS/$m"; done
du -sh "$ROOTFS"
}
if [ -n "${ROOTFS_DIR:-}" ]; then
    # for testing the image assembly only: a ready-made system folder
    say "Using the system in $ROOTFS_DIR (no Debian install)"
    cp -a "$ROOTFS_DIR"/. "$ROOTFS"/
else
    build_system
fi

# ------------------------------------------------------- boot partition
say "Boot partition: $CONSOLE, kernel $KERNEL"
cp -a "$CONS" "$BOOT/consoles"
# console folder -> boot logo folder, from arkos4clone's device selector
python3 - "$UP/dtbTools/internal/console/config.go" > "$BOOT/consoles/logos.txt" <<'PY'
import re, sys
src = open(sys.argv[1], encoding='utf-8').read()
for name, body in re.findall(r'RealName:\s*"([^"]+)"(.*?)(?=RealName:|\Z)', src, flags=re.S):
    m = re.search(r'ExtraSources:\s*\[\]string\{\s*"([^"]+)"', body)
    if m:
        print(f"{name}|{m.group(1).strip('/')}")
PY
grep -q "^$CONSOLE|" "$BOOT/consoles/logos.txt" || echo "WARNING: no boot logo listed for $CONSOLE"

# our changes to the device trees (build/dtb-fixes.txt), in the consoles folder
# itself so that rk-boot-select hands out the changed files too
: > "$BOOT/rk-dtb-fixes.txt"
while IFS='|' read -r console action node prop value; do
    console=$(echo "$console" | xargs); action=$(echo "$action" | xargs)
    node=$(echo "$node" | xargs); prop=$(echo "$prop" | xargs); value=$(echo "${value:-}" | xargs)
    [ -n "$console" ] || continue
    scope=; case $console in *@*) scope=${console##*@}; console=${console%@*} ;; esac
    for dtb in "$BOOT/consoles/$console"/*.dtb "$BOOT/consoles/$console"/5.10/*.dtb; do
        [ -f "$dtb" ] || continue
        case $dtb in */5.10/*) k=5.10 ;; *) k=4.4 ;; esac
        [ -z "$scope" ] || [ "$scope" = "$k" ] || continue
        rel=${dtb#$BOOT/}
        old=$(fdtget -t u "$dtb" "$node" "$prop" 2>/dev/null) ||
            die "dtb-fixes.txt: $node has no $prop in $rel: check the upstream change"
        case $action in
            delete-prop)
                fdtput -d "$dtb" "$node" "$prop"
                fdtget "$dtb" "$node" "$prop" >/dev/null 2>&1 && die "could not remove $prop from $rel"
                echo "removed $prop from $node in $rel" ;;
            set-u32)
                [[ $value =~ ^[0-9]+$ ]] || die "dtb-fixes.txt: set-u32 needs a decimal value for $prop"
                fdtput -t u "$dtb" "$node" "$prop" "$value"
                [ "$(fdtget -t u "$dtb" "$node" "$prop")" = "$value" ] || die "could not set $prop in $rel"
                echo "set $prop to $value (was $old) in $node in $rel" ;;
            *) die "dtb-fixes.txt: unknown action: $action" ;;
        esac | tee -a "$BOOT/rk-dtb-fixes.txt"
    done
done < <(grep -vE '^[[:space:]]*(#|$)' "$HERE/dtb-fixes.txt")

SELECT="$REPO/overlay/usr/local/sbin/rk-boot-select"
# the two ready-made sets a Mac or PC can copy over when one kernel does not start
for k in 4.4 5.10; do
    [ "$k" = 5.10 ] && [ ! -d "$CONS/$CONSOLE/5.10" ] && continue
    "$SELECT" -b "$BOOT" set "$CONSOLE" $k >/dev/null
    d="$BOOT/$([ $k = 5.10 ] && echo default-5.10 || echo fallback-4.4)"
    mkdir "$d"; cp "$BOOT/boot.ini" "$BOOT/Image" "$BOOT"/*.dtb "$d/"
done
"$SELECT" -b "$BOOT" set "$CONSOLE" "$KERNEL"
cp "$REPO/boot-files/wifi.txt" "$REPO/boot-files/README.txt" "$BOOT/"
printf '%s\r\n' "$HOSTNAME_" > "$BOOT/hostname.txt"
ls -la "$BOOT"; cat "$BOOT/boot.ini"

# ------------------------------------------------------------ the image
say "Filesystems"
BOOT_IMG="$WORK/boot.img"; ROOT_IMG="$WORK/root.img"
truncate -s ${BOOT_MB}M "$BOOT_IMG"
mkfs.vfat -F 32 -n BOOT "$BOOT_IMG" >/dev/null
( cd "$BOOT" && for e in *; do mcopy -s -Q -i "$BOOT_IMG" "$e" ::; done )
truncate -s ${ROOT_MB}M "$ROOT_IMG"
# orphan_file and metadata_csum_seed are newer than these kernels: with them
# the system partition would not mount
mkfs.ext4 -q -F -L RKROOT -O ^orphan_file,^metadata_csum_seed -m 1 -d "$ROOTFS" "$ROOT_IMG"

say "Image"
NAME="rk3326-linux-${HOSTNAME_}-${VERSION}"
IMG="$OUT/$NAME.img"
P1_START=32768                                   # 16 MiB
P1_SIZE=$(( BOOT_MB * 2048 ))
P2_START=$(( P1_START + P1_SIZE ))
P2_SIZE=$(( ROOT_MB * 2048 ))
rm -f "$IMG"; truncate -s $(( (P2_START + P2_SIZE) * 512 )) "$IMG"
dd if="$UP/uboot/idbloader.img" of="$IMG" bs=512 seek=64    conv=notrunc status=none
dd if="$UP/uboot/uboot.img"     of="$IMG" bs=512 seek=16384 conv=notrunc status=none
dd if="$UP/uboot/trust.img"     of="$IMG" bs=512 seek=24576 conv=notrunc status=none
dd if="$BOOT_IMG" of="$IMG" bs=1M seek=$(( P1_START / 2048 )) conv=notrunc status=none
dd if="$ROOT_IMG" of="$IMG" bs=1M seek=$(( P2_START / 2048 )) conv=notrunc status=none
sfdisk -q "$IMG" <<PT
label: dos
start=$P1_START, size=$P1_SIZE, type=b
start=$P2_START, size=$P2_SIZE, type=83
PT
sfdisk -l "$IMG"

"$HERE/verify-image.sh" "$IMG" "$UP" "$KERNEL"

say "Compress"
xz -T0 -6 -f "$IMG"
( cd "$OUT" && sha256sum "$NAME.img.xz" > "$NAME.img.xz.sha256" && ls -la )
echo "Done: $OUT/$NAME.img.xz"
