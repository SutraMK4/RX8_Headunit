"""
core/gps.py
-----------
Reads gpsd in a background thread and reports the fix through a Qt signal.

Why a thread: talking to gpsd is network I/O. When gpsd is not running
(always the case on the Windows dev machine) a connection attempt can take
around a second to be refused on Windows. Done on the UI thread every
2 s, that froze the whole head unit at regular intervals.

    poller = GpsPoller()
    poller.fix_changed.connect(top_bar.set_gps_from_poller)
    poller.start()

fix_changed(has_fix: bool, mode: int, speed_kmh: float or None)
status_changed(text: str)    "connected", "gpsd not reachable", ...
"""

import logging
import threading

from PyQt5.QtCore import QObject, pyqtSignal

from core.diagnostics import timed, record_error

try:
    import gpsd as _gpsd       # gpsd-py3: module-level singleton connection
    _HAS_GPSD = True
except ImportError:
    _gpsd = None
    _HAS_GPSD = False

log = logging.getLogger("rx8.gps")

POLL_S = 1.0          # read interval while connected
RETRY_S = 10.0        # wait between connection attempts when gpsd is down


class GpsPoller(QObject):
    fix_changed = pyqtSignal(bool, int, object)
    status_changed = pyqtSignal(str)

    def __init__(self, host="127.0.0.1", port=2947, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.status = "stopped"
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="gps-poller", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _set_status(self, text):
        if text != self.status:
            self.status = text
            log.info("gps: %s", text)
            self.status_changed.emit(text)

    def _run(self):
        if not _HAS_GPSD:
            self._set_status("gpsd-py3 not installed")
            self.fix_changed.emit(False, 0, None)
            return

        connected = False
        last_fix = None
        while not self._stop.is_set():
            if not connected:
                try:
                    with timed("gps.connect", slow_ms=None):
                        _gpsd.connect(host=self.host, port=self.port)
                    connected = True
                    self._set_status("connected")
                except Exception as e:
                    self._set_status(f"gpsd not reachable ({type(e).__name__})")
                    if last_fix is not False:
                        self.fix_changed.emit(False, 0, None)
                        last_fix = False
                    self._stop.wait(RETRY_S)
                    continue

            try:
                with timed("gps.poll", slow_ms=None):
                    packet = _gpsd.get_current()
                mode = int(getattr(packet, "mode", 0) or 0)
                if mode >= 2:
                    try:
                        speed = packet.hspeed * 3.6       # m/s → km/h
                    except Exception:
                        speed = None
                    self.fix_changed.emit(True, mode, speed)
                    last_fix = True
                elif last_fix is not False:
                    self.fix_changed.emit(False, mode, None)
                    last_fix = False
            except Exception as e:
                record_error("gps.poll", e, level=logging.WARNING)
                connected = False
                self._set_status("connection lost")
                continue
            self._stop.wait(POLL_S)
