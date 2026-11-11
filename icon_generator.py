"""
Dynamic tray icon generator for the Edifier R20.

Draws the speaker with volume wave indicators and an RGB badge that can either
show the per-mode accent colour or the *actual* live light colour (including the
sound-reactive rainbow animation).
"""

from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QIcon, QPainterPath
from PyQt6.QtCore import Qt, QRectF

# Accent colour per lighting mode (used when no live RGB colour is supplied).
RGB_MODE_COLORS = {
    1: QColor(0, 200, 255),    # Ambilight: Cyan
    2: QColor(160, 80, 255),   # Siren Song: Purple
    3: QColor(255, 220, 60),   # Transient Glow: Warm Yellow
    4: QColor(255, 100, 180),  # Athenian Pure: Pink
    5: QColor(80, 255, 140),   # Rippling Wave: Emerald Green
    6: QColor(255, 130, 40),   # Titan Breath: Orange
    7: QColor(100, 100, 110),  # Off: Dark Gray
}


def render_icon_pixmap(
    size: int = 64,
    volume: int = 12,
    is_connected: bool = True,
    light_mode: int = 2,
    rgb_color=None,
    with_background: bool = False,
) -> QPixmap:
    """Renders the tray icon at the requested pixel size.

    ``with_background`` adds a dark rounded card behind the speaker; used for the
    application/installer icon so it stays visible on light desktop wallpapers.
    """
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    if with_background:
        radius = size * 0.22
        painter.setPen(QPen(QColor(58, 58, 72), max(1.0, size * 0.02)))
        painter.setBrush(QBrush(QColor(30, 30, 38)))
        painter.drawRoundedRect(QRectF(0.5, 0.5, size - 1.0, size - 1.0), radius, radius)
        scale = 0.78
        painter.translate(size * (1 - scale) / 2.0, size * (1 - scale) / 2.0)
        painter.scale(scale, scale)

    base_color = QColor(240, 240, 245) if is_connected else QColor(120, 120, 130)
    s = size / 64.0

    # Speaker body
    speaker_path = QPainterPath()
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
        # Red X for "speaker not found"
        pen = QPen(QColor(235, 60, 60), 4.5 * s)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(int(36 * s), int(22 * s), int(56 * s), int(42 * s))
        painter.drawLine(int(56 * s), int(22 * s), int(36 * s), int(42 * s))
    elif volume == 0:
        # Muted: red slash across the sound area
        pen = QPen(QColor(240, 70, 70), 4.0 * s)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(int(36 * s), int(22 * s), int(54 * s), int(42 * s))
        painter.drawLine(int(54 * s), int(22 * s), int(36 * s), int(42 * s))
    else:
        num_waves = 1 if volume <= 5 else (2 if volume <= 11 else 3)
        wave_pen = QPen(base_color, 3.2 * s)
        wave_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(wave_pen)
        if num_waves >= 1:
            painter.drawArc(QRectF(26 * s, 24 * s, 16 * s, 16 * s), -50 * 16, 100 * 16)
        if num_waves >= 2:
            painter.drawArc(QRectF(24 * s, 17 * s, 28 * s, 30 * s), -50 * 16, 100 * 16)
        if num_waves >= 3:
            painter.drawArc(QRectF(22 * s, 10 * s, 40 * s, 44 * s), -50 * 16, 100 * 16)

    # RGB badge at the bottom right: live colour when known.
    if is_connected:
        if rgb_color is not None:
            try:
                r, g, b = (max(0, min(255, int(v))) for v in tuple(rgb_color)[:3])
                badge_color = QColor(r, g, b)
            except (TypeError, ValueError):
                badge_color = RGB_MODE_COLORS.get(light_mode, QColor(0, 200, 255))
        else:
            badge_color = RGB_MODE_COLORS.get(light_mode, QColor(0, 200, 255))
        painter.setPen(QPen(QColor(20, 20, 25), 1.5 * s))
        painter.setBrush(QBrush(badge_color))
        painter.drawEllipse(QRectF(44 * s, 44 * s, 14 * s, 14 * s))

    painter.end()
    return pix


def create_tray_icon(
    volume: int,
    is_connected: bool = True,
    light_mode: int = 2,
    size: int = 64,
    rgb_color=None,
) -> QIcon:
    """Builds a QIcon for the system tray."""
    return QIcon(render_icon_pixmap(size, volume, is_connected, light_mode, rgb_color))
