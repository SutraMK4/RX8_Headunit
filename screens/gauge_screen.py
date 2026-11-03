"""
screens/gauge_screen.py
------------------------
Hosts the OBD gauge cluster.
Embeds the GaugeWidget components from obd_gauges.py directly.

The screen does not know where values come from. It listens to
state.data (core.data_manager.DataManager), which forwards whichever
source is active: simulated, live OBD, ELM327 emulator or CSV replay.
A value of None (unsupported PID, no connection) shows as N/A.
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QGridLayout
from PyQt5.QtCore import Qt
from core import theme
from core.diagnostics import timed

# ── Import gauge widgets from the standalone file ──────────────────
# obd_gauges.py lives in the project root — add it to path if needed
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from obd_gauges import GaugeWidget

# ── Gauge definitions ──────────────────────────────────────────────
# Add / remove / reorder gauges here.
# 'key' is the python-obd command name (obd.commands.<NAME>). Data sources
# deliver plain floats in python-obd's units (rpm, °C, km/h, %), so a
# gauge in other units only needs its own 'fmt'.
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
        "key":     "RPM",
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
        "key":     "COOLANT_TEMP",
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
        "key":     "OIL_TEMP",
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
        "key":     "SPEED",
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
        "key":     "THROTTLE_POS",
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
        "key":     "ENGINE_LOAD",
    },
]


# Keys the data sources should deliver for this screen
GAUGE_KEYS = tuple(cfg["key"] for cfg in GAUGE_CONFIGS)

STATUS_COLOURS = {
    "running":    theme.SUCCESS_GREEN,
    "connecting": theme.WARN_ORANGE,
    "finished":   theme.TEXT_SECONDARY,
    "error":      theme.WARN_RED,
    "idle":       theme.TEXT_DIM,
}


class GaugeScreen(QWidget):
    def __init__(self, state, main_window):
        super().__init__()
        self.state = state
        self.main_window = main_window
        self._build_ui()

        if state.data is not None:
            state.data.values_updated.connect(self.on_values)
            state.data.status_changed.connect(self.on_status)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(8)

        # ── Data source status strip ───────────────────────────────
        self._status_label = QLabel("DATA: STOPPED")
        self._status_label.setAlignment(Qt.AlignRight)
        self._set_status_style(theme.TEXT_DIM)
        layout.addWidget(self._status_label)

        # ── Gauge grid (3 columns) ─────────────────────────────────
        grid = QGridLayout()
        grid.setSpacing(6)
        self._gauges = {}

        for i, cfg in enumerate(GAUGE_CONFIGS):
            g = GaugeWidget(cfg)
            grid.addWidget(g, i // 3, i % 3)
            self._gauges[cfg["key"]] = g

        layout.addLayout(grid)

    def _set_status_style(self, colour):
        self._status_label.setStyleSheet(f"""
            color: {colour};
            font-size: {theme.FONT_SIZE_SM}pt;
            letter-spacing: 2px;
        """)

    # ── Slots ──────────────────────────────────────────────────────
    def on_values(self, values):
        with timed("ui.gauges_update", slow_ms=50):
            for key, gauge in self._gauges.items():
                gauge.set_value(values.get(key))

    def on_status(self, kind, status, detail):
        if status == "running":
            text = kind.upper()
        elif status == "idle":
            text = "STOPPED"
        else:
            text = f"{kind.upper()} {status.upper()}"
        if detail and status != "idle":
            text += f"  ·  {detail}"
        self._status_label.setText(f"DATA: {text}")
        self._set_status_style(STATUS_COLOURS.get(status, theme.TEXT_SECONDARY))
