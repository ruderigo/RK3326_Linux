#!/bin/bash
# Step 5: on a card flashed before these were part of the image,
#   - the low-battery power-off (rk-battery) is turned on: an update brings
#     its files, and nothing else would start it;
#   - remote access (SSH) is turned off if the handheld still has its first
#     password, the public one. A handheld whose owner chose a password keeps
#     SSH exactly as it was.
[ -z "${RK_ARK:-}${RK_DATA:-}${RK_MIG_DIR:-}" ] || exit 0      # under test: not this machine's services
systemctl daemon-reload 2>/dev/null || true
systemctl enable --now rk-battery.service >/dev/null 2>&1 || echo "rk-migrate 0005: rk-battery was not started"
if /usr/local/sbin/rk-remote first; then
    /usr/local/sbin/rk-remote off >/dev/null 2>&1 || true
    echo "rk-migrate 0005: remote access is off until this handheld has its own password (Network, Remote access)"
fi
exit 0
