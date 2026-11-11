# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build description for ``EdifierR20Tray-Setup-<version>.exe``.

One-file Qt wizard that bundles:

* ``payload/``   - the application folder (``dist/EdifierR20Tray``)
* ``uninstall/`` - the generated ``Uninstall.exe``

Run ``packaging/build_windows.ps1`` so the payload, uninstaller and version
resource all exist before this spec is used.
"""

import importlib.util
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
PACKAGING = os.path.join(ROOT, "packaging")

# Read the version from the single source of truth (platform_utils.APP_VERSION).
_spec = importlib.util.spec_from_file_location(
    "edifier_platform_utils", os.path.join(ROOT, "platform_utils.py")
)
_platform_utils = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_platform_utils)
APP_VERSION = _platform_utils.APP_VERSION

PAYLOAD_DIR = os.path.join(ROOT, "dist", "EdifierR20Tray")
UNINSTALLER_EXE = os.path.join(ROOT, "build", "uninstaller", "Uninstall.exe")

datas = [
    (PAYLOAD_DIR, "payload"),
    (UNINSTALLER_EXE, "uninstall"),
]

excludes = [
    "tkinter",
    "unittest",
    "pydoc",
    "PIL",
    "pycaw",
    "comtypes",
    "hid",
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
    [os.path.join(PACKAGING, "installer_app.py")],
    pathex=[ROOT, PACKAGING],
    binaries=[],
    datas=datas,
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name="EdifierR20Tray-Setup-%s" % APP_VERSION,
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
