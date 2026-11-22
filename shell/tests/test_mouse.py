"""The rk-mouse motion math, without a gamepad or uinput.

    python3 tests/test_mouse.py
"""
import importlib.machinery
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "overlay", "usr", "local", "sbin", "rk-mouse")
loader = importlib.machinery.SourceFileLoader("rkmouse", SRC)
spec = importlib.util.spec_from_loader("rkmouse", loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)


def test_axis_fraction():
    # a 0..255 stick, centre 128
    assert abs(m.axis_fraction(128, 0, 255)) < 0.01
    assert m.axis_fraction(255, 0, 255) == 1.0
    assert m.axis_fraction(0, 0, 255) == -1.0
    # a signed stick -32768..32767
    assert abs(m.axis_fraction(0, -32768, 32767)) < 0.01
    # the hardware flat zone is removed: just outside centre reads ~0
    assert m.axis_fraction(130, 0, 255, flat=8) == 0.0
    assert m.axis_fraction(255, 0, 255, flat=8) == 1.0


def test_curve_deadzone():
    assert m.curve(0.1, 0.18, 2.0) == 0.0          # inside the dead zone
    assert m.curve(-0.1, 0.18, 2.0) == 0.0
    assert m.curve(1.0, 0.18, 2.0) == 1.0          # full push is full output
    assert m.curve(-1.0, 0.18, 2.0) == -1.0
    # just past the dead zone is small; monotonic and signed
    a = m.curve(0.3, 0.18, 2.0)
    b = m.curve(0.6, 0.18, 2.0)
    assert 0 < a < b < 1
    assert m.curve(-0.6, 0.18, 2.0) == -b


def test_delta_subpixel():
    cfg = dict(m.DEFAULTS)
    carry = [0.0, 0.0]
    # a tiny but non-zero push over many short ticks still moves, via the carry
    moved = 0
    for _ in range(60):
        dx, dy = m.delta(0.25, 0.0, cfg, 1 / 60, carry)
        moved += dx
        assert dy == 0
    assert moved > 0
    # centred stick never moves
    carry = [0.0, 0.0]
    assert m.delta(0.0, 0.0, cfg, 1 / 60, carry) == (0, 0)
    # full push for one second is about "speed" pixels
    carry = [0.0, 0.0]
    dx, _ = m.delta(1.0, 0.0, cfg, 1.0, carry)
    assert abs(dx - cfg["speed"]) <= 1


def test_config_merge():
    cfg = m.load_config()                           # no file -> defaults
    assert cfg["speed"] == m.DEFAULTS["speed"]
    assert set(cfg) == set(m.DEFAULTS)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("mouse: ok")
