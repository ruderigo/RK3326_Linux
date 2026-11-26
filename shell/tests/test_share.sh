#!/bin/bash
# The part of the card a computer can read: what rk-share does to a card.
#
#   bash tests/test_share.sh
#
# Runs the real rk-data-partition and rk-share on small card images. No root
# and no loop device: the partitions are files (RK_SHARE_PARTS), and the test
# copies them into the image where a kernel would have them. Needs sfdisk,
# e2fsprogs and exfatprogs. /data is 256 MiB here instead of 16 GiB.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
R="$HERE/../../overlay/usr/local/sbin"
PATH="$PATH:/usr/sbin:/sbin"
for t in sfdisk mkfs.ext4 resize2fs debugfs mkfs.exfat fsck.exfat blkid; do
    command -v $t >/dev/null || { echo "test_share: missing tool: $t"; exit 1; }
done
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT; cd "$W"
export RK_SHARE_STATE=$W/state RK_SHARE_FSTAB=$W/fstab RK_SHARE_PARTS=$W/parts RK_SHARE_DATA_MB=256 RK_SHARE_MIN_MB=128
DATA=$(( 256 * 2048 ))
bad() { echo "test_share: FAIL $*"; exit 1; }
tbl() { sfdisk -d card.img | grep ' : start=' | sed 's/^[^:]*: *//'; }
p() { sfdisk -d card.img | grep ' : start=' | sed -n "${1}p" | sed -n 's/.*start= *\([0-9]*\), *size= *\([0-9]*\).*/\1 \2/p'; }
chain() { head -c $(( 32768 * 512 )) card.img | tail -c +513 | sha256sum; }
image_table() { printf 'label: dos\nstart=32768, size=65536, type=b\nstart=98304, size=131072, type=83\n' | sfdisk -q card.img; }
new_card() {    # new_card MIB: a flashed card (boot chain, partitions 1 and 2), then the first start's partition 3
    rm -rf card.img state fstab parts src; mkdir parts; : > fstab; truncate -s "${1}M" card.img; image_table
    T12=$(tbl)
    dd if=/dev/urandom of=card.img bs=512 seek=64 count=2000 conv=notrunc status=none
    "$R/rk-data-partition" card.img >/dev/null || bad "rk-data-partition"
    read -r s3 n3 < <(p 3); total=$(( $(stat -c %s card.img) / 512 ))
    truncate -s $(( n3 * 512 )) parts/p3
    truncate -s $(( (total - s3 - ${2:-$DATA}) * 512 )) parts/p4    # the size the table will give partition 4
}
data_fs() { mkfs.ext4 -q -F -L RKDATA -O ^orphan_file,^metadata_csum_seed -d src parts/p3; }

# a new card: nothing on partition 3
new_card 1024; C=$(chain)
"$R/rk-share" convert card.img >/dev/null || bad "new card: convert"
[ "$(p 3)" = "$s3 $DATA" ] || bad "new card: partition 3 is $(p 3)"
read -r s4 n4 < <(p 4); [ "$s4" = $(( s3 + DATA )) ] && [ $(( s4 + n4 )) = "$total" ] || bad "new card: partition 4 is $s4 $n4"
[ "$(blkid -p -s TYPE -o value parts/p4)" = exfat ] && [ "$(blkid -p -s LABEL -o value parts/p4)" = RKSHARE ] || bad "new card: partition 4 is not exFAT RKSHARE"
fsck.exfat -n parts/p4 >/dev/null 2>&1 || bad "new card: fsck.exfat"
sfdisk -l card.img | grep -q 'HPFS/NTFS/exFAT' || bad "new card: partition 4's type is not the one computers expect for exFAT"
[ "$(chain)" = "$C" ] || bad "new card: the boot chain area changed"
[ "$(tbl | sed -n 1,2p)" = "$T12" ] || bad "new card: partitions 1 or 2 changed"
grep -q '^LABEL=RKSHARE  */share  *exfat .*nofail' fstab || bad "new card: no /share line in fstab"
[ ! -e state/share-format ] || bad "new card: the format marker is left"
T=$(tbl); "$R/rk-share" convert card.img >/dev/null && [ "$(tbl)" = "$T" ] && [ "$(grep -c RKSHARE fstab)" = 1 ] || bad "new card: a second run changed something"
echo "ok  a new card: /data $(( DATA / 2048 )) MiB, then $(( n4 / 2048 )) MiB exFAT RKSHARE; boot chain and partitions 1, 2 untouched; a second run changes nothing"

# a card whose /data fills it, with files in it
new_card 1024; mkdir -p src/ark/roms/psx src/opt
head -c 60M /dev/urandom > src/opt/big; echo game > src/ark/roms/psx/a.bin; data_fs
"$R/rk-share" convert card.img >/dev/null || bad "full /data: convert"
[ "$(p 3)" = "$s3 $DATA" ] || bad "full /data: partition 3 is $(p 3)"
e2fsck -f -n parts/p3 >/dev/null 2>&1 || bad "full /data: the filesystem has errors after the change"
[ "$(dumpe2fs -h parts/p3 2>/dev/null | awk -F: '/^Block count/ {c=$2} /^Block size/ {s=$2} END {print c*s/512}')" = "$DATA" ] || bad "full /data: the filesystem is not the partition's size"
debugfs -R "cat /opt/big" parts/p3 2>/dev/null | cmp -s - src/opt/big || bad "full /data: a file changed"
[ "$(debugfs -R "cat /ark/roms/psx/a.bin" parts/p3 2>/dev/null)" = game ] || bad "full /data: a file changed"
[ "$(blkid -p -s TYPE -o value parts/p4)" = exfat ] || bad "full /data: no visible partition"
echo "ok  /data filling the card: from $(( n3 / 2048 )) to $(( DATA / 2048 )) MiB with its files intact, and the visible partition after it"

# that card flashed again: the image's table has neither partition
truncate -s $(( DATA * 512 )) parts/p3
read -r s4 n4 < <(p 4)
dd if=parts/p3 of=card.img bs=1M seek=$(( s3 / 2048 )) conv=notrunc status=none
dd if=parts/p4 of=card.img bs=1M seek=$(( s4 / 2048 )) conv=notrunc status=none
H=$(sha256sum < parts/p4); rm -rf state fstab; : > fstab; image_table
"$R/rk-data-partition" card.img >/dev/null; read -r _ n3b < <(p 3)
truncate -s $(( n3b * 512 )) parts/p3       # the kernel shows partition 3 over the rest of the card
"$R/rk-share" convert card.img | grep -q "putting both back" || bad "flashed again: the visible partition was not recognised"
[ "$(p 3)" = "$s3 $DATA" ] && [ "$(p 4)" = "$s4 $n4" ] || bad "flashed again: table is $(p 3) / $(p 4)"
[ "$(sha256sum < parts/p4)" = "$H" ] && [ ! -e state/share-format ] || bad "flashed again: the visible partition was formatted"
echo "ok  flashed again: both partitions are back where they were, nothing formatted"

# the kernel does not show the new partition yet: nothing is formatted until it does
new_card 1024; rm parts/p4
"$R/rk-share" convert card.img >/dev/null; [ $? = 1 ] && [ -s state/share-format ] || bad "no device: expected a failed format and the marker kept"
truncate -s $(( (total - s3 - DATA) * 512 )) parts/p4
"$R/rk-share" convert card.img >/dev/null && [ "$(blkid -p -s TYPE -o value parts/p4)" = exfat ] && [ ! -e state/share-format ] || bad "no device: the next run did not format it"
echo "ok  a format that could not be done is done by the next run, and only for the partition this made"

# a small card: no room, left alone
new_card 300 0; T=$(tbl)
"$R/rk-share" convert card.img >/dev/null; [ $? = 4 ] && [ "$(tbl)" = "$T" ] || bad "small card: not left alone"
echo "ok  a card with no room for it is left as it is"

# /data holds more than the usual size: it keeps more
export RK_SHARE_DATA_MB=128; new_card 4096 $(( 2048 * 2048 )); mkdir src; head -c 500M /dev/urandom > src/big; data_fs
"$R/rk-share" convert card.img >/dev/null || bad "big /data: convert"
read -r _ n3e < <(p 3); [ "$n3e" = $(( 2048 * 2048 )) ] || bad "big /data: partition 3 is $(( n3e / 2048 )) MiB"
debugfs -R "cat /big" parts/p3 2>/dev/null | cmp -s - src/big || bad "big /data: a file changed"
echo "ok  /data holding more than the usual size keeps what it needs ($(( n3e / 2048 )) MiB)"
# and too much for any visible partition: refused, untouched
new_card 1024; mkdir src; head -c 620M /dev/urandom > src/big; data_fs; T=$(tbl); H=$(sha256sum < parts/p3)
"$R/rk-share" convert card.img >/dev/null; [ $? = 5 ] && [ "$(tbl)" = "$T" ] || bad "too full: not refused"
debugfs -R "cat /big" parts/p3 2>/dev/null | cmp -s - src/big || bad "too full: a file changed"
echo "ok  /data too full for a visible partition: refused, nothing changed"
export RK_SHARE_DATA_MB=256

# the games folder moves to the visible partition, and a link stays in its place
rm -rf share data state; mkdir -p share data/ark/roms/psx data/ark/roms/bios state; : > state/share-adopt
echo disc > data/ark/roms/psx/game.chd; echo bios > data/ark/roms/bios/scph1001.bin
export RK_SHARE_MNT=$W/share RK_SHARE_DATA=$W/data RK_SHARE_MOUNTED=1
"$R/rk-share" adopt >/dev/null || bad "adopt"
[ -L data/ark/roms ] && [ "$(cat data/ark/roms/psx/game.chd)" = disc ] && [ "$(cat share/roms/bios/scph1001.bin)" = bios ] || bad "adopt: the games did not move"
[ -d share/packages ] && [ -d share/roms/n64 ] && grep -q "packages/" share/README.txt && [ ! -e state/share-adopt ] || bad "adopt: folders, note or marker"
"$R/rk-share" adopt >/dev/null && [ "$(cat share/roms/psx/game.chd)" = disc ] || bad "adopt: a second run"
[ "$(HOME=$W/home bash -c "sed 's#/data/ark#$W/data/ark#g' '$R/../bin/rk-games' | bash -s where")" = "$W/share/roms" ] || bad "rk-games does not follow the link"
echo "ok  the games folder moves to the visible partition; /data/ark/roms is a link to it; Games follows it"

# AppManager finds a package copied to the visible partition, not the files a Mac leaves beside it
mkdir -p pk/demo/deploy pk/demo/dock && cat > mk.py <<'PY'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1], "w")
z.writestr("demo/deploy/install.sh", "#!/bin/bash\n")
z.writestr("demo/VERSION", "1.2.3\n")
z.writestr("demo/dock/demo.json", '{"name": "Demo", "exec": ["/data/ark/apps/demo/run"]}')
PY
python3 mk.py share/packages/demo-1.2.3.zip 2>/dev/null; cp share/packages/demo-1.2.3.zip share/packages/._demo-1.2.3.zip
out=$(RK_PKG_DIR=$W/none RK_PKG_MORE=$W/share/packages python3 "$R/rk-pkg" list 2>&1)
echo "$out" | grep -q '^bad|\._' && bad "rk-pkg lists a Mac's ._ file: $out"
echo "$out" | grep -q 'demo-1.2.3.zip' || echo "note: rk-pkg did not list the made-up package (its layout is checked in test_apps.py): $out" | head -3
echo "test_share: ok"
