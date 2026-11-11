"""
Shared Windows installer logic for the Edifier R20 tray controller.

Used by ``installer_app.py`` (the setup wizard / silent installer) and
``uninstaller_app.py`` (the generated ``Uninstall.exe``).  Only the standard
library is used so the uninstaller stays small and can run without Qt.

The installer is per-user: everything is written under ``%LOCALAPPDATA%`` and
``HKCU`` so no administrator rights are required.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import time
import uuid
import winreg
from ctypes import POINTER, byref, c_void_p, c_ulong, c_ushort, c_ubyte, wintypes

try:
    from platform_utils import APP_NAME, APP_PUBLISHER, APP_URL, APP_VERSION
except ImportError:  # pragma: no cover - fallback when imported standalone
    APP_NAME = "Edifier R20 Tray Controller"
    APP_PUBLISHER = "Mangotimmy"
    APP_URL = "https://github.com/Mangotimmy/speaker_control"
    APP_VERSION = "2.0.0"

APP_SHORT = "Edifier R20"
APP_EXE = "EdifierR20Tray.exe"
UNINSTALL_EXE = "Uninstall.exe"
APP_FOLDER = "EdifierR20Tray"

APP_REG_KEY = r"Software\EdifierR20Tray"
UNINSTALL_REG_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall\EdifierR20Tray"
)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "EdifierR20Tray"

CSIDL_PROGRAMS = 0x0002
CSIDL_DESKTOPDIRECTORY = 0x0010
CSIDL_APPDATA = 0x001A


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def _folder(csidl: int) -> str:
    buffer = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
    try:
        ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buffer)
    except OSError:
        pass
    return buffer.value


def appdata_dir() -> str:
    return _folder(CSIDL_APPDATA) or os.environ.get(
        "APPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    )


def local_appdata_dir() -> str:
    return os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Local"
    )


def default_install_dir() -> str:
    return os.path.join(local_appdata_dir(), "Programs", APP_FOLDER)


def settings_dir() -> str:
    return os.path.join(appdata_dir(), APP_FOLDER)


def desktop_dir() -> str:
    return _folder(CSIDL_DESKTOPDIRECTORY) or os.path.join(
        os.path.expanduser("~"), "Desktop"
    )


def start_menu_programs_dir() -> str:
    return _folder(CSIDL_PROGRAMS) or os.path.join(
        appdata_dir(), "Microsoft", "Windows", "Start Menu", "Programs"
    )


def start_menu_folder() -> str:
    return os.path.join(start_menu_programs_dir(), APP_SHORT)


def registry_install_dir() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APP_REG_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "InstallDir")
            return str(value)
    except OSError:
        return ""


def resolve_install_dir() -> str:
    return registry_install_dir() or default_install_dir()


def app_exe_path(install_dir: str | None = None) -> str:
    return os.path.join(install_dir or resolve_install_dir(), APP_EXE)


def uninstaller_path(install_dir: str | None = None) -> str:
    return os.path.join(install_dir or resolve_install_dir(), UNINSTALL_EXE)


def desktop_shortcut_path() -> str:
    return os.path.join(desktop_dir(), APP_SHORT + ".lnk")


def start_menu_shortcut_path() -> str:
    return os.path.join(start_menu_folder(), APP_SHORT + ".lnk")


def start_menu_uninstall_shortcut_path() -> str:
    return os.path.join(start_menu_folder(), "解除安裝 %s.lnk" % APP_SHORT)


# ---------------------------------------------------------------------------
# COM shortcut creation (no WScript.Shell dependency)
# ---------------------------------------------------------------------------
class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", c_ulong),
        ("Data2", c_ushort),
        ("Data3", c_ushort),
        ("Data4", c_ubyte * 8),
    ]


def _guid(text: str) -> _GUID:
    guid = _GUID()
    ctypes.memmove(ctypes.byref(guid), uuid.UUID(text).bytes_le, 16)
    return guid


_CLSID_SHELLLINK = _guid("00021401-0000-0000-C000-000000000046")
_IID_ISHELLLINKW = _guid("000214F9-0000-0000-C000-000000000046")
_IID_IPERSISTFILE = _guid("0000010B-0000-0000-C000-000000000046")
_CLSCTX_INPROC_SERVER = 1
_HRESULT = ctypes.c_long

_ole32 = ctypes.OleDLL("ole32")
_ole32.CoInitialize.argtypes = [c_void_p]
_ole32.CoInitialize.restype = _HRESULT
_ole32.CoUninitialize.argtypes = []
_ole32.CoUninitialize.restype = None
_ole32.CoCreateInstance.argtypes = [
    POINTER(_GUID), c_void_p, wintypes.DWORD, POINTER(_GUID), POINTER(c_void_p)
]
_ole32.CoCreateInstance.restype = _HRESULT


def _vtbl(interface: c_void_p, index: int, argtypes, args):
    vtable = ctypes.cast(interface, POINTER(POINTER(c_void_p)))[0]
    prototype = ctypes.WINFUNCTYPE(_HRESULT, c_void_p, *argtypes)
    function = prototype(vtable[index])
    return function(interface, *args)


def _release(interface: c_void_p) -> None:
    try:
        vtable = ctypes.cast(interface, POINTER(POINTER(c_void_p)))[0]
        prototype = ctypes.WINFUNCTYPE(c_ulong, c_void_p)
        prototype(vtable[2])(interface)
    except Exception:
        pass


def create_shortcut(
    lnk_path: str,
    target: str,
    arguments: str = "",
    working_dir: str = "",
    icon_path: str = "",
    description: str = "",
) -> bool:
    """Creates a .lnk file through IShellLinkW/IPersistFile (no WSH needed)."""
    os.makedirs(os.path.dirname(lnk_path), exist_ok=True)
    _ole32.CoInitialize(None)
    shell_link = c_void_p()
    persist_file = c_void_p()
    try:
        hr = _ole32.CoCreateInstance(
            byref(_CLSID_SHELLLINK), None, _CLSCTX_INPROC_SERVER,
            byref(_IID_ISHELLLINKW), byref(shell_link),
        )
        if hr != 0 or not shell_link:
            raise OSError("IShellLink CoCreateInstance failed: 0x%08X" % (hr & 0xFFFFFFFF))
        _vtbl(shell_link, 20, [wintypes.LPCWSTR], [target])          # SetPath
        if description:
            _vtbl(shell_link, 7, [wintypes.LPCWSTR], [description])  # SetDescription
        if working_dir:
            _vtbl(shell_link, 9, [wintypes.LPCWSTR], [working_dir])  # SetWorkingDirectory
        if arguments:
            _vtbl(shell_link, 11, [wintypes.LPCWSTR], [arguments])   # SetArguments
        if icon_path:
            _vtbl(shell_link, 17, [wintypes.LPCWSTR, ctypes.c_int], [icon_path, 0])

        hr = _vtbl(
            shell_link, 0, [POINTER(_GUID), POINTER(c_void_p)],
            [byref(_IID_IPERSISTFILE), byref(persist_file)],
        )
        if hr != 0 or not persist_file:
            raise OSError("IPersistFile QueryInterface failed: 0x%08X" % (hr & 0xFFFFFFFF))
        hr = _vtbl(persist_file, 6, [wintypes.LPCWSTR, wintypes.BOOL], [lnk_path, True])
        if hr != 0:
            raise OSError("IPersistFile::Save failed: 0x%08X" % (hr & 0xFFFFFFFF))
        return True
    finally:
        if persist_file:
            _release(persist_file)
        if shell_link:
            _release(shell_link)
        try:
            _ole32.CoUninitialize()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Process control
# ---------------------------------------------------------------------------
def kill_running_app() -> None:
    """Stops a running copy so the application files can be replaced/removed."""
    creationflags = 0x08000000  # CREATE_NO_WINDOW
    for image in (APP_EXE,):
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", image],
                capture_output=True, creationflags=creationflags, timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    time.sleep(0.4)


def launch_app(exe_path: str) -> bool:
    try:
        subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# File copy
# ---------------------------------------------------------------------------
def collect_files(root: str):
    files = []
    for directory, _dirs, names in os.walk(root):
        for name in names:
            full = os.path.join(directory, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            files.append((full, os.path.relpath(full, root), size))
    return files


def copy_tree_with_progress(src: str, dst: str, progress=None) -> int:
    """Copies ``src`` into ``dst``; ``progress(percent, message)`` is optional."""
    files = collect_files(src)
    total = sum(size for _full, _rel, size in files) or 1
    done = 0
    copied = 0
    os.makedirs(dst, exist_ok=True)
    for full, rel, size in files:
        target = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(full, target)
        done += size
        copied += 1
        if progress is not None:
            percent = int(done * 85 / total)  # copying is the first 85% of the work
            if copied % 8 == 0 or done >= total:
                progress(percent, rel)
    return copied


def directory_size_kb(path: str) -> int:
    total = 0
    for directory, _dirs, names in os.walk(path):
        for name in names:
            try:
                total += os.path.getsize(os.path.join(directory, name))
            except OSError:
                pass
    return max(1, int(round(total / 1024.0)))


def is_safe_install_dir(path: str) -> bool:
    """Guards against ever deleting something that is not our install folder."""
    path = os.path.abspath(path)
    if os.path.basename(path).lower() != APP_FOLDER.lower():
        return False
    if len(path.split(os.sep)) < 4:
        return False
    protected = {
        os.path.abspath(local_appdata_dir()),
        os.path.abspath(os.path.expanduser("~")),
    }
    return path not in protected


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
def _set_value(root, path, name, value, value_type=winreg.REG_SZ):
    with winreg.CreateKey(root, path) as key:
        winreg.SetValueEx(key, name, 0, value_type, value)


def _delete_value(root, path, name):
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
    except OSError:
        pass


def _delete_tree(root, path):
    try:
        winreg.DeleteKey(root, path)
    except OSError:
        pass


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
            return bool(value)
    except OSError:
        return False


def set_autostart(enabled: bool, install_dir: str) -> None:
    if enabled:
        _set_value(
            winreg.HKEY_CURRENT_USER, RUN_KEY, RUN_VALUE,
            '"%s"' % app_exe_path(install_dir),
        )
    else:
        _delete_value(winreg.HKEY_CURRENT_USER, RUN_KEY, RUN_VALUE)


def write_registry(install_dir: str) -> None:
    exe = app_exe_path(install_dir)
    uninstaller = uninstaller_path(install_dir)
    _set_value(winreg.HKEY_CURRENT_USER, APP_REG_KEY, "InstallDir", install_dir)
    _set_value(winreg.HKEY_CURRENT_USER, APP_REG_KEY, "Version", APP_VERSION)

    entries = {
        "DisplayName": APP_NAME,
        "DisplayVersion": APP_VERSION,
        "Publisher": APP_PUBLISHER,
        "DisplayIcon": "%s,0" % exe,
        "InstallLocation": install_dir,
        "URLInfoAbout": APP_URL,
        "HelpLink": APP_URL,
        "UninstallString": '"%s"' % uninstaller,
        "QuietUninstallString": '"%s" --silent' % uninstaller,
    }
    for name, value in entries.items():
        _set_value(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_KEY, name, value)
    for name, value in (("NoModify", 1), ("NoRepair", 1)):
        _set_value(
            winreg.HKEY_CURRENT_USER, UNINSTALL_REG_KEY, name, value,
            winreg.REG_DWORD,
        )
    _set_value(
        winreg.HKEY_CURRENT_USER, UNINSTALL_REG_KEY, "EstimatedSize",
        directory_size_kb(install_dir), winreg.REG_DWORD,
    )


def remove_registry() -> None:
    _delete_value(winreg.HKEY_CURRENT_USER, RUN_KEY, RUN_VALUE)
    _delete_tree(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_KEY)
    _delete_tree(winreg.HKEY_CURRENT_USER, APP_REG_KEY)


# ---------------------------------------------------------------------------
# Shortcuts
# ---------------------------------------------------------------------------
def create_shortcuts(install_dir: str, desktop: bool = True):
    """Creates the shortcuts and returns a list of failures (path, reason)."""
    exe = app_exe_path(install_dir)
    icon = exe + ",0"
    failures = []
    # Start menu folder with the app and the uninstaller
    targets = [
        (
            start_menu_shortcut_path(), exe,
            dict(working_dir=install_dir, icon_path=icon,
                 description="Edifier R20 speaker volume and RGB light controller"),
        ),
        (
            start_menu_uninstall_shortcut_path(), uninstaller_path(install_dir),
            dict(working_dir=install_dir, description="解除安裝 %s" % APP_SHORT),
        ),
    ]
    if desktop:
        targets.append(
            (
                desktop_shortcut_path(), exe,
                dict(working_dir=install_dir, icon_path=icon,
                     description="Edifier R20 speaker controller"),
            )
        )
    for lnk_path, target, options in targets:
        try:
            create_shortcut(lnk_path, target, **options)
        except OSError as exc:
            failures.append((lnk_path, str(exc)))
    return failures


def remove_shortcuts() -> None:
    for path in (desktop_shortcut_path(),):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
    folder = start_menu_folder()
    try:
        shutil.rmtree(folder)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Install / uninstall drivers
# ---------------------------------------------------------------------------
def install(
    payload_dir: str,
    uninstaller_source: str,
    install_dir: str | None = None,
    desktop_shortcut: bool = True,
    autostart: bool = True,
    progress=None,
) -> str:
    """Installs the payload; returns the install directory."""
    target = os.path.abspath(install_dir or resolve_install_dir())
    if not is_safe_install_dir(target):
        raise RuntimeError("Refusing to install into an unexpected path: %s" % target)
    if not os.path.isfile(os.path.join(payload_dir, APP_EXE)):
        raise RuntimeError(
            "The application payload was not found next to the installer "
            "(%s)." % payload_dir
        )
    if not os.path.isfile(uninstaller_source):
        raise RuntimeError("The uninstaller payload is missing: %s" % uninstaller_source)

    def report(percent, message):
        if progress is not None:
            progress(max(0, min(100, percent)), message)

    report(2, "正在結束執行中的程式…")
    kill_running_app()

    report(4, "正在準備安裝資料夾…")
    if os.path.isdir(target):
        if not _force_rmtree(target):
            raise RuntimeError("無法移除舊版本檔案，請先關閉程式後重試。")
    os.makedirs(target, exist_ok=True)

    report(6, "正在複製程式檔案…")
    copy_tree_with_progress(payload_dir, target, progress=progress)

    report(88, "正在安裝解除安裝程式…")
    shutil.copy2(uninstaller_source, uninstaller_path(target))

    report(91, "正在建立捷徑…")
    failures = create_shortcuts(target, desktop=desktop_shortcut)
    if failures:
        for lnk_path, reason in failures:
            print("Shortcut could not be created (%s): %s" % (lnk_path, reason))

    report(95, "正在寫入登錄資訊…")
    try:
        write_registry(target)
        set_autostart(autostart, target)
    except OSError as exc:
        # Offer to keep going: the application itself is already installed.
        print("Registry update failed: %s" % exc)

    report(100, "安裝完成")
    return target


def uninstall(remove_settings: bool = False, progress=None, install_dir: str | None = None) -> str:
    """Removes the application; returns the install directory that was removed."""
    target = os.path.abspath(install_dir or resolve_install_dir())
    if not is_safe_install_dir(target):
        raise RuntimeError("Refusing to uninstall from an unexpected path: %s" % target)

    def report(percent, message):
        if progress is not None:
            progress(max(0, min(100, percent)), message)

    report(5, "正在結束執行中的程式…")
    kill_running_app()

    report(30, "正在移除捷徑與登錄資訊…")
    remove_shortcuts()
    remove_registry()

    report(45, "正在刪除程式檔案…")
    removed = _force_rmtree(target)
    if not removed:
        raise RuntimeError(
            "部分檔案無法刪除，請確認程式已關閉後重試：\n%s" % target
        )

    if remove_settings:
        report(80, "正在刪除個人設定…")
        _force_rmtree(settings_dir())

    report(100, "解除安裝完成")
    return target


def _force_rmtree(path: str, attempts: int = 24, delay: float = 0.25) -> bool:
    """Deletes a directory tree, retrying while Windows releases file locks."""
    if not os.path.isdir(path):
        return True
    for _ in range(attempts):
        try:
            shutil.rmtree(path)
            return True
        except OSError:
            time.sleep(delay)
    return not os.path.isdir(path)
