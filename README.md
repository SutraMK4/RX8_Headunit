# RX-8 Head Unit

PyQt5 head unit for a 2004 Mazda RX-8, running on a Raspberry Pi 5 with a
7" 1024×600 touchscreen. Live OBD gauges, offline navigation (Organic Maps)
as a fallback, Android Auto via OpenDash, audio and settings screens.

## Run

From the project root (where `main.py` lives):

```powershell
# Windows
py -m pip install -r requirements.txt
py main.py
```

```bash
# Raspberry Pi / Linux
python3 -m pip install -r requirements.txt
python3 main.py
```

Settings are saved to `~/.rx8_headunit/config.json` (on Windows:
`C:\Users\<you>\.rx8_headunit\config.json`) when you press **Save** or
**Apply** in Settings.

## Project layout

```
main.py                      Entry point: AppState, DataManager, MainWindow
obd_gauges.py                GaugeWidget (QPainter gauge). Also runs standalone.
core/
  app_state.py               Shared state + config (JSON persistence)
  data_sources.py            Simulated / Live / Emulator / Replay sources
  data_manager.py            Owns the active source, forwards its signals
  diagnostics.py             Logging, timings, error capture, UI-freeze watchdog
  fonts.py                   Loads the bundled fonts (assets/fonts)
  event_store.py             SQLite history of distinct events, sessions, metrics
  gps.py                     gpsd reader in a background thread
  theme.py                   All colours, fonts, sizes — edit here for design
screens/
  main_window.py             Root window + bottom nav bar
  home_screen.py             Dashboard tiles, data status, Pi temp
  gauge_screen.py            Six gauges, GAUGE_CONFIGS
  navigation_screen.py       Launches Organic Maps, gpsd status
  audio_screen.py            Source/volume/playback UI (skeleton, TODOs)
  settings_screen.py         Data source, display, audio, nav, startup, system, diagnostics
  debug_panel.py             Debug window (metrics, UI stalls, errors, log)
tools/
  obd_logger.py              Scan the car's PIDs, record OBD data to CSV
  run_emulator.py            ELM327-emulator launcher with a Windows disconnect fix
  fetch_figma_assets.py      Downloads a Figma frame's SVG assets into assets/<screen>/
assets/
  fonts/                     Bundled fonts + OFL licences
  home_v2/                   SVGs for the v2 home screen (from Figma)
samples/
  emulator_sample.csv        Short recording from ELM327-emulator (for Replay)
images/                      Logos
```

## Where gauge data comes from

Gauges never talk to OBD directly. `DataManager` runs one *data source* and
the gauge screen draws whatever it sends. Pick the source in
**Settings → Data source**, then press **Apply**.

| Source | What it does | Needs |
|---|---|---|
| `simulated` | Fake warm-up and rev sweeps (default) | nothing |
| `live` | Real car through the OBDLink SX | adapter plugged in, ignition on |
| `emulator` | Same code path as `live`, against ELM327-emulator | `py tools/run_emulator.py` running |
| `replay` | Plays a recorded CSV back (speed 0.5×–10×, loop) | a CSV from `tools/obd_logger.py` |

A value the source cannot deliver (PID not supported by the car, empty CSV
cell, not connected) shows as **N/A** on the gauge instead of a fake number.
The strip above the gauges shows the source, its status and which values are N/A.

### Testing the live code path without the car

```powershell
py -m pip install ELM327-emulator
py tools/run_emulator.py     # leave this terminal open
```

Use `tools/run_emulator.py` rather than plain `elm -n 35000`, especially on
Windows. Plain `elm` gets stuck after the first client disconnects (endless
`[WinError 10053] An established connection was aborted` and no new
connections), and it writes a DEBUG trace of every request into `elm.log`
files in the current folder. The launcher fixes the first and logs only
warnings to `~/.rx8_headunit/logs/emulator.log` (`--emu-verbose` for the
full trace).

In the head unit: Settings → Source `emulator`, address
`socket://localhost:35000`, **Apply**. The emulator does not report oil
temperature, so that gauge shows N/A (that is expected).

### Recording from the car

Ignition on, OBDLink SX plugged in:

```powershell
py tools/obd_logger.py scan --port COM5 --out logs/rx8_supported.txt
py tools/obd_logger.py record --port COM5 --out logs/rx8_idle.csv
```

Cheap ELM327 clones often fail python-obd's speed auto-detection (endless
`Failed to read port`). Give the speed explicitly: `--baud 38400` for the
logger, Settings → OBD baud → 38400 in the head unit.

On the Pi use the stable port path, e.g.
`--port /dev/serial/by-id/usb-ScanTool.net_OBDLink_SX_...` (Settings → OBD
port → Refresh lists what is plugged in). `scan` tells you which of the six
gauges the RX-8 can feed. Stop recording with Ctrl+C, then play it back with
the `replay` source.

CSV format: header `elapsed_s,RPM,COOLANT_TEMP,...`. Columns are python-obd
command names, values are plain numbers (rpm, °C, km/h, %), empty = no reading.

## Layouts (v1 / v2)

Two UI layouts exist side by side:

| | |
|---|---|
| `v1` | Original layout (default) |
| `v2` | "Night drive", implemented from Figma: new home screen and bottom bar |

Switch in **Settings → Display → Layout**, press Save, restart. Or for one run:

```powershell
py main.py --layout v2
```

So far only the home screen and the bottom bar have a v2 design; the other
screens use their v1 content under the v2 bar.

### Figma → code workflow

1. Design a frame in Figma, ideally at **1024 × 600** (the real screen).
2. Send Claude the frame link (right-click → Copy link to selection). Claude
   reads layout, colours, fonts, text and SVG assets through the Figma
   connector (Starter plan: 6 reads a month, about 1–2 per screen).
3. Run the asset download Claude prepares (Claude's workspace cannot reach
   figma.com, your PC can):
   ```powershell
   py tools/fetch_figma_assets.py home_v2
   ```
   SVGs land in `assets/<screen>/`. Figma's asset links expire after 7 days.
4. Claude builds the screen, renders it, compares it with the Figma
   screenshot.

Fonts are bundled in `assets/fonts/` (Orbitron, Rajdhani, IBM Plex Mono; all
SIL Open Font License, licence files next to them), so the UI looks the same
on Windows, the VM and the Pi.

## Debugging

Two kinds of records, both under `~/.rx8_headunit/` (Windows:
`C:\Users\<you>\.rx8_headunit\`):

| What | Where | Kept |
|---|---|---|
| **Event history**: every *distinct* warning, error, UI freeze and unclean exit, with count, first/last seen, number of sessions and stack trace. Plus one row per app session and per-session timing metrics | `events.db` (SQLite) | 90 days since last seen |
| **Text log**: short-term, "what just happened". Repeats are collapsed (same message more than 3× per minute is suppressed and summarised) | `logs/headunit.log` (+ `.1`, `.2`) | last 3 sessions, max 2 MB each; older files are deleted |

Repeats of an event only increase its count, so the history stays small. A
session that was cut off (crash or power loss) is detected at the next start
and recorded as an event, with the crash dump if there was one. Repeat counts
are written every 10 s, so a session that was cut off loses its last
unwritten repeat counts. New distinct events are written immediately.

Open the **debug panel** with the **D** key, Settings → Diagnostics, or:

```powershell
py main.py --debug        # verbose log + debug panel open at start
```

| Tab | Shows |
|---|---|
| EVENTS | The event history across sessions (from `events.db`). EXPORT CSV writes it to the logs folder |
| METRICS | This session: how long things take (count / last / avg / max ms) and on which thread. Red = slow work on the UI thread |
| UI STALLS | This session's UI freezes longer than 250 ms, with the exact code the UI was stuck in |
| ERRORS | This session's exceptions with full stack trace (the app keeps running) |
| LOG | Live tail of the text log |

**COPY REPORT** puts this session's metrics, stalls, errors and the last log
lines on the clipboard, ready to paste into a chat.

Query the history directly if you like (DB Browser for SQLite, or Python):

```sql
SELECT count, sessions, level, source, message, last_seen FROM events ORDER BY count DESC;
SELECT * FROM sessions WHERE clean_exit = 0;           -- crashes / power cuts
SELECT name, avg_ms, max_ms FROM metrics WHERE session_id = 12;
```

To time your own code:

```python
from core.diagnostics import timed, record_error

with timed("audio.set_volume"):
    ...
try:
    ...
except Exception as e:
    record_error("audio.set_volume", e)
```

Rule: never do network, serial or file-system waits on the UI thread. Use a
background thread and a Qt signal (see `core/gps.py`). The UI STALLS tab
tells you when this rule was broken.

## Adding a gauge

Append an entry to `GAUGE_CONFIGS` in `screens/gauge_screen.py`:

```python
{"label": "INTAKE", "unit": "°C", "min": -20, "max": 80, "warn": 60,
 "danger": 70, "step": 10, "minor": 2, "fmt": lambda v: f"{v:.0f}",
 "key": "INTAKE_TEMP"},          # python-obd command name
```

`key` is all the data layer needs; every source picks it up automatically.

## Keyboard shortcuts (dev)

| Key | Action |
|-----|--------|
| 1–5 | Switch screens |
| D   | Debug panel |
| F   | Toggle fullscreen |
| Esc | Go to Home |

## Open TODOs in the code

Search for `# TODO`:
- `audio_screen.py` — OpenDash launcher, volume (amixer/pulsectl), source switching
- `settings_screen.py` — brightness control
- `navigation_screen.py` — RECALC / NORTH are stubs (Organic Maps has no IPC)

See `Claude.md` for hardware, decisions and the project plan.
