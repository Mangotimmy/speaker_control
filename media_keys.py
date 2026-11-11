"""
Low level media-key hook (Windows only).

The tray app swallows the keyboard volume keys while ``keep_windows_100`` sync
mode is active, so pressing them changes the speaker's own amplifier volume
instead of moving the Windows mixer.  On other platforms this module degrades to
a no-op: the desktop's volume keys keep controlling the default sink, and the
Linux volume bridge mirrors that onto the speaker.

The callback receives a ``VK_VOLUME_*`` virtual key code and returns ``True``
when the key press must be swallowed.
"""

from __future__ import annotations

import sys

IS_WINDOWS = sys.platform.startswith("win")

if IS_WINDOWS:  # pragma: no cover - Windows only
    import ctypes
    from ctypes import wintypes

    WH_KEYBOARD_LL = 13
    WM_KEYDOWN = 0x0100
    WM_SYSKEYDOWN = 0x0104

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_ulonglong),
        ]

    LRESULT = ctypes.c_longlong
    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.SetWindowsHookExW.argtypes = [
        ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD
    ]
    _user32.SetWindowsHookExW.restype = wintypes.HHOOK
    _user32.CallNextHookEx.argtypes = [
        wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
    ]
    _user32.CallNextHookEx.restype = LRESULT
    _user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    _user32.UnhookWindowsHookEx.restype = wintypes.BOOL


class MediaKeyHook:
    """Installs a ``WH_KEYBOARD_LL`` hook that reports volume key presses."""

    MEDIA_KEYS = (0xAD, 0xAE, 0xAF)  # VK_VOLUME_MUTE / DOWN / UP

    def __init__(self, callback):
        self._callback = callback
        self._hhook = None
        self._proc = None

    @property
    def installed(self) -> bool:
        return bool(self._hhook)

    def install(self) -> bool:
        if not IS_WINDOWS or self._hhook:
            return self.installed

        def _hook_proc(nCode, wParam, lParam):
            if nCode >= 0 and self._callback is not None:
                try:
                    info = KBDLLHOOKSTRUCT.from_address(lParam)
                    if info.vkCode in self.MEDIA_KEYS and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        if self._callback(int(info.vkCode)):
                            return 1
                except Exception:
                    pass
            return _user32.CallNextHookEx(None, nCode, wParam, lParam)

        self._proc = HOOKPROC(_hook_proc)
        self._hhook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        return bool(self._hhook)

    def uninstall(self) -> None:
        if self._hhook:
            try:
                _user32.UnhookWindowsHookEx(self._hhook)
            except Exception:
                pass
        self._hhook = None
