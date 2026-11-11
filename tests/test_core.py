"""Platform independent unit tests (no GUI required)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import platform_utils  # noqa: E402
from config import ConfigManager, DEFAULT_CONFIG  # noqa: E402
from r20_controller import (  # noqa: E402
    CMD_LIGHT_SET, CMD_VOLUME_SET, build_packet, select_control_interface,
)


class ProtocolTests(unittest.TestCase):
    def test_packet_layout_and_crc(self):
        packet = build_packet(CMD_VOLUME_SET, [5])
        self.assertEqual(len(packet), 64)
        self.assertEqual(packet[0], 0x2E)
        self.assertEqual(packet[1], 0xAA)
        self.assertEqual(packet[2], 0xEC)
        self.assertEqual(packet[3], CMD_VOLUME_SET)
        self.assertEqual((packet[4] << 8) | packet[5], 1)
        self.assertEqual(packet[6], 5)
        self.assertEqual(packet[7], sum(packet[1:7]) & 0xFF)
        self.assertTrue(all(b == 0 for b in packet[8:]))

    def test_light_packet_payload_length(self):
        payload = [0x16, 2, 11, 255, 146, 255, 255]
        packet = build_packet(CMD_LIGHT_SET, payload)
        self.assertEqual((packet[4] << 8) | packet[5], len(payload))
        self.assertEqual(packet[6:13], payload)
        self.assertEqual(packet[13], sum(packet[1:13]) & 0xFF)

    def test_empty_payload(self):
        packet = build_packet(0x66)
        self.assertEqual(len(packet), 64)
        self.assertEqual((packet[4] << 8) | packet[5], 0)


class InterfaceSelectionTests(unittest.TestCase):
    def test_prefers_vendor_usage_page(self):
        devices = [
            {"path": b"/dev/hidraw0", "interface_number": 0, "usage_page": 0x0001},
            {"path": b"/dev/hidraw1", "interface_number": 4, "usage_page": 0xFF14},
        ]
        self.assertEqual(select_control_interface(devices), b"/dev/hidraw1")

    def test_windows_col02_path(self):
        devices = [
            {"path": b"\\\\?\\hid#vid_2d99&pid_a121&mi_00#7&1", "interface_number": 0},
            {"path": b"\\\\?\\hid#vid_2d99&pid_a121&mi_04&col02#7&2", "interface_number": 4},
        ]
        self.assertEqual(select_control_interface(devices), devices[1]["path"])

    def test_linux_interface_number_fallback(self):
        devices = [
            {"path": b"/dev/hidraw0", "interface_number": 0},
            {"path": b"/dev/hidraw1", "interface_number": 4},
            {"path": b"/dev/hidraw2", "interface_number": 3},
        ]
        self.assertEqual(select_control_interface(devices), b"/dev/hidraw1")

    def test_empty_device_list(self):
        self.assertIsNone(select_control_interface([]))


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="edifier-config-")
        self.path = os.path.join(self.tmpdir, "config.json")

    def tearDown(self):
        for name in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, name))
        os.rmdir(self.tmpdir)

    def test_defaults_and_new_keys(self):
        manager = ConfigManager(self.path)
        for key in ("popup_x", "popup_y", "popup_pinned", "sound_reactive_rainbow"):
            self.assertIn(key, manager.config)
        self.assertIsNone(manager.popup_position())

    def test_roundtrip(self):
        manager = ConfigManager(self.path)
        manager.set("last_volume", 12)
        manager.save_popup_position(321, 654)
        manager.set("popup_pinned", True)

        reloaded = ConfigManager(self.path)
        self.assertEqual(reloaded.get("last_volume"), 12)
        self.assertEqual(reloaded.popup_position(), (321, 654))
        self.assertTrue(reloaded.get("popup_pinned"))

        reloaded.clear_popup_position()
        self.assertIsNone(ConfigManager(self.path).popup_position())

    def test_unknown_keys_preserved(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"future_option": "keep-me", "last_volume": 3}, fh)
        manager = ConfigManager(self.path)
        self.assertEqual(manager.get("future_option"), "keep-me")
        self.assertEqual(manager.get("last_volume"), 3)
        # A missing key still gets its default value.
        self.assertIn("last_rgb_mode", manager.config)

    def test_broken_file_falls_back_to_defaults(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        manager = ConfigManager(self.path)
        self.assertEqual(manager.get("last_volume"), DEFAULT_CONFIG["last_volume"])


class PlatformHelperTests(unittest.TestCase):
    def test_command_to_string_quotes_spaces(self):
        command = platform_utils.command_to_string(
            [r"C:\Program Files\Python\pythonw.exe", r"C:\x\tray_app.py"]
        )
        self.assertEqual(
            command,
            '"C:\\Program Files\\Python\\pythonw.exe" C:\\x\\tray_app.py',
        )

    def test_start_command_shape(self):
        command = platform_utils.start_command()
        self.assertGreaterEqual(len(command), 1)
        self.assertTrue(all(isinstance(part, str) for part in command))

    def test_single_instance_excludes_second_holder(self):
        lock = platform_utils.SingleInstance("edifier-test-lock")
        other = platform_utils.SingleInstance("edifier-test-lock")
        self.assertTrue(lock.acquire())
        self.assertFalse(other.acquire())
        lock.release()
        self.assertTrue(other.acquire())
        other.release()

    def test_show_request_roundtrip(self):
        platform_utils.consume_show_request()  # clear leftovers
        self.assertFalse(platform_utils.consume_show_request())
        platform_utils.request_show()
        self.assertTrue(platform_utils.consume_show_request())
        self.assertFalse(platform_utils.consume_show_request())

    def test_wording_is_platform_specific(self):
        label = platform_utils.system_volume_label()
        self.assertIn("音量", label)
        if platform_utils.IS_WINDOWS:
            self.assertIn("Windows", label)
        else:
            self.assertNotIn("Windows", label)


class LinuxVolumeSyncTests(unittest.TestCase):
    """Parsing tests for the Linux mixer backend (no audio system required)."""

    def _make(self, backend="wpctl"):
        from volume_sync import LinuxVolumeSync

        sync = LinuxVolumeSync(None, enabled=True, keep_windows_100=False)
        sync.backend = backend
        sync.commands = []
        return sync

    def test_wpctl_volume_parsing(self):
        sync = self._make()
        sync._capture = lambda args, timeout=3.0: "Volume: 0.45\n"
        self.assertAlmostEqual(sync.get_windows_volume_scalar(), 0.45)

    def test_wpctl_muted_reads_as_zero(self):
        sync = self._make()
        sync._capture = lambda args, timeout=3.0: "Volume: 0.45 [MUTED]\n"
        self.assertEqual(sync.get_windows_volume_scalar(), 0.0)
        self.assertEqual(sync._read_sink(), (0.45, True))

    def test_pactl_volume_and_mute_parsing(self):
        sync = self._make("pactl")

        def capture(args, timeout=3.0):
            if "get-sink-mute" in args:
                return "Mute: yes\n"
            return (
                "Volume: front-left: 32768 /  50% / -18.06 dB,   "
                "front-right: 32768 /  50% / -18.06 dB\n"
            )

        sync._capture = capture
        self.assertEqual(sync._read_sink(), (0.5, True))
        self.assertEqual(sync.get_windows_volume_scalar(), 0.0)

    def test_wpctl_write_commands(self):
        sync = self._make()
        calls = []

        def fake_exec(args, timeout=3.0):
            calls.append(args)
            return True

        sync._exec = fake_exec
        self.assertTrue(sync.set_windows_volume_scalar(0.5))
        self.assertIn(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "0.500"], calls)
        self.assertIn(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"], calls)

        calls.clear()
        sync.set_windows_volume_scalar(0.0)
        self.assertIn(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"], calls)

    def test_pactl_write_commands(self):
        sync = self._make("pactl")
        calls = []
        sync._exec = lambda args, timeout=3.0: calls.append(args) or True
        sync.set_windows_volume_scalar(0.25)
        self.assertIn(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "25%"], calls)
        self.assertIn(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"], calls)


@unittest.skipUnless(platform_utils.IS_WINDOWS, "Windows installer helpers")
class InstallerSafetyTests(unittest.TestCase):
    def test_install_dir_validation(self):
        sys.path.insert(0, os.path.join(ROOT, "packaging"))
        import installer_common as ic

        self.assertTrue(ic.is_safe_install_dir(r"C:\Users\me\AppData\Local\Programs\EdifierR20Tray"))
        self.assertFalse(ic.is_safe_install_dir(r"C:\Windows"))
        self.assertFalse(ic.is_safe_install_dir(r"C:\Users\me\AppData\Local\Programs\SomethingElse"))
        self.assertFalse(ic.is_safe_install_dir(r"C:\EdifierR20Tray"))

    def test_default_paths(self):
        sys.path.insert(0, os.path.join(ROOT, "packaging"))
        import installer_common as ic

        self.assertTrue(ic.default_install_dir().endswith("EdifierR20Tray"))
        self.assertTrue(ic.uninstaller_path(r"C:\x\EdifierR20Tray").endswith("Uninstall.exe"))
        self.assertTrue(ic.app_exe_path(r"C:\x\EdifierR20Tray").endswith("EdifierR20Tray.exe"))


if __name__ == "__main__":
    unittest.main()
