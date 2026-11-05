# Plan: oil temperature and oil pressure for the RX-8 (S1, 2004)

Status 5 Nov 2026. Replaces `RX8_OIL_TEMP_PLAN.md` (temperature only) and the
first draft `rx8_oil_temp_projektplan.md` (Arduino + MCP2515 + CAN).

## Why

A rotary lives and dies by its oil. The S1 gives the driver almost nothing:

- **Oil temperature:** no factory sensor at all. Not on OBD (PID 0x5C
  unsupported, confirmed by the scan on 5 Nov 2026).
- **Oil pressure:** the dash "gauge" is driven by a pressure *switch*, so it
  does not show real pressure.
- **Oil level:** a float sensor in the sump drives the low-oil warning light.
  That is the earliest warning for "running low" — pressure only drops once
  the level is already critical.

## Design

```
[oil temp NTC]  ─┐
[oil pressure]  ─┼─> [ADS1115 on the Pi, I²C] ──> core/oil_sensors.py ──> OIL TEMP / OIL PRESS gauges
                 │
[oil level light signal] ──> (later) optocoupler → Pi GPIO
```

Nothing is connected to the car's CAN bus. One ADS1115 (4 channels) reads
both senders; the steering wheel buttons get a second ADS1115 at address
0x49 later.

## Parts

| Part | Purpose | Notes |
|---|---|---|
| Racing Beat TYPE II oil pressure/temperature adapter (part 11803), or Wankelshop S1 sandwich adapter | Ports at the oil filter | Racing Beat: 1/8" NPT for pressure, 3/8" NPT for temperature, fits 2004–08. Wankelshop: **confirm both threads before buying senders** |
| NTC oil temperature sender, 0–150 °C, thread to match | Temperature | **Prefer 2-pole (insulated)**, see "Ground" |
| Oil pressure transducer, **ratiometric 0.5–4.5 V, 0–10 bar (≈150 psi), 5 V supply, 3-wire**, 1/8" NPT | Pressure | Ratiometric 3-wire, not the old single-wire resistive senders: more accurate, no ground-offset issue. 0–10 bar covers the RX-8's range |
| ADS1115 module | ADC | 3.3 V supply, address 0x48 |
| Resistors 0.1 %: R_fixed (temp divider), 10 k + 20 k (pressure divider), 10 k + 10 k (5 V reference) | Dividers | Pressure output up to 4.5 V must be divided below 3.3 V for the ADS1115 |
| 3 × (1 kΩ + 100 nF) | RC filters before A0–A2 | Against ignition noise |
| Shielded 4-core cable, grommet, connectors, heat shrink | Engine bay → cabin | Keep away from the ignition coils |
| NPT thread sealant | Leak-free | |

## Wiring (ADS1115 #1, address 0x48)

```
Pi 3V3 (pin 1) ──┬────────────────────────────────────────── ADS1115 VDD
                 ├── R_fixed ──┬── temp sender ── ground (pole 2 / engine)
                 │             └── 1k ─┬─ A0          (RC: 100 nF to GND)
                 └───────────────────────────────────────── A3   3V3 reference

Pi 5V (pin 2) ───┬────────────────────────────────────────── pressure sender +5V
                 └── 10k ──┬── 10k ── GND
                           └── 1k ─┬─ A2  5 V reference (= 5 V / 2)
pressure signal ── 10k ──┬── 20k ── GND
                         └── 1k ─┬─ A1  (= signal × 2/3, max 3.0 V)
pressure sender GND ─────────────────────────────────────── Pi GND

Pi GND (pin 6) ── ADS1115 GND, ADDR     Pi SDA (pin 3) ── SDA     Pi SCL (pin 5) ── SCL
```

- **Ratiometric:** temperature is measured against 3V3 (A3), pressure
  against 5 V (A2). Supply drift cancels out; the software uses these
  reference channels.
- **Ground:** a single-pole temperature sender returns through the engine
  block; an offset between engine ground and Pi ground at running engine
  shifts the reading. A 2-pole sender avoids it. The 3-wire pressure sender
  has its own ground wire and is not affected.

## Phases

### 0 — Parts
1. Choose the adapter, confirm both threads, then order the senders.
2. Keep the datasheets (temperature curve; pressure range and output).

### 1 — Bench (Pi, no car)
1. Enable I²C: `sudo raspi-config` → Interface → I2C (or
   `dtparam=i2c_arm=on` in `/boot/firmware/config.txt`), reboot.
2. `sudo apt install i2c-tools`, `i2cdetect -y 1` → **48** must appear.
3. `pip install smbus2`.
4. **Temperature:** measure the sender at room temperature and in hot water
   **with a kitchen thermometer** (water boils at about 98.5 °C in Zurich,
   not 100). Choose `R_fixed` ≈ sender resistance at ~100 °C. Then
   `py tools/oil_sensor_cal.py beta <T1> <R1> <T2> <R2>`.
5. **Pressure:** sender unpressurised must read ~0.0 bar (output ≈ 10 % of 5 V).
6. Live check of all channels:
   `python3 tools/oil_sensor_cal.py read --r-fixed <R> --r0 <..> --t0 <..> --beta <..>`

### 2 — Install (engine bay)
1. Oil filter off, adapter on, senders in with sealant, filter back on
   (torques per adapter/filter maker).
2. Run the engine, check for leaks, check the oil level.
3. Shielded cable away from the ignition coils and exhaust, through a
   firewall grommet into the cabin.

### 3 — Configure
`~/.rx8_headunit/config.json`:
```json
"oil_sensors": {
  "source": "ads1115",
  "temp":     {"r_fixed": 470, "r0": 2500, "t0": 20, "beta": 3450},
  "pressure": {"p_max_bar": 10}
}
```
(Example numbers — use your own from phase 1. Channels and dividers default
to the wiring above.) For development without hardware: `"source": "simulated"`.

### 4 — Baseline drive and low-pressure warning
The warning method comes from the MX-5 NA rule of thumb: a healthy warm idle
sits around 1.8–2.2 bar there, and a warm idle below its normal minimum is
the first sign of trouble. The RX-8's numbers are different, so they are
**measured, not assumed**:

1. Log several drives with the senders in (`oil_sensors` values are part of
   the head unit's data; recording to CSV follows).
2. Derive the RX-8 baseline:
   - **warm idle** pressure: coolant ≥ 80 °C, rpm < 1,200, engine running > 10 min
   - **~3,000 rpm** pressure with hot oil — Mazda's reference for the
     2008 standard-power 13B-MSP is 350 kPa (3.5 bar) at 3,000 rpm with oil at
     100 °C (2009 Service Highlights)
3. Then implement the warning in the head unit:
   - **critical:** engine running and pressure < ~0.5 bar → immediate alarm
   - **low:** warm idle below the measured baseline minimum
   - **drift:** warm-idle average trending down over weeks (service metric)
   The gauge's colour zones only cover the high end today; the low-pressure
   warning will be a separate alert, not a colour zone.

### 5 — Oil level light (later)
Tap the factory low-oil-level warning signal (float sensor in the sump) with
an optocoupler into a Pi GPIO, so the head unit can show and log it.
Needs research: where the signal runs and its voltage level.

## Software (done, 5 Nov 2026)

| File | What |
|---|---|
| `core/oil_sensors.py` | `OilSensorSource`: reads ADS1115 every 0.25 s in a daemon thread (UI never blocks); temperature via beta model, pressure ratiometric; 1 s smoothing; detects open/short/unplugged per sensor → N/A with message; temperature and pressure work independently (e.g. pressure runs while temperature is not yet calibrated); `simulated` mode |
| `core/data_manager.py` | Lays OIL_TEMP and OIL_PRESSURE over the main source (OBD live, replay, simulation) |
| `screens/gauge_screen.py` | 7 gauges, 4 columns: RPM, coolant, oil temp, oil pressure / speed, throttle, load |
| `tools/oil_sensor_cal.py` | Beta from two points, Ω → °C, live readout of all four ADC channels on the Pi |
| `core/app_state.py` | Config block `oil_sensors` (default `off`) |

## Later: listen-only on the car's CAN bus

A CAN HAT in listen-only mode never transmits, only reads the RX-8's own
broadcasts (rpm, speed, coolant …) — likely much faster than OBD polling
(~2.2 s per value with the clone). Needs the RX-8 CAN IDs researched first.
Never transmit onto the car's bus.
