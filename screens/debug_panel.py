"""
screens/debug_panel.py
----------------------
Separate window with what core/diagnostics.py collects:

  Events     history across sessions: every *distinct* warning, error and
             UI freeze, with count, first/last seen and stack (events.db)
  Metrics    how long things take this session (count / last / avg / max)
  UI stalls  this session's freezes, with the code the UI was stuck in
  Errors     this session's exceptions with full stack traces
  Log        live tail of the (deduplicated) log

Open with the D key, Settings → Diagnostics → OPEN DEBUG PANEL, or start
the app with --debug. "COPY REPORT" puts everything on the clipboard so it
can be pasted into a chat or an issue.
"""

import os
import subprocess
import sys
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget, QTableWidget,
    QTableWidgetItem, QPlainTextEdit, QSplitter, QListWidget, QLabel,
    QApplication, QHeaderView, QCheckBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from core import diagnostics as diag
from core import theme


def _mono():
    f = QFont("Courier New")
    f.setPointSize(theme.FONT_SIZE_SM)
    return f


class DebugPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("RX-8 Head Unit — Debug")
        self.resize(900, 560)
        self.setStyleSheet(f"""
            QWidget {{ background-color: {theme.BG_PRIMARY}; color: {theme.TEXT_PRIMARY}; }}
            QTabBar::tab {{ background: {theme.BG_SECONDARY}; color: {theme.TEXT_SECONDARY};
                           padding: 6px 14px; border: 1px solid {theme.BORDER}; }}
            QTabBar::tab:selected {{ color: {theme.TEXT_PRIMARY}; border-bottom: 2px solid {theme.ACCENT}; }}
            QTableWidget, QPlainTextEdit, QListWidget {{ background-color: {theme.BG_SECONDARY};
                           border: 1px solid {theme.BORDER}; gridline-color: {theme.BORDER}; }}
            QHeaderView::section {{ background-color: {theme.BG_CARD}; color: {theme.TEXT_SECONDARY};
                           border: none; padding: 4px; }}
            QPushButton {{ background: transparent; color: {theme.TEXT_SECONDARY};
                           border: 1px solid {theme.BORDER}; border-radius: 4px; padding: 4px 12px; }}
            QPushButton:hover {{ color: {theme.TEXT_PRIMARY}; border-color: {theme.ACCENT}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Summary + buttons ──────────────────────────────────────
        top = QHBoxLayout()
        self._summary = QLabel()
        self._summary.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        top.addWidget(self._summary, stretch=1)

        self._verbose = QCheckBox("verbose log")
        self._verbose.setChecked(diag.logging.getLogger().level <= diag.logging.DEBUG)
        self._verbose.toggled.connect(diag.set_verbose)
        top.addWidget(self._verbose)

        for text, slot in (("COPY REPORT", self._copy_report),
                           ("OPEN LOG FOLDER", self._open_log_folder),
                           ("CLEAR", self._clear)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            top.addWidget(b)
        layout.addLayout(top)

        # ── Tabs ───────────────────────────────────────────────────
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs, stretch=1)

        # Events (long-term, from events.db)
        ev_split = QSplitter(Qt.Vertical)
        ev_top = QWidget()
        ev_layout = QVBoxLayout(ev_top)
        ev_layout.setContentsMargins(0, 0, 0, 0)
        ev_bar = QHBoxLayout()
        self._sessions_lbl = QLabel()
        self._sessions_lbl.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        ev_bar.addWidget(self._sessions_lbl, stretch=1)
        for text, slot in (("EXPORT CSV", self._export_csv), ("CLEAR HISTORY", self._clear_history)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            ev_bar.addWidget(b)
        ev_layout.addLayout(ev_bar)
        self._events = QTableWidget(0, 6)
        self._events.setHorizontalHeaderLabels(["last seen", "level", "count", "sessions", "source", "message"])
        self._events.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self._events.verticalHeader().setVisible(False)
        self._events.setEditTriggers(QTableWidget.NoEditTriggers)
        self._events.setSelectionBehavior(QTableWidget.SelectRows)
        self._events.setFont(_mono())
        self._events.currentCellChanged.connect(lambda r, *_: self._show_event(r))
        ev_layout.addWidget(self._events)
        self._event_text = QPlainTextEdit()
        self._event_text.setReadOnly(True)
        self._event_text.setFont(_mono())
        ev_split.addWidget(ev_top)
        ev_split.addWidget(self._event_text)
        ev_split.setSizes([300, 200])
        self._tabs.addTab(ev_split, "EVENTS")
        self._event_rows = []
        self._events_sig = None
        self._events_tick = 0

        self._metrics = QTableWidget(0, 7)
        self._metrics.setHorizontalHeaderLabels(["name", "thread", "count", "last ms", "avg ms", "max ms", "last at"])
        self._metrics.setToolTip("Red = slow work on the UI thread (MainThread). "
                                 "Slow work in background threads does not freeze the UI.")
        self._metrics.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._metrics.verticalHeader().setVisible(False)
        self._metrics.setEditTriggers(QTableWidget.NoEditTriggers)
        self._metrics.setFont(_mono())
        self._tabs.addTab(self._metrics, "METRICS")

        self._stall_list, self._stall_text, stall_w = self._list_detail()
        self._tabs.addTab(stall_w, "UI STALLS")

        self._err_list, self._err_text, err_w = self._list_detail()
        self._tabs.addTab(err_w, "ERRORS")

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(_mono())
        self._log.setMaximumBlockCount(1000)
        self._tabs.addTab(self._log, "LOG")

        self._stall_list.currentRowChanged.connect(self._show_stall)
        self._err_list.currentRowChanged.connect(self._show_error)

        self._seen = {"stalls": -1, "errors": -1, "log": 0}
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.refresh)

    def _list_detail(self):
        split = QSplitter(Qt.Vertical)
        lst = QListWidget()
        lst.setFont(_mono())
        txt = QPlainTextEdit()
        txt.setReadOnly(True)
        txt.setFont(_mono())
        split.addWidget(lst)
        split.addWidget(txt)
        split.setSizes([160, 340])
        return lst, txt, split

    # ── lifecycle ──────────────────────────────────────────────────
    def showEvent(self, event):
        self.refresh()
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    # ── events (database) ──────────────────────────────────────────
    def refresh_events(self, force=False):
        store = diag.event_store()
        if store is None:
            self._sessions_lbl.setText("event store not available")
            return
        try:
            rows = store.events()
            sessions = store.sessions(limit=50)
        except Exception as e:
            self._sessions_lbl.setText(f"cannot read events.db: {e}")
            return
        unclean = sum(1 for s in sessions[1:] if not s[3])
        self._sessions_lbl.setText(
            f"{len(rows)} distinct events · session #{store.session_id} · "
            f"{unclean} of the previous {max(0, len(sessions) - 1)} sessions did not exit cleanly")
        sig = [(r[0], r[2]) for r in rows]
        if sig == self._events_sig and not force:
            return
        self._events_sig = sig
        self._event_rows = rows
        current = self._events.currentRow()
        self._events.setRowCount(len(rows))
        colours = {"ERROR": Qt.red, "CRITICAL": Qt.red, "WARNING": Qt.yellow}
        for r, (last, level, count, nsess, source, message, loc, detail, first) in enumerate(rows):
            vals = [last[5:], level, str(count), str(nsess), source, message]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if c in (2, 3):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 1 and level in colours:
                    item.setForeground(colours[level])
                self._events.setItem(r, c, item)
        for c in range(5):
            self._events.resizeColumnToContents(c)
        if 0 <= current < len(rows):
            self._events.setCurrentCell(current, 0)

    def _show_event(self, row):
        if 0 <= row < len(self._event_rows):
            last, level, count, nsess, source, message, loc, detail, first = self._event_rows[row]
            self._event_text.setPlainText(
                f"{level}  {source}\n{message}\n\n"
                f"seen {count}x in {nsess} session(s) · first {first} · last {last}\n"
                f"location: {loc or '-'}\n\n{detail}")

    def _export_csv(self):
        store = diag.event_store()
        if store is None:
            return
        path = os.path.join(diag.LOG_DIR, f"events_{datetime.now():%Y%m%d_%H%M}.csv")
        try:
            n = store.export_csv(path)
            self._sessions_lbl.setText(f"exported {n} events to {path}")
        except Exception as e:
            diag.record_error("debug.export_csv", e)

    def _clear_history(self):
        store = diag.event_store()
        if store is not None:
            store.clear_events()
            self.refresh_events(force=True)

    # ── refresh ────────────────────────────────────────────────────
    def refresh(self):
        # events.db is read every 5 s (cheap, but no need to hammer it)
        if self._events_tick % 5 == 0:
            self.refresh_events()
        self._events_tick += 1

        snap = diag.METRICS.snapshot()
        stall = snap.get("ui.stall")
        self._summary.setText(
            f"{len(diag.STALLS)} UI stalls"
            + (f" (worst {stall['max']:.0f} ms)" if stall else "")
            + f"  ·  {len(diag.ERRORS)} errors  ·  log: {diag.LOG_FILE}")

        rows = sorted(snap.items())
        self._metrics.setRowCount(len(rows))
        for r, (name, m) in enumerate(rows):
            ui_thread = m["thread"] == "MainThread"
            vals = [name, "UI" if ui_thread else m["thread"], str(m["count"]),
                    f"{m['last']:.1f}", f"{m['avg']:.1f}", f"{m['max']:.1f}", m["at"]]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if c >= 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 5 and ui_thread and m["max"] > diag.SLOW_MS_DEFAULT:
                    item.setForeground(Qt.red)
                self._metrics.setItem(r, c, item)

        stalls = list(diag.STALLS)
        if len(stalls) != self._seen["stalls"]:
            self._seen["stalls"] = len(stalls)
            self._stall_list.clear()
            for s in stalls:
                where = s["stack"].strip().splitlines()[-2].strip() if s["stack"].strip() else ""
                self._stall_list.addItem(f"[{s['at']}] {s['ms']:6.0f} ms  {where}")
            if stalls:
                self._stall_list.setCurrentRow(len(stalls) - 1)

        errors = list(diag.ERRORS)
        if len(errors) != self._seen["errors"]:
            self._seen["errors"] = len(errors)
            self._err_list.clear()
            for e in errors:
                self._err_list.addItem(f"[{e['at']}] {e['where']}: {e['message']}")
            if errors:
                self._err_list.setCurrentRow(len(errors) - 1)

        lines = list(diag.LOG_LINES)
        if len(lines) != self._seen["log"] or (lines and lines[-1] != getattr(self, "_last_line", None)):
            self._seen["log"] = len(lines)
            self._last_line = lines[-1] if lines else None
            bar = self._log.verticalScrollBar()
            at_bottom = bar.value() >= bar.maximum() - 2
            self._log.setPlainText("\n".join(lines))
            if at_bottom:
                bar.setValue(bar.maximum())

    def _show_stall(self, row):
        stalls = list(diag.STALLS)
        if 0 <= row < len(stalls):
            s = stalls[row]
            self._stall_text.setPlainText(
                f"UI thread blocked ~{s['ms']:.0f} ms at {s['at']}.\n"
                f"Stack of the UI thread during the freeze (most recent call last):\n\n{s['stack']}")

    def _show_error(self, row):
        errors = list(diag.ERRORS)
        if 0 <= row < len(errors):
            e = errors[row]
            self._err_text.setPlainText(f"{e['where']} at {e['at']}\n{e['message']}\n\n{e['trace']}")

    # ── actions ────────────────────────────────────────────────────
    def _copy_report(self):
        QApplication.clipboard().setText(diag.report_text())
        self._summary.setText("Report copied to clipboard.")

    def _open_log_folder(self):
        path = diag.LOG_DIR
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)                      # noqa: Windows only
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            diag.record_error("debug.open_log_folder", e)

    def _clear(self):
        diag.METRICS.clear()
        diag.STALLS.clear()
        diag.ERRORS.clear()
        self._seen = {"stalls": -1, "errors": -1, "log": 0}
        self.refresh()
