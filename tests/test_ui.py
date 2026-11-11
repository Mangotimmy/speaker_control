"""GUI tests for the movable control panel, run with the offscreen Qt platform."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
    from PyQt6.QtGui import QKeyEvent, QMouseEvent
    from PyQt6.QtWidgets import QApplication

    HAS_QT = True
except ImportError:  # pragma: no cover - depends on the test machine
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PyQt6 is required for the UI tests")
class MovablePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from config import ConfigManager
        from r20_controller import EdifierR20
        from tray_popup import R20Popup

        self.tmpdir = tempfile.mkdtemp(prefix="edifier-ui-")
        self.config = ConfigManager(os.path.join(self.tmpdir, "config.json"))
        self.r20 = EdifierR20()
        self.r20.light_groups[2] = {
            "R": 11, "G": 255, "B": 146, "brightness": 255, "speed": 255,
        }
        self.r20.light_groups[4] = {
            "R": 255, "G": 157, "B": 28, "brightness": 100, "speed": 255,
        }
        self.popup = R20Popup(self.r20, self.config)
        self.popup.resize(372, 640)

    def tearDown(self):
        self.popup.hide()
        self.popup.deleteLater()
        self.app.processEvents()
        for name in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, name))
        os.rmdir(self.tmpdir)

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _mouse(event_type, global_pos, buttons, button=Qt.MouseButton.LeftButton):
        return QMouseEvent(
            event_type,
            QPointF(10, 10),
            QPointF(*global_pos),
            button,
            buttons,
            Qt.KeyboardModifier.NoModifier,
        )

    def _update(self, mode=2, vol=8, connected=True, rainbow=False):
        self.popup.update_state(
            vol=vol,
            mode=mode,
            is_connected=connected,
            sound_mode=0,
            sound_reactive=rainbow,
        )
        self.app.processEvents()

    # ---------------------------------------------------- current colour UX
    def test_live_colour_label_shows_hex_and_rgb(self):
        self._update(mode=2)
        text = self.popup.lbl_live_color.text()
        self.assertIn("#0BFF92", text)
        self.assertIn("RGB(11, 255, 146)", text)
        self.assertEqual(self.popup.color_chip._color.name(), "#0bff92")

    def test_rgb_mode_buttons_show_colour_dots(self):
        self._update(mode=4)
        self.assertFalse(self.popup.rgb_buttons[2].icon().isNull())
        self.assertFalse(self.popup.rgb_buttons[4].icon().isNull())
        self.assertFalse(self.popup.rgb_buttons[7].icon().isNull())
        # Modes 1 and 3 are built-in effects without a single settable colour.
        self.assertTrue(self.popup.rgb_buttons[1].icon().isNull())
        self.assertTrue(self.popup.rgb_buttons[3].icon().isNull())

    def test_active_swatch_is_ringed(self):
        self._update(mode=4)
        matched = [
            sw for sw, rgb_tuple, _hex, _tip in self.popup.swatch_buttons
            if tuple(rgb_tuple) == (255, 157, 28)
        ]
        self.assertEqual(len(matched), 1)
        self.assertIn("3px solid #ffffff", matched[0].styleSheet())
        # A matching preset means the "custom" button stays inactive.
        self.assertNotIn("#1e3a8a", self.popup.btn_custom_color.styleSheet())

    def test_custom_colour_highlights_custom_button(self):
        self.r20.light_groups[2] = {
            "R": 12, "G": 34, "B": 56, "brightness": 255, "speed": 255,
        }
        self._update(mode=2)
        self.assertIn("#1e3a8a", self.popup.btn_custom_color.styleSheet())
        self.assertIn("#0C2238", self.popup.lbl_live_color.text())

    def test_live_rainbow_update(self):
        self._update(mode=2, rainbow=True)
        self.popup.set_live_color(10, 20, 30, animated=True)
        self.app.processEvents()
        self.assertIn("#0A141E", self.popup.lbl_live_color.text())
        self.assertIn("律動", self.popup.lbl_live_color.text())
        self.assertEqual(self.popup.color_chip._color.name(), "#0a141e")

    def test_off_mode_has_no_colour(self):
        self._update(mode=7)
        self.assertIn("燈效已關閉", self.popup.lbl_live_color.text())

    # ------------------------------------------------------------ movement
    def test_drag_moves_panel_and_persists_position(self):
        self.popup.move(100, 100)
        self.app.processEvents()

        self.popup.mousePressEvent(
            self._mouse(QEvent.Type.MouseButtonPress, (110, 110), Qt.MouseButton.LeftButton)
        )
        self.popup.mouseMoveEvent(
            self._mouse(QEvent.Type.MouseMove, (260, 310), Qt.MouseButton.LeftButton,
                        button=Qt.MouseButton.NoButton)
        )
        self.popup.mouseReleaseEvent(
            self._mouse(QEvent.Type.MouseButtonRelease, (260, 310), Qt.MouseButton.NoButton)
        )
        self.app.processEvents()

        self.assertEqual(self.popup.pos(), QPoint(250, 300))
        self.assertEqual(self.config.popup_position(), (250, 300))

    def test_show_near_tray_uses_saved_position(self):
        self.config.save_popup_position(180, 240)
        self.popup.show_near_tray()
        self.app.processEvents()
        self.assertEqual(self.popup.pos(), QPoint(180, 240))

    def test_reset_position_forgets_saved_position(self):
        self.config.save_popup_position(180, 240)
        self.popup.reset_position()
        self.app.processEvents()
        self.assertIsNone(self.config.popup_position())

    # ------------------------------------------------------ close and pin
    def test_close_button_hides_panel(self):
        self.popup.show()
        self.app.processEvents()
        self.assertTrue(self.popup.isVisible())
        self.popup.btn_close.click()
        self.app.processEvents()
        self.assertFalse(self.popup.isVisible())

    def test_escape_hides_panel(self):
        self.popup.show()
        self.app.processEvents()
        event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        )
        self.popup.keyPressEvent(event)
        self.app.processEvents()
        self.assertFalse(self.popup.isVisible())

    def test_pin_state_is_persisted(self):
        self.assertFalse(self.popup.btn_pin.isChecked())
        self.popup.btn_pin.setChecked(True)
        self.app.processEvents()
        self.assertTrue(self.config.get("popup_pinned"))
        self.assertIn("已釘選", self.popup.btn_pin.toolTip())

    def test_pinned_state_is_restored_on_startup(self):
        from tray_popup import R20Popup

        self.config.set("popup_pinned", True)
        popup = R20Popup(self.r20, self.config)
        try:
            self.assertTrue(popup.btn_pin.isChecked())
        finally:
            popup.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
