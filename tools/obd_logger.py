#!/usr/bin/env python3
"""
tools/obd_logger.py
-------------------
Records OBD data from the car to CSV, in the format ReplaySource plays
back (core/data_sources.py). Runs without the head unit UI.

  Scan what the car supports (do this first, ignition on):
      py tools/obd_logger.py scan
      py tools/obd_logger.py scan --port COM5

  Record (Ctrl+C to stop, or --seconds N). `log` and `record` are the same:
      py tools/obd_logger.py log --port COM4 --seconds 600 --out data/rx8_idle.csv
      py tools/obd_logger.py log --port COM4 --out data/rx8_drive.csv

  Against the emulator (run `py tools/run_emulator.py` in another terminal):
      py tools/obd_logger.py log --port socket://localhost:35000 --seconds 20 --out data/emu.csv

CSV format: header "elapsed_s,<KEY>,<KEY>,..." where KEY is the
python-obd command name. Values are plain numbers in python-obd units
(rpm, °C, km/h, %). Empty cell = no reading.
"""

import argparse
import csv
import os
import sys
import time

DEFAULT_KEYS = ["RPM", "COOLANT_TEMP", "OIL_TEMP", "SPEED",
                "THROTTLE_POS", "ENGINE_LOAD", "INTAKE_TEMP", "MAF",
                "TIMING_ADVANCE", "INTAKE_PRESSURE", "FUEL_LEVEL",
                "SHORT_FUEL_TRIM_1", "LONG_FUEL_TRIM_1", "CONTROL_MODULE_VOLTAGE"]


def connect(port, async_=False):
    import obd
    kwargs = dict(portstr=None if port in (None, "", "auto") else port, fast=False, timeout=30)
    if port and port.startswith("socket://"):
        kwargs["baudrate"] = 38400   # no baud detection over TCP
    conn = (obd.Async if async_ else obd.OBD)(**kwargs)
    if conn.status() != obd.OBDStatus.CAR_CONNECTED:
        print(f"Not connected to the car: {conn.status()}")
        print("Check: adapter plugged in, ignition ON, correct --port.")
        sys.exit(1)
    print(f"Connected: {conn.port_name()} · {conn.protocol_name()}")
    return conn


def cmd_scan(args):
    import obd
    conn = connect(args.port)
    names = sorted(c.name for c in conn.supported_commands)
    print(f"\n{len(names)} supported commands:")
    for n in names:
        print(f"  {n}")
    print("\nHead unit gauges:")
    for key in ["RPM", "COOLANT_TEMP", "OIL_TEMP", "SPEED", "THROTTLE_POS", "ENGINE_LOAD"]:
        ok = obd.commands.has_name(key) and conn.supports(obd.commands[key])
        print(f"  {key:<14} {'supported' if ok else 'NOT supported -> gauge shows N/A'}")
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w") as f:
            f.write("\n".join(names) + "\n")
        print(f"\nSaved list to {args.out}")
    conn.close()


def cmd_record(args):
    import obd
    conn = connect(args.port, async_=True)
    keys = [k for k in (args.keys.split(",") if args.keys else DEFAULT_KEYS)
            if obd.commands.has_name(k) and conn.supports(obd.commands[k])]
    if not keys:
        print("None of the requested values are supported.")
        sys.exit(1)
    for k in keys:
        conn.watch(obd.commands[k])
    conn.start()
    print(f"Recording {len(keys)} values at {args.hz:g} Hz: {', '.join(keys)}")
    print(f"Writing {args.out} — Ctrl+C to stop"
          + (f" (auto-stop after {args.seconds:g} s)" if args.seconds else ""))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    period = 1.0 / args.hz
    rows = 0
    t0 = time.monotonic()
    try:
        with open(args.out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["elapsed_s"] + keys)
            while True:
                t = time.monotonic() - t0
                if args.seconds and t >= args.seconds:
                    break
                row = [f"{t:.3f}"]
                for k in keys:
                    r = conn.query(obd.commands[k])
                    v = None if r.is_null() else getattr(r.value, "magnitude", r.value)
                    row.append("" if v is None else f"{float(v):.3f}")
                w.writerow(row)
                rows += 1
                if rows % int(args.hz * 5) == 0:
                    f.flush()
                    print(f"  {t:6.0f} s  {rows} rows")
                time.sleep(max(0.0, period - ((time.monotonic() - t0) - t)))
    except KeyboardInterrupt:
        pass
    finally:
        conn.stop()
        conn.close()
    print(f"\nDone: {rows} rows in {args.out}")


def main():
    ap = argparse.ArgumentParser(description="RX-8 OBD scanner / logger")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="list supported commands")
    s.add_argument("--port", default="auto")
    s.add_argument("--out", help="also save the list to this file")
    s.set_defaults(func=cmd_scan)

    r = sub.add_parser("record", aliases=["log"], help="record values to CSV")
    r.add_argument("--port", default="auto")
    r.add_argument("--out", required=True)
    r.add_argument("--hz", type=float, default=5.0,
                   help="rows per second (default 5; the car limits real throughput)")
    r.add_argument("--seconds", type=float, default=0,
                   help="stop after this many seconds (default: until Ctrl+C)")
    r.add_argument("--keys", help="comma-separated python-obd names (default: a useful set)")
    r.set_defaults(func=cmd_record)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
