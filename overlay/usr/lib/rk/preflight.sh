# preflight.sh: look before anything is fetched or installed.
#
# Sourced by rk-tools, rk-apps and rk-update. Every install path asks the
# same questions first, and stops with a plain message when the answer is no:
#
#   rk_need_space MB DIR WHAT    is there room where it is going?
#   rk_need_apt WHAT PKG...      room for these packages, from apt's own sizes
#   rk_need_mem MB WHAT          is there memory (free, plus swap) to do it?
#   rk_tmpdir NAME               a work folder on the card, never in memory
#
# A check that cannot measure (no df, no /proc/meminfo) lets the work go on:
# it is there to stop a certain failure, not to add a new way to fail.
# RK_PREFLIGHT_FREE_MB / RK_PREFLIGHT_MEM_MB stand in for the measurements in
# the tests.

_rk_say() { echo "${RK_WHO:-rk}: $*"; }

rk_free_mb() {      # megabytes free for root in the filesystem holding DIR (or its nearest parent)
    [ -n "${RK_PREFLIGHT_FREE_MB:-}" ] && { echo "$RK_PREFLIGHT_FREE_MB"; return; }
    local d="${1:-/}"
    while [ ! -e "$d" ] && [ "$d" != / ] && [ -n "$d" ]; do d=$(dirname "$d"); done
    df -Pm "$d" 2>/dev/null | awk 'NR==2 {print $4}'
}

rk_mount_of() { df -P "${1:-/}" 2>/dev/null | awk 'NR==2 {print $6}'; }

rk_place() {        # what to call the filesystem holding DIR
    case "$(rk_mount_of "$1")" in
        /data) echo "the data partition" ;;
        /boot) echo "the boot partition" ;;
        /)     echo "the system partition" ;;
        *)     echo "$1" ;;
    esac
}

rk_need_space() {   # rk_need_space MB DIR WHAT
    local need=$1 dir=$2 what=$3 have
    have=$(rk_free_mb "$dir")
    [ -n "$have" ] || return 0
    [ "$have" -ge "$need" ] && return 0
    _rk_say "not enough room on $(rk_place "$dir"): $have MB free, $what needs about $need MB."
    _rk_say "nothing was changed."
    if [ "$(rk_mount_of "$dir")" = / ]; then
        _rk_say "to free room: sudo apt autoremove, remove tools you do not use, or see Settings > About for what is full."
    fi
    return 1
}

rk_mem_mb() {       # megabytes of memory that can still be had: available, plus free swap
    [ -n "${RK_PREFLIGHT_MEM_MB:-}" ] && { echo "$RK_PREFLIGHT_MEM_MB"; return; }
    awk '/^MemAvailable:/ {a=$2} /^SwapFree:/ {s=$2} END {if (a != "") print int((a + s) / 1024)}' /proc/meminfo 2>/dev/null
}

rk_need_mem() {     # rk_need_mem MB WHAT
    local need=$1 what=$2 have
    have=$(rk_mem_mb)
    [ -n "$have" ] || return 0
    [ "$have" -ge "$need" ] && return 0
    _rk_say "not enough memory: $have MB to spare, $what needs about $need MB."
    _rk_say "nothing was changed. Close the app that is open (or restart the handheld) and try again."
    return 1
}

# What apt itself says an install will cost, before a byte is fetched:
# "DOWNLOAD INSTALLED" in megabytes, rounded up. Needs package lists
# (apt-get update). Nothing printed when apt cannot work it out.
rk_apt_cost() {
    local uris names
    uris=$(apt-get install -y --no-install-recommends --print-uris "$@" 2>/dev/null) || return 1
    names=$(printf '%s\n' "$uris" | awk '/^'"'"'/ {n=$2; sub(/_.*/, "", n); print n}')
    [ -n "$names" ] || { echo "0 0"; return 0; }
    {
        printf '%s\n' "$uris" | awk '/^'"'"'/ {print "D", $3}'
        # the size each package takes once unpacked (kB), newest candidate first
        apt-cache show --no-all-versions $names 2>/dev/null | awk '/^Installed-Size:/ {print "I", $2}'
    } | awk '$1=="D" {d+=$2} $1=="I" {i+=$2} END {printf "%d %d\n", (d + 1048575) / 1048576, (i + 1023) / 1024}'
}

# Where apt keeps the packages it downloads: on the data partition when there
# is one (it has the room; the system partition of an older card does not).
rk_apt_cache() {
    local d=/data/cache/apt
    if mountpoint -q /data 2>/dev/null && mkdir -p "$d/partial" 2>/dev/null; then
        chown _apt:root "$d/partial" 2>/dev/null; chmod 700 "$d/partial" 2>/dev/null
        echo "$d"
    else
        echo /var/cache/apt/archives
    fi
}

rk_need_apt() {     # rk_need_apt WHAT PKG...   (room for the download and for the unpacked files)
    local what=$1 cost dl inst cache=${RK_APT_CACHE:-/var/cache/apt/archives}
    shift
    cost=$(rk_apt_cost -o "Dir::Cache::archives=$cache" "$@") || return 0
    read -r dl inst <<<"$cost"
    [ -n "${dl:-}" ] && [ -n "${inst:-}" ] || return 0
    [ "$dl" -gt 0 ] || [ "$inst" -gt 0 ] || return 0
    _rk_say "$what: $dl MB to download, about $inst MB once installed."
    if [ "$(rk_mount_of "$cache")" = "$(rk_mount_of /usr)" ]; then
        # one partition holds both: the packages and their unpacked files, with a little to work in
        rk_need_space $(( dl + inst + 32 )) /usr "$what" || return 1
    else
        rk_need_space $(( dl + 8 )) "$cache" "$what (the download)" || return 1
        rk_need_space $(( inst + 32 )) /usr "$what" || return 1
    fi
}

# A work folder for downloads. /tmp is kept in memory on this system, and a
# large download there takes memory from everything else: use the data
# partition (most room), or the system partition.
rk_tmpdir() {
    local base
    for base in /data/tmp /var/tmp; do
        case $base in /data/*) mountpoint -q /data 2>/dev/null || continue ;; esac
        mkdir -p "$base" 2>/dev/null && [ -w "$base" ] || continue
        mktemp -d "$base/${1:-rk}.XXXXXX" 2>/dev/null && return 0
    done
    mktemp -d
}
