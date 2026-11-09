"""
Edifier R20 Controller
Reverse-engineered HID Protocol Implementation for Edifier R20 USB Speaker.
VID: 0x2D99, PID: 0xA121
Interface: MI_04, Col02 (UsagePage: 0xFF14)
"""

import time
import threading
import hid

VID = 0x2D99
PID = 0xA121

# Commands
CMD_VOLUME_QUERY = 0x66
CMD_VOLUME_SET   = 0x67
CMD_LIGHT_QUERY  = 0x6A
CMD_LIGHT_SET    = 0x6B
CMD_LIGHT_RESET  = 0x72
CMD_EQ_SET       = 0xC4
CMD_EQ_QUERY     = 0xD5

# Lighting Array Index for R20 (EffectArrayType.EA_16)
LIGHT_ARRAY_INDEX = 0x16

# 4 Sound Modes (EqType.EQ_0C) on R20
SOUND_MODES = [
    {"index": 0, "name": "音樂", "en_name": "Music", "icon": "🎵"},
    {"index": 1, "name": "遊戲", "en_name": "Game", "icon": "🎮"},
    {"index": 2, "name": "電影", "en_name": "Movie", "icon": "🎬"},
    {"index": 3, "name": "DIY",  "en_name": "DIY",   "icon": "🎚️"},
]

# 7 RGB Effects on R20 (EffectArrayType.EA_16)
RGB_MODES = [
    {
        "index": 1,
        "name": "流光溢彩",
        "en_name": "Ambilight",
        "icon": "🌈",
        "rgb_settable": False,
        "effect_types": [1, 2],
        "brightness_settable": True,
        "rate_settable": True,
        "default_group": {"R": 2, "G": 0, "B": 0, "brightness": 100, "speed": 10},
    },
    {
        "index": 2,
        "name": "海妖之聲",
        "en_name": "Siren Song",
        "icon": "🌊",
        "rgb_settable": True,
        "effect_types": [],
        "brightness_settable": False,
        "rate_settable": False,
        "default_group": {"R": 11, "G": 255, "B": 146, "brightness": 255, "speed": 255},
    },
    {
        "index": 3,
        "name": "浮光掠影",
        "en_name": "Transient Glow",
        "icon": "⚡",
        "rgb_settable": False,
        "effect_types": [1, 2],
        "brightness_settable": False,
        "rate_settable": True,
        "default_group": {"R": 1, "G": 0, "B": 0, "brightness": 255, "speed": 8},
    },
    {
        "index": 4,
        "name": "雅典純光",
        "en_name": "Athenian Pure",
        "icon": "💡",
        "rgb_settable": True,
        "effect_types": [],
        "brightness_settable": True,
        "rate_settable": False,
        "default_group": {"R": 255, "G": 157, "B": 28, "brightness": 100, "speed": 255},
    },
    {
        "index": 5,
        "name": "浪光搖曳",
        "en_name": "Rippling Wave",
        "icon": "✨",
        "rgb_settable": True,
        "effect_types": [],
        "brightness_settable": False,
        "rate_settable": False,
        "default_group": {"R": 59, "G": 0, "B": 195, "brightness": 255, "speed": 255},
    },
    {
        "index": 6,
        "name": "巨人氣息",
        "en_name": "Titan Breath",
        "icon": "🌬️",
        "rgb_settable": True,
        "effect_types": [],
        "brightness_settable": False,
        "rate_settable": True,
        "default_group": {"R": 29, "G": 147, "B": 0, "brightness": 255, "speed": 8},
    },
    {
        "index": 7,
        "name": "關閉燈效",
        "en_name": "Turn Off LED",
        "icon": "🌑",
        "rgb_settable": False,
        "effect_types": [],
        "brightness_settable": False,
        "rate_settable": False,
        "is_switch": True,
        "default_group": {"R": 0, "G": 0, "B": 1, "brightness": 255, "speed": 255},
    },
]

RGB_MODE_MAP = {m["index"]: m for m in RGB_MODES}
SOUND_MODE_MAP = {m["index"]: m for m in SOUND_MODES}

def build_packet(cmd, payload=None):
    if payload is None:
        payload = []
    # Frame format: COMMON(0x2E) + HEADER(0xAA) + DEVICE_TYPE(0xEC) + CMD + LEN_HI + LEN_LO + PAYLOAD + CRC
    hdr = [0x2E, 0xAA, 0xEC, cmd, (len(payload) >> 8) & 0xFF, len(payload) & 0xFF]
    buf = hdr + list(payload)
    crc = sum(buf[1:]) & 0xFF
    buf.append(crc)
    # Pad to 64 bytes
    return buf + [0] * (64 - len(buf))

class EdifierR20:
    def __init__(self):
        self._dev = None
        self._lock = threading.Lock()
        self.max_volume = 16
        self.current_volume = 8
        self.previous_unmuted_volume = 8
        self.current_light_mode = 2
        self.last_active_light_mode = 2
        self.light_switch_enabled = True
        self.current_brightness = 100
        self.current_speed = 8
        self.current_sound_mode = 0
        self.light_groups = {
            m["index"]: dict(m["default_group"]) for m in RGB_MODES
        }
        self.is_connected = False
        self._listeners = []

    def add_listener(self, callback):
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self, event, *args):
        for cb in list(self._listeners):
            try:
                cb(event, *args)
            except Exception as e:
                print(f"Listener error ({event}): {e}")

    def connect(self):
        with self._lock:
            if self._dev is not None:
                try:
                    self._dev.close()
                except Exception:
                    pass
                self._dev = None
                self.is_connected = False

            devices = hid.enumerate(VID, PID)
            target_path = None
            for d in devices:
                # Target the vendor interface Col02 (UsagePage: 0xFF14)
                if b'Col02' in d['path'] or (d.get('usage_page') == 0xFF14):
                    target_path = d['path']
                    break

            if not target_path and devices:
                for d in devices:
                    if b'MI_03' not in d['path']:
                        target_path = d['path']
                        break

            if not target_path:
                self.is_connected = False
                self._notify("connection", False)
                return False

            try:
                dev = hid.device()
                dev.open_path(target_path)
                dev.set_nonblocking(0)
                self._dev = dev
                self.is_connected = True
            except Exception as e:
                self._dev = None
                self.is_connected = False
                self._notify("connection", False)
                return False

        # Query initial state
        self.query_volume()
        self.query_light()
        self.query_sound_mode()
        self._notify("connection", True)
        return True

    def close(self):
        with self._lock:
            if self._dev:
                try:
                    self._dev.close()
                except Exception:
                    pass
                self._dev = None
            self.is_connected = False
            self._notify("connection", False)

    def ensure_connected(self):
        if not self.is_connected or self._dev is None:
            return self.connect()
        return True

    def _parse_frame(self, resp):
        if not resp or len(resp) < 6:
            return None
        if resp[0] not in (0x2E, 0x2F) or resp[1] not in (0xAA, 0xBB):
            return None
        resp_cmd = resp[3]
        resp_len = (resp[4] << 8) | resp[5]
        payload_resp = list(resp[6:6 + resp_len])
        return {
            "cmd": resp_cmd,
            "length": resp_len,
            "payload": payload_resp,
            "raw": resp
        }

    def _handle_unsolicited_frame(self, parsed, pending_events):
        if not parsed:
            return
        cmd = parsed["cmd"]
        payload = parsed["payload"]
        if cmd == CMD_VOLUME_QUERY and len(payload) >= 2:
            self.max_volume = payload[0]
            vol = payload[1]
            old_vol = self.current_volume
            self.current_volume = vol
            if vol > 0:
                self.previous_unmuted_volume = vol
            if old_vol != vol:
                pending_events.append(("volume", (vol,)))
        elif cmd == CMD_EQ_QUERY and len(payload) >= 1:
            eq_idx = payload[0]
            if 0 <= eq_idx <= 3 and eq_idx != self.current_sound_mode:
                self.current_sound_mode = eq_idx
                pending_events.append(("sound_mode", (eq_idx,)))

    def _send_command(self, cmd, payload=None, timeout_ms=300):
        pending_events = []
        result = None
        with self._lock:
            if not self._dev:
                return None
            pkt = build_packet(cmd, payload)
            try:
                # Drain any queued unsolicited reports before writing
                for _ in range(5):
                    stale = self._dev.read(64, timeout_ms=1)
                    if not stale:
                        break
                    self._handle_unsolicited_frame(self._parse_frame(stale), pending_events)

                written = self._dev.write(pkt)
                if written <= 0:
                    self.is_connected = False
                    return None

                # Read until matching response command or timeout
                deadline = time.time() + (timeout_ms / 1000.0)
                while time.time() < deadline:
                    rem_ms = max(10, int((deadline - time.time()) * 1000))
                    resp = self._dev.read(64, timeout_ms=rem_ms)
                    if not resp:
                        break
                    parsed = self._parse_frame(resp)
                    if not parsed:
                        continue
                    if parsed["cmd"] == cmd:
                        result = parsed
                        break
                    else:
                        self._handle_unsolicited_frame(parsed, pending_events)
            except Exception:
                self.is_connected = False
                try:
                    self._dev.close()
                except Exception:
                    pass
                self._dev = None
                result = None

        for ev, args in pending_events:
            self._notify(ev, *args)
        return result

    def poll_hardware(self):
        """
        Polls the speaker for real-time hardware button volume changes.
        Returns (changed: bool, current_volume: int).
        """
        if not self.is_connected or not self._dev:
            return False, self.current_volume
        before_vol = self.current_volume
        res = self._send_command(CMD_VOLUME_QUERY, timeout_ms=80)
        if res and res["cmd"] == CMD_VOLUME_QUERY and len(res["payload"]) >= 2:
            self.max_volume = res["payload"][0]
            vol = res["payload"][1]
            self.current_volume = vol
            if vol > 0:
                self.previous_unmuted_volume = vol
            if vol != before_vol:
                self._notify("volume", vol)
                return True, vol
        return (self.current_volume != before_vol), self.current_volume

    def query_volume(self):
        res = self._send_command(CMD_VOLUME_QUERY)
        if res and res["cmd"] == CMD_VOLUME_QUERY and len(res["payload"]) >= 2:
            self.max_volume = res["payload"][0]
            vol = res["payload"][1]
            old_vol = self.current_volume
            self.current_volume = vol
            if vol > 0:
                self.previous_unmuted_volume = vol
            if old_vol != vol:
                self._notify("volume", vol)
            return self.current_volume
        return self.current_volume

    def set_volume(self, volume):
        volume = max(0, min(self.max_volume, int(volume)))
        res = self._send_command(CMD_VOLUME_SET, [volume])
        if res:
            old_vol = self.current_volume
            self.current_volume = volume
            if volume > 0:
                self.previous_unmuted_volume = volume
            if old_vol != volume:
                self._notify("volume", volume)
            return self.current_volume
        return self.current_volume

    def volume_up(self, step=1):
        return self.set_volume(self.current_volume + step)

    def volume_down(self, step=1):
        return self.set_volume(self.current_volume - step)

    def toggle_mute(self):
        if self.current_volume > 0:
            self.previous_unmuted_volume = self.current_volume
            return self.set_volume(0)
        else:
            restore_vol = self.previous_unmuted_volume if self.previous_unmuted_volume > 0 else 8
            return self.set_volume(restore_vol)

    def is_muted(self):
        return self.current_volume == 0

    def _sanitize_light_group(self, mode_index, grp):
        spec = RGB_MODE_MAP.get(mode_index)
        if not spec:
            return dict(grp)
        dflt = spec["default_group"]
        r = int(grp.get("R", dflt["R"])) & 0xFF
        g = int(grp.get("G", dflt["G"])) & 0xFF
        b = int(grp.get("B", dflt["B"])) & 0xFF
        brightness = int(grp.get("brightness", dflt["brightness"])) & 0xFF
        speed = int(grp.get("speed", dflt["speed"])) & 0xFF

        if spec.get("is_switch"):
            return {
                "R": 0,
                "G": 0,
                "B": 1 if b != 0 else 0,
                "brightness": 255,
                "speed": 255,
            }

        # Fix blacked-out RGB or invalid sub-effect index
        if spec["rgb_settable"]:
            if r == 0 and g == 0 and b == 0:
                r, g, b = dflt["R"], dflt["G"], dflt["B"]
        elif spec["effect_types"]:
            if r not in spec["effect_types"]:
                r = dflt["R"]
            g, b = 0, 0

        # Fix brightness range (10..100 for brightness_settable, 255 otherwise)
        if spec["brightness_settable"]:
            if brightness < 10 or brightness > 100:
                brightness = dflt["brightness"]
            else:
                brightness = max(10, min(100, int(round(brightness / 10.0) * 10)))
        else:
            brightness = 255

        # Fix speed range (1..10 for rate_settable, 255 otherwise)
        if spec["rate_settable"]:
            if speed < 1 or speed > 10:
                speed = dflt["speed"]
        else:
            speed = 255

        return {
            "R": r,
            "G": g,
            "B": b,
            "brightness": brightness,
            "speed": speed,
        }

    def query_light(self):
        res = self._send_command(CMD_LIGHT_QUERY)
        if res and res["cmd"] == CMD_LIGHT_QUERY and len(res["payload"]) >= 2:
            payload = res["payload"]
            hw_active_idx = payload[1]
            if 1 <= hw_active_idx <= 6:
                self.last_active_light_mode = hw_active_idx

            # Parse 7 groups of 6 bytes [mode_idx, R, G, B, brightness, speed]
            if len(payload) >= 44:
                offset = 2
                for _ in range(7):
                    chunk = payload[offset:offset + 6]
                    offset += 6
                    m_idx = chunk[0]
                    if 1 <= m_idx <= 7:
                        raw_grp = {
                            "R": chunk[1],
                            "G": chunk[2],
                            "B": chunk[3],
                            "brightness": chunk[4],
                            "speed": chunk[5],
                        }
                        self.light_groups[m_idx] = self._sanitize_light_group(m_idx, raw_grp)

            # Check if mood light switch (Mode 7) is OFF (B == 0)
            grp7 = self.light_groups.get(7, {"B": 1})
            self.light_switch_enabled = (grp7.get("B", 1) != 0)

            old_mode = self.current_light_mode
            if not self.light_switch_enabled:
                self.current_light_mode = 7
            else:
                self.current_light_mode = hw_active_idx if 1 <= hw_active_idx <= 6 else self.last_active_light_mode

            active_grp = self.get_active_light_group()
            if active_grp["brightness"] <= 100:
                self.current_brightness = active_grp["brightness"]
            if active_grp["speed"] <= 10:
                self.current_speed = active_grp["speed"]

            if old_mode != self.current_light_mode:
                self._notify("light", self.current_light_mode, self.current_brightness)
            return self.current_light_mode
        return self.current_light_mode

    def get_active_light_group(self, mode_index=None):
        if mode_index is None:
            mode_index = self.current_light_mode
        if mode_index == 7:
            mode_index = self.last_active_light_mode
        return dict(self.light_groups.get(mode_index, RGB_MODE_MAP[2]["default_group"]))

    def set_light_mode(self, mode_index, brightness=None, speed=None, r=None, g=None, b=None):
        mode_index = max(1, min(7, int(mode_index)))

        # Mode 7 is the mood light switch OFF command: [0x16, 7, 0, 0, 0, 255, 255]
        if mode_index == 7:
            payload = [LIGHT_ARRAY_INDEX, 7, 0, 0, 0, 255, 255]
            res = self._send_command(CMD_LIGHT_SET, payload)
            if res:
                self.light_switch_enabled = False
                self.light_groups[7]["B"] = 0
                self.current_light_mode = 7
                self._notify("light", 7, self.current_brightness)
                return True
            return False

        # Switching to Mode 1..6: if switch was OFF, turn switch ON first ([0x16, 7, 0, 0, 1, 255, 255])
        if not self.light_switch_enabled or self.current_light_mode == 7:
            self._send_command(CMD_LIGHT_SET, [LIGHT_ARRAY_INDEX, 7, 0, 0, 1, 255, 255])
            self.light_switch_enabled = True
            self.light_groups[7]["B"] = 1

        spec = RGB_MODE_MAP[mode_index]
        grp = dict(self.light_groups.get(mode_index, spec["default_group"]))

        # Only apply optional overrides if valid for this mode
        if spec["rgb_settable"] and r is not None and g is not None and b is not None:
            if (r, g, b) != (0, 0, 0):
                grp["R"], grp["G"], grp["B"] = int(r) & 0xFF, int(g) & 0xFF, int(b) & 0xFF
        if spec["brightness_settable"] and brightness is not None and 10 <= int(brightness) <= 100:
            grp["brightness"] = int(brightness)
        if spec["rate_settable"] and speed is not None and 1 <= int(speed) <= 10:
            grp["speed"] = int(speed)

        grp = self._sanitize_light_group(mode_index, grp)
        self.light_groups[mode_index] = grp

        payload = [
            LIGHT_ARRAY_INDEX,
            mode_index,
            grp["R"],
            grp["G"],
            grp["B"],
            grp["brightness"],
            grp["speed"],
        ]
        res = self._send_command(CMD_LIGHT_SET, payload)
        if res:
            self.current_light_mode = mode_index
            self.last_active_light_mode = mode_index
            if grp["brightness"] <= 100:
                self.current_brightness = grp["brightness"]
            if grp["speed"] <= 10:
                self.current_speed = grp["speed"]
            self._notify("light", mode_index, self.current_brightness)
            return True
        return False

    def set_light_color(self, r: int, g: int, b: int):
        """Sets RGB color for the active mode (if rgb_settable)."""
        mode = self.current_light_mode if self.current_light_mode != 7 else self.last_active_light_mode
        spec = RGB_MODE_MAP.get(mode)
        if not spec or not spec["rgb_settable"]:
            return False
        if (r, g, b) == (0, 0, 0):
            return False
        self.light_groups[mode]["R"] = max(0, min(255, int(r)))
        self.light_groups[mode]["G"] = max(0, min(255, int(g)))
        self.light_groups[mode]["B"] = max(0, min(255, int(b)))
        return self.set_light_mode(mode)

    def set_light_sub_effect(self, sub_effect: int):
        """Sets sub-effect (1 or 2) for Modes 1 and 3."""
        mode = self.current_light_mode if self.current_light_mode != 7 else self.last_active_light_mode
        spec = RGB_MODE_MAP.get(mode)
        if not spec or not spec["effect_types"]:
            return False
        sub_effect = 1 if int(sub_effect) == 1 else 2
        self.light_groups[mode]["R"] = sub_effect
        self.light_groups[mode]["G"] = 0
        self.light_groups[mode]["B"] = 0
        return self.set_light_mode(mode)

    def set_light_brightness(self, brightness_val: int):
        """
        Sets brightness for modes that support brightness (Modes 1 & 4).
        Accepts either 1..10 step or 10..100 value.
        """
        mode = self.current_light_mode if self.current_light_mode != 7 else self.last_active_light_mode
        spec = RGB_MODE_MAP.get(mode)
        if not spec or not spec["brightness_settable"]:
            return False
        val = int(brightness_val)
        if 1 <= val <= 10:
            val = val * 10
        val = max(10, min(100, int(round(val / 10.0) * 10)))
        self.light_groups[mode]["brightness"] = val
        self.current_brightness = val
        return self.set_light_mode(mode)

    def set_light_speed(self, speed_val: int):
        """
        Sets animation speed (1..10) for modes that support speed (Modes 1, 3, 6).
        """
        mode = self.current_light_mode if self.current_light_mode != 7 else self.last_active_light_mode
        spec = RGB_MODE_MAP.get(mode)
        if not spec or not spec["rate_settable"]:
            return False
        val = max(1, min(10, int(speed_val)))
        self.light_groups[mode]["speed"] = val
        self.current_speed = val
        return self.set_light_mode(mode)

    def reset_lights_to_default(self):
        """Sends CMD_LIGHT_RESET (0x72) to restore factory default RGB parameters."""
        res = self._send_command(CMD_LIGHT_RESET)
        if res:
            self.query_light()
            return True
        return False

    def next_light_mode(self):
        next_mode = self.current_light_mode + 1
        if next_mode > 7:
            next_mode = 1
        self.set_light_mode(next_mode)
        return next_mode

    def get_mode_name(self, mode_index=None):
        if mode_index is None:
            mode_index = self.current_light_mode
        for m in RGB_MODES:
            if m["index"] == mode_index:
                return f"{m['icon']} {m['name']}"
        return f"模式 {mode_index}"

    def query_sound_mode(self):
        res = self._send_command(CMD_EQ_QUERY)
        if res and res["cmd"] == CMD_EQ_QUERY and len(res["payload"]) >= 1:
            eq_idx = res["payload"][0]
            if 0 <= eq_idx <= 3:
                old_eq = self.current_sound_mode
                self.current_sound_mode = eq_idx
                if old_eq != eq_idx:
                    self._notify("sound_mode", eq_idx)
        return self.current_sound_mode

    def set_sound_mode(self, eq_index: int):
        eq_index = max(0, min(3, int(eq_index)))
        res = self._send_command(CMD_EQ_SET, [eq_index])
        if res:
            old_eq = self.current_sound_mode
            self.current_sound_mode = eq_index
            if old_eq != eq_index:
                self._notify("sound_mode", eq_index)
            return True
        return False

    def next_sound_mode(self):
        next_eq = (self.current_sound_mode + 1) % len(SOUND_MODES)
        self.set_sound_mode(next_eq)
        return next_eq

    def get_sound_mode_name(self, eq_index=None):
        if eq_index is None:
            eq_index = self.current_sound_mode
        for m in SOUND_MODES:
            if m["index"] == eq_index:
                return f"{m['icon']} {m['name']}"
        return f"音效 {eq_index}"
