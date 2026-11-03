# RX-8 OBD-II data guide

Two parts: where to get synthetic OBD-II data for testing the head unit without the car, and a step-by-step plan for recording real data from the RX-8.

Companion file: `obd_logger.py` (read-only scan and CSV logger, built on python-obd).

---

## Part 1: Synthetic OBD-II data

### Option A: ELM327-emulator (recommended first)

A Python program that pretends to be an ELM327 adapter plugged into a car. Your head unit talks to it exactly like it talks to the OBDLink SX, so the real python-obd code path gets tested (connection, PID queries, error handling), not just the simulated mode.

- PyPI: https://pypi.org/project/ELM327-emulator (current release 4.0.0)
- GitHub: https://github.com/Ircama/ELM327-emulator
- Install: `pip install ELM327-emulator`
- Default scenario `car` is a Toyota Auris Hybrid. It answers 97 commands and returns changing values.
- It has no OIL_TEMP, which is a useful test of the "unsupported gauge" path.
- It can also simulate trouble codes, and it can build a profile of a real car (see step 14 below), so you can later emulate your own RX-8 at your desk.

Tested in the sandbox on Linux: `python3 -m elm -b out.txt -s car` starts it, the first line of `out.txt` is the virtual port (for example `/dev/pts/0`), and `obd_logger.py scan --port /dev/pts/0` and `log` both worked against it (about 5 rows per second, values varying).

On Linux and in your VirtualBox VM: run it as above, then set the head unit's OBD port to the path it prints.

On Windows: there are no pseudo-terminals. Two routes, neither tested on Windows:
1. Run the emulator in WSL or in the VM and test the head unit there.
2. Use the emulator's `-p` option with a virtual COM port pair (for example com0com).

I also tried its TCP mode (`-n 35000`) with a `socket://127.0.0.1:35000` port. python-obd failed with "Failed to set baudrate", so that route does not work with python-obd as it is.

### Option B: Recorded datasets for a replay source

These are CSV files of real drives. They are useful for a Replay data source that feeds the gauges with realistic movement. None of them include oil temperature.

| Dataset | What is in it | Covers which of your 6 gauges | Link |
|---|---|---|---|
| LEVIN open data (Yuñ Solutions) | About 30 cars over 4 months, 1 Hz OBD. Includes engine load, coolant temp, RPM, OBD speed, throttle, MAF, timing advance and more | RPM, coolant, speed, throttle, engine load (5 of 6) | https://github.com/YunSolutions/levin-openData |
| Automotive OBD-II Dataset, M. Weber (KIT), CC BY 4.0 | Routes around Karlsruhe, labelled by traffic condition. Coolant temp, intake pressure, RPM, speed, intake air temp, MAF, throttle, ambient temp, pedal positions | RPM, coolant, speed, throttle (4 of 6) | https://service.tib.eu/ldmservice/vdataset/rdr-doi-10-35097-1130 |
| carOBD, Toyota Etios 2014 | 1 Hz logs split into idle, drive, live, campus and long trips. RPM, speed, throttle and more. Check columns before relying on it | RPM, speed, throttle (check others) | https://github.com/eron93br/carOBD |
| IoT Vehicle Telemetry (IEEE DataPort) | Three months of daily CSVs: speed, acceleration, RPM, throttle, fuel consumption, coolant temp. Download may need a free IEEE account | RPM, speed, throttle, coolant | https://ieee-dataport.org/documents/iot-vehicle-telemetry |

Check each dataset's licence before copying files into your repo. KIT is CC BY 4.0 (attribution required). I did not see licence terms for the others in what I read.

Suggested pick: start with the LEVIN CSVs for replay because they cover the most gauges.

### Option C: Your own RX-8 recording

Part 2 below. This is the only source that tells you what the RX-8 itself exposes, and it is the best replay data you will have.

---

## Part 2: Getting real data from the RX-8, step by step

Everything here is read-only. The script requests standard values only. It never clears trouble codes and never writes to the car.

### Before you go to the car (at your desk)

1. Install Python 3 from python.org on the laptop. Tick "Add Python to PATH" in the installer. Check with `python --version` in a new PowerShell window.
2. Install the library: `pip install obd`.
3. Put `obd_logger.py` in your repo, for example in a `tools/` folder, and create a `data/` folder next to where you will run it.
4. Plug the OBDLink SX into the laptop by itself. Open Device Manager, expand "Ports (COM & LPT)", and note the COM number (for example COM4). If no port appears, install the driver from OBDLink's support page.
5. Optional sanity check: if you have the emulator running (Part 1), run `python tools\obd_logger.py scan --port <emulator port>` to see the output format before you are in the car.

### In the car

6. Park outside or somewhere well ventilated. Do not run the engine in a closed garage.
7. Plug the OBDLink SX into the OBD-II port under the dash on the driver's side, then connect the USB cable to the laptop. Put the laptop where it will not move and will not distract you.
8. Turn the ignition on, engine off. Run the scan and keep the report:
   `python tools\obd_logger.py scan --port COM4 --out data\rx8_scan.txt`
   Read the result:
   - Protocol: expect CAN 11-bit 500 kbaud. Note it if it differs.
   - For each of the six gauge values, YES or NO. OIL_TEMP is the one most likely to say NO.
9. Short test log with the engine off, 20 seconds:
   `python tools\obd_logger.py log --port COM4 --seconds 20 --out data\rx8_test.csv`
   Open the CSV. You should see RPM 0, a coolant temperature, battery voltage. If most columns are empty, stop and check the scan output.
10. Cold-start idle log. Start the engine and let it idle while recording a warm-up (5 to 10 minutes):
    `python tools\obd_logger.py log --port COM4 --seconds 600 --out data\rx8_2026-11-02_idle.csv`
11. Driving log, with a passenger operating the laptop. The driver does not touch it. Start the log before you move:
    `python tools\obd_logger.py log --port COM4 --out data\rx8_2026-11-02_drive.csv`
    Drive 15 to 30 minutes on public roads within the speed limits, with some stop-and-go, steady cruising, and a few full gear changes. Press Ctrl+C when parked. Turn off laptop sleep before you start, or the log will stop.
12. Shut the engine off, then unplug the adapter.

### Back at your desk

13. Check the data. Open each CSV, confirm the columns you expect have values, and that rows are about 4 to 5 per second. Keep the original files untouched, work on copies.
14. Optional: build an emulator profile of your car. ELM327-emulator includes a scanning tool (`obd_dictionary`) that queries every standard value one by one and builds a dictionary for that vehicle, which the emulator can then replay. Run it with the adapter connected to the car, following the emulator's README.
15. Commit the scan report and the logs to the repo under `data/rx8/`. Give Claude the scan report: it decides which gauges the RX-8 can feed.
16. Next software step: build a Replay data source in the head unit that plays these CSVs back into the gauges.

### If something goes wrong

- "Could not connect": ignition is not on, the adapter is not seated, or the COM port number is wrong. Leave `--port` out to let python-obd try to detect it.
- Connects but all values blank: the protocol may not have been detected. Send Claude the scan output.
- Rows per second much lower than 5: the car or adapter is answering slowly. That is fine for gauges. Lower `--hz`.
