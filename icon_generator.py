"""
Dynamic Tray Icon Generator for Edifier R20.
Draws vector speaker icons with volume wave indicators and RGB status badges.
"""

from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QIcon, QPainterPath
from PyQt6.QtCore import Qt, QPointF, QRectF

RGB_MODE_COLORS = {
    1: QColor(0, 200, 255),    # Atmosphere Breathing: Cyan
    2: QColor(160, 80, 255),   # Illusory Tide: Purple
    3: QColor(255, 220, 60),   # Pure Color: Warm Yellow
    4: QColor(255, 100, 180),  # Colorful Ripples: Pink
    5: QColor(80, 255, 140),   # Light Shadows: Emerald Green
    6: QColor(255, 130, 40),   # Dynamic Shadows: Orange
    7: QColor(100, 100, 110),  # Off: Dark Gray
}

def create_tray_icon(volume: int, is_connected: bool = True, light_mode: int = 2, size: int = 64) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    base_color = QColor(240, 240, 245) if is_connected else QColor(120, 120, 130)

    # Scale factor
    s = size / 64.0

    # Draw Speaker Body
    speaker_path = QPainterPath()
    # Left box of speaker
    speaker_path.moveTo(6 * s, 22 * s)
    speaker_path.lineTo(16 * s, 22 * s)
    speaker_path.lineTo(30 * s, 10 * s)
    speaker_path.lineTo(30 * s, 54 * s)
    speaker_path.lineTo(16 * s, 42 * s)
    speaker_path.lineTo(6 * s, 42 * s)
    speaker_path.closeSubpath()

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(base_color))
    painter.drawPath(speaker_path)

    if not is_connected:
        # Draw red disconnected slash / X
        pen = QPen(QColor(235, 60, 60), 4.5 * s)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(int(36 * s), int(22 * s), int(56 * s), int(42 * s))
        painter.drawLine(int(56 * s), int(22 * s), int(36 * s), int(42 * s))
    elif volume == 0:
        # Muted: Draw red slash across sound area
        pen = QPen(QColor(240, 70, 70), 4.0 * s)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(int(36 * s), int(22 * s), int(54 * s), int(42 * s))
        painter.drawLine(int(54 * s), int(22 * s), int(36 * s), int(42 * s))
    else:
        # Waves
        num_waves = 1 if volume <= 5 else (2 if volume <= 11 else 3)
        wave_pen = QPen(base_color, 3.2 * s)
        wave_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(wave_pen)

        # Wave 1
        if num_waves >= 1:
            rect1 = QRectF(26 * s, 24 * s, 16 * s, 16 * s)
            painter.drawArc(rect1, -50 * 16, 100 * 16)

        # Wave 2
        if num_waves >= 2:
            rect2 = QRectF(24 * s, 17 * s, 28 * s, 30 * s)
            painter.drawArc(rect2, -50 * 16, 100 * 16)

        # Wave 3
        if num_waves >= 3:
            rect3 = QRectF(22 * s, 10 * s, 40 * s, 44 * s)
            painter.drawArc(rect3, -50 * 16, 100 * 16)

    # RGB Mode Indicator Pill / Dot at bottom
    if is_connected:
        badge_color = RGB_MODE_COLORS.get(light_mode, QColor(0, 200, 255))
        painter.setPen(QPen(QColor(20, 20, 25), 1.5 * s))
        painter.setBrush(QBrush(badge_color))
        painter.drawEllipse(QRectF(44 * s, 44 * s, 14 * s, 14 * s))

    painter.end()
    return QIcon(pix)
