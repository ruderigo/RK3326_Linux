"""Debian's security updates as part of "Update this handheld", without a
handheld: apt-get and dpkg are stand-ins that write down what they were asked.

    python3 tests/test_packages.py
"""
import os
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RK_UPDATE = os.path.join(HERE, "..", "..", "overlay", "usr", "local", "sbin", "rk-update")

APT = r'''#!/bin/bash
echo "apt-get $*" >> "$LOG"
case " $* " in
    *" update "*)       exit "${APT_UPDATE_RC:-0}" ;;
    *" -s "*)           for i in $(seq 1 "${PENDING:-0}"); do echo "Inst pkg$i [1.0] (1.1 Debian-Security:13/stable-security [arm64])"; done ;;
    *" --print-uris "*) for i in $(seq 1 "${PENDING:-0}"); do echo "'http://security.debian.org/pkg$i.deb' pkg${i}_1.1_arm64.deb 2097152 SHA256:x"; done ;;
    *" clean "*)        ;;
    *" upgrade "*)      for i in $(seq 1 "${PENDING:-0}"); do echo "Unpacking pkg$i (1.1) over (1.0) ..."; echo "Setting up pkg$i (1.1) ..."; done
                        exit "${APT_UPGRADE_RC:-0}" ;;
esac
'''


def packages(pending=0, online=True, free=None, battery=None, **env):
    """Run rk-update's packages step; (exit code, what it said, what apt and dpkg were asked)."""
    with tempfile.TemporaryDirectory() as t:
        log = os.path.join(t, "asked")
        for name, text in (("apt-get", APT), ("dpkg", '#!/bin/bash\necho "dpkg $*" >> "$LOG"\n')):
            open(os.path.join(t, name), "w").write(text)
            os.chmod(os.path.join(t, name), 0o755)
        os.makedirs(os.path.join(t, "var/lib/apt/lists"))
        open(os.path.join(t, "var/lib/apt/lists/a_list"), "w").write("x")
        supply = os.path.join(t, "supply")
        if battery:
            os.makedirs(os.path.join(supply, "battery"))
            for k, v in zip(("type", "capacity", "status"), ("Battery",) + battery):
                open(os.path.join(supply, "battery", k), "w").write(f"{v}\n")
        body = (f'RK_UPDATE_SOURCE=1 RK_ROOT="{t}" source "{RK_UPDATE}"\n'
                f'need_root() {{ :; }}\nonline() {{ {"true" if online else "false"}; }}\n'
                f'rk_apt_cache() {{ echo "{t}/cache"; }}\npackages\n')
        e = dict(os.environ, PATH=t + os.pathsep + os.environ["PATH"], LOG=log, PENDING=str(pending),
                 RK_PACKAGES_TEST="1", RK_POWER_SUPPLY=supply, **env)
        if free is not None:
            e["RK_PREFLIGHT_FREE_MB"] = str(free)
        p = subprocess.run(["bash", "-c", body], env=e, capture_output=True, text=True)
        asked = open(log).read() if os.path.exists(log) else ""
        return p.returncode, p.stdout + p.stderr, asked, os.listdir(os.path.join(t, "var/lib/apt/lists"))


def upgraded(asked):
    return any(" upgrade -y -q" in ln for ln in asked.splitlines())


def test_nothing_pending():
    rc, said, asked, lists = packages(0)
    assert rc == 0 and "up to date" in said and not upgraded(asked)
    assert "dpkg --configure -a" in asked                       # an update cut short earlier is finished first
    assert lists == []                                          # the lists are not left on the card


def test_updates_go_in_and_are_named():
    rc, said, asked, lists = packages(3, free=4000)
    assert rc == 0 and upgraded(asked), said
    assert "3 Debian packages to update, 6 MB to download" in said
    assert "rk-update:   pkg2 1.1" in said and "Unpacking" not in said
    assert "Debian's packages are updated (3)" in said
    line = next(ln for ln in asked.splitlines() if " upgrade -y -q" in ln)
    assert "--force-confold" in line and "dist-upgrade" not in asked and "full-upgrade" not in asked
    assert "install" not in asked and "remove" not in asked     # never adds or removes a package
    assert asked.rstrip().splitlines()[-1].endswith("clean") and lists == []


def test_offline_or_no_lists_changes_nothing():
    rc, said, asked, _ = packages(3, online=False)
    assert rc != 0 and "no network" in said and asked == ""
    rc, said, asked, _ = packages(3, APT_UPDATE_RC="100")
    assert rc != 0 and "could not be refreshed" in said and not upgraded(asked)


def test_not_on_a_low_battery():
    rc, said, asked, _ = packages(3, free=4000, battery=(20, "Discharging"))
    assert rc != 0 and "battery is under 25%" in said and not upgraded(asked)
    assert upgraded(packages(3, free=4000, battery=(20, "Charging"))[2])       # on the charger: go
    assert upgraded(packages(3, free=4000, battery=(60, "Discharging"))[2])


def test_not_without_room():
    rc, said, asked, _ = packages(3, free=10)
    assert rc != 0 and "not enough room" in said and not upgraded(asked)


def test_a_failed_upgrade_is_said_and_tidied():
    rc, said, asked, lists = packages(2, free=4000, APT_UPGRADE_RC="100")
    assert rc != 0 and "did not all go in" in said and lists == []


def test_switched_off_and_under_other_tests():
    rc, said, asked, _ = packages(3, RK_NO_PACKAGES="1")
    assert rc == 0 and asked == ""


def test_apply_runs_it_and_cannot_be_failed_by_it():
    text = open(RK_UPDATE).read()
    assert text.count("packages || true") == 2                  # after an update, and when already current
    assert "    packages) packages ;;" in text


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
