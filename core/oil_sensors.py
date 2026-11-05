"""
core/oil_sensors.py
-------------------
Oil temperature and oil pressure from aftermarket senders, read by one
ADS1115 ADC on the Pi's I²C bus. The 2004 RX-8 has neither value on OBD:
no oil temperature sensor at all, and the dash "oil pressure gauge" is
driven by a pressure switch. See RX8_OIL_SENSORS_PLAN.md.

ADS1115 channels (default):
    A0  oil temperature  NTC sender in a divider from 3V3
    A1  oil pressure     ratiometric 0.5–4.5 V transducer (5 V), via 10k/20k divider
    A2  5 V reference    5 V via 10k/10k divider (pressure is ratiometric to 5 V)
    A3  3V3 reference    3V3 directly (temperature is ratiometric to 3V3)

Each reading is ratiometric to its own supply, so supply drift cancels.
Runs in a daemon thread (I²C never blocks the UI) and emits
values_updated({"OIL_TEMP": °C|None, "OIL_PRESSURE": bar|None}).

Config (state.config["oil_sensors"]):
    source       "off" | "ads1115" | "simulated"
    i2c_bus, i2c_address
    smooth_s     averaging window, seconds
    temp:     {enabled, channel, ref_channel, r_fixed, r0, t0, beta}
    pressure: {enabled, channel, ref_channel, out_divider, ref_divider,
               v_min_frac, v_max_frac, p_max_bar}
"""

import logging
import math
import random
import threading
import time
from collections import deque

from PyQt5.QtCore import QObject, pyqtSignal

from core.diagnostics import timed, record_error

log = logging.getLogger("rx8.oil")

KEY_TEMP = "OIL_TEMP"
KEY_PRESSURE = "OIL_PRESSURE"
KEYS = (KEY_TEMP, KEY_PRESSURE)
POLL_S = 0.25
VALID_TEMP_C = (-40.0, 180.0)

# ADS1115 registers and config bits
REG_CONVERSION = 0x00
REG_CONFIG = 0x01
MUX_SINGLE = {0: 0x4000, 1: 0x5000, 2: 0x6000, 3: 0x7000}
PGA_4V096 = 0x0200                 # ±4.096 V full scale; inputs stay ≤ 3.3 V
MODE_SINGLE = 0x0100
DR_128SPS = 0x0080
COMP_OFF = 0x0003
OS_START = 0x8000
FULL_SCALE_V = 4.096


# ──────────────────────────────────────────────────────────────────
#  Maths (pure functions, unit-tested)
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


def ratiometric_pressure(v_out, v_supply, v_min_frac=0.1, v_max_frac=0.9, p_max=10.0):
    """Ratiometric transducer: output = supply · (v_min_frac … v_max_frac)
    for 0 … p_max. Returns (bar, fault) — fault is None or a reason."""
    if v_out is None or not v_supply:
        return None, "no signal"
    frac = v_out / v_supply
    if frac < v_min_frac - 0.05:
        return None, "pressure sender open / unpowered"
    if frac > v_max_frac + 0.05:
        return None, "pressure sender short to supply"
    p = (frac - v_min_frac) / (v_max_frac - v_min_frac) * p_max
    return max(0.0, min(p_max, p)), None


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
DEFAULT_CONFIG = {
    "source": "off",
    "i2c_bus": 1,
    "i2c_address": "0x48",
    "smooth_s": 1.0,
    "temp": {"enabled": True, "channel": 0, "ref_channel": 3,
             "r_fixed": None, "r0": None, "t0": None, "beta": None},
    "pressure": {"enabled": True, "channel": 1, "ref_channel": 2,
                 "out_divider": 1.5,   # 10k/20k: sensor volts = ADC volts × 1.5
                 "ref_divider": 2.0,   # 10k/10k: 5 V = ADC volts × 2
                 "v_min_frac": 0.1, "v_max_frac": 0.9, "p_max_bar": 10.0},
}


def _merged_config(cfg):
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT_CONFIG.items()}
    for k, v in (cfg or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


class OilSensorSource(QObject):
    values_updated = pyqtSignal(dict)
    status_changed = pyqtSignal(str, str)

    def __init__(self, cfg, adc=None, parent=None):
        super().__init__(parent)
        self.cfg = _merged_config(cfg)
        self.mode = self.cfg.get("source", "off")
        self.status = {KEY_TEMP: ("idle", ""), KEY_PRESSURE: ("idle", "")}
        self._adc = adc
        self._stop = threading.Event()
        self._thread = None
        n = max(1, int(round(float(self.cfg.get("smooth_s", 1.0)) / POLL_S)))
        self._win = {KEY_TEMP: deque(maxlen=n), KEY_PRESSURE: deque(maxlen=n)}

    @property
    def keys(self):
        return [k for k, sec in ((KEY_TEMP, "temp"), (KEY_PRESSURE, "pressure"))
                if self.cfg[sec].get("enabled", True)]

    def start(self):
        if self.mode == "off" or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="oil-sensors", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _set_status(self, key, status, detail=""):
        if self.status.get(key) != (status, detail):
            self.status[key] = (status, detail)
            log.info("%s: %s %s", key, status, detail)
            self.status_changed.emit(f"{key}: {status}", detail)

    def _temp_calibrated(self):
        t = self.cfg["temp"]
        return all(t.get(k) not in (None, "") for k in ("r_fixed", "r0", "t0", "beta"))

    # ── worker ─────────────────────────────────────────────────────
    def _run(self):
        if self.mode == "simulated":
            self._run_simulated()
            return
        try:
            if self._adc is None:
                self._adc = ADS1115(int(self.cfg.get("i2c_bus", 1)),
                                    int(str(self.cfg.get("i2c_address", "0x48")), 0))
        except Exception as e:
            record_error("oil_sensors.open_adc", e, level=logging.WARNING)
            for k in self.keys:
                self._set_status(k, "error", f"ADS1115 not available ({type(e).__name__})")
            self.values_updated.emit({k: None for k in self.keys})
            return

        if KEY_TEMP in self.keys and not self._temp_calibrated():
            self._set_status(KEY_TEMP, "error", "not calibrated (r_fixed, r0, t0, beta)")

        failures = 0
        while not self._stop.is_set():
            try:
                with timed("oil_sensors.read", slow_ms=None):
                    values = self._read_once()
                failures = 0
            except Exception as e:
                failures += 1
                if failures == 1:
                    record_error("oil_sensors.read", e, level=logging.WARNING)
                for k in self.keys:
                    self._set_status(k, "error", "I²C read failed")
                values = {k: None for k in self.keys}
                self.values_updated.emit(values)
                self._stop.wait(2.0)
                continue
            self.values_updated.emit(values)
            self._stop.wait(POLL_S)

        if self._adc is not None:
            self._adc.close()

    def _smooth(self, key, value):
        win = self._win[key]
        if value is None:
            win.clear()
            return None
        win.append(value)
        return sum(win) / len(win)

    def _read_once(self):
        out = {}
        if KEY_TEMP in self.keys:
            out[KEY_TEMP] = self._smooth(KEY_TEMP, self._read_temp())
        if KEY_PRESSURE in self.keys:
            out[KEY_PRESSURE] = self._smooth(KEY_PRESSURE, self._read_pressure())
        return out

    def _read_temp(self):
        if not self._temp_calibrated():
            return None
        t = self.cfg["temp"]
        v = self._adc.read_volts(int(t["channel"]))
        ref = t.get("ref_channel")
        vs = self._adc.read_volts(int(ref)) if ref is not None else 3.3
        r = ntc_resistance(v, vs, float(t["r_fixed"]))
        temp = beta_temperature(r, float(t["r0"]), float(t["t0"]), float(t["beta"]))
        if temp is None or not (VALID_TEMP_C[0] <= temp <= VALID_TEMP_C[1]):
            why = ("sender open circuit" if r is None and v >= vs * 0.98 else
                   "sender short / no signal" if r is None else f"implausible {temp:.0f} °C")
            self._set_status(KEY_TEMP, "error", why)
            return None
        self._set_status(KEY_TEMP, "running", f"{v:.3f} V · {r:.0f} Ω")
        return temp

    def _read_pressure(self):
        p = self.cfg["pressure"]
        v_out = self._adc.read_volts(int(p["channel"])) * float(p["out_divider"])
        ref = p.get("ref_channel")
        v5 = self._adc.read_volts(int(ref)) * float(p["ref_divider"]) if ref is not None else 5.0
        bar, fault = ratiometric_pressure(v_out, v5, float(p["v_min_frac"]),
                                          float(p["v_max_frac"]), float(p["p_max_bar"]))
        if fault:
            self._set_status(KEY_PRESSURE, "error", fault)
            return None
        self._set_status(KEY_PRESSURE, "running", f"{v_out:.3f} V of {v5:.2f} V")
        return bar

    def _run_simulated(self):
        """Oil temp warms slowly; pressure follows a plausible rpm-like sweep."""
        for k in self.keys:
            self._set_status(k, "running", "simulated")
        temp, start = 25.0, time.monotonic()
        while not self._stop.is_set():
            s = time.monotonic() - start
            temp += ((100 + 6 * math.sin(s / 180.0)) - temp) * 0.01 + random.uniform(-0.1, 0.1)
            # cold oil = higher pressure; sweep stands in for engine speed
            rpm_like = 0.5 + 0.5 * math.sin(s / 4.0)
            pressure = 1.5 + 3.5 * rpm_like + max(0.0, (80 - temp) / 40) + random.uniform(-0.1, 0.1)
            out = {}
            if KEY_TEMP in self.keys:
                out[KEY_TEMP] = temp
            if KEY_PRESSURE in self.keys:
                out[KEY_PRESSURE] = max(0.0, pressure)
            self.values_updated.emit(out)
            self._stop.wait(POLL_S)
