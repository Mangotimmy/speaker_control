"""
Edifier R20 System Tray Application.
Tray icon, quick switch RGB modes, volume control, and Windows master volume sync.
"""

import sys
import os
import time
import traceback
import ctypes

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
try:
    os.chdir(SCRIPT_DIR)
except Exception:
    pass

def log_exception(exc_type, exc_value, exc_traceback):
    with open(os.path.join(SCRIPT_DIR, "crash.log"), "a", encoding="utf-8") as f:
        f.write("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)) + "\n")

sys.excepthook = log_exception
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMessageBox
)
from PyQt6.QtGui import QAction, QActionGroup, QIcon
from PyQt6.QtCore import Qt, QTimer, pyqtSlot, pyqtSignal, QObject

from r20_controller import EdifierR20, RGB_MODES, SOUND_MODES
from config import ConfigManager
from volume_sync import WindowsVolumeSync, VK_VOLUME_UP, VK_VOLUME_DOWN, VK_VOLUME_MUTE
from icon_generator import create_tray_icon
from tray_popup import R20Popup, R20VolumeOSD

from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)
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

_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
_user32.CallNextHookEx.restype = LRESULT
_user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL

# Mutex name for single instance
MUTEX_NAME = "EdifierR20TrayInstanceMutex"

class R20TrayApp(QObject):
    hardware_state_changed = pyqtSignal()
    media_key_pressed = pyqtSignal(int)

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self.hardware_state_changed.connect(self._update_all_ui)
        self.media_key_pressed.connect(self._on_media_key_pressed)
        self._hhook = None
        self._hook_proc = None

        # 1. Load config
        self.config = ConfigManager()

        # 2. Hardware Controller
        self.r20 = EdifierR20()

        # 3. Windows Volume Synchronization
        sync_enabled = self.config.get("sync_windows_volume", True)
        keep_win_100 = self.config.get("keep_windows_volume_100", True)
        self.volume_sync = WindowsVolumeSync(
            self.r20,
            enabled=sync_enabled,
            keep_windows_100=keep_win_100,
        )
        self.volume_sync.windows_volume_changed.connect(self._on_windows_volume_changed)
        self.volume_sync.speaker_synced.connect(self._on_speaker_synced_by_windows)
        self.volume_sync.hardware_volume_changed.connect(self._on_hardware_volume_changed)

        # 4. Floating Popup Window & On-Screen Volume OSD Bar
        self.osd = R20VolumeOSD()
        self.popup = R20Popup(self.r20, self.config)
        self.popup.volume_requested.connect(self.set_volume)
        self.popup.sound_mode_requested.connect(self.set_sound_mode)
        self.popup.light_mode_requested.connect(self.set_light_mode)
        self.popup.color_requested.connect(self.set_light_color)
        self.popup.sub_effect_requested.connect(self.set_light_sub_effect)
        self.popup.brightness_requested.connect(self.set_brightness)
        self.popup.speed_requested.connect(self.set_speed)
        self.popup.sync_toggled.connect(self.set_volume_sync_enabled)
        self.popup.keep_win_100_toggled.connect(self.set_keep_windows_100_enabled)
        self.popup.reconnect_requested.connect(self.reconnect_speaker)

        # 5. System Tray Icon & Menu
        self.tray_icon = QSystemTrayIcon(self.app)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self._build_context_menu()

        # 6. Connect controller listener and connect to hardware
        self.r20.add_listener(self._on_r20_hardware_event)
        connected = self.r20.connect()
        if connected:
            if sync_enabled:
                self.volume_sync.sync_windows_to_speaker_immediately()
            else:
                if self.r20.current_volume > 0:
                    self.config.set("pre_sync_volume", self.r20.current_volume)
                win_scalar = self.volume_sync.get_windows_volume_scalar()
                if win_scalar is not None and win_scalar > 0.0:
                    self.config.set("pre_sync_windows_volume", win_scalar)
            print(
                f"Edifier R20 connected: Vol={self.r20.current_volume}, "
                f"SoundMode={self.r20.current_sound_mode}, LightMode={self.r20.current_light_mode}"
            )
        else:
            print("Edifier R20 not detected on startup, will retry automatically.")

        # 7. Start Windows Volume Sync thread & Keyboard Media Volume Hook
        self.volume_sync.start()
        self._install_keyboard_hook()

        # 8. Periodic Check / Auto-Reconnect Timer
        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.setInterval(4000)
        self.reconnect_timer.timeout.connect(self._check_reconnect)
        self.reconnect_timer.start()

        # Initial UI update
        self._update_all_ui()
        self.tray_icon.show()

    def _build_context_menu(self):
        self.menu = QMenu()
        self.menu.setStyleSheet("""
            QMenu {
                background-color: #202027;
                color: #e2e8f0;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 6px;
                font-family: "Segoe UI", "Microsoft JhengHei UI", sans-serif;
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 24px 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #3b82f6;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #334155;
                margin: 4px 6px;
            }
        """)

        # Status item
        self.action_status = QAction("● Edifier R20 (檢查中...)", self.menu)
        self.action_status.setEnabled(False)
        self.menu.addAction(self.action_status)

        self.menu.addSeparator()

        # Action to open full popup
        action_open = QAction("🎛️ 開啟控制面板", self.menu)
        action_open.triggered.connect(self.popup.show_near_tray)
        self.menu.addAction(action_open)

        self.menu.addSeparator()

        # Volume Submenu
        self.menu_volume = self.menu.addMenu("🔊 音量控制")
        self.action_vol_status = QAction(f"目前音量: {self.r20.current_volume}/16", self.menu_volume)
        self.action_vol_status.setEnabled(False)
        self.menu_volume.addAction(self.action_vol_status)
        self.menu_volume.addSeparator()

        act_vol_up = QAction("➕ 音量 +1", self.menu_volume)
        act_vol_up.triggered.connect(lambda: self.set_volume(self.r20.current_volume + 1))
        self.menu_volume.addAction(act_vol_up)

        act_vol_down = QAction("➖ 音量 -1", self.menu_volume)
        act_vol_down.triggered.connect(lambda: self.set_volume(self.r20.current_volume - 1))
        self.menu_volume.addAction(act_vol_down)

        self.act_mute = QAction("🔇 靜音切換", self.menu_volume)
        self.act_mute.triggered.connect(self._toggle_mute)
        self.menu_volume.addAction(self.act_mute)

        self.menu_volume.addSeparator()
        # Presets
        for p_text, p_val in [("靜音 (0%)", 0), ("25% (4)", 4), ("50% (8)", 8), ("75% (12)", 12), ("100% (16)", 16)]:
            act_preset = QAction(p_text, self.menu_volume)
            act_preset.triggered.connect(lambda checked, v=p_val: self.set_volume(v))
            self.menu_volume.addAction(act_preset)

        # Quick Sound Mode (EQ) Submenu
        self.menu_sound = self.menu.addMenu("🎧 音效模式 (EQ)")
        self.sound_action_group = QActionGroup(self.menu_sound)
        self.sound_action_group.setExclusive(True)
        self.sound_actions = {}

        for sm in SOUND_MODES:
            eq_idx = sm["index"]
            act_eq = QAction(f"{sm['icon']} {sm['name']} ({sm['en_name']})", self.menu_sound)
            act_eq.setCheckable(True)
            act_eq.setChecked(eq_idx == self.r20.current_sound_mode)
            act_eq.triggered.connect(lambda checked, idx=eq_idx: self.set_sound_mode(idx))
            self.sound_action_group.addAction(act_eq)
            self.menu_sound.addAction(act_eq)
            self.sound_actions[eq_idx] = act_eq

        act_next_sound = QAction("🔀 切換下一個音效", self.menu)
        act_next_sound.triggered.connect(self.next_sound_mode)
        self.menu.addAction(act_next_sound)

        # RGB Lighting Submenu
        self.menu_rgb = self.menu.addMenu("✨ RGB 燈效模式")
        self.rgb_action_group = QActionGroup(self.menu_rgb)
        self.rgb_action_group.setExclusive(True)
        self.rgb_actions = {}

        for m in RGB_MODES:
            idx = m["index"]
            act = QAction(f"{m['icon']} {m['name']}", self.menu_rgb)
            act.setCheckable(True)
            act.setChecked(idx == self.r20.current_light_mode)
            act.triggered.connect(lambda checked, mode=idx: self.set_light_mode(mode))
            self.rgb_action_group.addAction(act)
            self.menu_rgb.addAction(act)
            self.rgb_actions[idx] = act

        act_next_mode = QAction("🔄 切換下一個燈效", self.menu)
        act_next_mode.triggered.connect(self.next_light_mode)
        self.menu.addAction(act_next_mode)

        self.menu.addSeparator()

        # Sync with Windows Option
        self.act_sync = QAction("🔄 與 Windows 系統音量同步", self.menu)
        self.act_sync.setCheckable(True)
        self.act_sync.setChecked(self.config.get("sync_windows_volume", True))
        self.act_sync.toggled.connect(self.set_volume_sync_enabled)
        self.menu.addAction(self.act_sync)

        # Keep Windows Mixer at 100% Option
        self.act_keep_win_100 = QAction("🔒 同步時保持 Windows 混音 100% (拉桿僅控喇叭硬體)", self.menu)
        self.act_keep_win_100.setCheckable(True)
        self.act_keep_win_100.setChecked(self.config.get("keep_windows_volume_100", True))
        self.act_keep_win_100.setEnabled(self.act_sync.isChecked())
        self.act_keep_win_100.toggled.connect(self.set_keep_windows_100_enabled)
        self.menu.addAction(self.act_keep_win_100)

        # Autostart Option
        self.act_autostart = QAction("🚀 開機自動啟動", self.menu)
        self.act_autostart.setCheckable(True)
        self.act_autostart.setChecked(self.config.is_autostart_enabled())
        self.act_autostart.toggled.connect(self.set_autostart_enabled)
        self.menu.addAction(self.act_autostart)

        # Reconnect
        act_reconnect = QAction("🔌 重新連線喇叭", self.menu)
        act_reconnect.triggered.connect(self.reconnect_speaker)
        self.menu.addAction(act_reconnect)

        self.menu.addSeparator()

        # Quit
        act_quit = QAction("❌ 結束程式", self.menu)
        act_quit.triggered.connect(self.quit_app)
        self.menu.addAction(act_quit)

        self.tray_icon.setContextMenu(self.menu)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Single Left-Click: Toggle Quick Settings popup
            if self.popup.isVisible():
                self.popup.hide()
            else:
                self.popup.show_near_tray()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            # Middle-Click: Quick Mute / Unmute
            self._toggle_mute()

    def _toggle_mute(self):
        new_vol = self.r20.toggle_mute()
        if not self.volume_sync.enabled and new_vol > 0:
            self.config.set("pre_sync_volume", new_vol)
        self.volume_sync.on_user_changed_r20_volume(new_vol)
        self._update_all_ui()

    @pyqtSlot(int)
    def set_volume(self, val: int):
        val = max(0, min(16, int(val)))
        if not self.volume_sync.enabled and val > 0:
            self.config.set("pre_sync_volume", val)
        self.config.set("last_volume", val)
        self.r20.set_volume(val)
        self.volume_sync.on_user_changed_r20_volume(val)
        self._update_all_ui()

    @pyqtSlot(int)
    def set_sound_mode(self, eq_idx: int):
        self.r20.set_sound_mode(eq_idx)
        self.config.set("last_sound_mode", eq_idx)
        self._update_all_ui()

    def next_sound_mode(self):
        next_eq = self.r20.next_sound_mode()
        self.config.set("last_sound_mode", next_eq)
        self._update_all_ui()

    @pyqtSlot(int)
    def set_light_mode(self, mode: int):
        self.r20.set_light_mode(mode)
        self.config.set("last_rgb_mode", mode)
        self._update_all_ui()

    @pyqtSlot(int, int, int)
    def set_light_color(self, r: int, g: int, b: int):
        self.r20.set_light_color(r, g, b)
        self._update_all_ui()

    @pyqtSlot(int)
    def set_light_sub_effect(self, sub_effect: int):
        self.r20.set_light_sub_effect(sub_effect)
        self._update_all_ui()

    @pyqtSlot(int)
    def set_brightness(self, val: int):
        self.r20.set_light_brightness(val)
        self.config.set("last_brightness", self.r20.current_brightness)
        self._update_all_ui()

    @pyqtSlot(int)
    def set_speed(self, val: int):
        self.r20.set_light_speed(val)
        self.config.set("last_speed", self.r20.current_speed)
        self._update_all_ui()

    def next_light_mode(self):
        next_mode = self.r20.next_light_mode()
        self.config.set("last_rgb_mode", next_mode)
        self._update_all_ui()

    @pyqtSlot(bool)
    def set_volume_sync_enabled(self, enabled: bool):
        was_enabled = self.volume_sync.enabled
        self.config.set("sync_windows_volume", enabled)

        if enabled and not was_enabled:
            # Save the pre-sync Windows system volume (e.g. 100%) before syncing
            win_scalar = self.volume_sync.get_windows_volume_scalar()
            if win_scalar is not None and win_scalar > 0.0:
                self.config.set("pre_sync_windows_volume", win_scalar)
            if self.r20.current_volume > 0:
                self.config.set("pre_sync_volume", self.r20.current_volume)
            self.volume_sync.set_sync_enabled(True)
            # Follow speaker hardware volume level: set Windows volume to match speaker!
            self.volume_sync.sync_windows_to_speaker_immediately()
        elif not enabled and was_enabled:
            # Turn off Windows sync: keep speaker at its current hardware volume,
            # and restore Windows system volume back to its pre-sync level (e.g. 100%)
            self.volume_sync.set_sync_enabled(False)
            restore_win = float(self.config.get("pre_sync_windows_volume", 1.0))
            restore_win = max(0.05, min(1.0, restore_win))
            self.volume_sync.set_windows_volume_scalar(restore_win)
        else:
            self.volume_sync.set_sync_enabled(enabled)

        self.act_sync.blockSignals(True)
        self.act_sync.setChecked(enabled)
        self.act_sync.blockSignals(False)
        self.act_keep_win_100.setEnabled(enabled)

        self.popup.chk_sync.blockSignals(True)
        self.popup.chk_sync.setChecked(enabled)
        self.popup.chk_sync.blockSignals(False)
        self.popup.chk_keep_win_100.setEnabled(enabled)

        self._update_all_ui()

    @pyqtSlot(bool)
    def set_keep_windows_100_enabled(self, keep_100: bool):
        self.config.set("keep_windows_volume_100", keep_100)
        self.volume_sync.set_keep_windows_100(keep_100)

        self.act_keep_win_100.blockSignals(True)
        self.act_keep_win_100.setChecked(keep_100)
        self.act_keep_win_100.blockSignals(False)

        self.popup.chk_keep_win_100.blockSignals(True)
        self.popup.chk_keep_win_100.setChecked(keep_100)
        self.popup.chk_keep_win_100.blockSignals(False)

        self._update_all_ui()

    @pyqtSlot(bool)
    def set_autostart_enabled(self, enabled: bool):
        self.config.set_autostart(enabled)
        self.act_autostart.blockSignals(True)
        self.act_autostart.setChecked(enabled)
        self.act_autostart.blockSignals(False)

        self.popup.chk_autostart.blockSignals(True)
        self.popup.chk_autostart.setChecked(enabled)
        self.popup.chk_autostart.blockSignals(False)

    def reconnect_speaker(self):
        connected = self.r20.connect()
        self._update_all_ui()
        if connected:
            self.tray_icon.showMessage(
                "Edifier R20",
                "已成功連線到 Edifier R20 喇叭！",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )

    def _check_reconnect(self):
        if not self.r20.is_connected:
            if self.r20.connect():
                self._update_all_ui()

    def _on_r20_hardware_event(self, event, *args):
        # Marshal hardware event from any thread to the Qt main thread
        self.hardware_state_changed.emit()

    @pyqtSlot(float, bool)
    def _on_windows_volume_changed(self, scalar: float, is_muted: bool):
        # Triggered when Windows master volume changes externally
        pass

    @pyqtSlot(int)
    def _on_speaker_synced_by_windows(self, new_vol: int):
        self.config.set("last_volume", new_vol)
        self._update_all_ui()
        self.osd.show_volume(new_vol)

    @pyqtSlot(int)
    def _on_hardware_volume_changed(self, new_vol: int):
        if not self.volume_sync.enabled and new_vol > 0:
            self.config.set("pre_sync_volume", new_vol)
        self.config.set("last_volume", new_vol)
        self._update_all_ui()
        self.osd.show_volume(new_vol)

    def _update_all_ui(self):
        vol = self.r20.current_volume
        mode = self.r20.current_light_mode
        sound_mode = self.r20.current_sound_mode
        connected = self.r20.is_connected
        percent = int(round((vol / 16.0) * 100))

        # 1. Update Tray Icon
        icon = create_tray_icon(vol, is_connected=connected, light_mode=mode)
        self.tray_icon.setIcon(icon)

        # 2. Update Tooltip
        mode_name = self.r20.get_mode_name(mode)
        sound_name = self.r20.get_sound_mode_name(sound_mode)
        sync_str = "開啟" if self.volume_sync.enabled else "關閉"
        if connected:
            tooltip = (
                f"Edifier R20 USB 喇叭\n"
                f"音量: {percent}% ({vol}/16)\n"
                f"音效: {sound_name}\n"
                f"燈效: {mode_name}\n"
                f"系統同步: {sync_str}"
            )
        else:
            tooltip = "Edifier R20 USB 喇叭 (未連線)"
        self.tray_icon.setToolTip(tooltip)

        # 3. Update Menu Items
        if connected:
            self.action_status.setText("● Edifier R20 (已連線)")
        else:
            self.action_status.setText("● Edifier R20 (未偵測到)")

        self.action_vol_status.setText(f"目前音量: {percent}% ({vol}/16)")
        self.act_mute.setText("🔊 取消靜音" if vol == 0 else "🔇 靜音")

        if sound_mode in self.sound_actions:
            self.sound_actions[sound_mode].setChecked(True)

        if mode in self.rgb_actions:
            self.rgb_actions[mode].setChecked(True)

        # 4. Update Popup
        self.popup.update_state(
            vol=vol,
            mode=mode,
            is_connected=connected,
            sound_mode=sound_mode,
        )

    def _install_keyboard_hook(self):
        def _low_level_kbd_proc(nCode, wParam, lParam):
            if nCode >= 0 and self.volume_sync.enabled:
                kb = KBDLLHOOKSTRUCT.from_address(lParam)
                if kb.vkCode in (VK_VOLUME_UP, VK_VOLUME_DOWN, VK_VOLUME_MUTE):
                    if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        self.media_key_pressed.emit(int(kb.vkCode))
                    if self.volume_sync.keep_windows_100:
                        return 1
            return _user32.CallNextHookEx(None, nCode, wParam, lParam)

        self._hook_proc = HOOKPROC(_low_level_kbd_proc)
        self._hhook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_proc, None, 0)

    def _uninstall_keyboard_hook(self):
        if self._hhook:
            try:
                _user32.UnhookWindowsHookEx(self._hhook)
            except Exception:
                pass
            self._hhook = None

    @pyqtSlot(int)
    def _on_media_key_pressed(self, vk_code: int):
        if vk_code == VK_VOLUME_UP:
            new_vol = min(16, self.r20.current_volume + 1)
            self.set_volume(new_vol)
            self.osd.show_volume(new_vol)
        elif vk_code == VK_VOLUME_DOWN:
            new_vol = max(0, self.r20.current_volume - 1)
            self.set_volume(new_vol)
            self.osd.show_volume(new_vol)
        elif vk_code == VK_VOLUME_MUTE:
            self._toggle_mute()
            self.osd.show_volume(self.r20.current_volume)

    def quit_app(self):
        self._uninstall_keyboard_hook()
        self.volume_sync.stop()
        self.r20.close()
        self.app.quit()

def main():
    # Single instance guard using Windows Mutex
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        print("Edifier R20 Tray App is already running.")
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setApplicationName("Edifier R20 Controller")

    tray_app = R20TrayApp(app)

    exit_code = app.exec()

    if mutex:
        kernel32.ReleaseMutex(mutex)
        kernel32.CloseHandle(mutex)

    sys.exit(exit_code)

if __name__ == "__main__":
    main()
