#!/usr/bin/env python3
"""
tools/oil_temp_cal.py
---------------------
Calibration and bench check for the oil temperature sender (ADS1115).
See RX8_OIL_TEMP_PLAN.md, phase 3.

  1. Beta from two measured points (multimeter on the sender):
       py tools/oil_temp_cal.py beta 20 2500 100 187
     → prints beta and the config lines to paste.

  2. What temperature a resistance means with a calibration:
       py tools/oil_temp_cal.py temp 187 --r0 2500 --t0 20 --beta 3450

  3. Live reading on the Pi (sender wired to the ADS1115):
       python3 tools/oil_temp_cal.py read --r-fixed 470 --r0 2500 --t0 20 --beta 3450

All resistances in ohms, temperatures in °C. The numbers above are
examples, not values for your sender.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.oil_temp import (ADS1115, beta_from_points, beta_temperature,  # noqa: E402
                           ntc_resistance)


def cmd_beta(a):
    b = beta_from_points(a.t1, a.r1, a.t2, a.r2)
    print(f"beta = {b:.0f} K")
    print("\nPut this into ~/.rx8_headunit/config.json under \"oil_temp\":")
    print(f'  "r0": {a.r1}, "t0": {a.t1}, "beta": {b:.0f}')
    for t in (40, 80, 100, 120, 140):
        r = a.r1 * pow(2.718281828, b * (1 / (t + 273.15) - 1 / (a.t1 + 273.15)))
        print(f"  check: {t:>3} °C ≈ {r:8.1f} Ω")


def cmd_temp(a):
    t = beta_temperature(a.ohms, a.r0, a.t0, a.beta)
    print(f"{a.ohms} Ω → {t:.1f} °C")


def cmd_read(a):
    adc = ADS1115(a.bus, int(a.address, 0))
    print("Ctrl+C to stop")
    try:
        while True:
            v = adc.read_volts(a.channel)
            vs = adc.read_volts(a.ref) if a.ref is not None else 3.3
            r = ntc_resistance(v, vs, a.r_fixed)
            t = beta_temperature(r, a.r0, a.t0, a.beta) if (r and a.beta) else None
            print(f"A{a.channel}={v:.4f} V  ref={vs:.4f} V  R={r if r is None else round(r, 1)} Ω  "
                  f"T={'—' if t is None else f'{t:.1f} °C'}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        adc.close()


def main():
    ap = argparse.ArgumentParser(description="Oil temp sender calibration")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("beta", help="beta from two (°C, ohm) points")
    for n in ("t1", "r1", "t2", "r2"):
        b.add_argument(n, type=float)
    b.set_defaults(func=cmd_beta)

    t = sub.add_parser("temp", help="ohms → °C")
    t.add_argument("ohms", type=float)
    for n in ("--r0", "--t0", "--beta"):
        t.add_argument(n, type=float, required=True)
    t.set_defaults(func=cmd_temp)

    r = sub.add_parser("read", help="live ADS1115 reading (Pi)")
    r.add_argument("--bus", type=int, default=1)
    r.add_argument("--address", default="0x48")
    r.add_argument("--channel", type=int, default=0)
    r.add_argument("--ref", type=int, default=3, help="3V3 reference channel (omit wiring: use --ref -1)")
    r.add_argument("--r-fixed", type=float, required=True)
    r.add_argument("--r0", type=float)
    r.add_argument("--t0", type=float)
    r.add_argument("--beta", type=float)
    r.set_defaults(func=cmd_read)

    a = ap.parse_args()
    if getattr(a, "ref", None) == -1:
        a.ref = None
    a.func(a)


if __name__ == "__main__":
    main()
