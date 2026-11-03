"""
core/diagnostics.py
-------------------
Debugging aids for the head unit. Installed once in main.py.

What it gives you:

  Logging     Short-term text log ~/.rx8_headunit/logs/headunit.log and
              the console. A fresh file per session, the last 3 sessions
              are kept, older ones deleted. Repeats are collapsed: the same
              message more than REPEAT_LIMIT times per REPEAT_WINDOW_S is
              suppressed and summarised ("+57 identical suppressed").

  Events      Every distinct warning / error / UI freeze is kept long-term
              in ~/.rx8_headunit/events.db (see core/event_store.py) with
              a count, first/last seen and stack trace. That is the record
              to look at later; the text log is just for "what happened
              just now".

  Crashes     Hard crashes (segfaults in Qt etc.) are dumped to crash.log;
              the next start moves that into the event store, and an app
              that was cut off (crash, power loss) is recorded as an event.

  Errors      Uncaught exceptions anywhere (UI slots, threads) are logged
              with the full stack trace and kept in a list for the debug
              panel. The app keeps running instead of dying silently.
              Use record_error("where", exc) in except blocks you care about.

  Metrics     with timed("obd.connect"):  ...   records how long it took
              (count / last / average / max). Slow calls are logged.

  UI stalls   A watchdog thread notices when the UI thread stops
              responding for longer than STALL_MS and records *which line
              of code it was stuck in*. That is how freezes get found.

Open the debug panel with the D key, Settings → Diagnostics, or start
with  py main.py --debug
"""

import collections
import faulthandler
import logging
import logging.handlers
import os
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from datetime import datetime
from functools import wraps

from PyQt5.QtCore import QObject, QTimer

from core import event_store as es

LOG_DIR = os.path.expanduser("~/.rx8_headunit/logs")
LOG_FILE = os.path.join(LOG_DIR, "headunit.log")
CRASH_FILE = os.path.join(LOG_DIR, "crash.log")

STALL_MS = 250          # UI unresponsive longer than this = a stall
HEARTBEAT_MS = 50       # how often the UI thread checks in
SLOW_MS_DEFAULT = 100   # timed() logs a warning above this (UI-thread work)

LOG_MAX_BYTES = 2_000_000   # per text log file
LOG_SESSIONS_KEPT = 3       # current + 2 previous sessions
REPEAT_LIMIT = 3            # identical messages allowed per window...
REPEAT_WINDOW_S = 60        # ...after that they are suppressed and counted

log = logging.getLogger("rx8")


def _now_str():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


# ──────────────────────────────────────────────────────────────────
#  In-memory stores (thread-safe) — read by the debug panel
# ──────────────────────────────────────────────────────────────────
class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {}

    def record(self, name, ms, thread=None):
        thread = thread or threading.current_thread().name
        with self._lock:
            m = self._data.get(name)
            if m is None:
                m = self._data[name] = {"count": 0, "total": 0.0, "max": 0.0,
                                        "last": 0.0, "at": "", "thread": thread}
            m["count"] += 1
            m["total"] += ms
            m["last"] = ms
            m["max"] = max(m["max"], ms)
            m["at"] = _now_str()
            m["thread"] = thread

    def snapshot(self):
        with self._lock:
            return {k: dict(v, avg=v["total"] / v["count"]) for k, v in self._data.items()}

    def clear(self):
        with self._lock:
            self._data.clear()


METRICS = Metrics()
ERRORS = collections.deque(maxlen=100)    # dicts: at, where, message, trace
STALLS = collections.deque(maxlen=100)    # dicts: at, ms, stack
LOG_LINES = collections.deque(maxlen=1000)


class _MemoryHandler(logging.Handler):
    def emit(self, record):
        try:
            LOG_LINES.append(self.format(record))
        except Exception:
            pass


class RepeatFilter(logging.Filter):
    """
    Collapses floods in the text log, console and LOG tab. The first
    REPEAT_LIMIT copies of a message per REPEAT_WINDOW_S pass; the rest are
    counted, and the next copy after the window carries
    "[+N identical suppressed]". Exact counts are in the event store.
    One instance is shared by several handlers; the decision is cached on
    the record so each record is judged once.
    """

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self._seen = {}     # key -> [window_start, passed, suppressed]

    def filter(self, record):
        cached = getattr(record, "_rx8_pass", None)
        if cached is not None:
            return cached
        msg = record.getMessage().partition("\n")[0]
        key = (record.levelno, record.name, es.normalise(msg))
        now = time.monotonic()
        with self._lock:
            st = self._seen.get(key)
            if st is None or now - st[0] > REPEAT_WINDOW_S:
                suppressed = st[2] if st else 0
                self._seen[key] = [now, 1, 0]
                if suppressed:
                    note = f"  [+{suppressed} identical suppressed in the previous {REPEAT_WINDOW_S} s]"
                    record.msg = str(record.msg) + note.replace("%", "%%")
                ok = True
            elif st[1] < REPEAT_LIMIT:
                st[1] += 1
                ok = True
            else:
                st[2] += 1
                ok = False
            if len(self._seen) > 2000:          # keep memory bounded
                self._seen.clear()
        record._rx8_pass = ok
        return ok


# ──────────────────────────────────────────────────────────────────
#  Timing
# ──────────────────────────────────────────────────────────────────
@contextmanager
def timed(name, slow_ms=SLOW_MS_DEFAULT):
    """with timed("gps.connect"): ...   Records duration; warns when slow.
    Pass slow_ms=None for work that is allowed to be slow (background)."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        ms = (time.perf_counter() - t0) * 1000
        METRICS.record(name, ms)
        if slow_ms is not None and ms > slow_ms:
            log.warning("slow: %s took %.0f ms (thread %s)",
                        name, ms, threading.current_thread().name)


def timed_fn(name=None, slow_ms=SLOW_MS_DEFAULT):
    """Decorator version of timed()."""
    def deco(fn):
        label = name or f"{fn.__module__}.{fn.__qualname__}"

        @wraps(fn)
        def wrapper(*a, **kw):
            with timed(label, slow_ms):
                return fn(*a, **kw)
        return wrapper
    return deco


# ──────────────────────────────────────────────────────────────────
#  Errors
# ──────────────────────────────────────────────────────────────────
def record_error(where, exc=None, trace=None, level=logging.ERROR, message=None):
    """Log an error with its stack trace and keep it for the debug panel.
    Call from an except block: record_error("obd.connect", e)."""
    if trace is None:
        if exc is not None and exc.__traceback__ is not None:
            trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        else:
            trace = "".join(traceback.format_stack()[:-1])
    if message is None:
        message = f"{type(exc).__name__}: {exc}" if exc is not None else where
    ERRORS.append({"at": _now_str(), "where": where, "message": message, "trace": trace})
    log.log(level, "%s: %s\n%s", where, message, trace.rstrip())


def _excepthook(exc_type, exc, tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    trace = "".join(traceback.format_exception(exc_type, exc, tb))
    ERRORS.append({"at": _now_str(), "where": "uncaught (UI thread)",
                   "message": f"{exc_type.__name__}: {exc}", "trace": trace})
    log.error("uncaught exception: %s: %s\n%s", exc_type.__name__, exc, trace.rstrip())
    # Do not exit: PyQt would otherwise abort the whole app on a slot error.


def _thread_excepthook(args):
    trace = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    name = args.thread.name if args.thread else "?"
    ERRORS.append({"at": _now_str(), "where": f"uncaught (thread {name})",
                   "message": f"{args.exc_type.__name__}: {args.exc_value}", "trace": trace})
    log.error("uncaught exception in thread %s: %s: %s\n%s", name,
              args.exc_type.__name__, args.exc_value, trace.rstrip())


# ──────────────────────────────────────────────────────────────────
#  UI stall watchdog
# ──────────────────────────────────────────────────────────────────
class StallWatchdog(QObject):
    """
    The UI thread ticks a heartbeat every HEARTBEAT_MS. A background thread
    checks it; when the heartbeat is older than threshold_ms the UI is
    frozen, and the watchdog grabs the UI thread's current stack: that is the
    code causing the freeze. When the heartbeat resumes, the stall is
    recorded with its duration.
    """

    def __init__(self, threshold_ms=STALL_MS, parent=None):
        super().__init__(parent)
        self.threshold = threshold_ms / 1000.0
        self._main_id = threading.main_thread().ident
        self._beat = time.perf_counter()
        self._running = True

        self._timer = QTimer(self)
        self._timer.setInterval(HEARTBEAT_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._thread = threading.Thread(target=self._watch, name="stall-watchdog", daemon=True)
        self._thread.start()

    def _tick(self):
        self._beat = time.perf_counter()

    def stop(self):
        self._running = False
        self._timer.stop()

    def _watch(self):
        in_stall = False
        stall_start = 0.0
        stack = ""
        while self._running:
            time.sleep(HEARTBEAT_MS / 2000.0)
            beat = self._beat
            gap = time.perf_counter() - beat
            if not in_stall and gap > self.threshold:
                in_stall = True
                stall_start = beat
                frame = sys._current_frames().get(self._main_id)
                stack = "".join(traceback.format_stack(frame)) if frame else "(no stack)"
            elif in_stall and beat > stall_start:
                in_stall = False
                ms = (beat - stall_start) * 1000 - HEARTBEAT_MS
                STALLS.append({"at": _now_str(), "ms": ms, "stack": stack})
                METRICS.record("ui.stall", ms, thread="MainThread")
                log.warning("UI STALL: UI thread blocked ~%.0f ms. It was here:\n%s",
                            ms, stack.rstrip())


# ──────────────────────────────────────────────────────────────────
#  Install
# ──────────────────────────────────────────────────────────────────
_installed = {}


def _prepare_log_files():
    """Start a fresh text log per session; keep the last LOG_SESSIONS_KEPT."""
    os.makedirs(LOG_DIR, exist_ok=True)
    keep = LOG_SESSIONS_KEPT - 1
    # shift headunit.log -> .1 -> .2 ..., drop the oldest
    for i in range(keep, 0, -1):
        src = LOG_FILE if i == 1 else f"{LOG_FILE}.{i - 1}"
        dst = f"{LOG_FILE}.{i}"
        if os.path.exists(src) and os.path.getsize(src) > 0:
            try:
                os.replace(src, dst)
            except OSError:
                pass
    # delete anything older (also files from the earlier 1 MB x 3 scheme)
    for name in os.listdir(LOG_DIR):
        if name.startswith("headunit.log."):
            suffix = name.rsplit(".", 1)[-1]
            if suffix.isdigit() and int(suffix) > keep:
                try:
                    os.remove(os.path.join(LOG_DIR, name))
                except OSError:
                    pass


def _take_crash_dump():
    """Return the previous session's crash dump (if any) and empty the file."""
    try:
        with open(CRASH_FILE, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return ""
    lines = [l for l in text.splitlines() if l.strip() and not l.startswith("--- session started")]
    return "\n".join(lines)


def install(verbose=False, stall_ms=STALL_MS, args=""):
    """Set up logging, event store, exception hooks, crash dumps and the
    stall watchdog. Call once after QApplication is created."""
    if _installed:
        return _installed["watchdog"]

    _prepare_log_files()
    crash_text = _take_crash_dump()

    fmt = logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)-7s %(threadName)-14s %(name)s: %(message)s",
                            "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    repeat = RepeatFilter()
    fh = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=LOG_MAX_BYTES,
                                              backupCount=0, encoding="utf-8")
    ch = logging.StreamHandler()
    mh = _MemoryHandler()
    for h in (fh, ch, mh):
        h.setFormatter(fmt)
        h.addFilter(repeat)
        root.addHandler(h)

    # Long-term distinct events (every occurrence counted, no filter)
    store = es.EventStore()
    try:
        store.open(args=args)
        eh = es.EventStoreHandler(store)
        eh.setFormatter(fmt)
        root.addHandler(eh)
        _installed["store"] = store
    except Exception as e:                  # pragma: no cover
        log.warning("event store not available: %s", e)

    # pint (unit library used by python-obd) warns "Redefining ..." on every
    # import; harmless noise
    logging.getLogger("pint").setLevel(logging.ERROR)

    sys.excepthook = _excepthook
    if hasattr(threading, "excepthook"):
        threading.excepthook = _thread_excepthook

    try:
        crash = open(CRASH_FILE, "w", encoding="utf-8")      # emptied each session
        crash.write(f"--- session started {datetime.now():%Y-%m-%d %H:%M:%S} ---\n")
        crash.flush()
        faulthandler.enable(crash)
        _installed["crash_file"] = crash   # keep it open for the session
    except Exception as e:                  # pragma: no cover
        log.warning("crash dump file not available: %s", e)

    wd = StallWatchdog(stall_ms)
    _installed["watchdog"] = wd
    log.info("diagnostics on: log %s, events %s, stall threshold %d ms, verbose=%s",
             LOG_FILE, es.DB_PATH, stall_ms, verbose)

    prev = store.previous_unclean if "store" in _installed else None
    if prev or crash_text:
        detail = ""
        if crash_text:
            detail = "Crash dump (faulthandler):\n" + crash_text
        else:
            detail = ("No crash dump: most likely power was cut or the process was "
                      "killed (no clean shutdown).")
        log.error("previous session did not exit cleanly (started %s)\n%s",
                  prev["started"] if prev else "?", detail)
    return wd


def shutdown():
    """Connect to QApplication.aboutToQuit: store metrics, mark clean exit."""
    store = _installed.get("store")
    if store is not None:
        store.close(METRICS.snapshot())
        _installed.pop("store", None)
    wd = _installed.get("watchdog")
    if wd is not None:
        wd.stop()


def event_store():
    return _installed.get("store")


def adopt_obd_logger(verbose=None):
    """python-obd attaches its own console handler, so every python-obd
    message was printed twice. Remove it (our handlers already show it) and
    keep python-obd at WARNING unless verbose. Call after `import obd`."""
    lg = logging.getLogger("obd")
    for h in list(lg.handlers):
        lg.removeHandler(h)
    lg.propagate = True
    if verbose is None:
        verbose = logging.getLogger().level <= logging.DEBUG
    lg.setLevel(logging.DEBUG if verbose else logging.WARNING)


def set_verbose(verbose):
    logging.getLogger().setLevel(logging.DEBUG if verbose else logging.INFO)
    adopt_obd_logger(verbose)
    log.info("verbose logging %s", "on" if verbose else "off")


def report_text():
    """Everything in one block of text, for copy/paste into a chat or issue."""
    lines = [f"RX-8 head unit diagnostics — {datetime.now():%Y-%m-%d %H:%M:%S}",
             f"Python {sys.version.split()[0]} on {sys.platform}", "", "== Metrics (ms) =="]
    for name, m in sorted(METRICS.snapshot().items()):
        lines.append(f"{name:<32} n={m['count']:<5} last={m['last']:8.1f} "
                     f"avg={m['avg']:8.1f} max={m['max']:8.1f}  [{m['thread']}]")
    lines += ["", f"== UI stalls ({len(STALLS)}) =="]
    for s in list(STALLS)[-10:]:
        lines += [f"[{s['at']}] {s['ms']:.0f} ms", s["stack"].rstrip(), ""]
    lines += ["", f"== Errors ({len(ERRORS)}) =="]
    for e in list(ERRORS)[-10:]:
        lines += [f"[{e['at']}] {e['where']}: {e['message']}", e["trace"].rstrip(), ""]
    lines += ["", "== Log (last 100 lines) =="] + list(LOG_LINES)[-100:]
    return "\n".join(lines)
