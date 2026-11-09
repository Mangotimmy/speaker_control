"""
Configuration and Persistence Manager for Edifier R20 Tray App.
"""

import os
import json
import winreg

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
STARTUP_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_APP_NAME = "EdifierR20Tray"

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
    "last_speed": 8
}

class ConfigManager:
    def __init__(self):
        self.config = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.config.update(data)
            except Exception as e:
                print(f"Error loading config: {e}")
        # Verify autostart status from registry
        self.config["autostart"] = self.is_autostart_enabled()
        return self.config

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save()

    def is_autostart_enabled(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY_PATH, 0, winreg.KEY_READ)
            val, _ = winreg.QueryValueEx(key, STARTUP_APP_NAME)
            winreg.CloseKey(key)
            return bool(val)
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def set_autostart(self, enable: bool):
        self.config["autostart"] = enable
        self.save()
        script_dir = os.path.dirname(os.path.abspath(__file__))
        vbs_path = os.path.join(script_dir, "start_tray.vbs")
        
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY_PATH, 0, winreg.KEY_SET_VALUE)
            if enable:
                cmd = f'wscript.exe "{vbs_path}"'
                winreg.SetValueEx(key, STARTUP_APP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, STARTUP_APP_NAME)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
            return True
        except Exception as e:
            print(f"Error updating startup registry: {e}")
            return False
