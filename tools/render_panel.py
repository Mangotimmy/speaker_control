"""Renders the control panel to PNG files (documentation / visual review).

Run from the repository root with the normal Qt platform:

    python tools/render_panel.py

Outputs to ``build/screens``; the README uses copies in ``docs/screenshots``.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtWidgets import QApplication  # noqa: E402

from config import ConfigManager  # noqa: E402
from r20_controller import EdifierR20  # noqa: E402
from tray_popup import R20Popup  # noqa: E402

OUT_DIR = os.path.join(ROOT, "docs", "screenshots")


def render(name, volume, mode, sound_mode, rainbow=False, live_rgb=None, connected=True):
    app = QApplication.instance() or QApplication([])
    config = ConfigManager(os.path.join(ROOT, "build", "render-config.json"))
    config.update(sound_reactive_rainbow=rainbow, popup_pinned=False)

    r20 = EdifierR20()
    r20.current_volume = volume
    r20.current_light_mode = mode
    r20.current_sound_mode = sound_mode
    r20.is_connected = connected
    if mode == 4:
        r20.light_groups[4] = {"R": 255, "G": 157, "B": 28, "brightness": 80, "speed": 255}
    if mode == 2:
        r20.light_groups[2] = {"R": 11, "G": 255, "B": 146, "brightness": 255, "speed": 255}

    popup = R20Popup(r20, config)
    popup.update_state(
        vol=volume, mode=mode, is_connected=connected,
        sound_mode=sound_mode, sound_reactive=rainbow,
    )
    if live_rgb is not None:
        popup.set_live_color(*live_rgb, animated=True)
    popup.adjustSize()
    popup.show()
    app.processEvents()
    path = os.path.join(OUT_DIR, name)
    popup.grab().save(path, "PNG")
    popup.hide()
    popup.deleteLater()
    app.processEvents()
    print("wrote", path)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    render("panel-rgb.png", 10, 4, 1)
    render("panel-rainbow.png", 12, 2, 0, rainbow=True, live_rgb=(120, 40, 200))
    render("panel-disconnected.png", 0, 2, 0, connected=False)


if __name__ == "__main__":
    main()
