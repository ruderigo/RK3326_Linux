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
#   CONSOLE   arkos4clone console folder the image starts on (default "r36max
#             type1"). Every console's boot files are on the card: another
#             handheld is chosen on the boot partition, without a rebuild.
#   KERNEL    5.10 or 4.4                  (default 5.10)
#   HOSTNAME_ the system's host name       (default from the console: r36max, r36s)
#   VERSION   shown in /etc/os-release     (default "dev")
#   ROOT_MB   size of the system partition (default 6144; empty space
#             compresses away, so the download stays small)
#   EMULATORS a bundle from build/build-emulators.sh to put in the image
#   KMODS     the folder build/build-kernel-modules.sh made: modules the 5.10
#             kernel's own build leaves out (the CH340 serial driver). "none"
#             builds an image without them.
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
#   after it       partition 3, ext4 "RKDATA": made at the first start, 16 GiB
#   after it       partition 4, exFAT "RKSHARE": made at the first start, the rest
#                  of the card; the one a computer shows, for games and packages
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
. "$HERE/upstream.env"

UP=${1:?usage: build-image.sh <upstream dir> <out dir>}
OUT=${2:?usage: build-image.sh <upstream dir> <out dir>}
CONSOLE=${CONSOLE:-r36max type1}
KERNEL=${KERNEL:-5.10}
VERSION=${VERSION:-dev}
KMODS=${KMODS:-}
ROOT_MB=${ROOT_MB:-6144}
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
FIRMWARE="$UP/rootfs/dArkOS/usr/lib/firmware"     # only what build/firmware-upstream.txt names is checked out
# dArkOS's graphics for the apps the dock opens: the Mali GPU driver and the
# SDL2 built against it (the panel only shows what goes through these), and
# its controller database (the right SELECT/START for this pad)
MALI="$UP/rootfs/dArkOS/usr/lib/aarch64-linux-gnu/mali/libmali-bifrost-g31-g29p1.so"
SDLRK="$UP/rootfs/dArkOS/home/ark/.quirks/rotate/sdl2/64/libSDL2-2.0.so.0.3200.10.norotate"
PADDB="$UP/rootfs/dArkOS/opt/inttools/gamecontrollerdb.txt"
# the same SDL2 built for panels mounted a quarter turn, upside down, or three quarters
SDLTURN=("" "${SDLRK%.norotate}.rotate90" "${SDLRK%.norotate}.rotate180" "${SDLRK%.norotate}.rotate270")
for f in "${SDLTURN[@]:1}" "$UP/uboot/idbloader.img" "$UP/uboot/uboot.img" "$UP/uboot/trust.img" \
         "$CONS/$CONSOLE/boot.ini" "$CONS/kernel/5.10/Image" "$CONS/kernel/original/Image" \
         "$MALI" "$SDLRK" "$PADDB"; do
    [ -f "$f" ] || die "missing in the upstream checkout: $f"
done
[ -d "$MODS" ] || die "missing in the upstream checkout: $MODS"
case $KMODS in
    none) ;;
    "") die "KMODS is not set: run build/build-kernel-modules.sh OUT first and pass KMODS=OUT (or KMODS=none for an image without the CH340 serial driver)" ;;
    *) ls "$KMODS"/*/kernel >/dev/null 2>&1 || die "no modules in KMODS=$KMODS"
       command -v depmod >/dev/null || die "missing tool: depmod (kmod)" ;;
esac

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

# Before the first package: what dpkg leaves out of every package (change
# logs, unused translations) and how apt behaves, so the whole system is
# installed under the same rules it keeps on the handheld.
( cd "$REPO/overlay/usr/share/rk/sysconf" && find etc/apt etc/dpkg -type f ) | while read -r f; do
    install -D -m 0644 "$REPO/overlay/usr/share/rk/sysconf/$f" "$ROOTFS/$f"
done

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

# the security toolset (packages-tools.txt): like the optional list, a name
# the archive does not carry is skipped, so the build does not depend on
# every tool being present on trixie arm64. What landed is listed at the end.
TOOLS_MISSING=
for p in $(grep -vE '^\s*(#|$)' "$HERE/packages-tools.txt"); do
    in_root apt-get install -y -q --no-install-recommends "$p" || TOOLS_MISSING="$TOOLS_MISSING $p"
done
[ -z "$TOOLS_MISSING" ] || echo "WARNING: security tools not installed:$TOOLS_MISSING"

# Video (packages-media.txt): the player and its kin. Skipped one by one like
# the lists above; rk-tools install-media installs the same set on a card
# that is already flashed.
MEDIA_MISSING=
for p in $(grep -vE '^\s*(#|$)' "$HERE/packages-media.txt"); do
    in_root apt-get install -y -q --no-install-recommends "$p" || MEDIA_MISSING="$MEDIA_MISSING $p"
done
[ -z "$MEDIA_MISSING" ] || echo "WARNING: Video packages not installed:$MEDIA_MISSING"

# A staple the Debian arm64 archive does not carry: nikto, a Perl web
# scanner, pulled from its source on the runner. Non-fatal.
say "Extra tools (from source)"
if in_root git clone --depth 1 https://github.com/sullo/nikto /opt/nikto; then
    in_root chmod +x /opt/nikto/program/nikto.pl
    in_root ln -sf /opt/nikto/program/nikto.pl /usr/local/bin/nikto
else
    echo "WARNING: nikto not fetched from source"
fi
in_root apt-get clean
rm -rf "$ROOTFS"/var/lib/apt/lists/*

# the languages most often sent along by a computer that logs in over SSH
if [ -x "$ROOTFS/usr/sbin/locale-gen" ]; then
    printf '%s UTF-8\n' en_US.UTF-8 en_CA.UTF-8 en_GB.UTF-8 fr_CA.UTF-8 fr_FR.UTF-8 es_ES.UTF-8 es_MX.UTF-8 es_US.UTF-8 > "$ROOTFS/etc/locale.gen"
    in_root locale-gen
    echo 'LANG=C.UTF-8' > "$ROOTFS/etc/default/locale"
fi

# Time zone (no RTC battery on these; NTP sets the clock over Wi-Fi, this
# names the zone so the desktop shows local time). Change with
# "sudo timedatectl set-timezone <Zone>".
ln -sf /usr/share/zoneinfo/America/Toronto "$ROOTFS/etc/localtime"
echo "America/Toronto" > "$ROOTFS/etc/timezone"

say "Kernel modules (4.4 and 5.10)"
mkdir -p "$ROOTFS/usr/lib/modules"
cp -a "$MODS"/. "$ROOTFS/usr/lib/modules/"
# Modules the 5.10 kernel's own build leaves out, built from its source by
# build/build-kernel-modules.sh (build/kernel-modules.env says which and
# why). depmod rewrites that kernel's module lists so a board that needs one
# loads it when it is plugged in.
if [ "$KMODS" != none ]; then
    . "$HERE/kernel-modules.env"
    # which bundle is in the image and what it put there: rk-tools
    # kernel-modules reads this, and finds nothing to do on a flashed card
    echo "bundle $KMODS_BUNDLE" > "$ROOTFS/usr/lib/modules/rk-kernel-modules.bundle"
    (cd "$KMODS" && find . -path './*/kernel/*' -name '*.ko' | sed 's#^\./##' | sort) >> "$ROOTFS/usr/lib/modules/rk-kernel-modules.bundle"
    for kdir in "$KMODS"/*/; do
        kver=$(basename "$kdir")
        [ -d "$ROOTFS/usr/lib/modules/$kver" ] || die "KMODS has modules for $kver, which is not a kernel of this image"
        cp -a "$kdir". "$ROOTFS/usr/lib/modules/$kver/"
        depmod -b "$ROOTFS/usr" "$kver" || die "depmod failed for $kver"
        (cd "$kdir" && find . -name '*.ko' | sed "s#^\./#  added to $kver: #")
    done
fi
chown -R 0:0 "$ROOTFS/usr/lib/modules"
ls "$ROOTFS/usr/lib/modules"

# Firmware for network adapters that Debian's packages do not carry, from the
# same place as the kernel modules that load it. Debian's files are kept
# where both have one (cp -n).
if [ -d "$FIRMWARE" ]; then
    say "Firmware for USB network adapters (from upstream, beside Debian's)"
    mkdir -p "$ROOTFS/usr/lib/firmware"
    before=$(find "$ROOTFS/usr/lib/firmware" -type f | wc -l)
    cp -an "$FIRMWARE"/. "$ROOTFS/usr/lib/firmware/"
    chown -R 0:0 "$ROOTFS/usr/lib/firmware"
    echo "  $(( $(find "$ROOTFS/usr/lib/firmware" -type f | wc -l) - before )) files added, $(du -sh "$ROOTFS/usr/lib/firmware" | cut -f1) of firmware in all"
else
    echo "WARNING: no upstream firmware checked out ($FIRMWARE): some USB Wi-Fi dongles will not start"
fi

say "Graphics for the apps (dArkOS's Mali driver and SDL2)"
# Kept apart from the system's libraries: only apps the desktop launches load
# them (it sets LD_LIBRARY_PATH), so the desktop itself keeps its own SDL.
GPU="$ROOTFS/usr/lib/rk-gpu"
mkdir -p "$GPU"
install -m 0644 "$MALI" "$GPU/libmali.so"
install -m 0644 "$SDLRK" "$GPU/libSDL2-2.0.so.0"
for n in libEGL.so.1 libGLESv2.so.2 libgbm.so.1; do ln -sf libmali.so "$GPU/$n"; done
# Panels mounted on their side or upside down: arkos4clone's SDL2 for each
# turn, in a folder of its own. The desktop puts the right one first for the
# apps it opens (rkshell/panel.py). They turn the picture with librga, which
# comes in the emulator bundle.
for n in 1 2 3; do install -D -m 0644 "${SDLTURN[$n]}" "$GPU/turn$n/libSDL2-2.0.so.0"; done
mkdir -p "$ROOTFS/usr/share"
install -m 0644 "$PADDB" "$ROOTFS/usr/share/gamecontrollerdb.txt"
ls -l "$GPU"

# Games: the emulator bundle (build/build-emulators.sh), when the caller has
# one. Without it the image still builds; Games is then fetched on the
# handheld (rk-tools install-media).
if [ -n "${EMULATORS:-}" ]; then
    say "Emulators ($(basename "$EMULATORS"))"
    [ -f "$EMULATORS" ] || die "no emulator bundle at $EMULATORS"
    tar -xJf "$EMULATORS" -C "$ROOTFS" --no-same-owner
    [ -x "$ROOTFS/opt/rk-emulators/bin/retroarch" ] || die "the emulator bundle has no RetroArch"
    [ -f "$ROOTFS/opt/rk-emulators/lib/librga.so.2" ] || die "the emulator bundle has no librga (panels mounted on their side need it)"
    python3 -I -c "import sys; b=open(sys.argv[1],'rb').read(20); sys.exit(0 if b[:4]==b'\x7fELF' and b[18]==183 else 1)" \
        "$ROOTFS/opt/rk-emulators/bin/retroarch" || die "the bundle's RetroArch is not an arm64 program"
    chown -R 0:0 "$ROOTFS/opt/rk-emulators"
    cat "$ROOTFS/opt/rk-emulators/VERSION"
else
    echo "WARNING: no emulator bundle given (EMULATORS=...): Games will be fetched on the handheld"
fi

say "System files"
cp -a "$REPO/overlay/." "$ROOTFS/"
# everything we add belongs to root, whoever owns the checkout
( cd "$REPO/overlay" && find . -mindepth 1 ) | while read -r f; do chown -h 0:0 "$ROOTFS/$f"; done
chmod 755 "$ROOTFS"/usr/local/sbin/rk-*
chmod 755 "$ROOTFS"/usr/local/bin/rk-*
chmod 440 "$ROOTFS/etc/sudoers.d/rkshell"
in_root visudo -c -q -f /etc/sudoers.d/rkshell || die "the sudoers file for the desktop is not valid"
# the settings files (a small log, no package work in the background, swap
# tuned for compressed memory): the same step an updated card runs
"$REPO/overlay/usr/local/sbin/rk-sysconf" "$ROOTFS"
[ -L "$ROOTFS/etc/systemd/system/apt-daily.timer" ] && [ -f "$ROOTFS/etc/sysctl.d/30-rk-memory.conf" ] ||
    die "the settings files are not in place"

# the desktop: our Python package, where Debian keeps Python packages
PYDIR="$ROOTFS/usr/lib/python3/dist-packages"
[ -d "$PYDIR" ] || die "no $PYDIR in the system"
rm -rf "$PYDIR/rkshell"
cp -r "$REPO/shell/rkshell" "$PYDIR/rkshell"
find "$PYDIR/rkshell" -name __pycache__ -prune -exec rm -rf {} +
chown -R 0:0 "$PYDIR/rkshell"
in_root python3 -m compileall -q /usr/lib/python3/dist-packages/rkshell || die "the desktop does not compile"
in_root env SDL_VIDEODRIVER=dummy python3 -m rkshell --demo --shots /tmp/rkshell-check >/dev/null ||
    die "the desktop does not draw inside the image"
# the scan helper runs as root: it must refuse a target that is really an
# option of nmap's (one could make root write a file or run a script)
for bad in '{"target":"-oN /etc/rk-pwned"}' '{"target":"10.0.0.1 --script=/tmp/x"}' 'not json'; do
    if printf '%s\n' "$bad" | in_root /usr/local/sbin/rk-scan run >/dev/null 2>&1; then
        die "rk-scan accepted: $bad"
    fi
done
[ ! -e "$ROOTFS/etc/rk-pwned" ] || die "rk-scan let a target write a file"
# the dock app descriptions must be valid JSON with a name and an exec
for j in "$ROOTFS"/usr/share/rk/apps/*.json; do
    python3 -I -c "import json,sys; d=json.load(open(sys.argv[1])); assert d['name'] and d['exec']" "$j" \
        || die "bad app file: $j"
done
rm -rf "$ROOTFS/tmp/rkshell-check"
echo "$HOSTNAME_" > "$ROOTFS/etc/hostname"
printf '127.0.0.1\tlocalhost\n127.0.1.1\t%s\n::1\tlocalhost ip6-localhost ip6-loopback\n' "$HOSTNAME_" > "$ROOTFS/etc/hosts"
cat > "$ROOTFS/etc/fstab" <<'FSTAB'
/dev/mmcblk0p2  /      ext4  defaults,noatime                                    0 1
/dev/mmcblk0p1  /boot  vfat  defaults,umask=0022,nofail                          0 2
FSTAB
# No line for /data here: its partition does not exist until the first start.
# A line for it made every first start wait 8 seconds and print TIME and
# DEPEND failures for /data. rk-firstboot adds the line once the partition is
# there.
mkdir -p "$ROOTFS/boot" "$ROOTFS/data" "$ROOTFS/share"
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

in_root systemctl enable rk-share.service rk-share-adopt.service rk-firstboot.service rk-bootcfg.service rk-audio.service rk-audiod.service rk-mouse.service rk-migrate.service ssh.service NetworkManager.service \
    avahi-daemon.service systemd-timesyncd.service rkshell.service
# the desktop has the first console; a text login is on the others (Ctrl+Alt+F2)
in_root systemctl disable getty@tty1.service 2>/dev/null || true
rm -f "$ROOTFS/etc/systemd/system/getty.target.wants/getty@tty1.service"
# starting does not wait for a network that may not be there
in_root systemctl disable NetworkManager-wait-online.service 2>/dev/null || true
in_root systemctl mask systemd-networkd-wait-online.service 2>/dev/null || true

say "The dock apps (Ember, FireFly, the Stump's files, the Provisioner)"
# Installed here, so a fresh card has them without a command being typed.
# They are fetched as rk-apps fetches them on a running handheld (the latest
# release of each), into ark's home, and handed to ark afterwards.
as_ark() { in_root env HOME=/home/ark USER=ark LOGNAME=ark "$@"; }
as_ark /usr/local/sbin/rk-apps install ember || die "Ember could not be fetched"
as_ark /usr/local/sbin/rk-apps install firefly || die "FireFly could not be installed"
[ -x "$ROOTFS/home/ark/firefly/venv/bin/python" ] && [ -x "$ROOTFS/home/ark/firefly/deploy/FireFly.sh" ] ||
    die "FireFly is not complete in the image"
# The Stump is set up on the handheld (its questions are the owner's: which
# chain, its secret, the radio). What needs no answer is put in place now:
# both repositories and the folder its cockpit writes to. (Not "linger" for
# ark: until the first password change the account is expired, and systemd's
# user@1000.service fails at boot. The Stump's installer turns it on.)
as_ark /usr/local/sbin/rk-apps install stump || die "the Stump's files could not be fetched"
# The Provisioner (the board bench) needs no answers: its release carries
# its firmware and its installer, which also puts the serial access rule in
# /etc/udev/rules.d. The dock entry is the image's own (overlay).
as_ark /usr/local/sbin/rk-apps install provisioner || die "the Provisioner could not be installed"
[ -x "$ROOTFS/home/ark/rk3326_provisioner/RK3326_Provisioner.sh" ] || die "the Provisioner is not complete in the image"
in_root git clone --depth 1 https://github.com/ruderigo/SandBox_Stump_On /home/ark/SandBox_Stump_On ||
    die "SandBox_Stump_On could not be fetched"
mkdir -p "$ROOTFS/roms/ports/stump_r36max/drop" "$ROOTFS/roms/ports/stump_r36max/tf_backup"
in_root chown -R ark:ark /home/ark /roms/ports/stump_r36max
in_root apt-get clean
ls -la "$ROOTFS/home/ark" "$ROOTFS/home/ark/ports"

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
            set-last-cell)
                [[ $value =~ ^[0-9]+$ ]] || die "dtb-fixes.txt: set-last-cell needs a decimal value for $prop"
                cells=($old); cells[$(( ${#cells[@]} - 1 ))]=$value
                fdtput -t u "$dtb" "$node" "$prop" "${cells[@]}"
                [ "$(fdtget -t u "$dtb" "$node" "$prop")" = "${cells[*]}" ] || die "could not set $prop in $rel"
                echo "set the last cell of $prop to $value (was: $old) in $node in $rel" ;;
            *) die "dtb-fixes.txt: unknown action: $action" ;;
        esac | tee -a "$BOOT/rk-dtb-fixes.txt"
    done
done < <(grep -vE '^[[:space:]]*(#|$)' "$HERE/dtb-fixes.txt")

SELECT="$REPO/overlay/usr/local/sbin/rk-boot-select"
# every console's boot.ini made ready for this system, so that copying a
# console's files by hand (README.txt) gives a card that starts; and each
# handheld's own name beside its folder name, for the lists
"$SELECT" -b "$BOOT" prepare
for d in "$BOOT"/consoles/*/; do
    [ -f "$d/boot.ini" ] || continue
    dtb=$(find "$d" -maxdepth 1 -name '*.dtb' | sort | head -n 1)
    echo "$(basename "$d")|$(fdtget -t s "$dtb" / model 2>/dev/null || true)"
done > "$BOOT/consoles/names.txt"
echo "$(wc -l < "$BOOT/consoles/names.txt") handhelds on the card"
# the two ready-made sets a Mac or PC can copy over when one kernel does not start
for k in 4.4 5.10; do
    [ "$k" = 5.10 ] && [ ! -d "$CONS/$CONSOLE/5.10" ] && continue
    "$SELECT" -b "$BOOT" set "$CONSOLE" $k >/dev/null
    d="$BOOT/$([ $k = 5.10 ] && echo default-5.10 || echo fallback-4.4)"
    mkdir "$d"; cp "$BOOT/boot.ini" "$BOOT/Image" "$BOOT"/*.dtb "$d/"
done
"$SELECT" -b "$BOOT" set "$CONSOLE" "$KERNEL"
cp "$REPO/boot-files/wifi.txt" "$REPO/boot-files/README.txt" "$BOOT/"
# the device chooser for a Mac or Linux computer: the same program the
# handheld uses, beside a launcher that can be double-clicked
cp "$SELECT" "$BOOT/consoles/rk-boot-select"
cp "$REPO/boot-files/Choose handheld.command" "$BOOT/"
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

KMODS="$KMODS" "$HERE/verify-image.sh" "$IMG" "$UP" "$KERNEL"

say "Compress"
xz -T0 -6 -f "$IMG"
( cd "$OUT" && sha256sum "$NAME.img.xz" > "$NAME.img.xz.sha256" && ls -la )
echo "Done: $OUT/$NAME.img.xz"
