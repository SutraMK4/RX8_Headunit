# RX-8 Head Unit — Project Instructions for Claude

Read this first. It reflects the decisions as of 3 Nov 2026 and supersedes
the June 2026 version (Pi 5 8 GB + NVMe, DSI screen, Mausberry PSU and
OpenAuto Pro are all **no longer the plan**).

## Who and how we work

- Owner: Roger Suter. Claude acts as technical lead: architecture, hardware
  selection, wiring, integration, documentation.
- Deliver complete, runnable files, not fragments. Keep `README.md` and this
  file in sync with the code whenever behaviour or structure changes.
- Roger does the visual design pass himself (`core/theme.py`, screen
  layouts). Claude handles technical scaffolding and integration.
- Roger is new to git: give explicit, copy-pasteable commands for Windows
  PowerShell and Raspberry Pi OS.
- Do not state hardware facts from memory. If unsure, say so and put it on
  the verification backlog below.

## Goal

Replace the factory 7" tilt/pop-out nav unit in a **2004 Mazda RX-8 Grand
Touring** (yellow, 6-port 238 hp, 6-speed manual) with a Raspberry Pi 5 and a
7" touchscreen:

- Live OBD-II gauges
- Android Auto (OpenDash) as the main nav and audio source when the phone
  (Android) is connected
- Offline navigation fallback: Organic Maps, Switzerland map
- Audio/source UI and settings
- Keep the Bose amp (Metra 70-7552), steering wheel controls and the factory
  tilt mechanism
- Offline-first: no SIM, no reliance on internet

## Hardware (decided, not yet ordered)

| Part | Choice | Notes |
|---|---|---|
| SBC | Raspberry Pi 5, 4 GB | 8 GB unnecessary |
| Storage | Transcend ESD320A 500 GB USB SSD | Via the hub. NVMe HAT ruled out |
| Display | Waveshare 7" HDMI IPS 1024×600, capacitive | HDMI video + USB touch |
| OBD | OBDLink SX (USB, STN chip) | OBD-II port under dash, driver side |
| GPS | GlobalSat BU-353-S4 USB puck | gpsd on the Pi |
| USB hub | Anker 4-port powered | Own 12V→5V 3 A supply |
| Pi power | 12V→5V 5 A buck, USB-C | **Product not chosen**, see backlog |
| Audio | Metra 70-7552 Bose retention harness | |
| Steering controls | PAC SWI-RC | **Approach unverified**, see backlog |
| Tilt motor | Factory mechanism + L298N | Current draw / end stops unmeasured |

Power: one ignition-switched 12V tap (add-a-fuse) feeding two separate buck
converters, one for the Pi, one for the hub. Data: HDMI to screen, screen
USB touch back to the Pi, one USB 3.0 cable Pi→hub; hub carries SSD,
OBDLink SX and GPS.

## Software stack

| Layer | Technology |
|---|---|
| UI | Python 3 + PyQt5 |
| OBD | python-obd (`obd.Async`) via `core/data_sources.py` |
| Android Auto | OpenDash (openDsh/dash), built from source |
| Offline nav | Organic Maps launched as a subprocess |
| GPS | gpsd + gpsd-py3 |
| Config | JSON at `~/.rx8_headunit/config.json` |
| GPIO | gpiozero (tilt, ignition sense — not written yet) |

### Dev environment

- Master copy: `F:\VM_STUFF\RX8_Code` on the desktop, pushed to the
  private GitHub repo `SutraMK4/RX8_Headunit`. Other machines clone from
  GitHub.
- The app runs directly on Windows (`py main.py`) and in the VirtualBox VM
  (Raspberry Pi Desktop, Bullseye i386; VM at `F:\VM_STUFF\MAZDA RX8 HeadUnit\`,
  shared folder mounted with `sudo mount -t vboxsf RX8_Code /media/RX8_Code`).
- Target is a 64-bit Pi 5 on Bookworm: bench-test on the real Pi early.

## Code structure

```
main.py                 AppState → DataManager → MainWindow, starts data
obd_gauges.py           GaugeWidget; set_value(None) shows N/A
core/app_state.py       config (deep-copied defaults), get()/set(), save
core/data_sources.py    SimulatedSource, LiveSource, EmulatorSource, ReplaySource
core/data_manager.py    one active source; values_updated / status_changed
core/diagnostics.py     logging, timed(), record_error(), UI-stall watchdog
core/event_store.py     SQLite events.db: distinct events, sessions, metrics
core/gps.py             gpsd reader in a daemon thread (fix_changed signal)
core/theme.py           design constants (SCREEN_W/H = 1024×600)
screens/*.py            home, gauges, navigation, audio, settings, main window
screens/debug_panel.py  debug window: metrics, UI stalls, errors, log (D key)
tools/obd_logger.py     scan supported PIDs, record CSV for replay
tools/run_emulator.py   ELM327-emulator launcher with Windows disconnect fix
samples/                small CSV recorded from ELM327-emulator
```

### Diagnostics and the UI-thread rule

- **Never block the UI thread** with network, serial, subprocess or file
  waits. Use a daemon thread and a Qt signal (pattern: `core/gps.py`,
  `_ConnectWorker` and `LiveSource._close` in `core/data_sources.py`).
  History: gpsd was polled on the UI thread every 2 s; on Windows a refused
  connection takes ~1 s, so the UI froze periodically. Closing the OBD
  connection also blocked the UI ~0.4 s. Both moved to background threads.
- Wrap anything worth measuring in `with timed("area.action"):` and call
  `record_error("area.action", e)` in except blocks. Metrics record the
  thread; slow UI-thread work shows red in the debug panel.
- `diagnostics.install()` sets `sys.excepthook` / `threading.excepthook`:
  uncaught exceptions are logged with stack and the app keeps running.
- The stall watchdog (250 ms, config `debug.stall_ms`) records the UI
  thread's stack during every freeze. Ask Roger for COPY REPORT from the
  debug panel when he reports lag or errors.
- Records: `~/.rx8_headunit/events.db` is the long-term history: one row
  per *distinct* WARNING+ event (fingerprint = level + logger + message with
  numbers replaced by # + last stack frame), with count / sessions / first
  and last seen / stack. Sessions table has `clean_exit`; a cut-off session
  is reported at next start (with faulthandler crash dump if any). Metrics
  per session are stored at clean exit. Retention 90 days.
- Text log `logs/headunit.log` is short-term: new file per session, last 3
  sessions kept, RepeatFilter suppresses >3 identical messages per minute.
  Ask Roger for EXPORT CSV (EVENTS tab) or COPY REPORT when debugging.
- python-obd adds its own console handler (double printing);
  `adopt_obd_logger()` removes it after `import obd`. pint's "Redefining"
  warnings are silenced.
- `py main.py --debug` = verbose + panel open.

### Data layer contract

- `DataManager` (on `state.data`) emits `values_updated(dict)` with
  `{python-obd command name: float | None}` and
  `status_changed(kind, status, detail)`.
- `None` = not available. Gauges show N/A; never substitute fake values
  when a real source is selected.
- `LiveSource` connects in a daemon thread, then `watch()`es every supported
  command before `start()`. Querying an un-watched command on `obd.Async`
  returns an empty response (this was the original bug).
- Emulator over TCP needs a fixed baudrate (38400); python-obd cannot
  detect one on a socket. `EmulatorSource` does this.
- Start the emulator with `tools/run_emulator.py`, not plain `elm -n 35000`.
  ELM327-emulator only handles ConnectionResetError; on Windows a client
  disconnect is ConnectionAbortedError (WinError 10053), after which plain
  `elm` loops on that error and never accepts another client. Plain `elm`
  also writes a DEBUG trace of every request (~2,600 lines/min) to `elm.log`
  in the current folder; the launcher logs WARNING+ to
  `~/.rx8_headunit/logs/emulator.log` instead (`--emu-verbose` for DEBUG).
- `state.obd_status` is a short summary for the home screen
  (simulated / live / emulator / replay / connecting / error / stopped).
- Add a gauge: append to `GAUGE_CONFIGS` with a `key`; nothing else needed.

## Screen status

| Screen | Status |
|---|---|
| Home | Working |
| Gauges | Working with all four sources (tested against ELM327-emulator) |
| Navigation | Launches Organic Maps, gpsd in background thread, NO FIX fallback. RECALC/NORTH stubs |
| Audio | Skeleton: TODO stubs for OpenDash, volume, source switching, playback |
| Settings | Working. Data source section; brightness is a TODO |

## Decisions and ruled out

- OpenAuto Pro: ruled out (vendor acquired, product discontinued) → OpenDash.
- NVMe HAT: ruled out (wrong form factor for the drive, no real gain).
- Tile server / QWebEngineView map: ruled out for now; Organic Maps subprocess
  is the fallback, Android Auto is the main nav.
- Pi 5 4 GB is sufficient.
- Live OBD failure shows errors and N/A; it does not silently fall back to
  simulation.

## Verification backlog (do not treat as fact)

1. **PAC SWI-RC → Pi.** The SWI-RC makes an aftermarket-stereo remote signal;
   it is not a USB/serial device and the Pi has no analog input. Likely
   alternative: read the RX-8 steering wheel resistor ladder via an ADC
   (e.g. ADS1115 over I²C). Check the SWI-RC manual and RX-8 SWC wiring first.
2. **Graceful shutdown.** Hard power cut on an SSD-booted Pi risks
   corruption. Needs ignition-sense GPIO + hold-up (supercap / small UPS /
   delay) or a read-only root. Decide ACC vs IGN vs constant + sense.
3. **Pi power supply product.** Pick a real product from its datasheet:
   wide 12V input with automotive surge tolerance, 5V ≥ 5 A, Pi 5 connection.
4. **Display config.** Legacy `hdmi_group/hdmi_mode/hdmi_cvt` is probably
   ignored on Pi 5 Bookworm; likely `video=HDMI-A-1:1024x600@60` in
   `cmdline.txt`. Check the Waveshare model's own instructions.
5. **OpenDash build** on Pi 5 / Bookworm: follow current upstream docs.
6. **Organic Maps on Linux arm64**: confirm a build exists (AppImage vs
   Flatpak). `_find_organic_maps()` already checks native, AppImage, Flatpak;
   the download URL in `navigation_screen.py` is a guess.
7. **Serial port naming.** Use `/dev/serial/by-id/` or udev rules for the
   OBDLink SX and GPS, never "ttyUSB0 comes first".
8. **RX-8 factory GPS antenna connector**: unverified, ignore until the puck
   has been tested in the car.
9. **Oil temp over OBD (PID 0x5C)**: may not be supported on the RX-8. Run
   `tools/obd_logger.py scan`; the gauge already shows N/A if not.
10. **VM vs target.** VM is 32-bit x86 Bullseye; target is 64-bit Bookworm.

## Project plan

**Phase 0 — dev environment.** Done on the desktop. Laptop: re-clone from
GitHub, install Python from python.org (tick "Add to PATH"),
`py -m pip install -r requirements.txt`.

**Phase 1 — OBD pipeline.** Done: data-source layer, emulator test, N/A
handling, replay, logger. Remaining: run `obd_logger.py scan` and record
idle + drive logs in the RX-8; decide which gauges stay based on the scan.

**Phase 2 — software.** Audio screen (OpenDash launcher, same subprocess
pattern as navigation, source switching); settings brightness and GPS port by
`/dev/serial/by-id/`; navigation install on the Pi; systemd autostart;
graceful shutdown on ignition-off.

**Phase 3 — procurement.** Resolve backlog items 1–3 first, then order.

**Phase 4 — bench bring-up on the Pi.** Bookworm 64-bit on the SSD, display
config, gpsd, OBDLink, Organic Maps, OpenDash.

**Phase 5 — car install.** Fuse tap and power, ignition sense, SWC
interface, tilt motor, GPS placement, Bose harness, mounting.

**Phase 6 — polish.** Roger's design pass, real-world testing.

## Open questions for Roger

- 12V source: ACC, IGN, or constant + ignition sense?
- Keep factory steering wheel controls via an ADC instead of the PAC unit?
- Physical space: where do the Pi and hub sit, how much depth behind the screen?

## Known cosmetic debt

- Gauge tick labels clip at the bottom of the arc; unit labels overlap the
  bottom ticks (`obd_gauges.py`).
- Fullscreen checkbox in Settings has no visible box with the current style.
