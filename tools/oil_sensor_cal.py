#!/usr/bin/env python3
"""
tools/oil_sensor_cal.py
-----------------------
Calibration and bench check for the oil temperature and pressure senders
on the ADS1115. See RX8_OIL_SENSORS_PLAN.md.

  1. Beta from two measured points (multimeter on the sender):
       py tools/oil_sensor_cal.py beta 20 2500 98.5 210
     → prints beta and the config lines to paste.

  2. What temperature a resistance means with a calibration:
       py tools/oil_sensor_cal.py temp 187 --r0 2500 --t0 20 --beta 3450

  3. Live reading on the Pi (both senders wired to the ADS1115):
       python3 tools/oil_sensor_cal.py read --r-fixed 470 --r0 2500 --t0 20 --beta 3450
     Shows all four channels, temperature and pressure (default wiring:
     A0 temp, A1 pressure via 10k/20k, A2 5 V via 10k/10k, A3 3V3).

All resistances in ohms, temperatures in °C. The numbers above are
examples, not values for your sender.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.oil_sensors import (ADS1115, beta_from_points, beta_temperature,  # noqa: E402
                              ntc_resistance, ratiometric_pressure)


def cmd_beta(a):
    b = beta_from_points(a.t1, a.r1, a.t2, a.r2)
    print(f"beta = {b:.0f} K")
    print("\nPut this into ~/.rx8_headunit/config.json under \"oil_sensors\":")
    print(f'  "temp": {{"r0": {a.r1}, "t0": {a.t1}, "beta": {b:.0f}, "r_fixed": <your resistor>}}')
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
            v = [adc.read_volts(ch) for ch in range(4)]
            v33 = v[3]
            r = ntc_resistance(v[0], v33, a.r_fixed) if a.r_fixed else None
            t = beta_temperature(r, a.r0, a.t0, a.beta) if (r and a.beta) else None
            v5 = v[2] * 2.0
            bar, fault = ratiometric_pressure(v[1] * 1.5, v5, p_max=a.p_max)
            print(f"A0={v[0]:.3f} A1={v[1]:.3f} A2={v[2]:.3f} A3={v[3]:.3f} V | "
                  f"R={'—' if r is None else f'{r:.0f} Ω'} T={'—' if t is None else f'{t:.1f} °C'} | "
                  f"5V={v5:.2f} P={fault if fault else f'{bar:.2f} bar'}")
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
    r.add_argument("--r-fixed", type=float)
    r.add_argument("--p-max", type=float, default=10.0, help="pressure sender full scale, bar")
    r.add_argument("--r0", type=float)
    r.add_argument("--t0", type=float)
    r.add_argument("--beta", type=float)
    r.set_defaults(func=cmd_read)

    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
