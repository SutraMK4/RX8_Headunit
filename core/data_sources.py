"""
core/data_sources.py
--------------------
Where engine values come from. The gauges never talk to OBD directly:
they listen to whichever DataSource is active and draw what it sends.

Four sources, one interface:

    SimulatedSource   fake but plausible engine data (default for dev)
    LiveSource        real car via python-obd (OBDLink SX over USB)
    EmulatorSource    same code path as Live, pointed at ELM327-emulator
    ReplaySource      plays back a CSV recorded from the car

Every source emits:

    values_updated(dict)        {"RPM": 3120.0, "OIL_TEMP": None, ...}
                                 None  = this value is not available
                                         (unsupported PID, empty CSV cell,
                                          not connected). Gauges show N/A.
    status_changed(str, str)    (status, detail)
                                 status is one of the STATUS_* constants,
                                 detail is a short human-readable message.

Value keys are python-obd command names (obd.commands.<NAME>), so a new
gauge only needs a key that python-obd knows.
"""

import csv
import logging
import math
import os
import random
import threading
import time
from datetime import datetime

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from core.diagnostics import timed, record_error, adopt_obd_logger

log = logging.getLogger("rx8.data")


# Values the head unit asks for by default (python-obd command names).
DEFAULT_KEYS = (
    "RPM",
    "COOLANT_TEMP",
    "OIL_TEMP",
    "SPEED",
    "RELATIVE_THROTTLE_POS",
    "ENGINE_LOAD",
)

STATUS_IDLE = "idle"              # created, not started / stopped
STATUS_CONNECTING = "connecting"  # opening the OBD connection
STATUS_RUNNING = "running"        # values are flowing
STATUS_FINISHED = "finished"      # replay reached the end (no loop)
STATUS_ERROR = "error"            # could not connect / could not read file


# ──────────────────────────────────────────────────────────────────
#  Base class
# ──────────────────────────────────────────────────────────────────
class DataSource(QObject):
    kind = "base"

    values_updated = pyqtSignal(dict)
    status_changed = pyqtSignal(str, str)

    def __init__(self, keys=DEFAULT_KEYS, parent=None):
        super().__init__(parent)
        self.keys = tuple(keys)
        self.status = STATUS_IDLE
        self.detail = ""
        # Keys this source can actually deliver. Filled in on start.
        self.supported = set()

    def start(self):
        raise NotImplementedError

    def stop(self):
        self._set_status(STATUS_IDLE, "stopped")

    def supported_command_names(self):
        """Everything the source could deliver (used by Settings → Scan)."""
        return sorted(self.supported)

    # ── helpers ────────────────────────────────────────────────────
    def _set_status(self, status, detail=""):
        self.status = status
        self.detail = detail
        self.status_changed.emit(status, detail)

    def _emit_all_none(self):
        self.values_updated.emit({k: None for k in self.keys})


# ──────────────────────────────────────────────────────────────────
#  Simulated
# ──────────────────────────────────────────────────────────────────
class SimulatedSource(DataSource):
    """Warm-up curve plus sinusoidal rev sweeps. Same model as before."""
    kind = "simulated"
    INTERVAL_MS = 80

    def __init__(self, keys=DEFAULT_KEYS, parent=None):
        super().__init__(keys, parent)
        self._timer = QTimer(self)
        self._timer.setInterval(self.INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self._reset()

    def _reset(self):
        self._phase = 0.0
        self._coolant = 65.0
        self._oil = 55.0

    def start(self):
        self._reset()
        self.supported = {"RPM", "COOLANT_TEMP", "OIL_TEMP", "OIL_PRESSURE", "SPEED",
                          "THROTTLE_POS", "RELATIVE_THROTTLE_POS", "ENGINE_LOAD"} & set(self.keys)
        self._timer.start()
        self._set_status(STATUS_RUNNING, "simulated data")

    def stop(self):
        self._timer.stop()
        super().stop()

    def _tick(self):
        self._phase += 0.025
        ph = self._phase

        rpm = max(700.0, 850
                  + math.sin(ph) * 3000
                  + math.sin(ph * 2.3) * 1200
                  + random.uniform(-30, 30))

        if self._coolant < 88:
            self._coolant += random.uniform(0.1, 0.3)
        else:
            self._coolant = 88 + math.sin(ph * 0.4) * 4

        if self._oil < self._coolant - 5:
            self._oil += random.uniform(0.05, 0.2)
        else:
            self._oil = self._coolant + 8 + math.sin(ph * 0.3) * 3

        speed = max(0.0, (rpm - 800) / 9000 * 180 + random.uniform(-5, 5))
        throttle = max(0.0, min(100.0, (rpm - 800) / 8200 * 100 + random.uniform(-3, 3)))
        load = max(0.0, min(100.0, throttle * 0.85 + random.uniform(-2, 2)))

        # oil pressure: rises with rpm, a little higher while the oil is cold
        oil_p = max(0.0, 1.2 + rpm / 9000 * 4.5 + max(0.0, (80 - self._oil) / 40)
                    + random.uniform(-0.05, 0.05))

        sim = {
            "RPM": rpm,
            "OIL_PRESSURE": oil_p,
            "COOLANT_TEMP": self._coolant,
            "OIL_TEMP": self._oil,
            "SPEED": speed,
            "THROTTLE_POS": throttle,
            "RELATIVE_THROTTLE_POS": throttle,
            "ENGINE_LOAD": load,
        }
        self.values_updated.emit({k: sim.get(k) for k in self.keys})


# ──────────────────────────────────────────────────────────────────
#  Live OBD (python-obd)
# ──────────────────────────────────────────────────────────────────
class _ConnectWorker(QObject):
    """
    Opens the obd.Async connection off the UI thread (can take ~30 s).
    Runs in a daemon thread: if the user switches source or quits while it
    is still connecting, it is simply abandoned and never delays shutdown.
    The result comes back to the UI thread through the queued `done` signal.
    """
    done = pyqtSignal(object, str)   # (connection or None, error message)

    def __init__(self, port, baudrate, fast, timeout):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.fast = fast
        self.timeout = timeout
        self.cancelled = False
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self.run, name="obd-connect", daemon=True)
        self._thread.start()

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def cancel(self):
        """Close the connection as soon as it opens; nobody wants it now."""
        self.cancelled = True
        try:
            self.done.disconnect()
        except TypeError:
            pass

    def run(self):
        try:
            import obd
        except ImportError:
            self.done.emit(None, "python-obd not installed (pip install obd)")
            return
        adopt_obd_logger()
        log.info("OBD connect: port=%s baudrate=%s fast=%s timeout=%s",
                 self.port or "auto", self.baudrate or "auto", self.fast, self.timeout)
        try:
            with timed("obd.connect", slow_ms=None):
                conn = obd.Async(portstr=self.port, baudrate=self.baudrate,
                                 fast=self.fast, timeout=self.timeout)
        except Exception as e:
            record_error("obd.connect", e)
            self.done.emit(None, f"connect failed: {e}")
            return

        if self.cancelled:
            conn.close()
            return

        status = conn.status()
        if status == obd.OBDStatus.CAR_CONNECTED:
            self.done.emit(conn, "")
            return

        conn.close()
        if status == obd.OBDStatus.NOT_CONNECTED:
            msg = "no adapter found" if self.port is None else f"no adapter on {self.port}"
        elif status in (obd.OBDStatus.ELM_CONNECTED, obd.OBDStatus.OBD_CONNECTED):
            msg = "adapter found, but no answer from the car (ignition on?)"
        else:
            msg = str(status)
        self.done.emit(None, msg)


def _to_float(value):
    """python-obd returns pint quantities (value.magnitude) or plain numbers."""
    if value is None:
        return None
    mag = getattr(value, "magnitude", value)
    try:
        return float(mag)
    except (TypeError, ValueError):
        return None


class LiveSource(DataSource):
    """
    Real car. Uses obd.Async: each supported value is registered with
    watch() before start(), after which query() returns the latest cached
    reading without blocking the UI. (Querying an un-watched command on an
    Async connection returns an empty response; that was the old bug.)
    """
    kind = "live"
    POLL_MS = 100

    def __init__(self, keys=DEFAULT_KEYS, port=None, baudrate=None,
                 fast=False, timeout=30, parent=None):
        super().__init__(keys, parent)
        self.port = port            # None = let python-obd scan
        self.baudrate = baudrate    # None = auto-detect
        self.fast = fast            # False is more reliable on the RX-8
        self.timeout = timeout
        self._conn = None
        self._cmds = {}             # key -> obd command
        self._worker = None
        self._stopped = False
        self._all_commands = []

        self._poll = QTimer(self)
        self._poll.setInterval(self.POLL_MS)
        self._poll.timeout.connect(self._read)

    # ── lifecycle ──────────────────────────────────────────────────
    def start(self):
        self._stopped = False
        self._emit_all_none()
        where = self.port or "auto"
        self._set_status(STATUS_CONNECTING, f"connecting ({where})")
        self._worker = _ConnectWorker(self.port, self.baudrate, self.fast, self.timeout)
        self._worker.done.connect(self._on_connected)
        self._worker.start()

    def stop(self):
        self._stopped = True
        self._poll.stop()
        if self._worker is not None and self._worker.is_running():
            self._worker.cancel()
        self._worker = None
        self._close()
        self._emit_all_none()
        super().stop()


    def _close(self):
        """Close in a background thread: python-obd's stop() joins its worker
        and the port close can take ~0.5 s, which would freeze the UI."""
        conn, self._conn = self._conn, None
        if conn is None:
            return

        def close():
            try:
                with timed("obd.close", slow_ms=None):
                    conn.stop()
                    conn.close()
            except Exception as e:
                record_error("obd.close", e, level=logging.WARNING)

        threading.Thread(target=close, name="obd-close", daemon=True).start()

    # ── connection result ──────────────────────────────────────────
    def _on_connected(self, conn, error):
        if self._stopped:
            # User switched source while we were still connecting.
            if conn is not None:
                conn.close()
            return
        if conn is None:
            self._set_status(STATUS_ERROR, error)
            self._emit_all_none()
            return

        import obd
        self._conn = conn
        self._cmds = {}
        self.supported = set()
        for key in self.keys:
            if not obd.commands.has_name(key):
                continue
            cmd = obd.commands[key]
            if conn.supports(cmd):
                conn.watch(cmd)
                self._cmds[key] = cmd
                self.supported.add(key)
        self._all_commands = sorted(c.name for c in conn.supported_commands)

        with timed("obd.start_watch"):
            conn.start()
        self._poll.start()
        missing = [k for k in self.keys if k not in self.supported]
        detail = f"{conn.protocol_name()} · {len(self.supported)}/{len(self.keys)} values"
        if missing:
            detail += " · N/A: " + ", ".join(missing)
        self._set_status(STATUS_RUNNING, detail)

    def supported_command_names(self):
        return list(self._all_commands)

    # ── polling (non-blocking, reads Async cache) ──────────────────
    def _read(self):
        if self._conn is None:
            return
        import obd
        if self._conn.status() != obd.OBDStatus.CAR_CONNECTED:
            self._poll.stop()
            self._close()
            self._set_status(STATUS_ERROR, "connection lost")
            self._emit_all_none()
            return

        values = {}
        with timed("obd.read_cache"):
            for key in self.keys:
                cmd = self._cmds.get(key)
                if cmd is None:
                    values[key] = None
                    continue
                r = self._conn.query(cmd)
                values[key] = None if r.is_null() else _to_float(r.value)
        self.values_updated.emit(values)


class EmulatorSource(LiveSource):
    """
    Live code path against ELM327-emulator, no car needed.
    Start the emulator in a separate terminal (patched launcher, see
    tools/run_emulator.py for why plain `elm` breaks on Windows):
        py tools/run_emulator.py
    and use port "socket://localhost:35000" (works on Windows and Linux).
    Over a TCP socket python-obd cannot detect a baud rate, so a fixed
    one is passed; the emulator ignores it.
    """
    kind = "emulator"

    def __init__(self, keys=DEFAULT_KEYS, port="socket://localhost:35000",
                 timeout=10, parent=None):
        super().__init__(keys, port=port, baudrate=38400, fast=False,
                         timeout=timeout, parent=parent)


# ──────────────────────────────────────────────────────────────────
#  Replay (CSV)
# ──────────────────────────────────────────────────────────────────
TIME_COLUMNS = ("elapsed_s", "elapsed", "time_s", "time", "timestamp", "t")
DEFAULT_ROW_INTERVAL_S = 0.1     # used only if the CSV has no time column


def _normalise_header(name):
    """'RPM (rpm)' -> 'RPM', ' coolant_temp ' -> 'COOLANT_TEMP'."""
    name = name.strip()
    for sep in (" ", "(", "["):
        if sep in name:
            name = name.split(sep, 1)[0]
    return name.upper()


def _parse_time(text):
    text = text.strip()
    try:
        return float(text)
    except ValueError:
        return datetime.fromisoformat(text).timestamp()


def _parse_value(text):
    text = (text or "").strip()
    if text == "" or text.lower() in ("none", "nan", "n/a", "null"):
        return None
    try:
        return float(text)
    except ValueError:
        # "3120.0 revolutions_per_minute" style: take the leading number
        try:
            return float(text.split()[0])
        except (ValueError, IndexError):
            return None


def load_replay_csv(path, keys=DEFAULT_KEYS):
    """
    Returns (rows, mapped_keys) where rows = [(t_seconds, {key: value})],
    t starting at 0. Raises ValueError with a readable message on problems.

    Expected format: a header row, one time column (any of TIME_COLUMNS,
    seconds or ISO datetime) and one column per value named after the
    python-obd command (RPM, COOLANT_TEMP, ...). Unit suffixes in the
    header like "RPM (rpm)" are ignored. Empty cells mean "no reading".
    """
    if not path or not os.path.isfile(path):
        raise ValueError(f"file not found: {path or '(none set)'}")

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError("CSV is empty")

        norm = [_normalise_header(h) for h in header]
        time_idx = None
        for i, h in enumerate(header):
            if h.strip().lower() in TIME_COLUMNS:
                time_idx = i
                break

        col_for_key = {}
        for key in keys:
            if key in norm:
                col_for_key[key] = norm.index(key)
        if not col_for_key:
            raise ValueError("no known columns (expected e.g. RPM, COOLANT_TEMP)")

        rows = []
        t0 = None
        for n, raw in enumerate(reader):
            if not raw or all(not c.strip() for c in raw):
                continue
            if time_idx is not None:
                try:
                    t = _parse_time(raw[time_idx])
                except (ValueError, IndexError):
                    continue
            else:
                t = n * DEFAULT_ROW_INTERVAL_S
            if t0 is None:
                t0 = t
            vals = {}
            for key, idx in col_for_key.items():
                vals[key] = _parse_value(raw[idx]) if idx < len(raw) else None
            rows.append((t - t0, vals))

    if not rows:
        raise ValueError("CSV has a header but no data rows")
    rows.sort(key=lambda r: r[0])
    return rows, set(col_for_key)


class ReplaySource(DataSource):
    """Plays a recorded CSV back in real time (or faster / slower)."""
    kind = "replay"
    TICK_MS = 50

    def __init__(self, keys=DEFAULT_KEYS, path="", speed=1.0, loop=True, parent=None):
        super().__init__(keys, parent)
        self.path = path
        self.speed = max(0.05, float(speed or 1.0))
        self.loop = loop
        self._rows = []
        self._idx = 0
        self._t_start = 0.0
        self._current = {}
        self._timer = QTimer(self)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._tick)

    def start(self):
        try:
            with timed("replay.load_csv"):
                self._rows, self.supported = load_replay_csv(self.path, self.keys)
        except ValueError as e:
            self._set_status(STATUS_ERROR, str(e))
            self._emit_all_none()
            return
        self._rewind()
        self._timer.start()
        dur = self._rows[-1][0]
        self._set_status(STATUS_RUNNING,
                         f"{os.path.basename(self.path)} · {len(self._rows)} rows · "
                         f"{dur:.0f} s · x{self.speed:g}")

    def stop(self):
        self._timer.stop()
        self._emit_all_none()
        super().stop()

    def _rewind(self):
        self._idx = 0
        self._t_start = time.monotonic()
        self._current = {k: None for k in self.keys}

    def _tick(self):
        elapsed = (time.monotonic() - self._t_start) * self.speed
        changed = False
        while self._idx < len(self._rows) and self._rows[self._idx][0] <= elapsed:
            for k, v in self._rows[self._idx][1].items():
                if v is not None:          # carry the last reading forward
                    self._current[k] = v
            self._idx += 1
            changed = True

        if changed:
            self.values_updated.emit(dict(self._current))

        if self._idx >= len(self._rows):
            if self.loop:
                self._rewind()
            else:
                self._timer.stop()
                self._set_status(STATUS_FINISHED, "end of recording")


SOURCE_KINDS = ("simulated", "live", "emulator", "replay")
