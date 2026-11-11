"""
System volume bridge for the Edifier R20.

The speaker has its own 0-16 hardware amplifier volume that is independent from
the operating system mixer.  This module keeps both in sync:

* :class:`WindowsVolumeSync` uses the Windows CoreAudio API (pycaw) and also
  follows physical volume keys.
* :class:`LinuxVolumeSync` uses ``wpctl`` (PipeWire / WirePlumber) or ``pactl``
  (PulseAudio) and mirrors the default sink.
* :class:`NullVolumeSync` keeps the application usable on unsupported
  platforms; it simply never changes anything.

Use :func:`create_volume_sync` to get the implementation for the current OS.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time

from PyQt6.QtCore import QThread, pyqtSignal

VK_LBUTTON     = 0x01
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP   = 0xAF

IS_WINDOWS = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")


class VolumeSyncBase(QThread):
    """Shared state machine for the platform specific workers."""

    # Signals emitted to the UI thread
    windows_volume_changed = pyqtSignal(float, bool)  # system scalar (0.0-1.0), muted
    speaker_synced = pyqtSignal(int)                  # new R20 volume (0-16) set from the OS
    hardware_volume_changed = pyqtSignal(int)         # new R20 volume from a physical button

    def __init__(self, r20_controller, enabled=True, keep_windows_100=True):
        super().__init__()
        self.r20 = r20_controller
        self.enabled = bool(enabled)
        self.keep_windows_100 = bool(keep_windows_100)
        self._running = True
        self._suppress_until = 0.0
        self._pending_restore_100_at = 0.0
        self._last_win_scalar = -1.0
        self._last_win_mute = False
        self._last_r20_vol = -1

    # --------------------------------------------------------------- config
    def set_sync_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        if not self.enabled:
            self._pending_restore_100_at = 0.0

    def set_keep_windows_100(self, keep_100: bool):
        self.keep_windows_100 = bool(keep_100)
        self._pending_restore_100_at = 0.0
        if self.enabled:
            if self.keep_windows_100:
                self.set_windows_volume_scalar(1.0)
            else:
                self.sync_windows_to_speaker_immediately()

    # -------------------------------------------------------------- helpers
    def get_windows_volume_scalar(self):
        """Current system master volume scalar (0.0 - 1.0), or None."""
        return None

    def set_windows_volume_scalar(self, win_scalar: float) -> bool:
        """Set the system master volume scalar (0.0 - 1.0)."""
        return False

    def sync_windows_to_speaker_immediately(self):
        """Align the system mixer with the current speaker hardware volume."""
        r20_vol = max(0, min(16, int(self.r20.current_volume)))
        self._last_r20_vol = r20_vol
        if self.keep_windows_100:
            self.set_windows_volume_scalar(1.0)
            return 1.0
        win_scalar = max(0.0, min(1.0, r20_vol / 16.0))
        self.set_windows_volume_scalar(win_scalar)
        return win_scalar

    def on_user_changed_r20_volume(self, r20_vol: int):
        """Called when the user changed the speaker volume from the tray app."""
        self._last_r20_vol = r20_vol
        if not self.enabled:
            return
        if self.keep_windows_100:
            self.set_windows_volume_scalar(1.0)
        else:
            win_scalar = max(0.0, min(1.0, r20_vol / 16.0))
            self.set_windows_volume_scalar(win_scalar)

    def stop(self):
        self._running = False
        self.wait(1500)

    def _apply_hardware_button_volume(self, hw_vol: int):
        """Mirror a physical volume button change onto the system mixer."""
        if not self.enabled:
            return
        if self.keep_windows_100:
            self._suppress_until = time.time() + 0.5
            self._last_win_scalar = 1.0
            self._last_win_mute = False
            current = self.get_windows_volume_scalar()
            if current is None or abs(current - 1.0) > 0.01:
                self.set_windows_volume_scalar(1.0)
        else:
            self._suppress_until = time.time() + 0.8
            win_scalar = max(0.0, min(1.0, hw_vol / 16.0))
            self._last_win_scalar = win_scalar
            self._last_win_mute = (hw_vol == 0)
            self.set_windows_volume_scalar(win_scalar)


class WindowsVolumeSync(VolumeSyncBase):
    """Windows implementation based on pycaw (WASAPI endpoint volume)."""

    def __init__(self, r20_controller, enabled=True, keep_windows_100=True):
        super().__init__(r20_controller, enabled, keep_windows_100)
        self._mute_key_was_down = False
        # Clear initial async key state bits
        try:
            import ctypes

            u32 = ctypes.windll.user32
            u32.GetAsyncKeyState(VK_VOLUME_UP)
            u32.GetAsyncKeyState(VK_VOLUME_DOWN)
            u32.GetAsyncKeyState(VK_VOLUME_MUTE)
        except Exception:
            pass

    # --------------------------------------------------------------- pycaw
    @staticmethod
    def _endpoint():
        from pycaw.utils import AudioUtilities

        speakers = AudioUtilities.GetSpeakers()
        if not speakers:
            return None
        return speakers.EndpointVolume

    def get_windows_volume_scalar(self):
        try:
            import comtypes

            comtypes.CoInitialize()
            try:
                ep = self._endpoint()
                if ep is not None:
                    if ep.GetMute():
                        return 0.0
                    return float(ep.GetMasterVolumeLevelScalar())
            finally:
                comtypes.CoUninitialize()
        except Exception as exc:
            print("Error reading Windows volume: %s" % exc)
        return None

    def set_windows_volume_scalar(self, win_scalar: float) -> bool:
        win_scalar = max(0.0, min(1.0, float(win_scalar)))
        self._suppress_until = time.time() + 0.08
        self._last_win_scalar = win_scalar
        self._last_win_mute = (win_scalar <= 0.001)
        try:
            import comtypes

            comtypes.CoInitialize()
            try:
                ep = self._endpoint()
                if ep is not None:
                    ep.SetMasterVolumeLevelScalar(win_scalar, None)
                    if win_scalar <= 0.001:
                        ep.SetMute(1, None)
                    elif ep.GetMute():
                        ep.SetMute(0, None)
                    return True
            finally:
                comtypes.CoUninitialize()
        except Exception as exc:
            print("Error setting Windows volume scalar: %s" % exc)
        return False

    # ----------------------------------------------------------------- loop
    def run(self):
        """
        Background loop polling both R20 hardware buttons and Windows master
        volume every 150 ms.
        """
        import comtypes

        comtypes.CoInitialize()
        user32 = None
        try:
            import ctypes

            user32 = ctypes.windll.user32
        except Exception:
            user32 = None

        ep = None
        try:
            while self._running:
                try:
                    # 1. Poll physical hardware buttons on Edifier R20
                    if self.r20.is_connected:
                        hw_changed, hw_vol = self.r20.poll_hardware()
                        if hw_changed:
                            self._last_r20_vol = hw_vol
                            if ep is not None and self.enabled:
                                try:
                                    if self.keep_windows_100:
                                        if abs(ep.GetMasterVolumeLevelScalar() - 1.0) > 0.01:
                                            ep.SetMasterVolumeLevelScalar(1.0, None)
                                        if ep.GetMute():
                                            ep.SetMute(0, None)
                                    else:
                                        win_scalar = max(0.0, min(1.0, hw_vol / 16.0))
                                        ep.SetMasterVolumeLevelScalar(win_scalar, None)
                                        if hw_vol == 0:
                                            ep.SetMute(1, None)
                                        elif ep.GetMute():
                                            ep.SetMute(0, None)
                                except Exception:
                                    pass
                            self.hardware_volume_changed.emit(hw_vol)

                    # 2. Get or refresh the audio endpoint if needed
                    if ep is None:
                        try:
                            ep = self._endpoint()
                        except Exception:
                            ep = None

                    if ep is not None:
                        current_scalar = ep.GetMasterVolumeLevelScalar()
                        is_muted = bool(ep.GetMute())

                        if self._last_win_scalar < 0.0:
                            self._last_win_scalar = current_scalar
                            self._last_win_mute = is_muted
                            changed = False
                        elif time.time() <= self._suppress_until:
                            changed = False
                        else:
                            changed = (
                                abs(current_scalar - self._last_win_scalar) > 0.015
                                or is_muted != self._last_win_mute
                            )

                        if changed:
                            self._last_win_scalar = current_scalar
                            self._last_win_mute = is_muted
                            self.windows_volume_changed.emit(current_scalar, is_muted)

                            if self.enabled:
                                if is_muted:
                                    target_r20 = 0
                                else:
                                    target_r20 = round(current_scalar * 16)

                                if target_r20 != self.r20.current_volume:
                                    self.r20.set_volume(target_r20)
                                    self._last_r20_vol = target_r20
                                    self.speaker_synced.emit(target_r20)

                                if self.keep_windows_100:
                                    self._pending_restore_100_at = time.time() + 0.35

                        # Snap the Windows mixer back to 100% after the user lets
                        # go of the volume slider.
                        if (
                            self.enabled
                            and self.keep_windows_100
                            and self._pending_restore_100_at > 0.0
                        ):
                            lbutton_down = bool(
                                user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000
                            ) if user32 is not None else False
                            if lbutton_down:
                                self._pending_restore_100_at = time.time() + 0.25
                            elif time.time() >= self._pending_restore_100_at:
                                self._pending_restore_100_at = 0.0
                                self._suppress_until = time.time() + 0.08
                                try:
                                    ep.SetMasterVolumeLevelScalar(1.0, None)
                                    if ep.GetMute():
                                        ep.SetMute(0, None)
                                    self._last_win_scalar = 1.0
                                    self._last_win_mute = False
                                except Exception:
                                    pass
                except Exception:
                    # Endpoint may be invalid if the device was reconnected
                    ep = None
                    time.sleep(1.0)

                time.sleep(0.15)
        finally:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass


class LinuxVolumeSync(VolumeSyncBase):
    """Linux implementation driving the default sink via wpctl or pactl."""

    POLL_SECONDS = 0.3

    def __init__(self, r20_controller, enabled=True, keep_windows_100=False):
        super().__init__(r20_controller, enabled, keep_windows_100)
        self.backend = self._detect_backend()

    @staticmethod
    def _detect_backend() -> str:
        if shutil.which("wpctl"):
            return "wpctl"
        if shutil.which("pactl"):
            return "pactl"
        return ""

    # ------------------------------------------------------------ commands
    @staticmethod
    def _capture(args, timeout=3.0):
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            return None
        if proc.returncode != 0:
            return None
        return proc.stdout or ""

    @staticmethod
    def _exec(args, timeout=3.0) -> bool:
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            return proc.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def _read_sink(self):
        """Returns (scalar, muted) for the default sink, or None."""
        if self.backend == "wpctl":
            out = self._capture(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
            if not out:
                return None
            match = re.search(r"([0-9]*\.?[0-9]+)", out)
            if not match:
                return None
            scalar = max(0.0, min(1.0, float(match.group(1))))
            return scalar, ("MUTED" in out.upper())
        if self.backend == "pactl":
            vol_out = self._capture(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
            if not vol_out:
                return None
            match = re.search(r"(\d+)%", vol_out)
            if not match:
                return None
            mute_out = self._capture(["pactl", "get-sink-mute", "@DEFAULT_SINK@"]) or ""
            muted = "yes" in mute_out.lower()
            return max(0.0, min(1.0, float(match.group(1)) / 100.0)), muted
        return None

    # ----------------------------------------------------------------- api
    def get_windows_volume_scalar(self):
        state = self._read_sink()
        if state is None:
            return None
        scalar, muted = state
        return 0.0 if muted else scalar

    def set_windows_volume_scalar(self, win_scalar: float) -> bool:
        win_scalar = max(0.0, min(1.0, float(win_scalar)))
        self._suppress_until = time.time() + 0.08
        self._last_win_scalar = win_scalar
        self._last_win_mute = (win_scalar <= 0.001)
        if self.backend == "wpctl":
            ok = self._exec(
                ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "%.3f" % win_scalar]
            )
            ok = self._exec(
                [
                    "wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@",
                    "1" if win_scalar <= 0.001 else "0",
                ]
            ) and ok
            return ok
        if self.backend == "pactl":
            ok = self._exec(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "%d%%" % int(round(win_scalar * 100))]
            )
            ok = self._exec(
                [
                    "pactl", "set-sink-mute", "@DEFAULT_SINK@",
                    "1" if win_scalar <= 0.001 else "0",
                ]
            ) and ok
            return ok
        return False

    # ----------------------------------------------------------------- loop
    def run(self):
        ep_state = self._read_sink()
        if ep_state is not None:
            self._last_win_scalar, self._last_win_mute = ep_state

        while self._running:
            try:
                # 1. Physical volume buttons / knob on the speaker itself
                if self.r20.is_connected:
                    hw_changed, hw_vol = self.r20.poll_hardware()
                    if hw_changed:
                        self._last_r20_vol = hw_vol
                        self._apply_hardware_button_volume(hw_vol)
                        self.hardware_volume_changed.emit(hw_vol)

                # 2. Default sink volume changed by the desktop (volume keys,
                #    mixer applet, media player ...)
                state = self._read_sink()
                if state is not None:
                    scalar, muted = state
                    if self._last_win_scalar < 0.0:
                        self._last_win_scalar, self._last_win_mute = scalar, muted
                        changed = False
                    elif time.time() <= self._suppress_until:
                        changed = False
                    else:
                        changed = (
                            abs(scalar - self._last_win_scalar) > 0.015
                            or muted != self._last_win_mute
                        )

                    if changed:
                        self._last_win_scalar, self._last_win_mute = scalar, muted
                        self.windows_volume_changed.emit(scalar, muted)
                        if self.enabled:
                            target_r20 = 0 if muted else int(round(scalar * 16))
                            if target_r20 != self.r20.current_volume:
                                self.r20.set_volume(target_r20)
                                self._last_r20_vol = target_r20
                                self.speaker_synced.emit(target_r20)
                            if self.keep_windows_100:
                                self._pending_restore_100_at = time.time() + 0.35

                    if (
                        self.enabled
                        and self.keep_windows_100
                        and self._pending_restore_100_at > 0.0
                        and time.time() >= self._pending_restore_100_at
                    ):
                        self._pending_restore_100_at = 0.0
                        self.set_windows_volume_scalar(1.0)
            except Exception as exc:
                print("Volume sync error: %s" % exc)
                time.sleep(1.0)

            time.sleep(self.POLL_SECONDS)


class NullVolumeSync(VolumeSyncBase):
    """No-op worker used when the platform has no supported mixer backend."""

    def run(self):
        while self._running:
            try:
                if self.r20.is_connected:
                    hw_changed, hw_vol = self.r20.poll_hardware()
                    if hw_changed:
                        self._last_r20_vol = hw_vol
                        self.hardware_volume_changed.emit(hw_vol)
            except Exception:
                time.sleep(0.5)
            time.sleep(0.5)


def create_volume_sync(r20_controller, enabled=True, keep_windows_100=True) -> VolumeSyncBase:
    """Returns the system-volume bridge that matches the current platform."""
    if IS_WINDOWS:
        return WindowsVolumeSync(r20_controller, enabled, keep_windows_100)
    if IS_LINUX:
        return LinuxVolumeSync(r20_controller, enabled, keep_windows_100)
    return NullVolumeSync(r20_controller, enabled, keep_windows_100)
