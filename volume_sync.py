"""
Windows Volume Synchronization Worker for Edifier R20.
Monitors Windows master audio volume and syncs it with Edifier R20 hardware amplifier volume.
"""

import time
import ctypes
import comtypes
from PyQt6.QtCore import QThread, pyqtSignal
import pycaw.pycaw as pycaw
from pycaw.utils import AudioUtilities

VK_LBUTTON     = 0x01
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP   = 0xAF

class WindowsVolumeSync(QThread):
    # Signals emitted to UI
    windows_volume_changed = pyqtSignal(float, bool)  # scalar (0.0 - 1.0), is_muted
    speaker_synced = pyqtSignal(int)                 # new R20 volume (0 - 16)
    hardware_volume_changed = pyqtSignal(int)        # new R20 volume from physical hardware button (0 - 16)

    def __init__(self, r20_controller, enabled=True, keep_windows_100=True):
        super().__init__()
        self.r20 = r20_controller
        self.enabled = enabled
        self.keep_windows_100 = bool(keep_windows_100)
        self._running = True
        self._suppress_until = 0.0
        self._pending_restore_100_at = 0.0
        self._last_win_scalar = -1.0
        self._last_win_mute = False
        self._last_r20_vol = -1
        self._mute_key_was_down = False
        # Clear initial async key state bits
        try:
            u32 = ctypes.windll.user32
            u32.GetAsyncKeyState(VK_VOLUME_UP)
            u32.GetAsyncKeyState(VK_VOLUME_DOWN)
            u32.GetAsyncKeyState(VK_VOLUME_MUTE)
        except Exception:
            pass

    def set_sync_enabled(self, enabled: bool):
        self.enabled = enabled
        if not enabled:
            self._pending_restore_100_at = 0.0

    def set_keep_windows_100(self, keep_100: bool):
        self.keep_windows_100 = bool(keep_100)
        self._pending_restore_100_at = 0.0
        if self.enabled:
            if self.keep_windows_100:
                self.set_windows_volume_scalar(1.0)
            else:
                self.sync_windows_to_speaker_immediately()

    def get_windows_volume_scalar(self):
        """Returns the current Windows master volume scalar (0.0 - 1.0), or None on failure."""
        try:
            comtypes.CoInitialize()
            speakers = AudioUtilities.GetSpeakers()
            if speakers:
                ep = speakers.EndpointVolume
                if ep.GetMute():
                    return 0.0
                return float(ep.GetMasterVolumeLevelScalar())
        except Exception as e:
            print(f"Error reading Windows volume: {e}")
        finally:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass
        return None

    def set_windows_volume_scalar(self, win_scalar: float):
        """Sets the Windows master volume scalar (0.0 - 1.0) and updates baseline."""
        win_scalar = max(0.0, min(1.0, float(win_scalar)))
        self._suppress_until = time.time() + 0.08
        self._last_win_scalar = win_scalar
        self._last_win_mute = (win_scalar <= 0.001)
        try:
            comtypes.CoInitialize()
            speakers = AudioUtilities.GetSpeakers()
            if speakers:
                ep = speakers.EndpointVolume
                ep.SetMasterVolumeLevelScalar(win_scalar, None)
                if win_scalar <= 0.001:
                    ep.SetMute(1, None)
                elif ep.GetMute():
                    ep.SetMute(0, None)
                return True
        except Exception as e:
            print(f"Error setting Windows volume scalar: {e}")
        finally:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass
        return False

    def sync_windows_to_speaker_immediately(self):
        """
        Immediately aligns Windows system volume according to the active sync mode:
        - If keep_windows_100 is True: keeps Windows mixer volume at 100% (1.0).
        - Otherwise: sets Windows system volume to match the speaker's hardware volume (0 - 16).
        """
        r20_vol = max(0, min(16, int(self.r20.current_volume)))
        self._last_r20_vol = r20_vol
        if self.keep_windows_100:
            self.set_windows_volume_scalar(1.0)
            return 1.0
        win_scalar = max(0.0, min(1.0, r20_vol / 16.0))
        self.set_windows_volume_scalar(win_scalar)
        return win_scalar

    def stop(self):
        self._running = False
        self.wait(1000)

    def on_user_changed_r20_volume(self, r20_vol: int):
        """
        Called when the user adjusts volume directly from the Tray App.
        If sync is enabled and keep_windows_100 is False, update Windows master volume.
        If keep_windows_100 is True, ensure Windows master volume stays at 100%.
        """
        self._last_r20_vol = r20_vol
        if not self.enabled:
            return
        if self.keep_windows_100:
            self.set_windows_volume_scalar(1.0)
        else:
            win_scalar = max(0.0, min(1.0, r20_vol / 16.0))
            self.set_windows_volume_scalar(win_scalar)

    def run(self):
        """
        Background loop polling both R20 hardware buttons and Windows master volume every 150ms.
        """
        comtypes.CoInitialize()
        user32 = ctypes.windll.user32
        ep = None
        try:
            while self._running:
                try:
                    # 1. Poll physical hardware buttons on Edifier R20
                    if self.r20.is_connected:
                        hw_changed, hw_vol = self.r20.poll_hardware()
                        if hw_changed:
                            self._last_r20_vol = hw_vol
                            if self.enabled and ep is not None:
                                if self.keep_windows_100:
                                    # Keep Windows mixer at 100% while speaker hardware volume changes
                                    self._suppress_until = time.time() + 0.5
                                    self._last_win_scalar = 1.0
                                    self._last_win_mute = False
                                    try:
                                        if abs(ep.GetMasterVolumeLevelScalar() - 1.0) > 0.01:
                                            ep.SetMasterVolumeLevelScalar(1.0, None)
                                        if ep.GetMute():
                                            ep.SetMute(0, None)
                                    except Exception:
                                        pass
                                else:
                                    # Standard 1:1 sync: update Windows volume to match hardware button
                                    self._suppress_until = time.time() + 0.8
                                    win_scalar = max(0.0, min(1.0, hw_vol / 16.0))
                                    self._last_win_scalar = win_scalar
                                    self._last_win_mute = (hw_vol == 0)
                                    try:
                                        ep.SetMasterVolumeLevelScalar(win_scalar, None)
                                        if hw_vol == 0:
                                            ep.SetMute(1, None)
                                        elif ep.GetMute():
                                            ep.SetMute(0, None)
                                    except Exception:
                                        pass
                            self.hardware_volume_changed.emit(hw_vol)

                    # 2. Get or refresh Windows audio endpoint if needed
                    if ep is None:
                        speakers = AudioUtilities.GetSpeakers()
                        if speakers:
                            ep = speakers.EndpointVolume

                    if ep is not None:
                        current_scalar = ep.GetMasterVolumeLevelScalar()
                        is_muted = bool(ep.GetMute())

                        # Initialize baseline on first read without overwriting speaker hardware volume
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

                            # If sync is enabled, apply Windows lever change to speaker hardware volume
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
                                    # Schedule snapping Windows mixer back to 100% after lever adjustment
                                    self._pending_restore_100_at = time.time() + 0.35

                        # Restore Windows mixer to 100% once user releases the Windows volume lever
                        if self.enabled and self.keep_windows_100 and self._pending_restore_100_at > 0.0:
                            lbutton_down = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
                            if lbutton_down:
                                # Keep deferring while user is actively dragging the Windows slider
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
                    # Endpoint may be invalid if device was reconnected
                    ep = None
                    time.sleep(1.0)

                time.sleep(0.15)
        finally:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass
