"""The migration runner and migration 0001, without a real card.

Exercises the guarantee that matters: an adopter's identity survives a
reflash, migrations are idempotent, and the schema is recorded.

    python3 tests/test_update.py
"""
import os
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OVERLAY = os.path.join(HERE, "..", "..", "overlay")
MIGRATE = os.path.join(OVERLAY, "usr", "local", "sbin", "rk-migrate")
MIG_DIR = os.path.join(OVERLAY, "usr", "lib", "rk", "migrations")
MIG1 = os.path.join(MIG_DIR, "0001-state-to-data.sh")
MIG2 = os.path.join(MIG_DIR, "0002-firefly-identity-to-data.sh")


def run(cmd, env):
    e = dict(os.environ, **env)
    return subprocess.run(cmd, env=e, capture_output=True, text=True)


def fake_card(root):
    ark, data, roms = f"{root}/home/ark", f"{root}/data/ark", f"{root}/roms"
    os.makedirs(f"{ark}/firefly")
    os.makedirs(f"{ark}/.firefly")
    os.makedirs(f"{ark}/.reticulum")
    os.makedirs(f"{roms}/ports/stump_r36max")
    open(f"{ark}/firefly/identity", "w").write("IDENTITY-123")
    open(f"{ark}/.firefly/identity", "w").write("FIREFLY-ID-9")
    open(f"{ark}/.reticulum/config", "w").write("mesh")
    open(f"{roms}/ports/stump_r36max/keep", "w").write("drop")
    return {"RK_ARK": ark, "RK_DATA": data, "RK_ROMS": roms}


def test_migration_moves_state_to_data():
    with tempfile.TemporaryDirectory() as t:
        env = fake_card(t)
        assert run(["bash", MIG1], env).returncode == 0
        # the old path is now a symlink, the file is on /data, the content is intact
        assert os.path.islink(env["RK_ARK"] + "/firefly")
        assert os.path.isfile(env["RK_DATA"] + "/firefly/identity")
        assert open(env["RK_ARK"] + "/firefly/identity").read() == "IDENTITY-123"
        assert os.path.islink(env["RK_ROMS"] + "/ports/stump_r36max")


def test_idempotent():
    with tempfile.TemporaryDirectory() as t:
        env = fake_card(t)
        run(["bash", MIG1], env)
        assert run(["bash", MIG1], env).returncode == 0          # second run: no error
        assert open(env["RK_ARK"] + "/firefly/identity").read() == "IDENTITY-123"


def test_reflash_keeps_the_adopters_copy():
    with tempfile.TemporaryDirectory() as t:
        env = fake_card(t)
        run(["bash", MIG1], env)
        # a reflash: /data is kept, /home/ark is rebuilt with the image's default
        import shutil
        shutil.rmtree(env["RK_ARK"])
        os.makedirs(env["RK_ARK"] + "/firefly")
        open(env["RK_ARK"] + "/firefly/identity", "w").write("BAKED-DEFAULT")
        assert run(["bash", MIG1], env).returncode == 0
        # the adopter's identity on /data wins; the baked default is dropped
        assert os.path.islink(env["RK_ARK"] + "/firefly")
        assert open(env["RK_ARK"] + "/firefly/identity").read() == "IDENTITY-123"


def test_firefly_identity_to_data():
    with tempfile.TemporaryDirectory() as t:
        env = fake_card(t)
        assert run(["bash", MIG2], env).returncode == 0
        assert os.path.islink(env["RK_ARK"] + "/.firefly")
        assert open(env["RK_ARK"] + "/.firefly/identity").read() == "FIREFLY-ID-9"
        assert os.path.isfile(env["RK_DATA"] + "/.firefly/identity")
        # a fresh FireFly (no ~/.firefly yet) still gets a /data-backed link
        import shutil
        shutil.rmtree(env["RK_DATA"] + "/.firefly"); os.remove(env["RK_ARK"] + "/.firefly")
        assert run(["bash", MIG2], env).returncode == 0
        assert os.path.islink(env["RK_ARK"] + "/.firefly")


def test_schema_runner_records_and_noops():
    with tempfile.TemporaryDirectory() as t:
        env = fake_card(t)
        schema = f"{t}/data/ark/.rk-schema"
        env.update(RK_MIG_DIR=MIG_DIR, RK_SCHEMA=schema)
        assert run(["bash", MIGRATE, "run"], env).returncode == 0
        assert open(schema).read().strip() == str(max(int(n[:4]) for n in os.listdir(MIG_DIR) if n[:4].isdigit()))
        # status shows nothing pending; a second run changes nothing
        out = run(["bash", MIGRATE, "status"], env).stdout
        assert "pending         : none" in out
        assert run(["bash", MIGRATE, "run"], env).returncode == 0



def lived_on_card(t):
    """A card after its first start: the steps done, the state on /data, the
    home folder linked to it, both records at the newest step."""
    env = fake_card(t)
    schema = f"{t}/data/ark/.rk-schema"
    env.update(RK_MIG_DIR=MIG_DIR, RK_SCHEMA=schema)
    assert run(["bash", MIGRATE, "run"], env).returncode == 0
    assert os.path.islink(env["RK_ARK"] + "/.firefly") and open(schema + ".system").read() == open(schema).read()
    return env, schema


def reflash(env, schema, firstboot_writes_the_record=True):
    """Flashed again: /data is kept, the system partition (the home folder
    and the system's own record with it) is the image's again."""
    import shutil
    shutil.rmtree(env["RK_ARK"])
    os.makedirs(env["RK_ARK"] + "/firefly")                     # the image's own copy of the app
    open(env["RK_ARK"] + "/firefly/identity", "w").write("BAKED-DEFAULT")
    os.remove(schema + ".system")
    if firstboot_writes_the_record:
        open(schema + ".system", "w").write("0\n")              # rk-firstboot, on a new system


def test_a_reflash_links_the_home_folder_to_the_kept_data_again():
    """The bug this guards: the record of the steps lived only on /data, so
    after a reflash it said "done" and the links were never made again.
    FireFly then started a new identity beside the one on /data."""
    newest = str(max(int(n[:4]) for n in os.listdir(MIG_DIR) if n[:4].isdigit()))
    with tempfile.TemporaryDirectory() as t:
        env, schema = lived_on_card(t)
        reflash(env, schema)
        assert open(schema).read().strip() == newest            # /data still says every step is done
        out = run(["bash", MIGRATE, "status"], env).stdout
        assert "pending         : none" not in out and "this system 0" in out
        p = run(["bash", MIGRATE, "run"], env)
        assert p.returncode == 0 and "its steps are done again" in p.stdout
        for name, inside, text in ((".firefly", "identity", "FIREFLY-ID-9"), (".reticulum", "config", "mesh"),
                                   ("firefly", "identity", "IDENTITY-123")):
            assert os.path.islink(f"{env['RK_ARK']}/{name}"), name
            assert open(f"{env['RK_ARK']}/{name}/{inside}").read() == text      # the owner's, not the image's
        assert open(schema).read().strip() == newest and open(schema + ".system").read().strip() == newest
        assert "already current" in run(["bash", MIGRATE, "run"], env).stdout


def test_an_identity_made_since_an_unlinked_reflash_is_kept_aside():
    """A card flashed again with an image from before this fix: no record on
    the system, the old identity on /data, a new one in the home folder."""
    with tempfile.TemporaryDirectory() as t:
        env, schema = lived_on_card(t)
        reflash(env, schema, firstboot_writes_the_record=False)
        os.makedirs(env["RK_ARK"] + "/.firefly")
        open(env["RK_ARK"] + "/.firefly/identity", "w").write("NEW-SINCE-REFLASH")
        os.makedirs(env["RK_ARK"] + "/.reticulum")
        open(env["RK_ARK"] + "/.reticulum/config", "w").write("new config")
        p = run(["bash", MIGRATE, "run"], env)
        assert p.returncode == 0, p.stdout + p.stderr
        assert open(env["RK_ARK"] + "/.firefly/identity").read() == "FIREFLY-ID-9"      # the address they had
        kept = [n for n in os.listdir(env["RK_DATA"]) if n.startswith(".firefly.set-aside-")]
        assert len(kept) == 1 and open(f"{env['RK_DATA']}/{kept[0]}/identity").read() == "NEW-SINCE-REFLASH"
        kept = [n for n in os.listdir(env["RK_DATA"]) if n.startswith(".reticulum.set-aside-")]
        assert len(kept) == 1 and open(f"{env['RK_DATA']}/{kept[0]}/config").read() == "new config"
        assert "kept in" in p.stdout


def test_an_updated_card_does_nothing_again():
    """A card that was never flashed again, from before the system's record:
    its links are right, so nothing is redone and the record is started."""
    with tempfile.TemporaryDirectory() as t:
        env, schema = lived_on_card(t)
        os.remove(schema + ".system")
        before = os.readlink(env["RK_ARK"] + "/.firefly")
        p = run(["bash", MIGRATE, "run"], env)
        assert p.returncode == 0 and "already current" in p.stdout and "done again" not in p.stdout
        assert os.readlink(env["RK_ARK"] + "/.firefly") == before
        assert open(schema + ".system").read().strip() == open(schema).read().strip()


def test_first_start_says_the_system_is_new():
    text = open(os.path.join(OVERLAY, "usr", "local", "sbin", "rk-firstboot")).read()
    assert "echo 0 > /var/lib/rk/schema" in text
    assert text.index("echo 0 > /var/lib/rk/schema") < text.index("firstboot-done")
    unit = open(os.path.join(OVERLAY, "etc", "systemd", "system", "rk-migrate.service")).read()
    assert "After=rk-firstboot.service" in unit                 # the steps run after it


RK_UPDATE = os.path.join(OVERLAY, "usr", "local", "sbin", "rk-update")


def drive(script, root, env=None):
    """Source rk-update under a test root and run `script` against its functions."""
    body = f'RK_UPDATE_SOURCE=1 RK_ROOT="{root}" source "{RK_UPDATE}"\n{script}'
    e = dict(os.environ, RK_ROOT=root)
    if env:
        e.update(env)
    return subprocess.run(["bash", "-c", body], capture_output=True, text=True, env=e)


def fake_system(root):
    """A minimal installed system under root, and a source checkout to update from."""
    sysdirs = [f"{root}/usr/lib/python3/dist-packages/rkshell", f"{root}/usr/share/rk",
               f"{root}/usr/local/sbin", f"{root}/etc", f"{root}/data/ark"]
    for d in sysdirs:
        os.makedirs(d, exist_ok=True)
    open(f"{root}/usr/lib/python3/dist-packages/rkshell/__init__.py", "w").write("old-code")
    open(f"{root}/usr/share/rk/channel", "w").write("old")
    open(f"{root}/etc/os-release.rk", "w").write('RK_VERSION="0.9.0"\n')
    src = root + "/src"
    for d in (f"{src}/shell/rkshell", f"{src}/overlay/usr/share/rk", f"{src}/overlay/usr/local/sbin"):
        os.makedirs(d)
    open(f"{src}/shell/rkshell/__init__.py", "w").write("new-code")
    open(f"{src}/overlay/usr/share/rk/channel", "w").write("new")
    open(f"{src}/overlay/usr/local/sbin/rk-new", "w").write("#!/bin/sh\n")
    return src


RAIL = 'SOFT_OVERLAY="usr/local usr/share/rk"; bk=$(backup); install_soft "$SRC"; echo "I:$(installed_channel)"; restore "$bk"; echo "R:$(installed_channel)"'


def test_rail_install_and_rollback():
    with tempfile.TemporaryDirectory() as t:
        src = fake_system(t)
        r = drive(RAIL, t, env={"SRC": src})
        assert r.returncode == 0, r.stderr
        assert "I:new" in r.stdout and "R:old" in r.stdout, r.stdout
        # the swapped code was installed then restored
        assert open(f"{t}/usr/lib/python3/dist-packages/rkshell/__init__.py").read() == "old-code"


def test_version_ref_guard():
    with tempfile.TemporaryDirectory() as t:
        fake_system(t)
        out = drive('is_version_ref v1.2.0 && echo yes; is_version_ref rail-test || echo no; '
                    'is_version_ref 0.9.1 && echo yes2', t).stdout
        assert "yes" in out and "no" in out and "yes2" in out, out


def test_source_config_roundtrip():
    with tempfile.TemporaryDirectory() as t:
        fake_system(t)
        out = drive('conf_set source fork repo me/fork; echo "slug=$(repo_slug)"; '
                    'conf_set source official; echo "slug2=$(repo_slug)"', t).stdout
        assert "slug=me/fork" in out and "slug2=ruderigo/RK3326_Linux" in out, out


def test_installed_version_and_channel():
    with tempfile.TemporaryDirectory() as t:
        fake_system(t)
        out = drive('echo "v=$(installed_version) c=$(installed_channel)"', t).stdout
        assert "v=0.9.0 c=old" in out, out


def test_newest_tag_picks_highest_semver():
    with tempfile.TemporaryDirectory() as t:
        fake_system(t)
        # a fake `git` on PATH returns ls-remote output; newest_tag must pick v0.10.0
        gitdir = t + "/bin"
        os.makedirs(gitdir)
        fake_git = gitdir + "/git"
        open(fake_git, "w").write("#!/bin/sh\nprintf 'h\\trefs/tags/v0.9.0\\nh\\trefs/tags/v0.10.0\\nh\\trefs/tags/v0.9.1\\n'\n")
        os.chmod(fake_git, 0o755)
        out = drive('echo "newest=$(newest_tag)"', t, env={"PATH": gitdir + os.pathsep + os.environ["PATH"]}).stdout
        assert "newest=v0.10.0" in out, out



if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("update: ok")
