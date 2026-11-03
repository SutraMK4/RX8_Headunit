#!/usr/bin/env python3
"""
tools/run_emulator.py
---------------------
Starts ELM327-emulator on TCP port 35000 with a fix for Windows.

Why: on Windows a client that disconnects (switching source, quitting the
head unit, the logger finishing) shows up as ConnectionAbortedError
(WinError 10053). ELM327-emulator only handles ConnectionResetError, so it
never notices the client is gone, floods the console with
"Error while reading from network: [WinError 10053] ..." and never accepts
a new connection. The head unit then hangs on "EMULATOR CONNECTING".

This launcher wraps the emulator's client socket so an aborted connection is
treated like a reset: the emulator drops the client and waits for the next.

It also quiets the emulator's own log. Plain `elm` writes every request
and response at DEBUG level (~2,600 lines a minute) into elm.log files in
whatever folder it was started from (e.g. the repo). The launcher writes
only warnings and errors, to ~/.rx8_headunit/logs/emulator.log (max 2 x 500 kB).

Usage (leave the window open):
    py tools/run_emulator.py              # same as: elm -n 35000 -s car
    py tools/run_emulator.py -n 35001     # any normal `elm` arguments
    py tools/run_emulator.py --emu-verbose   # full DEBUG trace (troubleshooting)

Then in the head unit: Settings -> Source "emulator",
address socket://localhost:35000, APPLY.
"""

import logging.config
import os
import sys

try:
    import elm
    import elm.elm as elm_module
    from elm.elm import Elm
except ImportError:
    print("ELM327-emulator is not installed:  py -m pip install ELM327-emulator")
    sys.exit(1)


class _ClientSocket:
    """Delegates to the real socket; turns 'aborted' into 'reset'."""

    def __init__(self, sock):
        self._sock = sock

    def recv(self, n):
        try:
            return self._sock.recv(n)
        except ConnectionAbortedError as e:
            raise ConnectionResetError(str(e))

    def sendall(self, data):
        try:
            return self._sock.sendall(data)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # Client is gone; the next recv() notices and resets cleanly.
            return None

    def __getattr__(self, name):
        return getattr(self._sock, name)


_original_accept = Elm.accept_connection


def _accept_connection(self):
    ok = _original_accept(self)
    if ok and self.sock_conn is not None and not isinstance(self.sock_conn, _ClientSocket):
        self.sock_conn = _ClientSocket(self.sock_conn)
    return ok


Elm.accept_connection = _accept_connection


# ── Quiet, out-of-repo logging ───────────────────────────────────────
EMU_LOG = os.path.expanduser("~/.rx8_headunit/logs/emulator.log")
_VERBOSE = "--emu-verbose" in sys.argv
if _VERBOSE:
    sys.argv.remove("--emu-verbose")


def _setup_logging(*_args, **_kwargs):
    os.makedirs(os.path.dirname(EMU_LOG), exist_ok=True)
    level = "DEBUG" if _VERBOSE else "WARNING"
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"f": {"format": "%(asctime)s %(levelname)-8s %(funcName)-15s %(message)s"}},
        "handlers": {
            "file": {"class": "logging.handlers.RotatingFileHandler", "formatter": "f",
                     "filename": EMU_LOG, "level": level, "encoding": "utf8",
                     "maxBytes": 500_000, "backupCount": 1},
            "console": {"class": "logging.StreamHandler", "formatter": "f",
                        "level": "INFO" if _VERBOSE else "WARNING",
                        "stream": "ext://sys.stdout"},
        },
        "root": {"level": level, "handlers": ["file", "console"]},
    })


elm_module.setup_logging = _setup_logging


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv += ["-n", "35000", "-s", "car"]
    print(f"Emulator log (warnings only{'; verbose' if _VERBOSE else ''}): {EMU_LOG}")
    elm.main()
