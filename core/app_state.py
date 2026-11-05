"""
core/app_state.py
-----------------
Central application state shared across all screens.
All screens get a reference to this object — no globals needed.
"""

import copy
import json
import os

DEFAULT_CONFIG = {
    "data": {
        # Where gauge values come from: simulated | live | emulator | replay
        "source": "simulated",
        "emulator_port": "socket://localhost:35000",
        "replay_file": "",
        "replay_speed": 1.0,
        "replay_loop": True,
    },
    "obd": {
        # "auto" lets python-obd scan. On the Pi prefer the stable path
        # /dev/serial/by-id/usb-... ; on Windows e.g. "COM5".
        "port": "auto",
        # "auto" = python-obd detects the speed. Cheap ELM327 clones often
        # fail auto-detection ("Failed to read port"); set 38400 for those.
        "baud": "auto",
        "fast": False,      # more reliable on the RX-8
        "timeout": 30,
    },
    "display": {
        "layout": "v1",         # v1 = original UI, v2 = "Night drive" (Figma)
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
        "driver_name": "Roger",   # greeting on the v2 home screen
    },
    "oil_temp": {
        # Aftermarket NTC sender via ADS1115 (see RX8_OIL_TEMP_PLAN.md)
        "source": "off",          # off | ads1115 | simulated
        "i2c_bus": 1,
        "i2c_address": "0x48",
        "channel": 0,             # sender divider on A0
        "ref_channel": 3,         # 3V3 on A3 (ratiometric); null = assume 3.3 V
        "r_fixed": None,          # ohms, top resistor of the divider
        "r0": None,               # calibration: sender ohms at t0
        "t0": None,               # °C
        "beta": None,             # K, from tools/oil_temp_cal.py
        "smooth_s": 3,
    },
    "debug": {
        "verbose": False,     # DEBUG-level logging (also: py main.py --debug)
        "stall_ms": 250,      # UI freezes longer than this are recorded
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

        # Data pipeline — set in main.py (core.data_manager.DataManager)
        self.data = None
        # Short status for the home screen, kept up to date by DataManager:
        # simulated | live | emulator | replay | connecting | error | stopped
        self.obd_status = "stopped"

        # Current screen tracking
        self.current_screen = self.config.get("startup", {}).get("default_screen", "home")

    # ── Config persistence ─────────────────────────────────────────
    def _load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    saved = json.load(f)
                # Merge saved over defaults so new keys always exist
                merged = copy.deepcopy(DEFAULT_CONFIG)
                for section, values in saved.items():
                    if section in merged and isinstance(values, dict):
                        merged[section].update(values)
                    else:
                        merged[section] = values
                return merged
            except Exception:
                pass
        return copy.deepcopy(DEFAULT_CONFIG)

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
