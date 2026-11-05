"""
core/oil_temp.py
----------------
Oil temperature from an aftermarket NTC sender, read by an ADS1115 ADC on
the Pi's I²C bus. The 2004 RX-8 has no factory oil temperature sensor, so
this value cannot come from OBD (see RX8_OIL_TEMP_PLAN.md).

Circuit (per ADS1115 channel, see the plan for the full drawing):

    3V3 ── R_fixed ──┬── (sender wire) ── NTC sender ── engine ground
                     │
                     └── 1 kΩ ──┬── ADS1115 A0
                                └── 100 nF ── GND        (RC filter)
    3V3 ─────────────────────────── ADS1115 A3          (supply reference)

The ADC measures the divider voltage and the 3V3 supply, so the reading is
ratiometric (supply drift cancels out). Resistance → temperature uses the
beta model, calibrated from two measured points (see tools/oil_temp_cal.py).

Runs in a daemon thread (I²C reads never block the UI) and emits the same
signals as a DataSource, so DataManager can lay OIL_TEMP over whatever the
main source (OBD, replay, ...) delivers.

Config (state.config["oil_temp"]):
    source        "off" | "ads1115" | "simulated"
    i2c_bus       1 (Pi default)          i2c_address  0x48
    channel       0..3 (sender)           ref_channel  3 (3V3), or null = assume 3.3 V
    r_fixed       ohms of the top resistor
    r0, t0, beta  calibration (ohms at t0 °C, beta in K); null = not calibrated
    smooth_s      averaging window in seconds (default 3)
"""

import logging
import math
import random
import threading
import time
from collections import deque

from PyQt5.QtCore import QObject, pyqtSignal

from core.diagnostics import timed, record_error

log = logging.getLogger("rx8.oiltemp")

KEY = "OIL_TEMP"
POLL_S = 0.5
VALID_C = (-40.0, 180.0)          # outside this: wiring fault, show N/A

# ADS1115 registers and config bits
REG_CONVERSION = 0x00
REG_CONFIG = 0x01
MUX_SINGLE = {0: 0x4000, 1: 0x5000, 2: 0x6000, 3: 0x7000}
PGA_4V096 = 0x0200                 # ±4.096 V full scale (fits 3.3 V signals)
MODE_SINGLE = 0x0100
DR_128SPS = 0x0080
COMP_OFF = 0x0003
OS_START = 0x8000
FULL_SCALE_V = 4.096


# ──────────────────────────────────────────────────────────────────
#  Maths (pure functions, unit-testable)
# ──────────────────────────────────────────────────────────────────
def ntc_resistance(v_node, v_supply, r_fixed):
    """Divider with r_fixed on top, NTC to ground: R = Rf·V/(Vs−V)."""
    if v_node is None or v_supply is None or v_node <= 0 or v_node >= v_supply:
        return None                 # open (≈Vs) or short (≈0): wiring fault
    return r_fixed * v_node / (v_supply - v_node)


def beta_temperature(r, r0, t0_c, beta):
    """Beta model: 1/T = 1/T0 + ln(R/R0)/B  (T in kelvin)."""
    if r is None or r <= 0:
        return None
    inv_t = 1.0 / (t0_c + 273.15) + math.log(r / r0) / beta
    return 1.0 / inv_t - 273.15


def beta_from_points(t1_c, r1, t2_c, r2):
    """Calibration: beta from two measured (°C, ohm) points."""
    k1, k2 = t1_c + 273.15, t2_c + 273.15
    return math.log(r1 / r2) / (1.0 / k1 - 1.0 / k2)


# ──────────────────────────────────────────────────────────────────
#  ADS1115 over I²C (smbus2, Linux only)
# ──────────────────────────────────────────────────────────────────
class ADS1115:
    def __init__(self, bus=1, address=0x48, smbus=None):
        if smbus is None:
            from smbus2 import SMBus           # pip install smbus2 (Pi only)
            smbus = SMBus(bus)
        self.bus = smbus
        self.address = address

    def read_volts(self, channel):
        cfg = OS_START | MUX_SINGLE[channel] | PGA_4V096 | MODE_SINGLE | DR_128SPS | COMP_OFF
        self.bus.write_i2c_block_data(self.address, REG_CONFIG, [(cfg >> 8) & 0xFF, cfg & 0xFF])
        time.sleep(0.009)                      # one conversion at 128 SPS ≈ 7.8 ms
        hi, lo = self.bus.read_i2c_block_data(self.address, REG_CONVERSION, 2)
        raw = (hi << 8) | lo
        if raw & 0x8000:
            raw -= 1 << 16
        return raw * FULL_SCALE_V / 32768.0

    def close(self):
        try:
            self.bus.close()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────
#  Source
# ──────────────────────────────────────────────────────────────────
class OilTempSource(QObject):
    """Emits values_updated({"OIL_TEMP": °C or None}) and status_changed."""
    values_updated = pyqtSignal(dict)
    status_changed = pyqtSignal(str, str)

    def __init__(self, cfg, adc=None, parent=None):
        super().__init__(parent)
        self.cfg = dict(cfg)
        self.mode = self.cfg.get("source", "off")
        self.status = "idle"
        self.detail = ""
        self._adc = adc                        # injectable for tests
        self._stop = threading.Event()
        self._thread = None
        window = max(1, int(round(float(self.cfg.get("smooth_s", 3)) / POLL_S)))
        self._window = deque(maxlen=window)

    # lifecycle
    def start(self):
        if self.mode == "off" or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="oil-temp", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _set_status(self, status, detail=""):
        if (status, detail) != (self.status, self.detail):
            self.status, self.detail = status, detail
            log.info("oil temp: %s %s", status, detail)
            self.status_changed.emit(status, detail)

    def calibrated(self):
        return all(self.cfg.get(k) not in (None, "") for k in ("r0", "t0", "beta", "r_fixed"))

    # worker
    def _run(self):
        if self.mode == "simulated":
            self._run_simulated()
            return
        if not self.calibrated():
            self._set_status("error", "not calibrated (set r_fixed, r0, t0, beta)")
            self.values_updated.emit({KEY: None})
            return
        try:
            if self._adc is None:
                self._adc = ADS1115(int(self.cfg.get("i2c_bus", 1)),
                                    int(str(self.cfg.get("i2c_address", "0x48")), 0))
        except Exception as e:
            record_error("oil_temp.open_adc", e, level=logging.WARNING)
            self._set_status("error", f"ADS1115 not available ({type(e).__name__})")
            self.values_updated.emit({KEY: None})
            return

        ch = int(self.cfg.get("channel", 0))
        ref = self.cfg.get("ref_channel", 3)
        r_fixed = float(self.cfg["r_fixed"])
        r0, t0, beta = float(self.cfg["r0"]), float(self.cfg["t0"]), float(self.cfg["beta"])
        failures = 0
        while not self._stop.is_set():
            try:
                with timed("oil_temp.read", slow_ms=None):
                    v = self._adc.read_volts(ch)
                    vs = self._adc.read_volts(int(ref)) if ref is not None else 3.3
                failures = 0
            except Exception as e:
                failures += 1
                if failures == 1:
                    record_error("oil_temp.read", e, level=logging.WARNING)
                self._set_status("error", "I²C read failed")
                self.values_updated.emit({KEY: None})
                self._stop.wait(2.0)
                continue

            r = ntc_resistance(v, vs, r_fixed)
            t = beta_temperature(r, r0, t0, beta)
            if t is None or not (VALID_C[0] <= t <= VALID_C[1]):
                self._window.clear()
                why = "sender open circuit" if r is None and v >= vs * 0.98 else \
                      "sender short / no signal" if r is None else f"implausible {t:.0f} °C"
                self._set_status("error", why)
                self.values_updated.emit({KEY: None})
            else:
                self._window.append(t)
                self._set_status("running", f"{v:.3f} V · {r:.0f} Ω")
                self.values_updated.emit({KEY: sum(self._window) / len(self._window)})
            self._stop.wait(POLL_S)

        if self._adc is not None:
            self._adc.close()

    def _run_simulated(self):
        """Warm-up curve: oil lags coolant, settles ~100 °C with drift."""
        self._set_status("running", "simulated")
        t, start = 25.0, time.monotonic()
        while not self._stop.is_set():
            minutes = (time.monotonic() - start) / 60.0
            target = 100 + 6 * math.sin(minutes / 3.0)
            t += (target - t) * 0.02 + random.uniform(-0.15, 0.15)
            self.values_updated.emit({KEY: t})
            self._stop.wait(POLL_S)
