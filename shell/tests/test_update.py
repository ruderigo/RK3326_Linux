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
        assert open(schema).read().strip() == "2"
        # status shows nothing pending; a second run changes nothing
        out = run(["bash", MIGRATE, "status"], env).stdout
        assert "pending         : none" in out
        assert run(["bash", MIGRATE, "run"], env).returncode == 0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("update: ok")
