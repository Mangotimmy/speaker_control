"""
Modern Floating Quick Settings Popup for Edifier R20.
Windows 11 Fluent Dark Aesthetic with volume sliders, presets, RGB matrix, and sync switches.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QPushButton, QCheckBox, QFrame, QGridLayout,
    QGraphicsDropShadowEffect, QApplication, QColorDialog, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QEvent, QTimer
from PyQt6.QtGui import QColor, QFont, QCursor, QGuiApplication

from r20_controller import RGB_MODES, RGB_MODE_MAP, SOUND_MODES, EdifierR20

STYLE_SHEET = """
QWidget#Container {
    background-color: #1e1e24;
    border: 1px solid #33333d;
    border-radius: 14px;
}

QLabel {
    color: #e6e6ec;
    font-family: "Segoe UI", "Microsoft JhengHei UI", sans-serif;
}

QLabel#HeaderTitle {
    font-size: 15px;
    font-weight: bold;
    color: #ffffff;
}

QLabel#StatusBadgeConnected {
    font-size: 11px;
    color: #4ade80;
    background-color: #1a3324;
    border: 1px solid #2d5a3c;
    border-radius: 9px;
    padding: 2px 8px;
}

QLabel#StatusBadgeDisconnected {
    font-size: 11px;
    color: #f87171;
    background-color: #381e1e;
    border: 1px solid #5c2c2c;
    border-radius: 9px;
    padding: 2px 8px;
}

QLabel#SectionHeader {
    font-size: 12px;
    font-weight: 600;
    color: #9ca3af;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

QLabel#VolumePercent {
    font-size: 26px;
    font-weight: bold;
    color: #60a5fa;
}

QLabel#VolumeStep {
    font-size: 13px;
    color: #9ca3af;
    margin-bottom: 4px;
}

/* Custom Volume Slider */
QSlider::groove:horizontal {
    border: none;
    height: 8px;
    background: #2d2d38;
    border-radius: 4px;
}

QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #60a5fa);
    border-radius: 4px;
}

QSlider::handle:horizontal {
    background: #ffffff;
    border: 2px solid #3b82f6;
    width: 18px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 9px;
}

QSlider::handle:horizontal:hover {
    background: #e0e7ff;
    border-color: #2563eb;
    transform: scale(1.1);
}

/* Preset Buttons */
QPushButton.PresetBtn {
    background-color: #262630;
    color: #d1d5db;
    border: 1px solid #3a3a48;
    border-radius: 6px;
    padding: 5px 0px;
    font-size: 11px;
    font-weight: 500;
}

QPushButton.PresetBtn:hover {
    background-color: #3b82f6;
    color: #ffffff;
    border-color: #60a5fa;
}

/* Sound Mode Buttons */
QPushButton.SoundBtn {
    background-color: #262632;
    color: #e5e7eb;
    border: 1px solid #373746;
    border-radius: 8px;
    padding: 6px 4px;
    text-align: center;
    font-size: 12px;
}

QPushButton.SoundBtn:hover {
    background-color: #323242;
    border-color: #8b5cf6;
}

QPushButton.SoundBtnActive {
    background-color: #2e1f47;
    color: #c4b5fd;
    border: 1.5px solid #8b5cf6;
    border-radius: 8px;
    padding: 6px 4px;
    text-align: center;
    font-size: 12px;
    font-weight: bold;
}

/* RGB Buttons */
QPushButton.RgbBtn {
    background-color: #262632;
    color: #e5e7eb;
    border: 1px solid #373746;
    border-radius: 8px;
    padding: 6px 10px;
    text-align: left;
    font-size: 12px;
}

QPushButton.RgbBtn:hover {
    background-color: #323242;
    border-color: #4f46e5;
}

QPushButton.RgbBtnActive {
    background-color: #1e293b;
    color: #38bdf8;
    border: 1.5px solid #0284c7;
    border-radius: 8px;
    padding: 6px 10px;
    text-align: left;
    font-size: 12px;
    font-weight: bold;
}

/* Mute Button */
QPushButton#MuteBtn {
    background-color: #2d2d38;
    color: #ffffff;
    border: 1px solid #404052;
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 12px;
}

QPushButton#MuteBtn:hover {
    background-color: #ef4444;
    border-color: #dc2626;
}

QPushButton#MuteBtnActive {
    background-color: #ef4444;
    color: #ffffff;
    border: 1px solid #dc2626;
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: bold;
}

/* Checkboxes */
QCheckBox {
    color: #d1d5db;
    font-size: 12px;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #4b5563;
    background: #262630;
}

QCheckBox::indicator:checked {
    background: #3b82f6;
    border-color: #2563eb;
    image: none;
}

QFrame.Separator {
    background-color: #2d2d38;
    max-height: 1px;
    height: 1px;
    border: none;
}
"""

COLOR_PRESETS = [
    ("#0bff92", (11, 255, 146), "極光青"),
    ("#7cfc00", (124, 252, 0), "霓虹綠"),
    ("#ff9d1c", (255, 157, 28), "暖陽橘"),
    ("#ff4500", (255, 69, 0), "烈焰紅"),
    ("#00bfff", (0, 191, 255), "冰川藍"),
    ("#8a2be2", (138, 43, 226), "星雲紫"),
    ("#ff1493", (255, 20, 147), "賽博粉"),
    ("#ffffff", (255, 255, 255), "純淨白"),
]

class R20Popup(QWidget):
    volume_requested = pyqtSignal(int)
    sound_mode_requested = pyqtSignal(int)
    light_mode_requested = pyqtSignal(int)
    color_requested = pyqtSignal(int, int, int)
    sub_effect_requested = pyqtSignal(int)
    brightness_requested = pyqtSignal(int)
    speed_requested = pyqtSignal(int)
    sync_toggled = pyqtSignal(bool)
    keep_win_100_toggled = pyqtSignal(bool)
    autostart_toggled = pyqtSignal(bool)
    reconnect_requested = pyqtSignal()

    def __init__(self, r20_controller: EdifierR20, config_mgr):
        super().__init__()
        self.r20 = r20_controller
        self.config = config_mgr
        self._updating_ui = False
        self._color_dialog_open = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(STYLE_SHEET)

        self._build_ui()
        self.installEventFilter(self)

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)

        # Container Frame for shadow and rounded corners
        self.container = QFrame(self)
        self.container.setObjectName("Container")
        
        # Shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 6)
        self.container.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self.container)
        layout.setSpacing(10)
        layout.setContentsMargins(18, 14, 18, 14)

        # 1. Header (Device Title + Status)
        header_layout = QHBoxLayout()
        title_label = QLabel("Edifier R20", self)
        title_label.setObjectName("HeaderTitle")
        
        self.status_badge = QLabel("● 已連線", self)
        self.status_badge.setObjectName("StatusBadgeConnected")
        
        self.btn_reconnect = QPushButton("重新連線", self)
        self.btn_reconnect.setStyleSheet("""
            QPushButton {
                background: #2a2a36; color: #a1a1aa; border: 1px solid #3f3f50;
                border-radius: 6px; padding: 2px 8px; font-size: 11px;
            }
            QPushButton:hover { background: #3b82f6; color: #fff; }
        """)
        self.btn_reconnect.clicked.connect(self.reconnect_requested.emit)
        self.btn_reconnect.setVisible(False)

        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_reconnect)
        header_layout.addWidget(self.status_badge)
        layout.addLayout(header_layout)

        # Separator
        sep1 = QFrame()
        sep1.setObjectName("Separator")
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setProperty("class", "Separator")
        layout.addWidget(sep1)

        # 2. Volume Section
        sec_vol = QLabel("音量控制 (HARDWARE AMPLIFIER)", self)
        sec_vol.setObjectName("SectionHeader")
        layout.addWidget(sec_vol)

        vol_display_layout = QHBoxLayout()
        self.lbl_volume_percent = QLabel("50%", self)
        self.lbl_volume_percent.setObjectName("VolumePercent")
        
        self.lbl_volume_step = QLabel("(8 / 16)", self)
        self.lbl_volume_step.setObjectName("VolumeStep")

        self.btn_mute = QPushButton("🔊 靜音", self)
        self.btn_mute.setObjectName("MuteBtn")
        self.btn_mute.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mute.clicked.connect(self._on_mute_clicked)

        vol_display_layout.addWidget(self.lbl_volume_percent)
        vol_display_layout.addWidget(self.lbl_volume_step, alignment=Qt.AlignmentFlag.AlignBottom)
        vol_display_layout.addStretch()
        vol_display_layout.addWidget(self.btn_mute)
        layout.addLayout(vol_display_layout)

        # Volume Slider
        self.vol_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.vol_slider.setRange(0, 16)
        self.vol_slider.setValue(self.r20.current_volume)
        self.vol_slider.setSingleStep(1)
        self.vol_slider.setPageStep(2)
        self.vol_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vol_slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self.vol_slider)

        # Volume Quick Presets
        presets_layout = QHBoxLayout()
        presets_layout.setSpacing(6)
        preset_values = [
            ("0%", 0),
            ("25%", 4),
            ("50%", 8),
            ("75%", 12),
            ("100%", 16)
        ]
        for text, val in preset_values:
            btn = QPushButton(text, self)
            btn.setProperty("class", "PresetBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, v=val: self._set_volume(v))
            presets_layout.addWidget(btn)
        layout.addLayout(presets_layout)

        # Separator
        sep_eq = QFrame()
        sep_eq.setFrameShape(QFrame.Shape.HLine)
        sep_eq.setProperty("class", "Separator")
        layout.addWidget(sep_eq)

        # 3. Quick Sound Mode Section (EQ)
        sec_eq = QLabel("音效模式 (QUICK SOUND MODE)", self)
        sec_eq.setObjectName("SectionHeader")
        layout.addWidget(sec_eq)

        self.sound_buttons = {}
        eq_layout = QHBoxLayout()
        eq_layout.setSpacing(6)
        for sm in SOUND_MODES:
            eq_idx = sm["index"]
            btn = QPushButton(f"{sm['icon']} {sm['name']}", self)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("class", "SoundBtn")
            btn.clicked.connect(lambda checked, idx=eq_idx: self._on_sound_mode_clicked(idx))
            self.sound_buttons[eq_idx] = btn
            eq_layout.addWidget(btn)
        layout.addLayout(eq_layout)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setProperty("class", "Separator")
        layout.addWidget(sep2)

        # 4. RGB Lighting Section
        sec_rgb = QLabel("RGB 燈效切換 (7 MODES)", self)
        sec_rgb.setObjectName("SectionHeader")
        layout.addWidget(sec_rgb)

        # Grid of 7 RGB modes
        self.rgb_buttons = {}
        rgb_grid = QGridLayout()
        rgb_grid.setSpacing(6)

        row, col = 0, 0
        for m in RGB_MODES:
            idx = m["index"]
            btn = QPushButton(f"{m['icon']} {m['name']}", self)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("class", "RgbBtn")
            btn.clicked.connect(lambda checked, mode=idx: self._on_rgb_mode_clicked(mode))
            self.rgb_buttons[idx] = btn

            # Mode 7 (Turn Off LED) spans 2 columns
            if idx == 7:
                rgb_grid.addWidget(btn, row, 0, 1, 2)
            else:
                rgb_grid.addWidget(btn, row, col)
                col += 1
                if col >= 2:
                    col = 0
                    row += 1
        layout.addLayout(rgb_grid)

        # Color Swatches Row (shown for rgb_settable modes 2, 4, 5, 6)
        self.color_row_widget = QWidget(self)
        color_layout = QHBoxLayout(self.color_row_widget)
        color_layout.setContentsMargins(0, 2, 0, 0)
        color_layout.setSpacing(5)
        lbl_color = QLabel("🎨 顏色:", self)
        lbl_color.setStyleSheet("font-size: 11px; color: #9ca3af;")
        color_layout.addWidget(lbl_color)

        self.swatch_buttons = []
        for hex_code, rgb_tuple, tip in COLOR_PRESETS:
            sw = QPushButton("", self.color_row_widget)
            sw.setFixedSize(20, 20)
            sw.setToolTip(tip)
            sw.setCursor(Qt.CursorShape.PointingHandCursor)
            sw.setStyleSheet(
                f"QPushButton {{ background-color: {hex_code}; border: 1.5px solid #4b5563; border-radius: 10px; }}"
                f"QPushButton:hover {{ border: 2px solid #ffffff; }}"
            )
            sw.clicked.connect(lambda checked, c=rgb_tuple: self._on_swatch_clicked(c))
            self.swatch_buttons.append((sw, rgb_tuple, hex_code))
            color_layout.addWidget(sw)

        self.btn_custom_color = QPushButton("自訂", self.color_row_widget)
        self.btn_custom_color.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_custom_color.setStyleSheet("""
            QPushButton {
                background: #2a2a36; color: #d1d5db; border: 1px solid #3f3f50;
                border-radius: 6px; padding: 2px 7px; font-size: 11px;
            }
            QPushButton:hover { background: #3b82f6; color: #ffffff; }
        """)
        self.btn_custom_color.clicked.connect(self._on_custom_color_clicked)
        color_layout.addStretch()
        color_layout.addWidget(self.btn_custom_color)
        layout.addWidget(self.color_row_widget)

        # Sub-effect Row (shown for multi-color modes 1 & 3 which have sub-effect 1 & 2)
        self.sub_effect_widget = QWidget(self)
        sub_layout = QHBoxLayout(self.sub_effect_widget)
        sub_layout.setContentsMargins(0, 2, 0, 0)
        sub_layout.setSpacing(6)
        lbl_sub = QLabel("✨ 色彩樣式:", self)
        lbl_sub.setStyleSheet("font-size: 11px; color: #9ca3af;")
        sub_layout.addWidget(lbl_sub)
        self.btn_sub_1 = QPushButton("幻彩樣式 A", self.sub_effect_widget)
        self.btn_sub_2 = QPushButton("幻彩樣式 B", self.sub_effect_widget)
        for sub_idx, b_sub in [(1, self.btn_sub_1), (2, self.btn_sub_2)]:
            b_sub.setCursor(Qt.CursorShape.PointingHandCursor)
            b_sub.setProperty("class", "PresetBtn")
            b_sub.clicked.connect(lambda checked, s=sub_idx: self.sub_effect_requested.emit(s))
            sub_layout.addWidget(b_sub)
        layout.addWidget(self.sub_effect_widget)

        # Brightness Slider (1..10 -> 10..100, active on Modes 1 & 4)
        self.brightness_widget = QWidget(self)
        brightness_layout = QHBoxLayout(self.brightness_widget)
        brightness_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_bright = QLabel("💡 亮度 (10):", self.brightness_widget)
        self.lbl_bright.setFixedWidth(78)
        self.lbl_bright.setStyleSheet("font-size: 11px; color: #9ca3af;")
        self.bright_slider = QSlider(Qt.Orientation.Horizontal, self.brightness_widget)
        self.bright_slider.setRange(1, 10)
        self.bright_slider.setValue(max(1, min(10, int(round(self.r20.current_brightness / 10.0)))))
        self.bright_slider.valueChanged.connect(self._on_brightness_changed)
        brightness_layout.addWidget(self.lbl_bright)
        brightness_layout.addWidget(self.bright_slider)
        layout.addWidget(self.brightness_widget)

        # Speed Slider (1..10, active on Modes 1, 3, 6)
        self.speed_widget = QWidget(self)
        speed_layout = QHBoxLayout(self.speed_widget)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_speed = QLabel("⚡ 速度 (8):", self.speed_widget)
        self.lbl_speed.setFixedWidth(78)
        self.lbl_speed.setStyleSheet("font-size: 11px; color: #9ca3af;")
        self.speed_slider = QSlider(Qt.Orientation.Horizontal, self.speed_widget)
        self.speed_slider.setRange(1, 10)
        self.speed_slider.setValue(max(1, min(10, self.r20.current_speed)))
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        speed_layout.addWidget(self.lbl_speed)
        speed_layout.addWidget(self.speed_slider)
        layout.addWidget(self.speed_widget)

        # Separator
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setProperty("class", "Separator")
        layout.addWidget(sep3)

        # 5. Sync & Options
        options_layout = QVBoxLayout()
        options_layout.setSpacing(6)

        self.chk_sync = QCheckBox("與 Windows 系統音量自動同步", self)
        self.chk_sync.setChecked(self.config.get("sync_windows_volume", True))
        self.chk_sync.toggled.connect(self._on_sync_toggled)

        self.chk_keep_win_100 = QCheckBox("同步時保持 Windows 混音 100% (拉桿僅控喇叭硬體)", self)
        self.chk_keep_win_100.setChecked(self.config.get("keep_windows_volume_100", True))
        self.chk_keep_win_100.setEnabled(self.chk_sync.isChecked())
        self.chk_keep_win_100.toggled.connect(self._on_keep_win_100_toggled)

        self.chk_autostart = QCheckBox("開機自動啟動", self)
        self.chk_autostart.setChecked(self.config.is_autostart_enabled())
        self.chk_autostart.toggled.connect(self._on_autostart_toggled)

        options_layout.addWidget(self.chk_sync)
        options_layout.addWidget(self.chk_keep_win_100)
        options_layout.addWidget(self.chk_autostart)
        layout.addLayout(options_layout)

        root_layout.addWidget(self.container)
        self.setFixedWidth(372)

    def update_state(
        self,
        vol: int = None,
        mode: int = None,
        is_connected: bool = None,
        sound_mode: int = None,
    ):
        self._updating_ui = True
        try:
            if is_connected is not None:
                if is_connected:
                    self.status_badge.setText("● 已連線")
                    self.status_badge.setObjectName("StatusBadgeConnected")
                    self.status_badge.setStyleSheet("")  # re-apply QSS
                    self.btn_reconnect.setVisible(False)
                else:
                    self.status_badge.setText("● 未偵測到喇叭")
                    self.status_badge.setObjectName("StatusBadgeDisconnected")
                    self.status_badge.setStyleSheet("")
                    self.btn_reconnect.setVisible(True)

            if vol is not None:
                self.vol_slider.setValue(vol)
                percent = int(round((vol / 16.0) * 100))
                self.lbl_volume_percent.setText(f"{percent}%")
                self.lbl_volume_step.setText(f"({vol} / 16)")

                if vol == 0:
                    self.btn_mute.setText("🔇 已靜音")
                    self.btn_mute.setObjectName("MuteBtnActive")
                    self.lbl_volume_percent.setText("靜音")
                else:
                    self.btn_mute.setText("🔊 靜音")
                    self.btn_mute.setObjectName("MuteBtn")
                self.btn_mute.setStyleSheet("")

            if sound_mode is None:
                sound_mode = self.r20.current_sound_mode
            for eq_idx, btn in self.sound_buttons.items():
                if eq_idx == sound_mode:
                    btn.setProperty("class", "SoundBtnActive")
                else:
                    btn.setProperty("class", "SoundBtn")
                btn.setStyleSheet("")

            if mode is not None:
                for idx, btn in self.rgb_buttons.items():
                    if idx == mode:
                        btn.setProperty("class", "RgbBtnActive")
                    else:
                        btn.setProperty("class", "RgbBtn")
                    btn.setStyleSheet("")

                spec = RGB_MODE_MAP.get(mode, RGB_MODE_MAP[2])
                grp = self.r20.get_active_light_group(mode)

                # Show/hide color picker row vs sub-effect row
                self.color_row_widget.setVisible(bool(spec.get("rgb_settable")))
                self.sub_effect_widget.setVisible(bool(spec.get("effect_types")))

                if spec.get("effect_types"):
                    active_sub = grp.get("R", 1)
                    self.btn_sub_1.setProperty("class", "RgbBtnActive" if active_sub == 1 else "PresetBtn")
                    self.btn_sub_2.setProperty("class", "RgbBtnActive" if active_sub == 2 else "PresetBtn")
                    self.btn_sub_1.setStyleSheet("")
                    self.btn_sub_2.setStyleSheet("")

                # Brightness slider state
                b_settable = bool(spec.get("brightness_settable"))
                self.brightness_widget.setVisible(b_settable)
                if b_settable:
                    b_step = max(1, min(10, int(round(grp.get("brightness", 100) / 10.0))))
                    self.bright_slider.setValue(b_step)
                    self.lbl_bright.setText(f"💡 亮度 ({b_step}):")

                # Speed slider state
                s_settable = bool(spec.get("rate_settable"))
                self.speed_widget.setVisible(s_settable)
                if s_settable:
                    s_step = max(1, min(10, int(grp.get("speed", 8))))
                    self.speed_slider.setValue(s_step)
                    self.lbl_speed.setText(f"⚡ 速度 ({s_step}):")

                self.adjustSize()
        finally:
            self._updating_ui = False

    def _set_volume(self, val: int):
        self.volume_requested.emit(val)

    def _on_slider_changed(self, val: int):
        if not self._updating_ui:
            self.volume_requested.emit(val)

    def _on_mute_clicked(self):
        if self.r20.current_volume > 0:
            self.volume_requested.emit(0)
        else:
            restore_val = self.r20.previous_unmuted_volume if self.r20.previous_unmuted_volume > 0 else 8
            self.volume_requested.emit(restore_val)

    def _on_sound_mode_clicked(self, eq_idx: int):
        if not self._updating_ui:
            self.sound_mode_requested.emit(eq_idx)

    def _on_rgb_mode_clicked(self, mode: int):
        if not self._updating_ui:
            self.light_mode_requested.emit(mode)

    def _on_swatch_clicked(self, rgb_tuple):
        if not self._updating_ui:
            r, g, b = rgb_tuple
            self.color_requested.emit(r, g, b)

    def _on_custom_color_clicked(self):
        grp = self.r20.get_active_light_group()
        initial = QColor(grp.get("R", 11), grp.get("G", 255), grp.get("B", 146))
        self._color_dialog_open = True
        try:
            color = QColorDialog.getColor(initial, self, "選擇 RGB 燈效顏色")
        finally:
            self._color_dialog_open = False
        if color.isValid():
            r, g, b = color.red(), color.green(), color.blue()
            if (r, g, b) == (0, 0, 0):
                r, g, b = 16, 16, 16
            self.color_requested.emit(r, g, b)
        self.raise_()
        self.activateWindow()

    def _on_brightness_changed(self, val: int):
        self.lbl_bright.setText(f"💡 亮度 ({val}):")
        if not self._updating_ui:
            self.brightness_requested.emit(val * 10)

    def _on_speed_changed(self, val: int):
        self.lbl_speed.setText(f"⚡ 速度 ({val}):")
        if not self._updating_ui:
            self.speed_requested.emit(val)

    def _on_sync_toggled(self, checked: bool):
        self.chk_keep_win_100.setEnabled(checked)
        if not self._updating_ui:
            self.config.set("sync_windows_volume", checked)
            self.sync_toggled.emit(checked)

    def _on_keep_win_100_toggled(self, checked: bool):
        if not self._updating_ui:
            self.config.set("keep_windows_volume_100", checked)
            self.keep_win_100_toggled.emit(checked)

    def _on_autostart_toggled(self, checked: bool):
        if not self._updating_ui:
            self.config.set_autostart(checked)
            self.autostart_toggled.emit(checked)

    def wheelEvent(self, event):
        """Allows mouse wheel anywhere on the popup to change volume."""
        delta = event.angleDelta().y()
        if delta > 0:
            new_vol = min(16, self.r20.current_volume + 1)
        elif delta < 0:
            new_vol = max(0, self.r20.current_volume - 1)
        else:
            return
        self.volume_requested.emit(new_vol)
        event.accept()

    def show_near_tray(self):
        """Positions the popup neatly above the system tray area."""
        self.update_state(
            vol=self.r20.current_volume,
            mode=self.r20.current_light_mode,
            is_connected=self.r20.is_connected,
            sound_mode=self.r20.current_sound_mode,
        )
        self.adjustSize()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = screen.right() - self.width() - 16
        y = max(screen.top() + 8, screen.bottom() - self.height() - 16)
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def changeEvent(self, event):
        # Automatically close when clicking outside / losing active focus
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow() and not self._color_dialog_open:
                self.hide()
        super().changeEvent(event)


class R20VolumeOSD(QWidget):
    """
    Floating On-Screen Display (OSD) volume bar for Edifier R20 hardware volume.
    Appears at the bottom-center of the screen when adjusting volume via keyboard or hardware buttons.
    """

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(1800)
        self._hide_timer.timeout.connect(self.hide)

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        self.card = QFrame(self)
        self.card.setObjectName("OsdCard")
        self.card.setStyleSheet("""
            QFrame#OsdCard {
                background-color: rgba(24, 24, 32, 242);
                border: 1.5px solid #3b82f6;
                border-radius: 14px;
            }
            QLabel {
                font-family: "Segoe UI", "Microsoft JhengHei UI", sans-serif;
            }
            QProgressBar {
                border: none;
                background-color: #2d2d3a;
                border-radius: 5px;
                height: 10px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #38bdf8);
                border-radius: 5px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 190))
        shadow.setOffset(0, 4)
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.lbl_icon_title = QLabel("🔊 Edifier R20 硬體音量", self.card)
        self.lbl_icon_title.setStyleSheet("font-size: 13px; font-weight: 600; color: #e2e8f0;")

        self.lbl_val = QLabel("44% (7/16)", self.card)
        self.lbl_val.setStyleSheet("font-size: 15px; font-weight: bold; color: #60a5fa;")

        top_row.addWidget(self.lbl_icon_title)
        top_row.addStretch()
        top_row.addWidget(self.lbl_val)
        card_layout.addLayout(top_row)

        self.bar = QProgressBar(self.card)
        self.bar.setRange(0, 16)
        self.bar.setValue(7)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        card_layout.addWidget(self.bar)

        root.addWidget(self.card)
        self.setFixedWidth(300)
        self.adjustSize()

    def show_volume(self, vol: int):
        vol = max(0, min(16, int(vol)))
        percent = int(round((vol / 16.0) * 100))
        self.bar.setValue(vol)

        if vol == 0:
            self.lbl_icon_title.setText("🔇 Edifier R20 硬體音量")
            self.lbl_val.setText("靜音 (0/16)")
            self.lbl_val.setStyleSheet("font-size: 15px; font-weight: bold; color: #f87171;")
        else:
            self.lbl_icon_title.setText("🔊 Edifier R20 硬體音量")
            self.lbl_val.setText(f"{percent}% ({vol}/16)")
            self.lbl_val.setStyleSheet("font-size: 15px; font-weight: bold; color: #60a5fa;")

        self.adjustSize()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        # Position at bottom-center, right above the native Windows 11 volume OSD pill
        x = screen.left() + (screen.width() - self.width()) // 2
        y = screen.bottom() - self.height() - 96
        self.move(x, y)

        if not self.isVisible():
            self.show()
        self.raise_()
        self._hide_timer.start()
