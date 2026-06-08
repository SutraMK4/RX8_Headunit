# RX-8 Head Unit — Project Structure

## Run
```bash
# From project root (where main.py lives):
python3 main.py

# obd_gauges.py must be in the same directory as main.py
```

## Project layout
```
rx8_headunit/
├── main.py                      # Entry point
├── obd_gauges.py                # Gauge widgets (copy from previous session)
│
├── core/
│   ├── app_state.py             # Shared state + config (JSON persistence)
│   ├── obd_manager.py           # OBD connection thread
│   └── theme.py                 # All colours, fonts, sizes — edit here for design
│
└── screens/
    ├── main_window.py           # Root window + bottom nav bar
    ├── home_screen.py           # Dashboard / quick launch tiles
    ├── gauge_screen.py          # OBD gauge cluster (6 gauges)
    ├── navigation_screen.py     # Map placeholder — wire your map lib here
    ├── audio_screen.py          # Source selector, volume, playback
    └── settings_screen.py       # All config sections + save/reboot/shutdown
```

## Config
Saved automatically to `~/.rx8_headunit/config.json` when you hit Save in Settings.

## Keyboard shortcuts (dev)
| Key | Action |
|-----|--------|
| 1–5 | Switch screens |
| F   | Toggle fullscreen |
| Esc | Go to Home |

## Adding gauges
Edit `GAUGE_CONFIGS` list in `screens/gauge_screen.py`.
Each entry needs: label, unit, min, max, warn, danger, step, minor, fmt, obd_cmd, scale.

## TODO markers
Search for `# TODO` across the codebase — each marks an integration point:
- `navigation_screen.py` — map library integration
- `audio_screen.py`      — amixer/pulsectl volume, source switching
- `settings_screen.py`   — brightness control (rpi-backlight or xrandr)
- `obd_manager.py`       — already functional, just needs OBDLink plugged in
