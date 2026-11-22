"""The sound routing (rk-audiod) and the recorder, without a sound card.

    python3 tests/test_sound.py
"""
import importlib.machinery
import importlib.util
import os
import stat
import sys
import tempfile
import time
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
DAEMON = os.path.join(HERE, "..", "..", "overlay", "usr", "local", "sbin", "rk-audiod")

loader = importlib.machinery.SourceFileLoader("rkaudiod", DAEMON)
spec = importlib.util.spec_from_loader("rkaudiod", loader)
d = importlib.util.module_from_spec(spec)
loader.exec_module(d)

CARDS = """ 0 [rockchiprk817co]: rockchip_rk817- - rockchip,rk817-codec
                      rockchip,rk817-codec
 1 [Headset        ]: USB-Audio - USB-C Headset
                      Generic USB-C Headset at usb-ff300000.usb-1, full speed
 2 [Mic            ]: USB-Audio - Desk Mic
                      Desk Mic at usb-ff300000.usb-1.2, full speed
"""


def proc(tmp, layout):
    """A stand-in /proc/asound: {card: (usb, playback devices, capture devices)}."""
    with open(os.path.join(tmp, "cards"), "w") as f:
        f.write("".join(l + "\n" for l in CARDS.splitlines() if any(l.startswith(f" {n} ") or not l.strip()[0].isdigit() for n in layout)))
    for n, (usb, play, rec) in layout.items():
        os.makedirs(os.path.join(tmp, f"card{n}"), exist_ok=True)
        if usb:
            open(os.path.join(tmp, f"card{n}", "usbid"), "w").close()
        for dev in play:
            os.makedirs(os.path.join(tmp, f"card{n}", f"pcm{dev}p"))
        for dev in rec:
            os.makedirs(os.path.join(tmp, f"card{n}", f"pcm{dev}c"))
    return tmp


def test_choice():
    with tempfile.TemporaryDirectory() as t:                  # the handheld alone
        p = proc(t, {0: (False, [0], [0])})
        out, mic = d.choose(d.cards(p), p)
        assert (out["card"], out["usb"], mic["card"]) == ("rockchiprk817co", False, "rockchiprk817co")
        conf = d.asound_conf(out, mic)
        assert "type dmix" in conf and "rate 44100" in conf and 'capture.pcm "rkin"' in conf
    with tempfile.TemporaryDirectory() as t:                  # a USB microphone only: speaker stays, mic moves
        p = proc(t, {0: (False, [0], [0]), 2: (True, [], [0])})
        out, mic = d.choose(d.cards(p), p)
        assert (out["card"], mic["card"], mic["usb"]) == ("rockchiprk817co", "Mic", True)
        assert "type dmix" in d.asound_conf(out, mic) and "hw:CARD=Mic,DEV=0" in d.asound_conf(out, mic)
    with tempfile.TemporaryDirectory() as t:                  # a USB headset: both move, no shared mixer on it
        p = proc(t, {0: (False, [0], [0]), 1: (True, [0], [0])})
        out, mic = d.choose(d.cards(p), p)
        assert (out["card"], mic["card"]) == ("Headset", "Headset")
        conf = d.asound_conf(out, mic)
        assert "dmix" not in conf and 'card "Headset"' in conf
    assert d.asound_conf(None, None) == d.MARK                # no sound card: no default to break


def test_jack():
    assert d.decide("auto", True) == "HP" and d.decide("auto", False) == "SPK"
    assert d.decide("spk", True) == "SPK" and d.decide("hp", False) == "HP"


def test_own_conf_is_kept():
    with tempfile.TemporaryDirectory() as t:
        path = os.path.join(t, "asound.conf")
        old = d.ASOUND
        d.ASOUND = path
        try:
            with open(path, "w") as f:
                f.write("pcm.!default { type null }\n")
            assert d.write_if_changed(path, d.MARK + "x") is False
            assert open(path).read().startswith("pcm.!default")
            os.remove(path)
            assert d.write_if_changed(path, d.MARK + "x") is True
            assert d.write_if_changed(path, d.MARK + "y") is True and open(path).read() == d.MARK + "y"
        finally:
            d.ASOUND = old


def test_recorder():
    from rkshell import system
    with tempfile.TemporaryDirectory() as t:
        fake = os.path.join(t, "arecord")                     # half a second of a loud square wave, then silence
        with open(fake, "w") as f:
            f.write("#!/usr/bin/env python3\nimport sys\n"
                    "sys.stdout.buffer.write((b'\\x00\\x40' * 50 + b'\\x00\\xc0' * 50) * 221)\n"
                    "sys.stdout.buffer.write(bytes(44100 * 2))\n")
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
        old_path, old_clip = os.environ["PATH"], system.SOUND_CLIP
        os.environ["PATH"] = t + os.pathsep + old_path
        system.SOUND_CLIP = os.path.join(t, "clip.wav")
        try:
            rec = system.Recorder()
            rec.record(1)
            for _ in range(100):
                if not rec.recording:
                    break
                time.sleep(0.05)
            assert not rec.recording and rec.has_clip and not rec.error, rec.error
            assert 0.45 < rec.peak < 0.55, rec.peak
            with wave.open(system.SOUND_CLIP) as w:
                assert (w.getnchannels(), w.getframerate(), w.getnframes()) == (1, 44100, 44100)
            tone = os.path.join(t, "tone.wav")
            system.write_tone(tone)
            with wave.open(tone) as w:
                assert w.getnchannels() == 2 and w.getnframes() == int(1.2 * 44100)
        finally:
            os.environ["PATH"], system.SOUND_CLIP = old_path, old_clip


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("sound: ok")
