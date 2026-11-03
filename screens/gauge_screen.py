"""
screens/gauge_screen.py
------------------------
Hosts the OBD gauge cluster.
Embeds the GaugeWidget components from obd_gauges.py directly.
Handles OBD connection and wires live data to gauges.

Simulated data is used when OBD is not connected.
"""

import math
import random
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout
)
from PyQt5.QtCore import Qt, QTimer
from core import theme

# ── Import gauge widgets from the standalone file ──────────────────
# obd_gauges.py lives in the project root — add it to path if needed
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from obd_gauges import GaugeWidget

# ── Gauge definitions ──────────────────────────────────────────────
# Add / remove / reorder gauges here.
# 'obd_cmd' maps to the python-obd command name (obd.commands.<name>)
# 'scale'   converts the raw value to the gauge's display unit
GAUGE_CONFIGS = [
    {
        "label":   "RPM",
        "unit":    "×1000",
        "min":     0,
        "max":     9000,
        "warn":    7000,
        "danger":  8000,
        "step":    1000,
        "minor":   5,
        "fmt":     lambda v: f"{v/1000:.1f}",
        "obd_cmd": "RPM",
        "scale":   lambda v: v.magnitude,
    },
    {
        "label":   "COOLANT",
        "unit":    "°C",
        "min":     40,
        "max":     130,
        "warn":    105,
        "danger":  118,
        "step":    10,
        "minor":   2,
        "fmt":     lambda v: f"{v:.0f}",
        "obd_cmd": "COOLANT_TEMP",
        "scale":   lambda v: v.magnitude,
    },
    {
        "label":   "OIL TEMP",
        "unit":    "°C",
        "min":     40,
        "max":     150,
        "warn":    120,
        "danger":  135,
        "step":    10,
        "minor":   2,
        "fmt":     lambda v: f"{v:.0f}",
        "obd_cmd": "OIL_TEMP",
        "scale":   lambda v: v.magnitude,
    },
    {
        "label":   "SPEED",
        "unit":    "km/h",
        "min":     0,
        "max":     260,
        "warn":    220,
        "danger":  250,
        "step":    20,
        "minor":   4,
        "fmt":     lambda v: f"{v:.0f}",
        "obd_cmd": "SPEED",
        "scale":   lambda v: v.magnitude,
    },
    {
        "label":   "THROTTLE",
        "unit":    "%",
        "min":     0,
        "max":     100,
        "warn":    95,
        "danger":  100,
        "step":    10,
        "minor":   2,
        "fmt":     lambda v: f"{v:.0f}",
        "obd_cmd": "THROTTLE_POS",
        "scale":   lambda v: v.magnitude,
    },
    {
        "label":   "ENGINE LOAD",
        "unit":    "%",
        "min":     0,
        "max":     100,
        "warn":    90,
        "danger":  100,
        "step":    10,
        "minor":   2,
        "fmt":     lambda v: f"{v:.0f}",
        "obd_cmd": "ENGINE_LOAD",
        "scale":   lambda v: v.magnitude,
    },
]


class GaugeScreen(QWidget):
    def __init__(self, state, main_window):
        super().__init__()
        self.state = state
        self.main_window = main_window
        self._sim_phase = 0.0
        self._sim_rpm = 800.0
        self._sim_coolant = 65.0
        self._sim_oil = 55.0
        self._build_ui()
        self._start_data_loop()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(8)

        # ── OBD status strip ───────────────────────────────────────
        self._status_label = QLabel("OBD: SIMULATED")
        self._status_label.setStyleSheet(f"""
            color: {theme.WARN_ORANGE};
            font-size: {theme.FONT_SIZE_SM}pt;
            letter-spacing: 2px;
        """)
        self._status_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self._status_label)

        # ── Gauge grid (3 columns) ─────────────────────────────────
        grid = QGridLayout()
        grid.setSpacing(6)
        self._gauges = []

        for i, cfg in enumerate(GAUGE_CONFIGS):
            g = GaugeWidget(cfg)
            grid.addWidget(g, i // 3, i % 3)
            self._gauges.append(g)

        layout.addLayout(grid)

    def _start_data_loop(self):
        self._data_timer = QTimer(self)
        self._data_timer.setInterval(80)
        self._data_timer.timeout.connect(self._update_data)
        self._data_timer.start()

    def _update_data(self):
        conn = self.state.obd_connection

        if conn and self.state.obd_status == "connected":
            # ── Live OBD data ──────────────────────────────────────
            self._status_label.setText("OBD: LIVE")
            self._status_label.setStyleSheet(f"color: {theme.SUCCESS_GREEN}; font-size: {theme.FONT_SIZE_SM}pt;")

            for i, cfg in enumerate(GAUGE_CONFIGS):
                try:
                    import obd
                    cmd = obd.commands[cfg["obd_cmd"]]
                    response = conn.query(cmd)
                    if not response.is_null():
                        value = cfg["scale"](response.value)
                        self._gauges[i].set_value(value)
                except Exception:
                    pass  # Gauge keeps last value on error

        else:
            # ── Simulated data ─────────────────────────────────────
            self._status_label.setText("OBD: SIMULATED")
            self._status_label.setStyleSheet(f"color: {theme.WARN_ORANGE}; font-size: {theme.FONT_SIZE_SM}pt;")
            self._run_simulation()

    def _run_simulation(self):
        self._sim_phase += 0.025

        rpm = max(700, 850
                  + math.sin(self._sim_phase) * 3000
                  + math.sin(self._sim_phase * 2.3) * 1200
                  + random.uniform(-30, 30))

        if self._sim_coolant < 88:
            self._sim_coolant += random.uniform(0.1, 0.3)
        else:
            self._sim_coolant = 88 + math.sin(self._sim_phase * 0.4) * 4

        if self._sim_oil < self._sim_coolant - 5:
            self._sim_oil += random.uniform(0.05, 0.2)
        else:
            self._sim_oil = self._sim_coolant + 8 + math.sin(self._sim_phase * 0.3) * 3

        speed   = max(0, (rpm - 800) / 9000 * 180 + random.uniform(-5, 5))
        throttle = max(0, min(100, (rpm - 800) / 8200 * 100 + random.uniform(-3, 3)))
        load    = max(0, min(100, throttle * 0.85 + random.uniform(-2, 2)))

        sim_values = [rpm, self._sim_coolant, self._sim_oil, speed, throttle, load]
        for i, val in enumerate(sim_values):
            if i < len(self._gauges):
                self._gauges[i].set_value(val)
