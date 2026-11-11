"""
Configuration and persistence manager for the Edifier R20 tray controller.

Works on Windows and Linux: the file lives next to the sources during
development and in the per-user configuration directory for installed builds.
Autostart handling is delegated to :mod:`platform_utils`.
"""

from __future__ import annotations

import json
import os

import platform_utils

DEFAULT_CONFIG = {
    "sync_windows_volume": True,
    "keep_windows_volume_100": True,
    "autostart": False,
    "last_volume": 8,
    "pre_sync_volume": 8,
    "pre_sync_windows_volume": 1.0,
    "last_sound_mode": 0,
    "last_rgb_mode": 2,
    "last_brightness": 100,
    "last_speed": 8,
    "sound_reactive_rainbow": False,
    # Floating panel state (requirement: movable panel with close button)
    "popup_x": None,
    "popup_y": None,
    "popup_pinned": False,
    # Internal migration marker
    "config_schema": 2,
}


def platform_defaults() -> dict:
    """Default configuration adjusted for the current operating system."""
    values = dict(DEFAULT_CONFIG)
    if platform_utils.IS_LINUX:
        # On Linux the desktop's own volume keys drive the default sink.  Let the
        # speaker simply mirror that level instead of pinning the mixer at 100%.
        values["keep_windows_volume_100"] = False
    return values


class ConfigManager:
    """Loads, merges and persists the application settings as JSON."""

    def __init__(self, path: str | None = None):
        self.path = path or platform_utils.config_file_path()
        self.config = platform_defaults()
        self.load()

    # ------------------------------------------------------------------ io
    def load(self) -> dict:
        data = None
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError) as exc:
                print("Error loading config: %s" % exc)
        elif platform_utils.is_frozen():
            # Migrate a portable ``config.json`` shipped next to a legacy build.
            legacy = os.path.join(platform_utils.app_root(), "config.json")
            if os.path.exists(legacy):
                try:
                    with open(legacy, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                except (OSError, ValueError):
                    data = None
        if isinstance(data, dict):
            self.config.update(data)

        # Drop the legacy "pre-windows-volume" key range surprises.
        try:
            self.config["pre_sync_windows_volume"] = float(
                self.config.get("pre_sync_windows_volume", 1.0)
            )
        except (TypeError, ValueError):
            self.config["pre_sync_windows_volume"] = 1.0

        # The registry / autostart entry is the source of truth.
        self.config["autostart"] = self.is_autostart_enabled()
        # Repair entries written by older versions (the VBScript launcher is gone).
        if self.config["autostart"]:
            platform_utils.refresh_autostart()
        return self.config

    def save(self) -> bool:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            tmp_path = self.path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(self.config, fh, indent=4, ensure_ascii=False)
            os.replace(tmp_path, self.path)
            return True
        except OSError as exc:
            print("Error saving config: %s" % exc)
            return False

    # --------------------------------------------------------------- access
    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save()

    def update(self, **values):
        self.config.update(values)
        self.save()

    # ------------------------------------------------------------ autostart
    def is_autostart_enabled(self) -> bool:
        return platform_utils.is_autostart_enabled()

    def set_autostart(self, enable: bool) -> bool:
        ok = platform_utils.set_autostart(bool(enable))
        self.config["autostart"] = self.is_autostart_enabled()
        self.save()
        return ok

    # ---------------------------------------------------------- panel state
    def save_popup_position(self, x: int, y: int) -> None:
        self.config["popup_x"] = int(x)
        self.config["popup_y"] = int(y)
        self.save()

    def popup_position(self):
        x = self.config.get("popup_x")
        y = self.config.get("popup_y")
        if x is None or y is None:
            return None
        try:
            return int(x), int(y)
        except (TypeError, ValueError):
            return None

    def clear_popup_position(self) -> None:
        self.config["popup_x"] = None
        self.config["popup_y"] = None
        self.save()
