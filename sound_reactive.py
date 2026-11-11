"""
Sound-reactive rainbow light effect for the Edifier R20.

While enabled, the RGB color of the selected RGB-settable light mode
(e.g. "海妖之聲" / Siren Song, index 2) follows the current audio level:
the louder the sound, the brighter the color and the faster the rainbow
hue advances.

The audio level is measured with the platform audio peak meter (Windows
WASAPI endpoint meter, or the PulseAudio/PipeWire monitor on Linux, see
:mod:`audio_meter`).
If the meter is unavailable, the speaker hardware volume is used as a
fallback so the option keeps working everywhere.
"""

import colorsys
import threading
import time

from PyQt6.QtCore import QThread, pyqtSignal

from audio_meter import create_audio_meter
from r20_controller import RGB_MODE_MAP


class SoundReactiveLight(QThread):
    """
    Background worker that turns the speaker RGB light into a dancing
    rainbow driven by the live audio level.
    """

    color_changed = pyqtSignal(int, int, int)   # current animated RGB
    level_changed = pyqtSignal(float)           # smoothed 0.0 - 1.0 level

    TICK_SECONDS = 0.055

    def __init__(self, r20_controller):
        super().__init__()
        self.r20 = r20_controller
        self._running = True
        self._lock = threading.Lock()
        self._active = False
        self._mode = 2
        self._level = 0.0
        self._hue = 0.0
        self._last_rgb = (-1, -1, -1)
        self._last_send = 0.0
        self._applied_mode = None
        self._audio_meter = None

    # ------------------------------------------------------------------ API
    def start_effect(self, mode_index: int):
        with self._lock:
            self._mode = int(mode_index)
            self._active = True
            self._level = 0.0
            self._applied_mode = None

    def stop_effect(self):
        with self._lock:
            self._active = False
            self._applied_mode = None
            self._last_rgb = (-1, -1, -1)

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def mode(self) -> int:
        with self._lock:
            return self._mode

    def stop(self):
        self._running = False
        self.wait(1500)

    # -------------------------------------------------------- audio meter
    def _read_peak(self):
        if self._audio_meter is None:
            self._audio_meter = create_audio_meter()
        return self._audio_meter.get_peak()

    # -------------------------------------------------------------- loop
    def run(self):
        try:
            while self._running:
                with self._lock:
                    active = self._active
                    mode = self._mode
                    applied = self._applied_mode
                if not active:
                    time.sleep(0.12)
                    continue

                # Make sure the target light mode is active (also re-enables the
                # mood light if it was switched off with mode 7).
                if applied != mode:
                    if self.r20.set_light_mode(mode):
                        with self._lock:
                            self._applied_mode = mode
                    else:
                        time.sleep(0.3)
                        continue

                peak = self._read_peak()
                if peak is None:
                    # Fallback: use the speaker hardware volume as level
                    level = max(0.0, min(1.0, self.r20.current_volume / 16.0))
                else:
                    level = max(0.0, min(1.0, peak))

                # Fast attack, slow release for a lively but not jittery feel
                if level > self._level:
                    self._level += (level - self._level) * 0.45
                else:
                    self._level += (level - self._level) * 0.10
                lvl = self._level

                # Hue = slow rainbow drift + direct level-driven offset, so the
                # colour jumps with the beat (follows sound level) while still
                # cycling through the rainbow.
                self._hue = (self._hue + 0.008 + 0.045 * lvl) % 1.0
                hue = (self._hue + 0.45 * min(1.0, lvl * 1.5)) % 1.0
                value = 0.28 + 0.72 * min(1.0, lvl * 1.15)
                r, g, b = colorsys.hsv_to_rgb(hue, 1.0, value)
                rgb = (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))

                self.level_changed.emit(lvl)

                # Re-check before writing: the effect may have been stopped
                # while this tick was computing.
                with self._lock:
                    if not self._active:
                        continue

                now = time.time()
                if rgb != self._last_rgb and (now - self._last_send) >= 0.045:
                    if self.r20.set_light_color_fast(rgb[0], rgb[1], rgb[2], mode_index=mode):
                        self._last_rgb = rgb
                        self._last_send = now
                        self.color_changed.emit(rgb[0], rgb[1], rgb[2])

                time.sleep(self.TICK_SECONDS)
        finally:
            meter, self._audio_meter = self._audio_meter, None
            if meter is not None:
                try:
                    meter.close()
                except Exception:
                    pass


def is_rgb_settable_mode(mode_index: int) -> bool:
    spec = RGB_MODE_MAP.get(mode_index)
    return bool(spec and spec.get("rgb_settable"))
