"""
Cross-platform audio peak meter used by the sound-reactive rainbow light.

Two implementations are provided:

* :class:`WasapiMeter` (Windows) reads ``IAudioMeterInformation`` of the default
  render endpoint through pycaw/comtypes.
* :class:`PulseMonitorMeter` (Linux) records the default sink monitor with
  ``parec`` (works for PulseAudio and PipeWire via pipewire-pulse) and tracks the
  peak of the last audio block.

Both return a normalised 0.0 - 1.0 peak, or ``None`` when the meter is not
available; callers should then fall back to the speaker hardware volume.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from array import array

from platform_utils import IS_LINUX, IS_WINDOWS

if IS_WINDOWS:  # pragma: no cover - Windows only import chain
    import comtypes
    from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
    from comtypes.automation import UINT
    from ctypes import POINTER, c_float

    class IAudioMeterInformation(IUnknown):
        _iid_ = GUID("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetPeakValue",
                      (["out"], POINTER(c_float), "pfPeak")),
            COMMETHOD([], HRESULT, "GetMeteringChannelCount",
                      (["out"], POINTER(UINT), "pnChannelCount")),
            COMMETHOD([], HRESULT, "GetChannelsPeakValues",
                      (["in"], UINT, "u32ChannelCount"),
                      (["out"], POINTER(c_float), "afPeakValues")),
            COMMETHOD([], HRESULT, "QueryHardwareSupport",
                      (["out"], POINTER(comtypes.c_ulong), "pdwHardwareSupportMask")),
        ]


class AudioMeter:
    """Base class returning "no metering available"."""

    name = "none"

    def get_peak(self):
        return None

    def close(self):
        pass


class WasapiMeter(AudioMeter):
    """Windows WASAPI endpoint peak meter."""

    name = "wasapi"

    def __init__(self):
        self._meter = None
        self._retry_at = 0.0
        self._com_ready = False

    def _ensure_com(self):
        if not self._com_ready:
            comtypes.CoInitialize()
            self._com_ready = True

    def _open(self):
        try:
            from pycaw.utils import AudioUtilities

            speakers = AudioUtilities.GetSpeakers()
            if not speakers or not hasattr(speakers, "_dev"):
                return None
            iface = speakers._dev.Activate(
                IAudioMeterInformation._iid_, comtypes.CLSCTX_ALL, None
            )
            return iface.QueryInterface(IAudioMeterInformation)
        except Exception:
            return None

    def get_peak(self):
        self._ensure_com()
        now = time.time()
        if self._meter is None:
            if now < self._retry_at:
                return None
            self._retry_at = now + 5.0
            self._meter = self._open()
        if self._meter is None:
            return None
        try:
            return float(self._meter.GetPeakValue())
        except Exception:
            self._meter = None
            self._retry_at = now + 5.0
            return None

    def close(self):
        self._meter = None
        if self._com_ready:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass
            self._com_ready = False


class PulseMonitorMeter(AudioMeter):
    """Linux peak meter reading the default sink monitor via ``parec``."""

    name = "pulse-monitor"

    def __init__(self, rate: int = 8000, chunk_bytes: int = 4096):
        self._rate = rate
        self._chunk = chunk_bytes
        self._proc = None
        self._thread = None
        self._peak = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._next_attempt = 0.0

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _default_monitor():
        pactl = shutil.which("pactl")
        if not pactl:
            return None
        try:
            result = subprocess.run(
                [pactl, "get-default-sink"], capture_output=True, text=True, timeout=3
            )
        except (OSError, subprocess.SubprocessError):
            return None
        lines = (result.stdout or "").strip().splitlines()
        if not lines or not lines[0].strip():
            return None
        return lines[0].strip() + ".monitor"

    def _ensure_started(self) -> bool:
        if self._proc is not None and self._proc.poll() is None:
            return True
        now = time.time()
        if now < self._next_attempt:
            return False
        self._next_attempt = now + 5.0
        parec = shutil.which("parec")
        if not parec:
            return False
        device = self._default_monitor()
        if not device:
            return False
        args = [
            parec,
            "--raw",
            "--format=s16le",
            "--rate=%d" % self._rate,
            "--channels=1",
            "--latency-msec=30",
            "--device=" + device,
        ]
        try:
            self._proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
        except OSError:
            self._proc = None
            return False
        self._thread = threading.Thread(
            target=self._reader, args=(self._proc,), daemon=True, name="edifier-audio-meter"
        )
        self._thread.start()
        return True

    def _reader(self, proc):
        stdout = proc.stdout
        if stdout is None:
            return
        while not self._stop.is_set():
            try:
                data = stdout.read(self._chunk)
            except (OSError, ValueError):
                break
            if not data:
                break
            if len(data) % 2:
                data = data[:-1]
            samples = array("h")
            samples.frombytes(data)
            if not samples:
                continue
            peak = max(max(samples), -min(samples)) / 32768.0
            with self._lock:
                # Fast attack, fast release; the animation loop smooths further.
                self._peak = max(peak, self._peak * 0.72)
        try:
            proc.terminate()
        except OSError:
            pass

    # ---------------------------------------------------------------- api
    def get_peak(self):
        self._ensure_started()
        with self._lock:
            return min(1.0, self._peak)

    def close(self):
        self._stop.set()
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.terminate()
            except OSError:
                pass
            try:
                proc.wait(timeout=1.0)
            except Exception:
                pass


def create_audio_meter() -> AudioMeter:
    if IS_WINDOWS:
        return WasapiMeter()
    if IS_LINUX:
        return PulseMonitorMeter()
    return AudioMeter()
