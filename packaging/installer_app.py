"""
Windows setup program for the Edifier R20 tray controller.

Built with PyInstaller as ``EdifierR20Tray-Setup-<version>.exe`` and bundles:

* ``payload/``       - the application folder (dist/EdifierR20Tray)
* ``uninstall/``     - the small ``Uninstall.exe`` copied into the install dir

Installation is per user (``%LOCALAPPDATA%\\Programs\\EdifierR20Tray``) and does
not require administrator rights.  Everything the app needs is created by this
program: files, Start menu/desktop shortcuts, uninstall registry entry and the
optional start-with-Windows entry.

Command line (for unattended installs):
    EdifierR20Tray-Setup.exe --silent [--dir <path>] [--no-desktop]
                             [--no-autostart] [--autostart] [--no-launch]
    EdifierR20Tray-Setup.exe --version
"""

from __future__ import annotations

import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _path in (HERE, ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import installer_common as ic  # noqa: E402
import platform_utils  # noqa: E402

LOG_PATH = os.path.join(
    os.environ.get("TEMP") or os.environ.get("TMP") or ".",
    "EdifierR20Tray-Setup.log",
)


def log(message: str) -> None:
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), message)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def payload_dir() -> str:
    bundled = platform_utils.resource_path("payload")
    if os.path.isdir(bundled):
        return bundled
    return os.path.join(ROOT, "dist", "EdifierR20Tray")


def uninstaller_payload() -> str:
    bundled = platform_utils.resource_path("uninstall", ic.UNINSTALL_EXE)
    if os.path.isfile(bundled):
        return bundled
    return os.path.join(ROOT, "build", "uninstaller", ic.UNINSTALL_EXE)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
def parse_args(argv):
    options = {
        "silent": False,
        "dir": "",
        "desktop": True,
        "autostart": None,  # None = automatic
        "launch": True,
        "help": False,
        "version": False,
    }
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--silent" or arg == "/S":
            options["silent"] = True
        elif arg == "--no-desktop":
            options["desktop"] = False
        elif arg == "--no-autostart":
            options["autostart"] = False
        elif arg == "--autostart":
            options["autostart"] = True
        elif arg == "--no-launch":
            options["launch"] = False
        elif arg in ("--help", "-h", "/?"):
            options["help"] = True
        elif arg in ("--version", "-V"):
            options["version"] = True
        elif arg.startswith("--dir="):
            options["dir"] = arg.split("=", 1)[1]
        elif arg == "--dir" and index + 1 < len(argv):
            index += 1
            options["dir"] = argv[index]
        index += 1
    return options


def resolve_autostart(option) -> bool:
    if option is not None:
        return bool(option)
    # Upgrade: keep the user's previous choice; fresh install enables it.
    if ic.registry_install_dir():
        return ic.is_autostart_enabled()
    return True


def silent_install(options) -> int:
    target = options["dir"] or ic.resolve_install_dir()
    autostart = resolve_autostart(options["autostart"])
    log("silent install: target=%s desktop=%s autostart=%s"
        % (target, options["desktop"], autostart))
    try:
        installed = ic.install(
            payload_dir(),
            uninstaller_payload(),
            install_dir=target,
            desktop_shortcut=options["desktop"],
            autostart=autostart,
            progress=lambda percent, message: log("%3d%% %s" % (percent, message)),
        )
    except Exception as exc:
        log("ERROR: %s" % exc)
        log(traceback.format_exc())
        return 1
    log("installed to %s" % installed)
    if options["launch"]:
        ic.launch_app(ic.app_exe_path(installed))
    return 0


# ---------------------------------------------------------------------------
# Qt wizard
# ---------------------------------------------------------------------------
STYLE = """
QWidget {
    background-color: #17171d;
    color: #e6e6ec;
    font-family: "Segoe UI", "Microsoft JhengHei UI", "Noto Sans CJK TC", sans-serif;
}
QLabel#Title { font-size: 20px; font-weight: bold; color: #ffffff; }
QLabel#Subtitle { font-size: 12px; color: #9ca3af; }
QLabel#SectionLabel { font-size: 12px; font-weight: 600; color: #9ca3af; }
QLabel#Status { font-size: 12px; color: #cbd5e1; }
QLineEdit {
    background-color: #23232c; border: 1px solid #3a3a48; border-radius: 6px;
    padding: 6px 8px; color: #e5e7eb; font-size: 12px;
}
QLineEdit:focus { border-color: #3b82f6; }
QPushButton {
    background-color: #262630; border: 1px solid #3a3a48; border-radius: 6px;
    color: #e5e7eb; padding: 8px 16px; font-size: 12px;
}
QPushButton:hover { background-color: #323242; }
QPushButton#Primary {
    background-color: #2563eb; border-color: #3b82f6; color: #ffffff; font-weight: bold;
}
QPushButton#Primary:hover { background-color: #3b82f6; }
QPushButton#Primary:disabled { background-color: #1f2937; color: #6b7280; border-color: #374151; }
QCheckBox { font-size: 12px; color: #d1d5db; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid #4b5563; background: #262630;
}
QCheckBox::indicator:checked { background: #3b82f6; border-color: #2563eb; }
QProgressBar {
    border: none; background: #2d2d38; border-radius: 6px; height: 12px; text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    border-radius: 6px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #38bdf8);
}
QFrame#Card { background-color: #1e1e24; border: 1px solid #33333d; border-radius: 14px; }
"""


def run_gui(options) -> int:
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
    from PyQt6.QtWidgets import (
        QApplication, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
        QLineEdit, QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget,
    )

    class InstallWorker(QThread):
        progressed = pyqtSignal(int, str)
        succeeded = pyqtSignal(str)
        failed = pyqtSignal(str)

        def __init__(self, target, desktop, autostart):
            super().__init__()
            self.target = target
            self.desktop = desktop
            self.autostart = autostart

        def run(self):
            try:
                installed = ic.install(
                    payload_dir(),
                    uninstaller_payload(),
                    install_dir=self.target,
                    desktop_shortcut=self.desktop,
                    autostart=self.autostart,
                    progress=lambda percent, message: self.progressed.emit(percent, message),
                )
                self.succeeded.emit(installed)
            except Exception as exc:
                log("ERROR: %s" % exc)
                log(traceback.format_exc())
                self.failed.emit(str(exc))

    class InstallWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("安裝 %s %s" % (ic.APP_NAME, ic.APP_VERSION))
            self.setFixedSize(560, 430)
            self.setStyleSheet(STYLE)
            self._worker = None
            self._installed_dir = ""
            self._build()

        # ---------------------------------------------------------- layout
        def _build(self):
            outer = QVBoxLayout(self)
            outer.setContentsMargins(18, 18, 18, 18)
            card = QFrame(self)
            card.setObjectName("Card")
            outer.addWidget(card)
            layout = QVBoxLayout(card)
            layout.setContentsMargins(22, 20, 22, 20)
            layout.setSpacing(12)

            title = QLabel(ic.APP_NAME, self)
            title.setObjectName("Title")
            subtitle = QLabel(
                "版本 %s · 漫步者 Edifier R20 USB 喇叭音量、音效與 RGB 燈效控制"
                % ic.APP_VERSION, self
            )
            subtitle.setObjectName("Subtitle")
            subtitle.setWordWrap(True)
            layout.addWidget(title)
            layout.addWidget(subtitle)

            location_label = QLabel("安裝位置", self)
            location_label.setObjectName("SectionLabel")
            layout.addWidget(location_label)

            location_row = QHBoxLayout()
            self.path_edit = QLineEdit(ic.resolve_install_dir(), self)
            browse = QPushButton("瀏覽…", self)
            browse.clicked.connect(self._browse)
            location_row.addWidget(self.path_edit, 1)
            location_row.addWidget(browse)
            layout.addLayout(location_row)

            self.chk_desktop = QCheckBox("建立桌面捷徑", self)
            self.chk_desktop.setChecked(True)
            self.chk_autostart = QCheckBox("開機時自動在背景啟動", self)
            self.chk_autostart.setChecked(resolve_autostart(options["autostart"]))
            self.chk_launch = QCheckBox("安裝完成後立即啟動", self)
            self.chk_launch.setChecked(True)
            layout.addWidget(self.chk_desktop)
            layout.addWidget(self.chk_autostart)
            layout.addWidget(self.chk_launch)

            layout.addStretch(1)

            self.status = QLabel("按「安裝」開始，不需要系統管理員權限。", self)
            self.status.setObjectName("Status")
            self.status.setWordWrap(True)
            layout.addWidget(self.status)

            self.progress = QProgressBar(self)
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setVisible(False)
            layout.addWidget(self.progress)

            buttons = QHBoxLayout()
            buttons.addStretch(1)
            self.btn_cancel = QPushButton("取消", self)
            self.btn_cancel.clicked.connect(self.close)
            self.btn_install = QPushButton("安裝", self)
            self.btn_install.setObjectName("Primary")
            self.btn_install.setDefault(True)
            self.btn_install.clicked.connect(self._start_install)
            buttons.addWidget(self.btn_cancel)
            buttons.addWidget(self.btn_install)
            layout.addLayout(buttons)

        # --------------------------------------------------------- actions
        def _browse(self):
            directory = QFileDialog.getExistingDirectory(
                self, "選擇安裝資料夾", self.path_edit.text()
            )
            if directory:
                self.path_edit.setText(directory)

        def _set_busy(self, busy: bool):
            self.btn_install.setEnabled(not busy)
            self.btn_cancel.setEnabled(not busy)
            self.path_edit.setEnabled(not busy)
            self.chk_desktop.setEnabled(not busy)
            self.chk_autostart.setEnabled(not busy)
            self.chk_launch.setEnabled(not busy)
            if busy:
                self.progress.setVisible(True)

        def _start_install(self):
            target = self.path_edit.text().strip() or ic.default_install_dir()
            if not ic.is_safe_install_dir(target):
                QMessageBox.warning(
                    self, "安裝位置無效",
                    "請選擇一個名為 %s 的資料夾，例如：\n\n%s"
                    % (ic.APP_FOLDER, ic.default_install_dir()),
                )
                return
            self._set_busy(True)
            self.progress.setValue(0)
            self.status.setText("正在準備安裝…")
            log("gui install: target=%s desktop=%s autostart=%s"
                % (target, self.chk_desktop.isChecked(), self.chk_autostart.isChecked()))

            self._worker = InstallWorker(
                target, self.chk_desktop.isChecked(), self.chk_autostart.isChecked()
            )
            self._worker.progressed.connect(self._on_progress)
            self._worker.succeeded.connect(self._on_success)
            self._worker.failed.connect(self._on_failure)
            self._worker.start()

        def _on_progress(self, percent: int, message: str):
            self.progress.setValue(percent)
            self.status.setText(message)

        def _on_success(self, installed: str):
            self._installed_dir = installed
            self._set_busy(False)
            self.progress.setValue(100)
            self.status.setText("已安裝到：\n%s" % installed)
            self.btn_install.setText("完成")
            try:
                self.btn_install.clicked.disconnect()
            except TypeError:
                pass
            self.btn_install.clicked.connect(self._finish)
            if self.chk_launch.isChecked():
                ic.launch_app(ic.app_exe_path(installed))

        def _on_failure(self, message: str):
            self._set_busy(False)
            self.progress.setVisible(False)
            self.status.setText("安裝失敗。")
            QMessageBox.critical(self, "安裝失敗", message)

        def _finish(self):
            self.close()

        def closeEvent(self, event):
            if self._worker is not None and self._worker.isRunning():
                event.ignore()
                return
            super().closeEvent(event)

    app = QApplication(sys.argv)
    app.setApplicationName("%s Setup" % ic.APP_NAME)
    window = InstallWindow()
    window.show()
    return app.exec()


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    options = parse_args(argv)

    if options["help"]:
        try:
            print(__doc__)
        except Exception:
            pass
        return 0
    if options["version"]:
        try:
            print("%s %s" % (ic.APP_NAME, ic.APP_VERSION))
        except Exception:
            pass
        return 0

    log("setup started: %s" % " ".join(argv))
    if options["silent"]:
        return silent_install(options)
    try:
        return run_gui(options)
    except Exception as exc:
        log("FATAL: %s" % exc)
        log(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
