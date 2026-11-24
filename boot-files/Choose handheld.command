#!/bin/bash
# Choose the handheld this card starts on, from a Mac or a Linux computer.
# Mac: double-click this file. Linux: bash "Choose handheld.command"
# (Windows: see "Another handheld" in README.txt; three files to copy.)
#
# The card holds the boot files of every handheld it supports, in consoles/.
# This copies the right three to the top of the partition; nothing else on
# the card changes, and it can be run again.
cd "$(dirname "$0")" || exit 1
S=consoles/rk-boot-select
[ -f "$S" ] || { echo "consoles/rk-boot-select is missing: is this the card's BOOT partition?"; exit 1; }
echo "This card now starts on:"
bash "$S" -b . status | sed -n '1,2p'
echo
names=()
while IFS= read -r line; do names+=("${line%%    *}"); printf '%3d  %s\n' "${#names[@]}" "$line"; done < <(bash "$S" -b . list)
echo
echo "The name is the one arkos4clone uses. Not sure which is yours? Its"
echo "DTB Analysis Tool tells you: https://github.com/lcdyk0517/arkos4clone"
printf 'Number of your handheld (Enter to leave as it is): '
read -r n
case "$n" in ''|*[!0-9]*) echo "Nothing changed."; exit 0 ;; esac
[ "$n" -ge 1 ] && [ "$n" -le "${#names[@]}" ] || { echo "No such number. Nothing changed."; exit 1; }
printf 'Kernel: Enter for 5.10 (the default), or type 4.4 if 5.10 does not start: '
read -r k
[ "$k" = 4.4 ] || k=5.10
bash "$S" -b . set "${names[$((n - 1))]}" "$k" && echo "Done. Eject the card and put it in the handheld."
