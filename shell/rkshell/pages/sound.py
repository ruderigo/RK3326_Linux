"""Sound: where audio goes, where it comes from, and a recorder to prove it.

rk-audiod decides the routing for the whole system (USB audio when plugged
in, else the built-in chip; headphones or speaker by the 3.5 mm jack). This
window shows what it decided, lets you override the output, and records and
plays through the same "default" device every app gets. If the recorder
hears a microphone and an app does not, the app is choosing its own device.
"""
import pygame

from .. import gfx as G
from .. import theme as T
from .base import Page

MODES = [("auto", "Automatic"), ("spk", "Speaker"), ("hp", "Headphones")]
MODE_NOTES = {"auto": "follows the 3.5 mm jack", "spk": "always, whatever the jack says", "hp": "always the 3.5 mm jack"}
ROWS = ["output", "jack", "tone", "record", "play"]


class SoundPage(Page):
    title, icon = "Sound", "sound"
    live = True

    def __init__(self, app):
        super().__init__(app)
        self.sel = 0
        self.rec = app.system.recorder()
        self.st = {}

    def enter(self):
        self.st = self.app.system.sound_status()

    def leave(self):
        self.rec.stop()

    @property
    def hints(self):
        what = {"output": "change", "jack": "reads backwards: flip", "tone": "play", "record": "record 5 s", "play": "play"}
        return [("A", what[ROWS[self.sel]]), ("B", "close")]

    def poll(self):
        self.st = self.app.system.sound_status()
        self.rec.playing                      # collects a finished player's error
        self.app.dirty = True

    def handle(self, action):
        if action in ("up", "down"):
            self.sel = (self.sel + (-1 if action == "up" else 1)) % len(ROWS)
            return
        if action != "a":
            return
        row, system = ROWS[self.sel], self.app.system
        if row == "output":
            names = [m for m, _ in MODES]
            mode = names[(names.index(self.st.get("mode", "auto")) + 1) % len(names)]
            if not system.set_sound_output(mode):
                self.app.toast("The sound service is not running", 4, error=True)
        elif row == "jack":
            if not system.set_jack_reversed(not self.st.get("jack_reversed")):
                self.app.toast("The sound service is not running", 4, error=True)
        elif row == "tone":
            self.rec.tone()
        elif row == "record":
            self.rec.record(5)
        elif row == "play":
            if self.rec.has_clip:
                self.rec.play()
            else:
                self.app.toast("Record something first", 3)

    # ---------------------------------------------------------------- draw
    def lines(self):
        """(title, detail, colour) for each row."""
        st, rec = self.st, self.rec
        out, mic = st.get("out"), st.get("mic")
        if not st:
            going = "The sound service has not reported yet"
        elif out and out["usb"]:
            going = "now: USB, " + out["name"]
        else:
            going = "now: " + {"SPK": "the speaker", "HP": "the 3.5 mm headphones"}.get(st.get("path"), st.get("path") or "nothing")
        mode = dict(MODES).get(st.get("mode", "auto"), "")
        if not st.get("jack_found"):
            jack = ("not found", T.MUTED)
        else:
            jack = ("a plug is in" if st.get("jack") else "empty", T.OK if st.get("jack") else T.TEXT)
        mic_name = ("USB, " + mic["name"] if mic["usb"] else "built in") if mic else "none found"
        if rec.recording:
            record = (f"listening…  {rec.elapsed:.0f} of {rec.seconds:.0f} s", T.EMBER_BRIGHT)
        elif rec.error:
            record = (rec.error, T.ERROR)
        elif rec.has_clip:
            loud = "nothing but silence" if rec.peak < 0.02 else "quiet" if rec.peak < 0.15 else "good level" if rec.peak < 0.95 else "too loud (clipping)"
            record = (f"recorded: {loud}", T.ERROR if rec.peak < 0.02 else T.OK)
        else:
            record = ("microphone: " + mic_name, T.MUTED)
        going = MODE_NOTES.get(st.get("mode", "auto"), "") + "  ·  " + going if st else going
        return [("Output: " + mode, going, T.MUTED),
                ("Headphone jack", jack[0] + ("  (read backwards)" if st.get("jack_reversed") else ""), jack[1]),
                ("Test tone", "playing…" if rec.playing and not rec.recording else "left, right, then both", T.MUTED),
                ("Record 5 seconds", record[0], record[1]),
                ("Play it back", "playing…" if rec.playing else "through the output above", T.MUTED)]

    def draw(self, surf, f, area):
        y = area.y + 10
        row_h = f.line + f.small_line + 14
        for i, (title, detail, colour) in enumerate(self.lines()):
            r = pygame.Rect(area.x + 12, y, area.w - 24, row_h - 4)
            sel = i == self.sel
            if sel:
                G.box(surf, r, T.ROW, 6, T.EMBER)
            G.text(surf, f.big, G.fit(f.big, title, r.w - 28), (r.x + 14, r.y + 5), T.EMBER_BRIGHT if sel else T.TEXT)
            G.text(surf, f.small, G.fit(f.small, detail, r.w - 28), (r.x + 14, r.y + 9 + f.line), colour)
            if ROWS[i] == "record" and self.rec.recording:
                G.meter(surf, pygame.Rect(r.right - 174, r.y + 14, 160, 12), min(1, self.rec.level * 1.5))
            y += row_h
        note = ("This window uses the same default device every app gets. If it records your microphone "
                "and an app does not, that app is picking its own device.")
        for k, ln in enumerate(G.wrap(f.small, note, area.w - 32)[:3]):
            G.text(surf, f.small, ln, (area.x + 16, area.bottom - 3 * f.small_line - 6 + k * f.small_line), T.DIM)
