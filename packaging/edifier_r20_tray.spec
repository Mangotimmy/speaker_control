# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build description for the Edifier R20 tray controller.

Produces ``dist/EdifierR20Tray/EdifierR20Tray.exe`` (one folder, windowed).
Build it through ``packaging/build_windows.ps1`` which also generates the icon,
the version resource and the setup program that bundles this folder.
"""

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
PACKAGING = os.path.join(ROOT, "packaging")

hiddenimports = [
    "comtypes",
    "comtypes.client",
    "comtypes.stream",
    "pycaw",
    "pycaw.pycaw",
    "pycaw.utils",
    "pycaw.api.audioclient",
    "pycaw.api.endpointvolume",
    "pycaw.api.mmdeviceapi",
    "hid",
]

excludes = [
    "tkinter",
    "unittest",
    "pydoc",
    "PIL",
    # Qt modules this app never uses (keeps the bundle small)
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebEngineQuick",
    "PyQt6.QtQml",
    "PyQt6.QtQuick",
    "PyQt6.QtQuickWidgets",
    "PyQt6.QtQuick3D",
    "PyQt6.QtMultimedia",
    "PyQt6.QtMultimediaWidgets",
    "PyQt6.QtCharts",
    "PyQt6.QtDataVisualization",
    "PyQt6.Qt3DCore",
    "PyQt6.Qt3DRender",
    "PyQt6.Qt3DInput",
    "PyQt6.Qt3DLogic",
    "PyQt6.Qt3DAnimation",
    "PyQt6.Qt3DExtras",
    "PyQt6.QtBluetooth",
    "PyQt6.QtDesigner",
    "PyQt6.QtHelp",
    "PyQt6.QtNetworkAuth",
    "PyQt6.QtPdf",
    "PyQt6.QtPdfWidgets",
    "PyQt6.QtPositioning",
    "PyQt6.QtSensors",
    "PyQt6.QtSerialPort",
    "PyQt6.QtSql",
    "PyQt6.QtTest",
    "PyQt6.QtTextToSpeech",
    "PyQt6.QtWebChannel",
    "PyQt6.QtWebSockets",
]

a = Analysis(
    [os.path.join(ROOT, "tray_app.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EdifierR20Tray",
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
    icon=os.path.join(PACKAGING, "app.ico"),
    version=os.path.join(ROOT, "build", "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="EdifierR20Tray",
)
