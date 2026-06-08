"""
core/app_state.py
-----------------
Central application state shared across all screens.
All screens get a reference to this object — no globals needed.
"""

import json
import os

DEFAULT_CONFIG = {
    "obd": {
        "port": "auto",
        "baudrate": 38400,
    },
    "display": {
        "brightness": 80,
        "timeout_seconds": 0,   # 0 = never
        "fullscreen": False,
    },
    "audio": {
        "default_volume": 50,
        "source": "aux",
    },
    "navigation": {
        "maps_path": "/home/mazda/maps",
        "gps_device": "/dev/ttyUSB0",
        "units": "metric",
    },
    "system": {
        "hostname": "rx8-headunit",
    },
    "startup": {
        "default_screen": "home",   # home | gauges | navigation | audio
        "fullscreen": False,
    },
}

CONFIG_PATH = os.path.expanduser("~/.rx8_headunit/config.json")


class AppState:
    def __init__(self):
        self.config = self._load_config()

        # OBD connection — set by OBDManager, read by gauge screen
        self.obd_connection = None
        self.obd_status = "disconnected"   # disconnected | connecting | connected | error

        # Current screen tracking
        self.current_screen = self.config.get("startup", {}).get("default_screen", "home")

    # ── Config persistence ─────────────────────────────────────────
    def _load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    saved = json.load(f)
                # Merge saved over defaults so new keys always exist
                merged = DEFAULT_CONFIG.copy()
                for section, values in saved.items():
                    if section in merged and isinstance(values, dict):
                        merged[section].update(values)
                    else:
                        merged[section] = values
                return merged
            except Exception:
                pass
        return DEFAULT_CONFIG.copy()

    def save_config(self):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(self.config, f, indent=2)

    def get(self, *keys, default=None):
        """Nested config getter: state.get('obd', 'port')"""
        val = self.config
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val

    def set(self, *keys_and_value):
        """Nested config setter: state.set('obd', 'port', '/dev/ttyUSB0')"""
        *keys, value = keys_and_value
        target = self.config
        for k in keys[:-1]:
            target = target.setdefault(k, {})
        target[keys[-1]] = value
