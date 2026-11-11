# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build description for the generated ``Uninstall.exe``.

Small one-file, window-less executable without Qt.  It is copied into the
installation folder by the setup program.
"""

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(ROOT, "packaging", "uninstaller_app.py")],
    pathex=[ROOT, os.path.join(ROOT, "packaging")],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "pydoc",
        "PyQt6",
        "pycaw",
        "comtypes",
        "hid",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Uninstall",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "packaging", "app.ico"),
    version=os.path.join(ROOT, "build", "version_info.txt"),
)
