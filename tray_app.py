"""
Edifier R20 system tray application (Windows and Linux).

Tray icon, quick RGB mode switching, hardware volume control, system volume
bridging and the movable control panel.  The module is import-safe on every
platform; OS specific parts live in :mod:`platform_utils`, :mod:`media_keys`,
:mod:`volume_sync` and :mod:`audio_meter`.

Command line:
    tray_app.py              start normally (single instance enforced)
    tray_app.py --autostart  same as above, used by the autostart entry
    tray_app.py --diagnose   print environment / device diagnostics and exit
    tray_app.py --version    print the version and exit
"""

from __future__ import annotations

import os
import sys
import time
import traceback

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
try:
    os.chdir(SCRIPT_DIR)
except OSError:
    pass

import platform_utils


def _ensure_std_streams():
    """Windowed (PyInstaller) builds start without stdout/stderr.

    Without this, the first ``print`` would raise ``AttributeError`` and kill the
    process.  Redirect the missing streams to a log file instead.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    stream = None
    try:
        log_path = os.path.join(platform_utils.log_dir(), "tray_app.log")
        stream = open(log_path, "a", encoding="utf-8", buffering=1)
    except OSError:
        try:
            stream = open(os.devnull, "w", encoding="utf-8")
        except OSError:
            stream = None
    if stream is not None:
        if sys.stdout is None:
            sys.stdout = stream
        if sys.stderr is None:
            sys.stderr = stream


_ensure_std_streams()


def log_exception(exc_type, exc_value, exc_traceback):
    """Writes uncaught exceptions to ``<config dir>/logs/crash.log``."""
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    try:
        path = os.path.join(platform_utils.log_dir(), "crash.log")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    except OSError:
        pass
    try:
        sys.stderr.write(text)
    except Exception:
        pass


sys.excepthook = log_exception

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtCore import QTimer, pyqtSlot, pyqtSignal, QObject

from r20_controller import EdifierR20, RGB_MODES, SOUND_MODES
from config import ConfigManager
from volume_sync import (
    create_volume_sync, VK_VOLUME_UP, VK_VOLUME_DOWN, VK_VOLUME_MUTE,
)
from sound_reactive import SoundReactiveLight, is_rgb_settable_mode
from icon_generator import create_tray_icon
from tray_popup import R20Popup, R20VolumeOSD
from media_keys import MediaKeyHook


class R20TrayApp(QObject):
    hardware_state_changed = pyqtSignal()
    media_key_pressed = pyqtSignal(int)

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self.hardware_state_changed.connect(self._update_all_ui)
        self.media_key_pressed.connect(self._on_media_key_pressed)

        # 1. Load config
        self.config = ConfigManager()

        # 2. Hardware controller
        self.r20 = EdifierR20()

        # 2b. Sound-reactive rainbow light engine (audio level -> RGB)
        self.rainbow = SoundReactiveLight(self.r20)
        self.rainbow.color_changed.connect(self._on_rainbow_color)
        self._rainbow_saved_color = None
        self._last_icon_refresh = 0.0

        # 3. System volume bridge (Windows: pycaw, Linux: wpctl/pactl)
        sync_enabled = self.config.get("sync_windows_volume", True)
        keep_win_100 = self.config.get("keep_windows_volume_100", True)
        self.volume_sync = create_volume_sync(
            self.r20,
            enabled=sync_enabled,
            keep_windows_100=keep_win_100,
        )
        self.volume_sync.windows_volume_changed.connect(self._on_windows_volume_changed)
        self.volume_sync.speaker_synced.connect(self._on_speaker_synced_by_windows)
        self.volume_sync.hardware_volume_changed.connect(self._on_hardware_volume_changed)

        # 4. Movable control panel and on-screen volume OSD
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
        self.popup.sound_reactive_toggled.connect(self.set_sound_reactive_enabled)
        self.popup.autostart_toggled.connect(self.set_autostart_enabled)
        self.popup.reconnect_requested.connect(self.reconnect_speaker)

        # 5. System tray icon and menu
        self.tray_icon = QSystemTrayIcon(self.app)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self._build_context_menu()

        # 6. Connect to the hardware and restore persisted state
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
                "Edifier R20 connected: Vol=%s, SoundMode=%s, LightMode=%s"
                % (self.r20.current_volume, self.r20.current_sound_mode,
                   self.r20.current_light_mode)
            )
            # Restore the sound-reactive rainbow option if it was enabled
            if self.config.get("sound_reactive_rainbow", False):
                mode = self.r20.current_light_mode
                if not is_rgb_settable_mode(mode):
                    mode = self.config.get("last_rgb_mode", 2)
                    if not is_rgb_settable_mode(mode):
                        mode = 2
                    self.r20.set_light_mode(mode)
                grp = self.r20.get_active_light_group(mode)
                self._rainbow_saved_color = (grp["R"], grp["G"], grp["B"])
                self.rainbow.start_effect(mode)
        else:
            print("Edifier R20 not detected on startup, will retry automatically.")

        # 7. Background workers: volume bridge, rainbow engine, media keys
        self.volume_sync.start()
        self.rainbow.start()
        self.media_hook = MediaKeyHook(self._on_media_key)
        self.media_hook.install()

        # 8. Periodic auto-reconnect timer
        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.setInterval(4000)
        self.reconnect_timer.timeout.connect(self._check_reconnect)
        self.reconnect_timer.start()

        # 8b. Poll for "show the panel" requests from a second launch
        self._show_poll_timer = QTimer(self)
        self._show_poll_timer.setInterval(400)
        self._show_poll_timer.timeout.connect(self._poll_show_request)
        self._show_poll_timer.start()

        # Initial UI update
        self._update_all_ui()
        self.tray_icon.show()

    # ----------------------------------------------------------------- menu
    def _build_context_menu(self):
        self.menu = QMenu()
        self.menu.setStyleSheet("""
            QMenu {
                background-color: #202027;
                color: #e2e8f0;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 6px;
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

        # Action to open the movable panel
        action_open = QAction("🎛️ 開啟控制面板", self.menu)
        action_open.triggered.connect(self.popup.show_near_tray)
        self.menu.addAction(action_open)

        action_reset = QAction("📍 面板回到系統匣位置", self.menu)
        action_reset.triggered.connect(self._reset_panel_position)
        self.menu.addAction(action_reset)

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

        # Sound-reactive rainbow (audio level drives the RGB color)
        self.act_rainbow = QAction("🌈 彩虹律動 (海妖之聲 RGB 跟隨音量)", self.menu)
        self.act_rainbow.setCheckable(True)
        self.act_rainbow.setChecked(self.config.get("sound_reactive_rainbow", False))
        self.act_rainbow.toggled.connect(self.set_sound_reactive_enabled)
        self.menu.addAction(self.act_rainbow)

        self.menu.addSeparator()

        # Sync with the system mixer
        self.act_sync = QAction(
            "🔄 與 %s 同步" % platform_utils.system_volume_label(), self.menu
        )
        self.act_sync.setCheckable(True)
        self.act_sync.setChecked(self.config.get("sync_windows_volume", True))
        self.act_sync.toggled.connect(self.set_volume_sync_enabled)
        self.menu.addAction(self.act_sync)

        # Keep the system mixer at 100% option
        self.act_keep_win_100 = QAction(
            "🔒 同步時保持 %s 100%% (拉桿僅控喇叭硬體)" % platform_utils.mixer_label(),
            self.menu,
        )
        self.act_keep_win_100.setCheckable(True)
        self.act_keep_win_100.setChecked(self.config.get("keep_windows_volume_100", True))
        self.act_keep_win_100.setEnabled(self.act_sync.isChecked())
        self.act_keep_win_100.toggled.connect(self.set_keep_windows_100_enabled)
        self.menu.addAction(self.act_keep_win_100)

        # Autostart option
        self.act_autostart = QAction("🚀 開機自動啟動", self.menu)
        self.act_autostart.setCheckable(True)
        self.act_autostart.setChecked(self.config.is_autostart_enabled())
        self.act_autostart.setEnabled(platform_utils.autostart_supported())
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

    # ---------------------------------------------------------------- tray
    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Single left-click: toggle the movable panel
            if self.popup.isVisible():
                self.popup.hide()
            else:
                self.popup.show_near_tray()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.popup.show_near_tray()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            # Middle-click: quick mute / unmute
            self._toggle_mute()

    def _poll_show_request(self):
        """A second launch (Start menu / shortcut) re-opens the closed panel."""
        if platform_utils.consume_show_request():
            self.popup.show_near_tray()

    def _reset_panel_position(self):
        self.popup.reset_position()
        self.popup.show_near_tray()

    def _toggle_mute(self):
        new_vol = self.r20.toggle_mute()
        if not self.volume_sync.enabled and new_vol > 0:
            self.config.set("pre_sync_volume", new_vol)
        self.volume_sync.on_user_changed_r20_volume(new_vol)
        self._update_all_ui()

    # --------------------------------------------------------- volume / eq
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

    # ---------------------------------------------------------- light / rgb
    @pyqtSlot(int)
    def set_light_mode(self, mode: int):
        self.r20.set_light_mode(mode)
        self.config.set("last_rgb_mode", mode)
        if self.rainbow.active:
            if is_rgb_settable_mode(mode):
                # Keep animating but retarget to the newly selected mode
                grp = self.r20.get_active_light_group(mode)
                self._rainbow_saved_color = (grp["R"], grp["G"], grp["B"])
                self.rainbow.start_effect(mode)
            else:
                # Animated rainbow is only possible on RGB-settable modes
                self.rainbow.stop_effect()
                self.config.set("sound_reactive_rainbow", False)
                self._sync_rainbow_widgets(False)
        self._update_all_ui()

    @pyqtSlot(int, int, int)
    def set_light_color(self, r: int, g: int, b: int):
        # Manually picking a static color turns the rainbow effect off
        if self.rainbow.active:
            self.rainbow.stop_effect()
            self.config.set("sound_reactive_rainbow", False)
            self._sync_rainbow_widgets(False)
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

    @pyqtSlot(int, int, int)
    def _on_rainbow_color(self, r: int, g: int, b: int):
        """Live colour from the rainbow engine -> panel chip and tray icon."""
        self.popup.set_live_color(r, g, b, animated=True)
        now = time.time()
        if now - self._last_icon_refresh >= 0.25:
            self._last_icon_refresh = now
            self.tray_icon.setIcon(create_tray_icon(
                self.r20.current_volume,
                is_connected=self.r20.is_connected,
                light_mode=self.r20.current_light_mode,
                rgb_color=(r, g, b),
            ))

    # --------------------------------------------------------------- options
    @pyqtSlot(bool)
    def set_volume_sync_enabled(self, enabled: bool):
        was_enabled = self.volume_sync.enabled
        self.config.set("sync_windows_volume", enabled)

        if enabled and not was_enabled:
            # Save the pre-sync system volume before syncing
            win_scalar = self.volume_sync.get_windows_volume_scalar()
            if win_scalar is not None and win_scalar > 0.0:
                self.config.set("pre_sync_windows_volume", win_scalar)
            if self.r20.current_volume > 0:
                self.config.set("pre_sync_volume", self.r20.current_volume)
            self.volume_sync.set_sync_enabled(True)
            # Follow the speaker hardware volume level
            self.volume_sync.sync_windows_to_speaker_immediately()
        elif not enabled and was_enabled:
            # Turn sync off: keep the speaker volume, restore the system mixer
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
    def set_sound_reactive_enabled(self, enabled: bool):
        """Enable/disable the audio-reactive rainbow RGB effect."""
        enabled = bool(enabled)
        self.config.set("sound_reactive_rainbow", enabled)

        if enabled:
            if not self.r20.is_connected:
                self.r20.connect()
            mode = self.r20.current_light_mode
            if not is_rgb_settable_mode(mode):
                # Rainbow needs an RGB-settable effect: use 海妖之聲 (mode 2)
                mode = 2
                self.r20.set_light_mode(mode)
                self.config.set("last_rgb_mode", mode)
            # Remember the static color so it can be restored when turned off
            grp = self.r20.get_active_light_group(mode)
            self._rainbow_saved_color = (grp["R"], grp["G"], grp["B"])
            self.rainbow.start_effect(mode)
        else:
            was_mode = self.rainbow.mode if self.rainbow.active else self.r20.current_light_mode
            self.rainbow.stop_effect()
            # Restore the static color that was active before the animation
            if self.r20.is_connected and is_rgb_settable_mode(was_mode):
                self._apply_saved_rainbow_color(was_mode)
                # Re-apply shortly after to win any in-flight animation write
                QTimer.singleShot(150, lambda m=was_mode: self._apply_saved_rainbow_color(m))

        self._sync_rainbow_widgets(enabled)
        self._update_all_ui()

    def _sync_rainbow_widgets(self, enabled: bool):
        self.act_rainbow.blockSignals(True)
        self.act_rainbow.setChecked(enabled)
        self.act_rainbow.blockSignals(False)

        self.popup.chk_rainbow.blockSignals(True)
        self.popup.chk_rainbow.setChecked(enabled)
        self.popup.chk_rainbow.blockSignals(False)

    def _apply_saved_rainbow_color(self, mode: int):
        """Restore the static RGB color of a mode after the animation stops."""
        if self.rainbow.active:
            return
        if not self.r20.is_connected or not is_rgb_settable_mode(mode):
            return
        if self._rainbow_saved_color:
            r, g, b = self._rainbow_saved_color
            self.r20.set_light_color(r, g, b)
        else:
            self.r20.set_light_mode(mode)
        self._update_all_ui()

    @pyqtSlot(bool)
    def set_autostart_enabled(self, enabled: bool):
        self.config.set_autostart(enabled)
        enabled = self.config.is_autostart_enabled()
        self.act_autostart.blockSignals(True)
        self.act_autostart.setChecked(enabled)
        self.act_autostart.blockSignals(False)

        self.popup.chk_autostart.blockSignals(True)
        self.popup.chk_autostart.setChecked(enabled)
        self.popup.chk_autostart.blockSignals(False)

    # ------------------------------------------------------------- hardware
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
        # Marshal hardware events from any thread onto the Qt main thread
        self.hardware_state_changed.emit()

    @pyqtSlot(float, bool)
    def _on_windows_volume_changed(self, scalar: float, is_muted: bool):
        # Triggered when the system master volume changes externally
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

    def _on_media_key(self, vk_code: int) -> bool:
        """Low level keyboard hook callback (Windows only)."""
        if not self.volume_sync.enabled:
            return False
        self.media_key_pressed.emit(int(vk_code))
        return bool(getattr(self.volume_sync, "keep_windows_100", False))

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

    # ------------------------------------------------------------------ ui
    def _update_all_ui(self):
        vol = self.r20.current_volume
        mode = self.r20.current_light_mode
        sound_mode = self.r20.current_sound_mode
        connected = self.r20.is_connected
        percent = int(round((vol / 16.0) * 100))

        # 1. Update tray icon with the live RGB colour when available
        live_rgb = None
        if connected and is_rgb_settable_mode(mode):
            grp = self.r20.get_active_light_group()
            live_rgb = (grp.get("R", 0), grp.get("G", 0), grp.get("B", 0))
        icon = create_tray_icon(
            vol, is_connected=connected, light_mode=mode, rgb_color=live_rgb
        )
        self.tray_icon.setIcon(icon)

        # 2. Update tooltip
        mode_name = self.r20.get_mode_name(mode)
        sound_name = self.r20.get_sound_mode_name(sound_mode)
        sync_str = "開啟" if self.volume_sync.enabled else "關閉"
        if connected:
            tooltip = (
                "Edifier R20 USB 喇叭\n"
                "音量: %d%% (%d/16)\n"
                "音效: %s\n"
                "燈效: %s\n"
                "系統同步: %s" % (percent, vol, sound_name, mode_name, sync_str)
            )
            if live_rgb:
                tooltip += "\n顏色: #%02X%02X%02X" % tuple(live_rgb)
            if self.rainbow.active:
                tooltip += "\n彩虹律動: 開啟 🌈"
        else:
            tooltip = "Edifier R20 USB 喇叭 (未連線)"
        self.tray_icon.setToolTip(tooltip)

        # 3. Update menu items
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

        rainbow_on = self.rainbow.active
        self.act_rainbow.blockSignals(True)
        self.act_rainbow.setChecked(rainbow_on)
        self.act_rainbow.blockSignals(False)

        # 4. Update the movable control panel
        self.popup.update_state(
            vol=vol,
            mode=mode,
            is_connected=connected,
            sound_mode=sound_mode,
            sound_reactive=rainbow_on,
        )

    # ---------------------------------------------------------------- quit
    def quit_app(self):
        try:
            self.reconnect_timer.stop()
            self._show_poll_timer.stop()
        except Exception:
            pass
        self.media_hook.uninstall()
        self.rainbow.stop()
        self.volume_sync.stop()
        self.r20.close()
        self.app.quit()


def run_diagnostics(show_gui: bool = True) -> int:
    """Writes environment / device information to a report (``--diagnose``).

    The packaged application is a windowed executable without a console, so the
    report is also stored in ``<log dir>/diagnose.txt`` and shown in a message
    box on Windows.
    """
    import platform as platform_module
    import shutil

    lines = []

    def add(text):
        lines.append(text)

    add("%s %s" % (platform_utils.APP_NAME, platform_utils.APP_VERSION))
    add("python          : %s (%s)" % (platform_module.python_version(), sys.executable))
    add("platform        : %s" % platform_module.platform())
    add("frozen build    : %s" % platform_utils.is_frozen())
    add("app root        : %s" % platform_utils.app_root())
    add("config file     : %s" % platform_utils.config_file_path())
    add("log dir         : %s" % platform_utils.log_dir())
    add("autostart       : %s" % platform_utils.is_autostart_enabled())
    try:
        from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR

        add("PyQt6           : %s (Qt %s)" % (PYQT_VERSION_STR, QT_VERSION_STR))
    except Exception as exc:
        add("PyQt6           : MISSING (%s)" % exc)
    try:
        from r20_controller import describe_devices, enumerate_devices

        devices = enumerate_devices()
        add("R20 interfaces  : %d" % len(devices))
        for line in describe_devices():
            add("  - %s" % line)
    except Exception as exc:
        add("R20 interfaces  : ERROR (%s)" % exc)
    try:
        from audio_meter import create_audio_meter

        meter = create_audio_meter()
        add("audio meter     : %s" % meter.name)
        meter.close()
    except Exception as exc:
        add("audio meter     : ERROR (%s)" % exc)
    if platform_utils.IS_WINDOWS:
        try:
            import pycaw  # noqa: F401

            add("volume backend  : pycaw (Windows CoreAudio)")
        except Exception as exc:
            add("volume backend  : ERROR (%s)" % exc)
    elif platform_utils.IS_LINUX:
        backend = "wpctl" if shutil.which("wpctl") else ("pactl" if shutil.which("pactl") else "none")
        add("volume backend  : %s" % backend)
        add("parec available : %s" % bool(shutil.which("parec")))
    else:
        add("volume backend  : unsupported platform")

    report = "\n".join(lines)
    try:
        print(report)
    except Exception:
        pass

    report_path = os.path.join(platform_utils.log_dir(), "diagnose.txt")
    try:
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")
    except OSError:
        report_path = "(無法寫入)"

    if show_gui and platform_utils.IS_WINDOWS and platform_utils.is_frozen():
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                report + "\n\n已儲存到:\n" + report_path,
                "Edifier R20 診斷資訊",
                0x40,  # MB_ICONINFORMATION
            )
        except Exception:
            pass
    return 0


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if "--version" in args or "-V" in args:
        try:
            print("%s %s" % (platform_utils.APP_NAME, platform_utils.APP_VERSION))
        except Exception:
            pass
        return 0
    if "--diagnose" in args:
        return run_diagnostics(show_gui="--no-message" not in args)

    # Single instance: a second launch just re-opens the panel of the first one.
    guard = platform_utils.SingleInstance()
    if not guard.acquire():
        platform_utils.request_show()
        print("Edifier R20 Tray App is already running.")
        return 0

    try:
        app = QApplication(sys.argv)
        app.setApplicationName(platform_utils.APP_NAME)
        app.setApplicationDisplayName(platform_utils.APP_SHORT_NAME)
        app.setApplicationVersion(platform_utils.APP_VERSION)
        app.setQuitOnLastWindowClosed(False)
        if platform_utils.IS_LINUX:
            # Groups the window/tray under the installed .desktop file.
            app.setDesktopFileName(platform_utils.DESKTOP_ID)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print(
                "Warning: no system tray available. The control panel is still "
                "reachable from the application shortcut."
            )

        tray_app = R20TrayApp(app)  # noqa: F841 - keep the controller alive
        return int(app.exec() or 0)
    finally:
        guard.release()


if __name__ == "__main__":
    sys.exit(main())
