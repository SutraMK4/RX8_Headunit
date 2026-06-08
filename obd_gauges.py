#!/usr/bin/env python3
"""
RX-8 Head Unit — OBD Gauge Window (Step 1: Simulated Data)
----------------------------------------------------------
Three gauges: RPM, Coolant Temp, Oil Temp
Simulated data via QTimer — drop-in for real OBD later.
Run: python3 obd_gauges.py
"""

import sys
import math
import random
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt5.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont, QFontDatabase,
    QLinearGradient, QRadialGradient, QPainterPath, QConicalGradient
)

# ─────────────────────────────────────────────
#  Colour palette  (RX-8 red + dark cockpit)
# ─────────────────────────────────────────────
C_BG        = QColor("#0a0a0f")
C_BEZEL     = QColor("#1a1a24")
C_RING      = QColor("#2a2a38")
C_TRACK     = QColor("#1e1e2a")
C_ARC_NORM  = QColor("#c0392b")   # Mazda red
C_ARC_WARN  = QColor("#e67e22")   # orange warning
C_ARC_HOT   = QColor("#e74c3c")   # hot red
C_NEEDLE    = QColor("#ff4444")
C_NEEDLE_TIP= QColor("#ffffff")
C_TEXT_HI   = QColor("#f0f0f0")
C_TEXT_LO   = QColor("#606070")
C_TICK_MAJ  = QColor("#cccccc")
C_TICK_MIN  = QColor("#444455")
C_GLOW      = QColor(192, 57, 43, 60)


# ─────────────────────────────────────────────
#  Gauge configuration
# ─────────────────────────────────────────────
GAUGE_CONFIGS = [
    {
        "label":   "RPM",
        "unit":    "×1000",
        "min":     0,
        "max":     9000,
        "warn":    7000,       # redline start
        "danger":  8000,
        "step":    1000,
        "minor":   5,          # minor ticks per major
        "fmt":     lambda v: f"{v/1000:.1f}",
        "decimals": 0,
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
        "decimals": 0,
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
        "decimals": 0,
    },
]

# Arc sweep: 240° total, starting at 150° (bottom-left)
ARC_START_DEG = 150
ARC_SWEEP_DEG = 240


def value_to_angle(value, cfg):
    """Map a value to a painter angle (0° = 3-o'clock, CCW positive in math)."""
    ratio = (value - cfg["min"]) / (cfg["max"] - cfg["min"])
    ratio = max(0.0, min(1.0, ratio))
    # Qt arc: 0° = 3-o'clock, positive = CCW
    # We want: ARC_START_DEG from top going CW → negate and offset
    deg = ARC_START_DEG - ratio * ARC_SWEEP_DEG
    return deg


# ─────────────────────────────────────────────
#  Single gauge widget
# ─────────────────────────────────────────────
class GaugeWidget(QWidget):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._value = cfg["min"]
        self._target = cfg["min"]
        self._needle_angle = ARC_START_DEG  # degrees, Qt convention

        # Smooth needle animation
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)   # ~60 fps
        self._anim_timer.timeout.connect(self._animate_needle)
        self._anim_timer.start()

        self.setMinimumSize(240, 240)

    def set_value(self, v):
        self._target = max(self.cfg["min"], min(self.cfg["max"], v))

    def _animate_needle(self):
        target_angle = value_to_angle(self._target, self.cfg)
        diff = target_angle - self._needle_angle
        if abs(diff) > 0.3:
            self._needle_angle += diff * 0.18   # lerp factor
            self._value += (self._target - self._value) * 0.18
            self.update()

    # ── painting ──────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        size = min(w, h)
        cx, cy = w / 2, h / 2
        r = size * 0.44          # outer radius of arc
        painter.translate(cx, cy)

        self._draw_bezel(painter, r)
        self._draw_arc_track(painter, r)
        self._draw_ticks(painter, r)
        self._draw_arc_value(painter, r)
        self._draw_needle(painter, r)
        self._draw_hub(painter, r)
        self._draw_labels(painter, r)

    def _draw_bezel(self, p, r):
        # Outer dark ring
        p.setPen(Qt.NoPen)
        grad = QRadialGradient(0, 0, r * 1.1)
        grad.setColorAt(0.75, C_BEZEL)
        grad.setColorAt(1.0,  QColor("#101018"))
        p.setBrush(grad)
        p.drawEllipse(QRectF(-r * 1.12, -r * 1.12, r * 2.24, r * 2.24))

        # Inner face
        face_grad = QRadialGradient(0, -r * 0.2, r * 0.9)
        face_grad.setColorAt(0.0, QColor("#141420"))
        face_grad.setColorAt(1.0, QColor("#0a0a12"))
        p.setBrush(face_grad)
        p.drawEllipse(QRectF(-r, -r, r * 2, r * 2))

        # Subtle ring glow when near warn
        cfg = self.cfg
        if self._value >= cfg["warn"]:
            ratio = min(1.0, (self._value - cfg["warn"]) / (cfg["max"] - cfg["warn"]))
            glow_alpha = int(40 + ratio * 80)
            glow_col = QColor(C_ARC_WARN if self._value < cfg["danger"] else C_ARC_HOT)
            glow_col.setAlpha(glow_alpha)
            pen = QPen(glow_col, r * 0.06)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(-r * 1.05, -r * 1.05, r * 2.1, r * 2.1))

    def _draw_arc_track(self, p, r):
        """Grey background arc track."""
        rect = QRectF(-r * 0.88, -r * 0.88, r * 1.76, r * 1.76)
        pen = QPen(C_TRACK, r * 0.08, Qt.SolidLine, Qt.FlatCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        # Qt drawArc: angle in 1/16th degrees; start from ARC_START going CCW (negative sweep)
        p.drawArc(rect,
                  int(ARC_START_DEG * 16),
                  int(-ARC_SWEEP_DEG * 16))

    def _draw_arc_value(self, p, r):
        """Coloured arc up to current value."""
        cfg = self.cfg
        rect = QRectF(-r * 0.88, -r * 0.88, r * 1.76, r * 1.76)

        ratio = (self._value - cfg["min"]) / (cfg["max"] - cfg["min"])
        sweep = ratio * ARC_SWEEP_DEG

        # Colour by zone
        if self._value < cfg["warn"]:
            col = C_ARC_NORM
        elif self._value < cfg["danger"]:
            col = C_ARC_WARN
        else:
            col = C_ARC_HOT

        pen = QPen(col, r * 0.08, Qt.SolidLine, Qt.FlatCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(rect,
                  int(ARC_START_DEG * 16),
                  int(-sweep * 16))

    def _draw_ticks(self, p, r):
        cfg = self.cfg
        total = cfg["max"] - cfg["min"]
        step  = cfg["step"]
        minor = cfg["minor"]

        # Major ticks
        major_count = int(total / step)
        for i in range(major_count + 1):
            val = cfg["min"] + i * step
            angle_deg = value_to_angle(val, cfg)
            angle_rad = math.radians(angle_deg)

            # Outer point
            ox = math.cos(angle_rad) * r * 0.97
            oy = -math.sin(angle_rad) * r * 0.97
            # Inner point
            ix = math.cos(angle_rad) * r * 0.80
            iy = -math.sin(angle_rad) * r * 0.80

            col = C_ARC_HOT if val >= cfg["danger"] else (C_ARC_WARN if val >= cfg["warn"] else C_TICK_MAJ)
            pen = QPen(col, r * 0.018)
            p.setPen(pen)
            p.drawLine(QPointF(ox, oy), QPointF(ix, iy))

            # Tick label
            lx = math.cos(angle_rad) * r * 0.68
            ly = -math.sin(angle_rad) * r * 0.68
            font = QFont("Courier New", max(7, int(r * 0.10)))
            font.setBold(True)
            p.setFont(font)
            p.setPen(QPen(C_TEXT_LO))
            label = cfg["fmt"](val)
            fm = p.fontMetrics()
            p.drawText(QRectF(lx - 24, ly - 12, 48, 24),
                       Qt.AlignCenter, label)

        # Minor ticks
        total_minor = major_count * minor
        for i in range(total_minor + 1):
            if i % minor == 0:
                continue  # skip, already drew major
            val = cfg["min"] + i * (step / minor)
            if val > cfg["max"]:
                break
            angle_deg = value_to_angle(val, cfg)
            angle_rad = math.radians(angle_deg)

            ox = math.cos(angle_rad) * r * 0.97
            oy = -math.sin(angle_rad) * r * 0.97
            ix = math.cos(angle_rad) * r * 0.89
            iy = -math.sin(angle_rad) * r * 0.89

            p.setPen(QPen(C_TICK_MIN, r * 0.009))
            p.drawLine(QPointF(ox, oy), QPointF(ix, iy))

    def _draw_needle(self, p, r):
        angle_rad = math.radians(self._needle_angle)
        cos_a = math.cos(angle_rad)
        sin_a = -math.sin(angle_rad)

        tip_len  = r * 0.78
        tail_len = r * 0.22
        half_w   = r * 0.025

        # Needle body path
        tip   = QPointF(cos_a * tip_len,  sin_a * tip_len)
        tail  = QPointF(-cos_a * tail_len, -sin_a * tail_len)
        perp_x = -sin_a * half_w
        perp_y = -cos_a * half_w

        path = QPainterPath()
        path.moveTo(tip)
        path.lineTo(QPointF(perp_x, perp_y))
        path.lineTo(tail)
        path.lineTo(QPointF(-perp_x, -perp_y))
        path.closeSubpath()

        # Needle gradient: red body, white tip
        grad = QLinearGradient(tail, tip)
        grad.setColorAt(0.0, QColor("#550000"))
        grad.setColorAt(0.6, C_NEEDLE)
        grad.setColorAt(1.0, C_NEEDLE_TIP)

        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawPath(path)

        # Needle glow
        glow_pen = QPen(QColor(255, 80, 80, 60), r * 0.04)
        p.setPen(glow_pen)
        p.drawLine(tail, tip)

    def _draw_hub(self, p, r):
        # Centre cap
        p.setPen(Qt.NoPen)
        hub_r = r * 0.08
        hub_grad = QRadialGradient(0, 0, hub_r)
        hub_grad.setColorAt(0.0, QColor("#888888"))
        hub_grad.setColorAt(0.5, QColor("#333333"))
        hub_grad.setColorAt(1.0, QColor("#111111"))
        p.setBrush(hub_grad)
        p.drawEllipse(QRectF(-hub_r, -hub_r, hub_r * 2, hub_r * 2))

    def _draw_labels(self, p, r):
        cfg = self.cfg

        # Value readout (digital)
        val_str = cfg["fmt"](self._value)
        font = QFont("Courier New", max(11, int(r * 0.17)))
        font.setBold(True)
        p.setFont(font)
        col = C_TEXT_HI if self._value < cfg["warn"] else (C_ARC_WARN if self._value < cfg["danger"] else C_ARC_HOT)
        p.setPen(QPen(col))
        p.drawText(QRectF(-r, r * 0.28, r * 2, r * 0.28), Qt.AlignCenter, val_str)

        # Unit
        font2 = QFont("Courier New", max(7, int(r * 0.09)))
        p.setFont(font2)
        p.setPen(QPen(C_TEXT_LO))
        p.drawText(QRectF(-r, r * 0.50, r * 2, r * 0.22), Qt.AlignCenter, cfg["unit"])

        # Label (top)
        font3 = QFont("Courier New", max(7, int(r * 0.09)))
        font3.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        p.setFont(font3)
        p.setPen(QPen(C_TEXT_LO))
        p.drawText(QRectF(-r, -r * 0.55, r * 2, r * 0.20), Qt.AlignCenter, cfg["label"])


# ─────────────────────────────────────────────
#  Main window
# ─────────────────────────────────────────────
class GaugeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RX-8 Head Unit — OBD Gauges (Simulated)")
        self.setStyleSheet(f"background-color: {C_BG.name()};")
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        # Central widget + layout
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Create gauges
        self.gauges = []
        for cfg in GAUGE_CONFIGS:
            g = GaugeWidget(cfg)
            layout.addWidget(g)
            self.gauges.append(g)

        # Simulated data timer
        self._sim_rpm      = 800.0
        self._sim_coolant  = 65.0
        self._sim_oil      = 55.0
        self._sim_phase    = 0.0   # for sinusoidal RPM sweep

        self._data_timer = QTimer(self)
        self._data_timer.setInterval(80)   # 12.5 Hz data updates
        self._data_timer.timeout.connect(self._update_sim)
        self._data_timer.start()

        # Seed initial values
        self.gauges[0].set_value(self._sim_rpm)
        self.gauges[1].set_value(self._sim_coolant)
        self.gauges[2].set_value(self._sim_oil)

        self.resize(800, 300)

    def _update_sim(self):
        """Simulate a realistic engine warm-up + rev cycle."""
        self._sim_phase += 0.025

        # RPM: idle baseline + sinusoidal rev sweeps
        base_rpm = 850
        sweep = math.sin(self._sim_phase) * 3000 + math.sin(self._sim_phase * 2.3) * 1200
        self._sim_rpm = max(700, base_rpm + sweep + random.uniform(-30, 30))

        # Coolant: warms up to ~90°C operating temp over time, slight variation
        if self._sim_coolant < 88:
            self._sim_coolant += random.uniform(0.1, 0.3)
        else:
            self._sim_coolant = 88 + math.sin(self._sim_phase * 0.4) * 4 + random.uniform(-0.5, 0.5)

        # Oil: lags behind coolant, higher operating temp
        if self._sim_oil < self._sim_coolant - 5:
            self._sim_oil += random.uniform(0.05, 0.2)
        else:
            self._sim_oil = self._sim_coolant + 8 + math.sin(self._sim_phase * 0.3) * 3 + random.uniform(-0.3, 0.3)

        self.gauges[0].set_value(self._sim_rpm)
        self.gauges[1].set_value(self._sim_coolant)
        self.gauges[2].set_value(self._sim_oil)

    # ── keyboard shortcuts ──────────────────────
    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape or key == Qt.Key_Q:
            self.close()
        elif key == Qt.Key_F:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        super().keyPressEvent(event)


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("RX-8 OBD Gauges")

    win = GaugeWindow()
    win.show()
    sys.exit(app.exec_())
