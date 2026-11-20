#!/bin/bash
# Checks on a built image that need no handheld:
#   verify-image.sh <image> <upstream dir> <kernel 5.10|4.4>
# It cannot show that the image starts on a handheld; it shows that the
# pieces a start depends on are where they have to be.
set -euo pipefail
IMG=$1; UP=$2; KERNEL=$3
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail() { echo "VERIFY FAILED: $*" >&2; exit 1; }
ok() { echo "  ok  $*"; }

echo "=== Verify $IMG"
# boot chain at its fixed sectors
for pair in idbloader.img:64 uboot.img:16384 trust.img:24576; do
    f=${pair%%:*}; seek=${pair##*:}; size=$(stat -c %s "$UP/uboot/$f")
    cmp -s <(dd if="$IMG" bs=512 skip=$seek status=none | head -c "$size") "$UP/uboot/$f" || fail "$f is not at sector $seek"
    ok "$f at sector $seek"
done
[ $(( 64 * 512 + $(stat -c %s "$UP/uboot/idbloader.img") )) -le $(( 16384 * 512 )) ] || fail "idbloader overlaps uboot"

# partition table
read -r P1S P1N P1T < <(sfdisk -d "$IMG" | sed -n 's/.*img1 : start= *\([0-9]*\), size= *\([0-9]*\), type=\([0-9a-f]*\).*/\1 \2 \3/p')
read -r P2S P2N P2T < <(sfdisk -d "$IMG" | sed -n 's/.*img2 : start= *\([0-9]*\), size= *\([0-9]*\), type=\([0-9a-f]*\).*/\1 \2 \3/p')
[ "$P1S" = 32768 ] && [ "$P1T" = b ] || fail "partition 1 is not FAT32 at 16 MiB (start=$P1S type=$P1T)"
[ "$P2S" = $(( P1S + P1N )) ] && [ "$P2T" = 83 ] || fail "partition 2 does not follow partition 1"
[ $(( (P2S + P2N) * 512 )) -eq "$(stat -c %s "$IMG")" ] || fail "partition 2 does not end at the end of the image"
ok "partitions: BOOT ${P1N}s at ${P1S}s, system ${P2N}s at ${P2S}s"

# boot partition
dd if="$IMG" of="$T/boot.img" bs=512 skip="$P1S" count="$P1N" status=none
fsck.vfat -n "$T/boot.img" >/dev/null || fail "FAT filesystem check"
mcopy -i "$T/boot.img" ::boot.ini "$T/boot.ini"
head -n 1 "$T/boot.ini" | grep -q '^odroidgoa-uboot-config' || fail "boot.ini does not start with the u-boot marker"
grep -q '^booti \${loadaddr} - \${dtb_loadaddr}' "$T/boot.ini" || fail "boot.ini does not start the kernel without a ramdisk"
grep -q 'root=/dev/mmcblk0p2' "$T/boot.ini" || fail "boot.ini does not name the system partition"
while read -r f; do
    mcopy -i "$T/boot.img" "::$f" "$T/loaded" 2>/dev/null || fail "boot.ini loads $f, which is not on the boot partition"
    [ -s "$T/loaded" ] || fail "$f is empty"
    ok "boot.ini loads $f ($(stat -c %s "$T/loaded") bytes)"
    case $f in
        Image) src="$UP/boot/dArkOS/consoles/kernel/$([ "$KERNEL" = 5.10 ] && echo 5.10 || echo original)/Image"
               cmp -s "$T/loaded" "$src" || fail "Image is not the $KERNEL kernel" ;;
        *.dtb) [ "$(head -c 4 "$T/loaded" | od -An -tx1 | tr -d ' ')" = d00dfeed ] || fail "$f is not a device tree" ;;
    esac
    rm -f "$T/loaded"
done < <(sed -n 's/^load mmc 1:1 \${[a-z_]*} \(.*\)$/\1/p' "$T/boot.ini" | tr -d '\r')
# our device tree changes are in the tree the card starts
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mcopy -i "$T/boot.img" ::rk-device.txt "$T/rk-device.txt"
CONSOLE=$(sed -n 's/^console=//p' "$T/rk-device.txt" | tr -d '\r')
DTB=$(sed -n 's/^load mmc 1:1 \${dtb_loadaddr} \(.*\)$/\1/p' "$T/boot.ini" | tr -d '\r' | head -n 1)
mcopy -i "$T/boot.img" "::$DTB" "$T/started.dtb"
while IFS='|' read -r console action node prop value; do
    console=$(echo "$console" | xargs); action=$(echo "$action" | xargs)
    node=$(echo "$node" | xargs); prop=$(echo "$prop" | xargs); value=$(echo "${value:-}" | xargs)
    [ "$console" = "$CONSOLE" ] || continue
    if [ "$action" = set-u32 ]; then
        got=$(fdtget -t u "$T/started.dtb" "$node" "$prop" 2>/dev/null) || fail "$DTB has no $prop in $node"
        [ "$got" = "$value" ] || fail "$DTB: $prop is $got, not $value"
        ok "$DTB: $prop is $value"
    else
        fdtget "$T/started.dtb" "$node" "$prop" >/dev/null 2>&1 && fail "$DTB still has $prop in $node"
        ok "$DTB: $prop is not in $node"
    fi
done < <(grep -vE '^[[:space:]]*(#|$)' "$HERE/dtb-fixes.txt")
for f in wifi.txt README.txt hostname.txt rk-device.txt consoles/logos.txt fallback-4.4/boot.ini fallback-4.4/Image; do
    mdir -i "$T/boot.img" "::$f" >/dev/null 2>&1 || fail "missing on the boot partition: $f"
done
ok "settings files and the 4.4 fallback set are on the boot partition"

# system partition
dd if="$IMG" of="$T/root.img" bs=512 skip="$P2S" count="$P2N" status=none
e2fsck -fn "$T/root.img" >/dev/null 2>&1 || fail "ext4 filesystem check"
FEAT=$(dumpe2fs -h "$T/root.img" 2>/dev/null | sed -n 's/^Filesystem features: *//p')
for bad in orphan_file metadata_csum_seed; do
    case " $FEAT " in *" $bad "*) fail "ext4 feature $bad is on: kernels 4.4 and 5.10 cannot mount it" ;; esac
done
ok "ext4 features: $FEAT"
has() { debugfs -R "stat $1" "$T/root.img" 2>/dev/null | grep -q '^Inode:'; }
KVER=$([ "$KERNEL" = 5.10 ] && echo 5.10.252-arkos4clone || echo 4.4.189)
for p in /usr/lib/systemd/systemd /usr/sbin/sshd /usr/sbin/NetworkManager /usr/sbin/sfdisk /usr/sbin/mkfs.ext4 \
         /usr/local/sbin/rk-firstboot /usr/local/sbin/rk-bootcfg /usr/local/sbin/rk-boot-select \
         /etc/fstab /etc/hostname /home/ark /boot /data \
         /usr/lib/modules/$KVER/modules.dep /usr/lib/modules/4.4.189/modules.dep \
         /etc/systemd/system/multi-user.target.wants/rk-firstboot.service \
         /etc/systemd/system/multi-user.target.wants/rk-bootcfg.service \
         /etc/systemd/system/multi-user.target.wants/ssh.service \
         /etc/systemd/system/multi-user.target.wants/NetworkManager.service; do
    has "$p" || fail "missing in the system: $p"
done
ok "system files, both kernels' modules and enabled services are present"
for p in /etc/ssh/ssh_host_ed25519_key /etc/ssh/ssh_host_rsa_key /usr/sbin/policy-rc.d; do
    has "$p" && fail "must not be in the image: $p"
done
ok "no SSH host keys in the image (each card makes its own)"
filecat() { debugfs -R "cat $1" "$T/root.img" 2>/dev/null; }
# the user: a password is set, it must be changed at the first login, root has none
ARK=$(filecat /etc/shadow | grep '^ark:') || fail "no user ark"
[ "$(echo "$ARK" | cut -d: -f2 | cut -c1)" = '$' ] || fail "ark has no password set"
[ "$(echo "$ARK" | cut -d: -f3)" = 0 ] || fail "ark's password is not marked to be changed at the first login"
filecat /etc/shadow | grep -qE '^root:[!*]' || fail "root is not locked"
ok "user ark: password set and due for change at first login; root locked"
filecat /etc/fstab | grep -q '^/dev/mmcblk0p2[[:space:]]*/[[:space:]]' || fail "fstab has no system partition line"
[ -z "$(filecat /etc/machine-id)" ] || fail "machine-id is not empty"
ok "fstab and an empty machine-id"
# firmware of the Wi-Fi dongle the project uses (Ralink RT3070, driver rt2800usb)
has /usr/lib/firmware/rt2870.bin && ok "firmware for the RT3070 dongle (rt2870.bin)" ||
    echo "  WARNING: /usr/lib/firmware/rt2870.bin is missing: the RT3070 dongle will not start"
DEP=$(filecat /usr/lib/modules/$KVER/modules.dep)
for m in rt2800usb cp210x; do
    echo "$DEP" | grep -q "/$m\.ko" && ok "kernel $KVER has the $m module" ||
        echo "  note: $m is not a module of $KVER (it may be built in)"
done
echo "=== Verify passed (not a boot test)"
