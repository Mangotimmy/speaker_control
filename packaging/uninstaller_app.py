"""
Uninstaller for the Edifier R20 tray controller.

Built with PyInstaller as a small ``Uninstall.exe`` (no Qt) and copied into the
installation folder by the setup program.  It removes the application files,
shortcuts, registry entries and (optionally) the per-user settings.

Because Windows locks a running executable, the uninstaller copies itself to the
temporary folder, restarts from there and lets the original process exit before
deleting the installation directory.

Command line:
    Uninstall.exe                 interactive
    Uninstall.exe --silent        unattended (keeps the settings)
    Uninstall.exe --keep-settings interactive, keeps the settings
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _path in (HERE, ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import installer_common as ic  # noqa: E402

MB_OK = 0x00000000
MB_YESNO = 0x00000004
MB_ICONQUESTION = 0x00000020
MB_ICONINFORMATION = 0x00000040
MB_ICONERROR = 0x00000010
IDYES = 6

FALLBACK_EXE_NAME = "EdifierR20Tray-Uninstaller.exe"
LOG_PATH = os.path.join(
    os.environ.get("TEMP") or os.environ.get("TMP") or ".",
    "EdifierR20Tray-Uninstall.log",
)


def log(message: str) -> None:
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), message)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def message_box(text: str, title: str, flags: int) -> int:
    try:
        return int(
            ctypes.windll.user32.MessageBoxW(None, text, title, flags)
            or 0
        )
    except OSError:
        return 0


def _install_dir_from_exe() -> str:
    """The folder this uninstaller lives in, when it looks like an install dir."""
    directory = os.path.dirname(os.path.abspath(sys.argv[0]))
    if os.path.basename(directory).lower() == ic.APP_FOLDER.lower():
        return directory
    if os.path.isfile(os.path.join(directory, ic.APP_EXE)):
        return directory
    return ""


def _parse_target(argv) -> str:
    for index, arg in enumerate(argv):
        if arg.startswith("--target="):
            return arg.split("=", 1)[1]
        if arg == "--target" and index + 1 < len(argv):
            return argv[index + 1]
    return ""


def _relaunch_from_temp(argv, target_dir: str = "") -> bool:
    """Restarts the uninstaller from %TEMP% so the install dir is unlocked."""
    if not getattr(sys, "frozen", False):
        return False
    source = os.path.abspath(sys.executable)
    if not os.path.isfile(source):
        return False
    copied = os.path.join(tempfile.gettempdir(), FALLBACK_EXE_NAME)
    try:
        if os.path.abspath(source).lower() == copied.lower():
            return False
        shutil.copy2(source, copied)
        child_args = [copied, "--from-temp"]
        child_args += [arg for arg in argv if arg not in ("--from-temp",)]
        if target_dir:
            child_args += ["--target", target_dir]
        subprocess.Popen(
            child_args,
            cwd=tempfile.gettempdir(),
            close_fds=True,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        return True
    except OSError as exc:
        log("relaunch from temp failed: %s" % exc)
        return False


def _schedule_self_delete() -> None:
    try:
        path = os.path.abspath(sys.argv[0])
        ctypes.windll.kernel32.MoveFileExW(path, None, 0x00000004)
    except OSError:
        pass


def run_uninstall(silent: bool, keep_settings: bool, target_dir: str = "") -> int:
    install_dir = os.path.abspath(target_dir) if target_dir else ic.resolve_install_dir()
    log("uninstall start: dir=%s silent=%s keep_settings=%s"
        % (install_dir, silent, keep_settings))

    if not silent:
        answer = message_box(
            "確定要解除安裝「%s」嗎？\n\n"
            "程式檔案、捷徑與開機啟動設定都會被移除。" % ic.APP_NAME,
            "解除安裝 %s" % ic.APP_NAME,
            MB_YESNO | MB_ICONQUESTION,
        )
        if answer != IDYES:
            log("cancelled by user")
            return 0

    remove_settings = False
    if not silent and not keep_settings:
        answer = message_box(
            "是否也要刪除個人設定？\n\n"
            "包含控制面板位置、音量、燈效與彩虹律動設定。\n"
            "選擇「否」會保留這些設定，日後重新安裝時可繼續使用。",
            "刪除個人設定？",
            MB_YESNO | MB_ICONQUESTION,
        )
        remove_settings = answer == IDYES

    try:
        ic.uninstall(remove_settings=remove_settings, install_dir=install_dir)
    except Exception as exc:
        log("ERROR: %s" % exc)
        log(traceback.format_exc())
        if not silent:
            message_box(
                "解除安裝失敗：\n\n%s\n\n請關閉程式後再試一次。" % exc,
                "解除安裝失敗",
                MB_OK | MB_ICONERROR,
            )
        return 1

    log("uninstall finished")
    if not silent:
        message_box(
            "「%s」已移除。\n\n%s"
            % (
                ic.APP_NAME,
                "個人設定已刪除。" if remove_settings else "個人設定已保留。",
            ),
            "解除安裝完成",
            MB_OK | MB_ICONINFORMATION,
        )
    _schedule_self_delete()
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv or "/?" in argv:
        try:
            print(__doc__)
        except Exception:
            pass
        return 0
    if "--version" in argv or "-V" in argv:
        try:
            print("%s %s" % (ic.APP_NAME, ic.APP_VERSION))
        except Exception:
            pass
        return 0

    silent = "--silent" in argv or "/S" in argv
    keep_settings = "--keep-settings" in argv
    from_temp = "--from-temp" in argv

    target_dir = _parse_target(argv)
    if not target_dir and not from_temp:
        # Prefer the folder we were started from: this keeps uninstalling
        # working even when the registry entry is missing or damaged.
        target_dir = _install_dir_from_exe()

    if not from_temp and _relaunch_from_temp(argv, target_dir):
        log("relaunched from temp to unlock the installation folder")
        return 0

    try:
        return run_uninstall(silent, keep_settings, target_dir)
    except Exception as exc:
        log("FATAL: %s" % exc)
        log(traceback.format_exc())
        if not silent:
            message_box(
                "解除安裝時發生未預期的錯誤：\n\n%s" % exc,
                "解除安裝失敗",
                MB_OK | MB_ICONERROR,
            )
        return 1


if __name__ == "__main__":
    sys.exit(main())


