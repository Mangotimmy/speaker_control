"""Windows-only manual self-check of the installer/uninstaller logic.

Redirects the Start menu / desktop / settings folders into
``build/installer-check`` so the developer profile is not touched.  The HKCU
registry entries are written and removed again by the test.

Run on Windows from the repository root:

    python tools/installer_selfcheck.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "packaging"))

if not sys.platform.startswith("win"):
    raise SystemExit("This self-check is Windows only.")

import installer_common as ic  # noqa: E402

WORK = os.path.join(ROOT, "build", "installer-check")
TARGET = os.path.join(WORK, "install", "EdifierR20Tray")
START_MENU = os.path.join(WORK, "startmenu")
DESKTOP = os.path.join(WORK, "desktop")
SETTINGS = os.path.join(WORK, "settings")
PAYLOAD = os.path.join(ROOT, "dist", "EdifierR20Tray")
UNINSTALLER = os.path.join(ROOT, "build", "uninstaller", "Uninstall.exe")

ic.start_menu_programs_dir = lambda: START_MENU
ic.desktop_dir = lambda: DESKTOP
ic.settings_dir = lambda: SETTINGS


def check(condition, message):
    if not condition:
        raise SystemExit("FAIL: " + message)
    print("ok  -", message)


def main():
    import shutil
    import winreg

    if not os.path.isfile(UNINSTALLER):
        raise SystemExit(
            "Build the artifacts first: pwsh -File packaging/build_windows.ps1"
        )

    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(SETTINGS, exist_ok=True)
    with open(os.path.join(SETTINGS, "config.json"), "w", encoding="utf-8") as fh:
        fh.write('{"last_volume": 8}')

    # ------------------------------------------------------------- install
    target = ic.install(
        PAYLOAD, UNINSTALLER,
        install_dir=TARGET,
        desktop_shortcut=True,
        autostart=True,
        progress=lambda percent, message: None,
    )
    check(os.path.abspath(target) == os.path.abspath(TARGET), "installed into requested folder")
    check(os.path.isfile(os.path.join(TARGET, ic.APP_EXE)), "application executable copied")
    check(os.path.isdir(os.path.join(TARGET, "_internal")), "application payload copied")
    check(os.path.isfile(os.path.join(TARGET, ic.UNINSTALL_EXE)), "uninstaller copied")
    check(os.path.isfile(os.path.join(DESKTOP, ic.APP_SHORT + ".lnk")), "desktop shortcut created")
    check(
        os.path.isfile(os.path.join(START_MENU, ic.APP_SHORT, ic.APP_SHORT + ".lnk")),
        "start menu shortcut created",
    )
    check(
        os.path.isfile(os.path.join(START_MENU, ic.APP_SHORT, "解除安裝 %s.lnk" % ic.APP_SHORT)),
        "uninstall shortcut created",
    )
    check(ic.registry_install_dir().lower() == TARGET.lower(), "registry install dir written")
    check(ic.is_autostart_enabled(), "autostart entry written")

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ic.UNINSTALL_REG_KEY) as key:
        display, _ = winreg.QueryValueEx(key, "DisplayName")
        uninstall_string, _ = winreg.QueryValueEx(key, "UninstallString")
    check(display == ic.APP_NAME, "uninstall entry DisplayName")
    check(TARGET.lower() in uninstall_string.lower(), "uninstall entry UninstallString")

    # ------------------------------------------------------------- upgrade
    ic.install(PAYLOAD, UNINSTALLER, install_dir=TARGET, desktop_shortcut=False,
               autostart=True, progress=None)
    check(os.path.isfile(os.path.join(TARGET, ic.APP_EXE)), "upgrade reinstall works")

    # ----------------------------------------------------------- uninstall
    ic.uninstall(remove_settings=True)
    check(not os.path.isdir(TARGET), "install folder removed")
    check(not os.path.exists(os.path.join(DESKTOP, ic.APP_SHORT + ".lnk")), "desktop shortcut removed")
    check(not os.path.isdir(os.path.join(START_MENU, ic.APP_SHORT)), "start menu folder removed")
    check(not ic.is_autostart_enabled(), "autostart entry removed")
    check(ic.registry_install_dir() == "", "registry install dir removed")
    check(not os.path.isdir(SETTINGS), "settings removed when requested")

    print("\nINSTALLER LOGIC OK")


if __name__ == "__main__":
    main()
