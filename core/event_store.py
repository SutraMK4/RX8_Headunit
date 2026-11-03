"""
core/event_store.py
-------------------
Long-term record of *distinct* problems, in SQLite
(~/.rx8_headunit/events.db). The text log is short-lived; this is what
you keep and look at later.

Tables
  events    one row per distinct warning / error / UI freeze
            (fingerprint, level, source, message, detail = stack trace,
             first_seen, last_seen, count, sessions = in how many sessions)
            A repeat only increments count and updates last_seen.
  sessions  one row per app start: started, ended, clean_exit, platform.
            A session without `ended` was cut off (crash or power loss);
            the next start records that as an event.
  metrics   per session: timing summary of every timed() name.

"Distinct" = same level, same source (logger), same message once numbers
are replaced by '#', and same code location (last stack frame). So
"slow: x took 63 ms" and "slow: x took 71 ms" are one event.

Writes happen on a background thread. A new distinct event is written
within a moment (so it survives a power cut); repeat counts are batched
every FLUSH_S seconds to keep SSD/SD writes low.

Why SQLite and not JSON/CSV: counts are updated in place without rewriting
the file, writes are atomic (no corrupt file after a power cut), and it is
part of Python. export_csv() gives a CSV whenever one is wanted.
"""

import csv
import hashlib
import logging
import os
import platform
import queue
import re
import sqlite3
import sys
import threading
import time
from datetime import datetime, timedelta

DB_PATH = os.path.expanduser("~/.rx8_headunit/events.db")
FLUSH_S = 10.0
RETENTION_DAYS = 90
KEEP_SESSIONS = 300

_FRAME_RE = re.compile(r'File "([^"]+)", line (\d+), in (\S+)')
_HEX_RE = re.compile(r"0x[0-9a-fA-F]+")
_NUM_RE = re.compile(r"\d+(\.\d+)?")
_SUPPRESSED_RE = re.compile(r"\s*\[\+\d+ identical suppressed[^\]]*\]")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalise(text):
    """Strip the parts that change between repeats (numbers, addresses)."""
    return _NUM_RE.sub("#", _HEX_RE.sub("#", text)).strip()


def split_record(record, formatter=None):
    """(message first line, detail) of a LogRecord. Detail holds the stack."""
    text = _SUPPRESSED_RE.sub("", record.getMessage())   # note added by RepeatFilter
    first, _, rest = text.partition("\n")
    detail = rest
    if record.exc_info:
        fmt = formatter or logging.Formatter()
        detail = (detail + "\n" if detail else "") + fmt.formatException(record.exc_info)
    return first.strip(), detail.strip("\n")


def location(detail):
    """Last stack frame in the detail, as 'file.py:123 in func'."""
    frames = _FRAME_RE.findall(detail or "")
    if not frames:
        return ""
    path, line, func = frames[-1]
    return f"{os.path.basename(path)}:{line} in {func}"


def fingerprint(record, message=None, detail=None):
    if message is None:
        message, detail = split_record(record)
    key = "|".join((record.levelname, record.name, normalise(message), location(detail)))
    return hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()[:16]


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started     TEXT NOT NULL,
    ended       TEXT,
    clean_exit  INTEGER DEFAULT 0,
    platform    TEXT,
    python      TEXT,
    args        TEXT
);
CREATE TABLE IF NOT EXISTS events (
    fingerprint  TEXT PRIMARY KEY,
    level        TEXT,
    source       TEXT,
    message      TEXT,
    location     TEXT,
    detail       TEXT,
    first_seen   TEXT,
    last_seen    TEXT,
    count        INTEGER DEFAULT 0,
    sessions     INTEGER DEFAULT 0,
    last_session INTEGER
);
CREATE TABLE IF NOT EXISTS metrics (
    session_id  INTEGER,
    name        TEXT,
    thread      TEXT,
    count       INTEGER,
    avg_ms      REAL,
    max_ms      REAL,
    PRIMARY KEY (session_id, name)
);
CREATE INDEX IF NOT EXISTS idx_events_last_seen ON events(last_seen);
"""


class EventStore:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.session_id = None
        self.previous_unclean = None      # dict of the cut-off session, if any
        self._q = queue.Queue()
        self._thread = None
        os.makedirs(os.path.dirname(path), exist_ok=True)

    # ── connection (one per thread; sqlite3 objects are thread-bound) ──
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")      # safe + fast, survives power loss
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    # ── session lifecycle ──────────────────────────────────────────
    def open(self, args=""):
        """Create tables, prune old data, detect an unclean previous exit,
        start a new session and the writer thread."""
        conn = self._connect()
        with conn:
            conn.executescript(SCHEMA)
            row = conn.execute(
                "SELECT id, started FROM sessions WHERE ended IS NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row:
                self.previous_unclean = {"id": row[0], "started": row[1]}
                conn.execute("UPDATE sessions SET ended = '(cut off)' WHERE ended IS NULL")
            self._prune(conn)
            cur = conn.execute(
                "INSERT INTO sessions (started, platform, python, args) VALUES (?, ?, ?, ?)",
                (_now(), f"{platform.system()} {platform.release()} {platform.machine()}",
                 sys.version.split()[0], args))
            self.session_id = cur.lastrowid
        conn.close()

        self._thread = threading.Thread(target=self._writer, name="event-store", daemon=True)
        self._thread.start()
        return self.session_id

    def close(self, metrics_snapshot=None):
        """Flush, store the session's metrics, mark a clean exit."""
        if self._thread is None:
            return
        self._q.put(("close", metrics_snapshot or {}))
        self._thread.join(timeout=3)
        self._thread = None

    def _prune(self, conn):
        cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("DELETE FROM events WHERE last_seen < ?", (cutoff,))
        conn.execute("DELETE FROM sessions WHERE id <= (SELECT MAX(id) FROM sessions) - ?",
                     (KEEP_SESSIONS,))
        conn.execute("DELETE FROM metrics WHERE session_id NOT IN (SELECT id FROM sessions)")

    # ── writing (called from logging, any thread; never blocks) ────
    def add(self, fp, level, source, message, loc, detail, when=None):
        self._q.put(("event", (fp, level, source, message, loc, detail, when or _now())))

    def _writer(self):
        conn = self._connect()
        known = set(r[0] for r in conn.execute("SELECT fingerprint FROM events"))
        seen_this_session = set()
        pending = {}                   # fp -> [count, last_seen]
        last_flush = time.monotonic()

        def flush():
            if not pending:
                return
            with conn:
                for fp, (n, last) in pending.items():
                    conn.execute("UPDATE events SET count = count + ?, last_seen = ? "
                                 "WHERE fingerprint = ?", (n, last, fp))
            pending.clear()

        while True:
            try:
                kind, payload = self._q.get(timeout=FLUSH_S)
            except queue.Empty:
                kind, payload = None, None

            if kind == "event":
                fp, level, source, message, loc, detail, when = payload
                if fp not in known:
                    # New distinct event: write now so a power cut cannot lose it
                    with conn:
                        conn.execute(
                            "INSERT INTO events (fingerprint, level, source, message, location, "
                            "detail, first_seen, last_seen, count, sessions, last_session) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?)",
                            (fp, level, source, message[:500], loc, detail[:20000],
                             when, when, self.session_id))
                    known.add(fp)
                    seen_this_session.add(fp)
                elif fp not in seen_this_session:
                    # Known event, first time this session: refresh text, count session
                    with conn:
                        conn.execute(
                            "UPDATE events SET count = count + 1, last_seen = ?, "
                            "sessions = sessions + 1, last_session = ?, message = ?, "
                            "detail = CASE WHEN ? != '' THEN ? ELSE detail END "
                            "WHERE fingerprint = ?",
                            (when, self.session_id, message[:500], detail, detail[:20000], fp))
                    seen_this_session.add(fp)
                else:
                    p = pending.setdefault(fp, [0, when])
                    p[0] += 1
                    p[1] = when

            if kind == "reset_known":
                known.clear()
                seen_this_session.clear()
                pending.clear()

            if kind == "close":
                flush()
                with conn:
                    for name, m in (payload or {}).items():
                        conn.execute(
                            "INSERT OR REPLACE INTO metrics VALUES (?, ?, ?, ?, ?, ?)",
                            (self.session_id, name, m.get("thread", ""), m["count"],
                             round(m["avg"], 2), round(m["max"], 2)))
                    conn.execute("UPDATE sessions SET ended = ?, clean_exit = 1 WHERE id = ?",
                                 (_now(), self.session_id))
                conn.close()
                return

            if time.monotonic() - last_flush >= FLUSH_S:
                flush()
                last_flush = time.monotonic()

    # ── reading (debug panel, export) ──────────────────────────────
    def query(self, sql, params=()):
        conn = self._connect()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def events(self, limit=500):
        return self.query(
            "SELECT last_seen, level, count, sessions, source, message, location, detail, first_seen "
            "FROM events ORDER BY last_seen DESC LIMIT ?", (limit,))

    def sessions(self, limit=20):
        return self.query(
            "SELECT id, started, ended, clean_exit, platform FROM sessions "
            "ORDER BY id DESC LIMIT ?", (limit,))

    def export_csv(self, path):
        rows = self.query(
            "SELECT first_seen, last_seen, level, count, sessions, source, message, "
            "location, detail FROM events ORDER BY last_seen DESC")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["first_seen", "last_seen", "level", "count", "sessions",
                        "source", "message", "location", "detail"])
            w.writerows(rows)
        return len(rows)

    def clear_events(self):
        conn = self._connect()
        with conn:
            conn.execute("DELETE FROM events")
        conn.close()
        self._q.put(("reset_known", None))


class EventStoreHandler(logging.Handler):
    """Feeds WARNING and above into the EventStore (no deduplication here:
    the store needs every occurrence to count it)."""

    def __init__(self, store, level=logging.WARNING):
        super().__init__(level)
        self.store = store

    def emit(self, record):
        try:
            message, detail = split_record(record, self.formatter)
            fp = fingerprint(record, message, detail)
            self.store.add(fp, record.levelname, record.name, message,
                           location(detail), detail,
                           datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            self.handleError(record)
