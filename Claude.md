# RX-8 Head Unit — Project Summary & Claude Code Handoff

## Project Goal

Replace the factory 7" tilt/pop-out navigation unit in a **2004 Mazda RX-8 Grand Touring** (yellow, 187th produced, 6-port 238hp, 6-speed manual) with a custom Raspberry Pi 5-based head unit. The replacement must fit the factory DIN slot, retain the motorised tilt mechanism, and integrate with the existing Bose 9-speaker audio system via a retention harness.

### Build priorities (in order)
1. Modern offline navigation
2. Android Auto / Apple CarPlay
3. OBD/ECU gauge display
4. Audio quality upgrade

---

## Hardware Decisions (Finalised)

| Component | Part | Purpose |
|---|---|---|
| Computer | Raspberry Pi 5 8GB + NVMe SSD | Main compute |
| Screen | Waveshare 7" DSI touchscreen | Direct Pi DSI connection, fits factory DIN |
| Power | Mausberry ignition-aware PSU | Clean shutdown on ignition off |
| OBD adapter | OBDLink SX (USB) | Reads engine data via OBD-II port |
| Audio harness | Metra 70-7552 | Retains Bose amplifier and speakers |
| Tilt motor | Factory motor + L298N driver | Pi GPIO controls factory tilt mechanism |
| Steering controls | PAC SWI-RC | Translates factory steering wheel buttons |
| CarPlay/AA | OpenAuto Pro | Licensed Android Auto / Apple CarPlay |

### OBDLink SX — What it is
A USB OBD-II adapter using a genuine STN1110 chip (not a cheap ELM327 clone). Plugs into the RX-8's OBD-II port under the dash (driver's side) and connects to the Pi via USB. Translates the car's OBD-II protocol into serial data readable by `python-obd`. Chosen over clones for reliability, consistent timing, and zero Bluetooth pairing issues on Linux/Pi.

---

## Software Stack

| Layer | Technology |
|---|---|
| UI framework | Python 3 + PyQt5 |
| OBD data | python-obd (async) |
| Maps | TBD — Navit / QWebEngineView + OSM tiles |
| CarPlay/AA | OpenAuto Pro |
| Config persistence | JSON (`~/.rx8_headunit/config.json`) |
| GPIO | gpiozero |

### Development Environment
- Oracle VirtualBox — Raspberry Pi Desktop (Bullseye i386)
- VM location: `F:\VM_STUFF\MAZDA RX8 HeadUnit\`
- Shared folder: `F:\VM_STUFF\RX8_Code\` ↔ `/media/RX8_Code/` in VM
- Packages installed: `python3`, `PyQt5`, `python-serial`, `git`, `python-obd`, `gpiozero`
- Guest Additions: kernel module loaded (`vboxguest`), manual mount required on boot:
  ```bash
  sudo mount -t vboxsf RX8_Code /media/RX8_Code
  ```

---

## What Has Been Built

### 1. `obd_gauges.py` — Standalone gauge widget ✅

A PyQt5 analogue gauge cluster with three gauges (RPM, Coolant Temp, Oil Temp) using simulated data. This file is the foundation for all gauge rendering.

**Features:**
- Custom-drawn analogue gauges via `QPainter` — no external gauge libraries
- Smooth needle animation via lerp (60fps `QTimer`)
- Colour zones: normal (Mazda red arc) → orange warning → red danger
- Bezel glow effect when entering warning zone
- Digital readout below needle
- Realistic simulation: engine warm-up behaviour, sinusoidal RPM sweeps, oil temp lags coolant
- `F` = fullscreen toggle, `Q`/`Esc` = exit
- `set_value(v)` is the only method needed to feed live OBD data

**Gauge config structure** (add new gauges by appending to `GAUGE_CONFIGS`):
```python
{
    "label":   "RPM",
    "unit":    "×1000",
    "min":     0,
    "max":     9000,
    "warn":    7000,
    "danger":  8000,
    "step":    1000,
    "minor":   5,
    "fmt":     lambda v: f"{v/1000:.1f}",
    "obd_cmd": "RPM",           # python-obd command name
    "scale":   lambda v: v.magnitude,  # converts pint Quantity to float
}
```

---

### 2. `rx8_headunit/` — Main application skeleton ✅

Full multi-screen PyQt5 application. Run with `python3 main.py` from the project root (where `obd_gauges.py` also lives).

#### Project structure
```
rx8_headunit/
├── main.py
├── obd_gauges.py          ← copy here from root
├── core/
│   ├── app_state.py
│   ├── obd_manager.py
│   └── theme.py
└── screens/
    ├── main_window.py
    ├── home_screen.py
    ├── gauge_screen.py
    ├── navigation_screen.py
    ├── audio_screen.py
    └── settings_screen.py
```

#### `core/app_state.py`
Central shared state passed to every screen. Holds:
- `config` dict (loaded from / saved to `~/.rx8_headunit/config.json`)
- `obd_connection` — the live `obd.Async` object (set by OBDManager)
- `obd_status` — `"disconnected"` | `"connecting"` | `"connected"` | `"error"`
- `current_screen` — name of active screen
- `get(*keys)` / `set(*keys, value)` — nested config accessors
- `save_config()` — persists to JSON

#### `core/obd_manager.py`
Runs OBD connection in a `QThread`. Emits:
- `status_changed(str)` — UI can react without blocking
- `connection_ready(object)` — fires with the `obd.Async` connection

Connection flags: `fast=False, timeout=30` (recommended for RX-8).

#### `core/theme.py`
**Single file for all visual design.** Every colour, font, and size constant lives here. Change this file to restyle the entire application. Key constants: `BG_PRIMARY`, `ACCENT` (Mazda red `#c0392b`), `TEXT_PRIMARY`, `WARN_ORANGE`, `WARN_RED`, `SUCCESS_GREEN`.

#### `screens/main_window.py`
Root `QMainWindow`. Contains:
- `QStackedWidget` holding all five screens
- `NavBar` — bottom navigation bar with five buttons + clock
- `switch_screen(name)` — called by nav buttons and child screens
- Keyboard shortcuts: `1`–`5` = switch screens, `F` = fullscreen, `Esc` = home

#### `screens/home_screen.py`
Dashboard with four quick-launch tiles (Gauges, Nav, Audio, Settings), OBD connection status, and Pi CPU temperature. Status refreshes every 2 seconds.

#### `screens/gauge_screen.py`
Hosts six `GaugeWidget` instances in a 3×2 grid:

| Gauge | OBD command | Warning | Danger |
|---|---|---|---|
| RPM | `RPM` | 7,000 | 8,000 |
| Coolant Temp | `COOLANT_TEMP` | 105°C | 118°C |
| Oil Temp | `OIL_TEMP` | 120°C | 135°C |
| Speed | `SPEED` | 220 km/h | 250 km/h |
| Throttle | `THROTTLE_POS` | 95% | 100% |
| Engine Load | `ENGINE_LOAD` | 90% | 100% |

Automatically switches between simulated data and live OBD data depending on `state.obd_status`. Status strip in top-right corner shows `OBD: SIMULATED` (orange) or `OBD: LIVE` (green).

#### `screens/navigation_screen.py`
Skeleton with:
- Top bar: GPS status, search placeholder, speed readout
- `MapPlaceholder` frame — replace with actual map widget
- Bottom controls: Back, Home, Recalc, North-up, GPS centre

**Integration path options:**
- **Option A**: Navit as subprocess, embed via `QWindow.fromWinId()`
- **Option B**: `QWebEngineView` + local OSM tile server (offline tiles)
- **Option C**: PyQt5 + Leaflet.js in embedded Chromium

#### `screens/audio_screen.py`
Skeleton with:
- Now Playing card (album art placeholder + metadata)
- Source selector: AUX / USB / Bluetooth / FM Radio / Android Auto
- Volume slider (wired to `state.config`, ready for `amixer`/`pulsectl`)
- Playback controls (⏮ ⏪ ⏯ ⏩ ⏭ — wired to TODO stubs)

#### `screens/settings_screen.py`
Six scrollable sections, all wired to `AppState`:

| Section | Controls |
|---|---|
| OBD | Port (combo), Connect / Disconnect / Scan PIDs buttons, live status label |
| Display | Brightness slider, screen timeout combo, fullscreen toggle |
| Audio | Default volume slider |
| Navigation | Maps path (text), GPS device (combo), units (metric/imperial) |
| Startup | Default screen (combo), fullscreen on boot (checkbox) |
| System | Pi temp readout, hostname field, Reboot / Shutdown buttons |

**Save All Settings** button writes everything to `~/.rx8_headunit/config.json`.

---

## OBD-II — Available PIDs on RX-8

Full python-obd docs: https://python-obd.readthedocs.io/en/latest/
Full command table: https://python-obd.readthedocs.io/en/latest/Command%20Tables/

### Confirmed available on RX-8 2004 (standard OBD-II Mode 01)

| Command | Description | Display use |
|---|---|---|
| `RPM` | Engine RPM | ✅ Gauge |
| `COOLANT_TEMP` | Coolant temperature | ✅ Gauge |
| `OIL_TEMP` | Oil temperature (PID 5C — verify on car) | ✅ Gauge |
| `SPEED` | Vehicle speed km/h | ✅ Gauge |
| `THROTTLE_POS` | Throttle position % | ✅ Gauge |
| `ENGINE_LOAD` | Calculated engine load % | ✅ Gauge |
| `INTAKE_TEMP` | Intake air temperature | Future gauge |
| `MAF` | Mass air flow g/s | Future gauge |
| `TIMING_ADVANCE` | Ignition timing °BTDC | Future gauge |
| `FUEL_LEVEL` | Fuel tank % | Future gauge |
| `INTAKE_PRESSURE` | Manifold pressure kPa | Future gauge |
| `SHORT_FUEL_TRIM_1` | Short term fuel trim % | Diagnostic |
| `LONG_FUEL_TRIM_1` | Long term fuel trim % | Diagnostic |
| `O2_B1S1` / `O2_B1S2` | O2 sensor voltages | Diagnostic |
| `GET_DTC` | Fault codes | Diagnostic |
| `ELM_VOLTAGE` | Battery voltage from OBD port | Info |

**Note on OIL_TEMP:** The RX-8 factory oil temp gauge runs off a dedicated sensor. PID 5C may return null — run `connection.supported_commands` after first connection to confirm.

### PID scan (run after first OBD connection)
```python
import obd
connection = obd.OBD()
print(connection.supported_commands)
```

### ECU extras (no stock ECU mods needed for above)
Standard OBD-II covers everything in the table above — no ECU modification required. The OBDLink SX reads what the stock ECU already broadcasts.

For future extras: wideband AFR needs an AEM X-Series wideband kit; EGT needs a MAX31855 thermocouple amplifier on Pi GPIO. Both are analogue additions, not ECU modifications.

---

## TODO Map (Integration Hooks)

Search `# TODO` in the codebase. Key integration points:

| File | TODO | What to wire |
|---|---|---|
| `navigation_screen.py` | Map widget | Navit / QWebEngineView / OSM |
| `navigation_screen.py` | GPS | gpsd or direct serial `/dev/ttyUSB0` |
| `audio_screen.py` | Volume | `amixer` or `pulsectl` library |
| `audio_screen.py` | Source switching | Hardware relay or software routing |
| `audio_screen.py` | Playback | python-vlc or mpd client |
| `settings_screen.py` | Brightness | `rpi-backlight` or `xrandr` |
| `obd_manager.py` | Ready to use | Just needs OBDLink SX plugged in |

---

## Known Issues / Cosmetic Debt

- Gauge tick labels clip at the bottom of the arc (8.0/9.0 on RPM, 120–150 on temp gauges) — arc needs scaling in slightly
- Unit labels (×1000, °C) overlap bottom tick marks — needs vertical offset adjustment
- VirtualBox shared folder requires manual mount on each VM boot (`sudo mount -t vboxsf RX8_Code /media/RX8_Code`) — add to `/etc/fstab` to automate
- `vboxsf` group not present (Guest Additions not fully installed) — drag-and-drop file transfer not working; use shared folder method

---

## Next Steps (Suggested Order)

1. **Get launcher running** — copy all files to `F:\VM_STUFF\RX8_Code\rx8_headunit\`, run `python3 main.py`
2. **Design pass** — restyle via `core/theme.py` and individual screen files
3. **Fix gauge label clipping** — cosmetic fix in `obd_gauges.py`
4. **Wire OBD** — plug in OBDLink SX, use Settings → OBD → Connect, verify PID scan
5. **Navigation** — decide on map solution, integrate into `MapPlaceholder`
6. **Audio** — wire volume to `amixer`, implement source switching
7. **Real hardware** — migrate from VM to actual Raspberry Pi 5
8. **Tilt motor** — implement GPIO control via L298N in a new `core/tilt_manager.py`
9. **Steering wheel controls** — PAC SWI-RC integration
10. **OpenAuto Pro** — CarPlay/Android Auto overlay or tab integration
