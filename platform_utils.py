"""
Cross-platform helpers for the Edifier R20 tray controller.

Everything that differs between operating systems lives here:

* application / data / log directories (frozen PyInstaller build vs. source run),
* "start with the system" registration (Windows registry, freedesktop autostart),
* detached background launching (replaces the old VBScript launcher),
* the single-instance lock plus the "show my panel again" IPC trick,
* platform specific user facing wording.

The module only imports the standard library so it can be used by any other
module (including ``config.py``) without pulling in Qt.
"""

from __future__ import annotations

import os
import sys
import tempfile

APP_NAME = "Edifier R20 Tray Controller"
APP_SHORT_NAME = "Edifier R20"
APP_VERSION = "2.0.0"
APP_PUBLISHER = "Mangotimmy"
APP_URL = "https://github.com/Mangotimmy/speaker_control"

#: Folder name used for the configuration directory.
APP_DIR_NAME = "EdifierR20Tray"
#: Name used for the Windows Run key / linux autostart file / lock file.
STARTUP_NAME = "EdifierR20Tray"
#: freedesktop application id (also used as the Qt desktop file name).
DESKTOP_ID = "edifier-r20-tray"

IS_WINDOWS = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform == "darwin"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def is_frozen() -> bool:
    """True when running from a PyInstaller (or similar) bundle."""
    return bool(getattr(sys, "frozen", False))


def app_root() -> str:
    """Directory that contains the application entry point.

    For a frozen build this is the folder holding the executable, otherwise the
    folder holding the Python sources.
    """
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(*parts: str) -> str:
    """Absolute path to a bundled resource (works for onefile PyInstaller too)."""
    base = getattr(sys, "_MEIPASS", None) or app_root()
    return os.path.join(base, *parts)


def _base_dir(env_var: str, windows_dir: str, linux_dir: str, mac_dir: str) -> str:
    override = os.environ.get(env_var)
    if override:
        return override
    home = os.path.expanduser("~")
    if IS_WINDOWS:
        root = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        return os.path.join(root, windows_dir)
    if IS_MACOS:
        return os.path.join(home, "Library", "Application Support", mac_dir)
    root = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    return os.path.join(root, linux_dir)


def user_config_dir() -> str:
    """Per-user writable configuration directory (created on demand)."""
    path = _base_dir("EDIFIER_R20_CONFIG_HOME", APP_DIR_NAME, "edifier-r20-tray", APP_DIR_NAME)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def config_file_path() -> str:
    """Default configuration file location.

    * explicit override: ``EDIFIER_R20_CONFIG`` (used by tests and portable runs)
    * frozen build: ``<user config dir>/config.json`` so an install under
      ``Program Files`` stays writable
    * source run: ``./config.json`` next to the sources (developer friendly)
    """
    override = os.environ.get("EDIFIER_R20_CONFIG")
    if override:
        return os.path.abspath(override)
    if is_frozen():
        return os.path.join(user_config_dir(), "config.json")
    return os.path.join(app_root(), "config.json")


def log_dir() -> str:
    """Directory for log files (created on demand, falls back to the app dir)."""
    candidates = [os.path.join(user_config_dir(), "logs"), app_root()]
    for path in candidates:
        try:
            os.makedirs(path, exist_ok=True)
            probe = os.path.join(path, ".write-test")
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write("ok")
            os.remove(probe)
            return path
        except OSError:
            continue
    return tempfile.gettempdir()


# ---------------------------------------------------------------------------
# Launching
# ---------------------------------------------------------------------------
def pythonw_executable() -> str:
    """Console-less Python interpreter for the current installation."""
    exe = sys.executable or "python3"
    if IS_WINDOWS:
        base = os.path.basename(exe).lower()
        if base == "python.exe":
            candidate = os.path.join(os.path.dirname(exe), "pythonw.exe")
            if os.path.exists(candidate):
                return candidate
    return exe


def entry_point() -> str:
    """The script/binary that starts the tray application."""
    if is_frozen():
        return os.path.abspath(sys.executable)
    return os.path.join(app_root(), "tray_app.py")


def start_command() -> list[str]:
    """Command line that starts the tray app in the background."""
    if is_frozen():
        return [entry_point()]
    return [pythonw_executable(), entry_point()]


def command_to_string(args: list[str]) -> str:
    """Quote a command line for the Windows Run registry value."""
    quoted = []
    for arg in args:
        if not arg:
            continue
        if " " in arg or "\t" in arg:
            quoted.append('"%s"' % arg)
        else:
            quoted.append(arg)
    return " ".join(quoted)


def _desktop_quote(arg: str) -> str:
    """Quote an argument for a freedesktop ``Exec=`` line."""
    escaped = arg.replace("\\", "\\\\").replace('"', '\\"')
    if any(ch in escaped for ch in ' \t"'):
        return '"%s"' % escaped
    return escaped


def _detached_flags() -> int:
    if IS_WINDOWS:
        DETACHED_PROCESS = 0x00000008
        CREATE_NO_WINDOW = 0x08000000
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        return DETACHED_PROCESS | CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    return 0


def spawn_detached(args: list[str], cwd: str | None = None) -> "subprocess.Popen":
    """Start ``args`` fully detached; output is appended to ``launcher.log``."""
    import subprocess

    log_path = os.path.join(log_dir(), "launcher.log")
    log_handle = open(log_path, "ab", buffering=0)
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONUNBUFFERED", "1")
    try:
        return subprocess.Popen(
            args,
            cwd=cwd or app_root(),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=log_handle,
            creationflags=_detached_flags() if IS_WINDOWS else 0,
            start_new_session=not IS_WINDOWS,
            close_fds=True,
            env=env,
        )
    finally:
        # The child keeps its own copy of the handle.
        log_handle.close()


# ---------------------------------------------------------------------------
# Autostart / startup registration
# ---------------------------------------------------------------------------
_WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _windows_run_key(access: int):
    import winreg

    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0, access)


def _linux_autostart_file() -> str:
    root = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(root, "autostart", DESKTOP_ID + ".desktop")


def autostart_supported() -> bool:
    return IS_WINDOWS or IS_LINUX


def is_autostart_enabled() -> bool:
    if IS_WINDOWS:
        import winreg

        try:
            key = _windows_run_key(winreg.KEY_READ)
            try:
                value, _ = winreg.QueryValueEx(key, STARTUP_NAME)
            finally:
                winreg.CloseKey(key)
            return bool(value)
        except FileNotFoundError:
            return False
        except OSError:
            return False
    if IS_LINUX:
        return os.path.exists(_linux_autostart_file())
    return False


def _write_linux_autostart_file() -> bool:
    path = _linux_autostart_file()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        command = " ".join(_desktop_quote(a) for a in start_command())
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=%s\n"
            "Comment=Edifier R20 speaker volume and RGB light controller\n"
            "Exec=%s\n"
            "Icon=%s\n"
            "Terminal=false\n"
            "Categories=AudioVideo;Audio;\n"
            "X-GNOME-Autostart-enabled=true\n"
            "StartupNotify=false\n"
        ) % (APP_NAME, command, DESKTOP_ID)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return True
    except OSError as exc:
        print("Error writing autostart entry: %s" % exc)
        return False


def refresh_autostart() -> bool:
    """Rewrites an existing autostart entry so it points at the current launcher.

    Older versions registered ``wscript.exe start_tray.vbs``; VBScript has been
    removed from the sources and is unavailable on hardened Windows machines, so
    a stale entry is silently replaced by the direct ``pythonw``/exe command.
    """
    if not is_autostart_enabled():
        return False
    if IS_WINDOWS:
        import winreg

        try:
            key = _windows_run_key(winreg.KEY_READ | winreg.KEY_SET_VALUE)
            try:
                current, _ = winreg.QueryValueEx(key, STARTUP_NAME)
                expected = command_to_string(start_command())
                if str(current).strip() != expected:
                    winreg.SetValueEx(key, STARTUP_NAME, 0, winreg.REG_SZ, expected)
                    print("Updated stale autostart entry: %r -> %r" % (current, expected))
                    return True
            finally:
                winreg.CloseKey(key)
        except OSError as exc:
            print("Could not refresh autostart entry: %s" % exc)
        return False
    if IS_LINUX:
        return _write_linux_autostart_file()
    return False


def set_autostart(enabled: bool) -> bool:
    """Register/unregister the app to start with the desktop session."""
    if IS_WINDOWS:
        import winreg

        try:
            key = _windows_run_key(winreg.KEY_SET_VALUE)
            try:
                if enabled:
                    winreg.SetValueEx(
                        key, STARTUP_NAME, 0, winreg.REG_SZ,
                        command_to_string(start_command()),
                    )
                else:
                    try:
                        winreg.DeleteValue(key, STARTUP_NAME)
                    except FileNotFoundError:
                        pass
            finally:
                winreg.CloseKey(key)
            return True
        except OSError as exc:
            print("Error updating startup registry: %s" % exc)
            return False
    if IS_LINUX:
        path = _linux_autostart_file()
        try:
            if enabled:
                return _write_linux_autostart_file()
            if os.path.exists(path):
                os.remove(path)
            return True
        except OSError as exc:
            print("Error updating autostart entry: %s" % exc)
            return False
    return False


# ---------------------------------------------------------------------------
# Single instance + "open the panel" IPC
# ---------------------------------------------------------------------------
def _lock_path() -> str:
    return os.path.join(tempfile.gettempdir(), DESKTOP_ID + ".lock")


def _show_request_path() -> str:
    return os.path.join(tempfile.gettempdir(), DESKTOP_ID + ".show")


class SingleInstance:
    """Cross-platform process lock held for the lifetime of the application.

    Uses ``msvcrt.locking`` on Windows and ``fcntl.flock`` elsewhere.  Stale
    locks disappear automatically because the OS releases them when the owning
    process exits.
    """

    def __init__(self, name: str = DESKTOP_ID):
        self._path = os.path.join(tempfile.gettempdir(), name + ".lock")
        self._fh = None

    def acquire(self) -> bool:
        try:
            fh = open(self._path, "a+b")
        except OSError:
            return True  # Cannot create a lock file: do not block startup.
        try:
            fh.seek(0)
            if IS_WINDOWS:
                import msvcrt

                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        try:
            fh.seek(0)
            fh.truncate()
            fh.write(str(os.getpid()).encode("ascii", "ignore"))
            fh.flush()
        except OSError:
            pass
        self._fh = fh
        return True

    def release(self) -> None:
        fh, self._fh = self._fh, None
        if fh is None:
            return
        try:
            fh.seek(0)
            if IS_WINDOWS:
                import msvcrt

                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            try:
                fh.close()
            except OSError:
                pass


def request_show() -> None:
    """Ask the already running instance to show its panel."""
    try:
        with open(_show_request_path(), "w", encoding="utf-8") as fh:
            fh.write("show")
    except OSError:
        pass


def consume_show_request() -> bool:
    """Return True once per pending show request."""
    path = _show_request_path()
    if not os.path.exists(path):
        return False
    try:
        os.remove(path)
    except OSError:
        return False
    return True


# ---------------------------------------------------------------------------
# Platform specific wording
# ---------------------------------------------------------------------------
def system_volume_label() -> str:
    return "Windows 系統音量" if IS_WINDOWS else "系統音量"


def mixer_label() -> str:
    return "Windows 混音" if IS_WINDOWS else "系統混音"
