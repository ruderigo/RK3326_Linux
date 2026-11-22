"""Wi-Fi adapter detection and the readiness line, without real hardware.

    python3 tests/test_wifi.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from rkshell import system as S

# `iw phy` with two radios: phy0 (onboard, managed only), phy1 (a dongle with monitor).
IW_PHY = """Wiphy phy1
	wiphy index: 1
	Supported interface modes:
		 * IBSS
		 * managed
		 * AP
		 * monitor
		 * mesh point
	Band 1:
Wiphy phy0
	wiphy index: 0
	Supported interface modes:
		 * managed
		 * P2P-client
	Band 1:
		Capabilities: 0x172
"""


def fake_sys(root, phys):
    """phys: {index: (bus_link, driver, iface)}; builds a /sys/class/ieee80211 tree."""
    for idx, (link, driver, iface) in phys.items():
        base = f"{root}/sys/class/ieee80211/phy{idx}"
        dev = f"{root}/dev/{idx}"
        os.makedirs(dev, exist_ok=True)
        os.makedirs(os.path.dirname(base), exist_ok=True)
        os.symlink(dev, base) if not os.path.exists(base) else None
        os.makedirs(f"{base}/device", exist_ok=True) if False else None
        # device is itself a symlink to a bus path
        target = f"{root}/buses/{link}"
        os.makedirs(target, exist_ok=True)
        os.symlink(target, f"{base}/device")
        if driver:
            drv = f"{root}/drivers/{driver}"
            os.makedirs(drv, exist_ok=True)
            os.symlink(drv, f"{base}/device/driver")
        if iface:
            os.makedirs(f"{base}/device/net/{iface}", exist_ok=True)
    return f"{root}/sys"


def test_monitor_parse():
    m = S.parse_monitor_modes(IW_PHY)
    assert m == {1: True, 0: False}, m
    assert S.parse_monitor_modes("") == {}


def test_adapters_and_status():
    with tempfile.TemporaryDirectory() as t:
        root = fake_sys(t, {
            0: ("mmc0/sdio/wlan", "aic8800_fdrv", "wlan0"),      # onboard
            1: ("usb1/1-1/1-1.2", "rtl8812au", "wlan1"),         # dongle
        })
        ads = S.wifi_adapters(sys_root=root, iw_phy_text=IW_PHY)
        by = {a["phy"]: a for a in ads}
        assert by[0]["bus"] == "sdio" and by[0]["monitor"] is False
        assert by[1]["bus"] == "usb" and by[1]["monitor"] is True
        assert by[1]["driver"] == "rtl8812au" and by[1]["iface"] == "wlan1"
        st = S.wifi_audit_status(ads)
        assert st["level"] == "ok" and st["ready"] and "rtl8812au" in st["line"]


def test_status_variants():
    onboard = [{"phy": 0, "iface": "wlan0", "driver": "aic8800", "bus": "sdio", "monitor": False}]
    assert S.wifi_audit_status(onboard)["level"] == "muted"
    assert not S.wifi_audit_status(onboard)["ready"]
    dongle_no_mon = [{"phy": 1, "iface": "wlan1", "driver": "r8188eu", "bus": "usb", "monitor": False}]
    assert S.wifi_audit_status(dongle_no_mon)["level"] == "warn"
    assert S.wifi_audit_status([], have_iw=False)["level"] == "muted"
    assert "iw" in S.wifi_audit_status([], have_iw=False)["line"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("wifi: ok")
