# Projektplan: Öltemperatur für das RX-8 (S1, 2004)

Stand 5. Nov 2026. Ersetzt den ersten Entwurf (Arduino + MCP2515 + CAN).

## Ausgangslage

- Das RX-8 S1 hat **ab Werk keinen Öltemperatursensor**. Der Scan vom
  5. Nov 2026 bestätigt: OBD-PID 0x5C (OIL_TEMP) wird nicht unterstützt
  (siehe `RX8_OBD_PIDS.md`). Der Wert muss von einem eigenen Sensor kommen.
- Der Pi sitzt hinter dem Armaturenbrett, das Sensorkabel kommt ohnehin durch
  die Spritzwand in den Innenraum.

## Entscheid: Variante A — NTC-Geber → ADS1115 → Pi

```
[NTC-Geber im Öladapter] ──(1 Ader + Masse)──> [ADS1115 am Pi, I²C] ──> Datenquelle "oil_temp" ──> Öltemp-Anzeige
```

**Warum nicht der CAN-Entwurf:**

| | CAN-Entwurf | Variante A |
|---|---|---|
| Teile | Arduino, MCP2515, CAN-HAT, Gehäuse | 1 ADS1115-Modul + 2 Widerstände + 1 Kondensator |
| Eigene Firmware | Ja (Arduino) | Nein |
| Risiko fürs Auto | Eigene Frames auf dem Fahrzeug-CAN (Motor, ABS/DSC, Lenkung) | Keins — nichts hängt am Fahrzeugbus |
| Mehrwert | — | Der ADS1115 hat 4 Kanäle: Öltemp, Lenkradtasten, später Öldruck |

Der CAN-Weg lohnt sich nur bei langer Strecke zwischen Sensor und Pi oder
vielen Sensoren im Motorraum. Beides trifft hier nicht zu.

## Teileliste

| Teil | Zweck | Hinweis |
|---|---|---|
| Öl-Sandwich-Adapter S1 (Wankelshop) oder Racing Beat TYPE II (Teil 11803) | Sensorgewinde am Ölfilter | Racing Beat: 3/8" NPT für Temperatur, 1/8" NPT für Druck, passt 2004–08. Beim Wankelshop-Adapter **Gewinde vor dem Geberkauf prüfen** |
| NTC-Öltemperaturgeber 0–150 °C (z. B. VDO), Gewinde passend zum Adapter | Messfühler | **Bevorzugt 2-polig (isoliert)**, siehe "Masse" unten. Kennlinie (Widerstand bei 2 Temperaturen) aus dem Datenblatt notieren |
| ADS1115-Modul (I²C, 16 Bit) | Analog → digital | Mit 3,3 V betreiben, Adresse 0x48 (ADDR an GND) |
| Festwiderstand 0,1 %, Wert ≈ Geberwiderstand bei ~100 °C | Spannungsteiler | Erst Geber messen, dann Wert wählen (siehe Phase 1) |
| 1 kΩ + 100 nF | RC-Filter vor dem ADC-Eingang | Gegen Zündstörungen |
| Abgeschirmtes 2-adriges Kabel, Durchführungstülle, Schrumpfschlauch, Steckverbinder | Verbindung Motorraum → Innenraum | Weg zur Zündanlage meiden |
| Teflon-Gewindedichtung / Dichtmittel für NPT | Dichtheit | |

## Schaltung

```
Pi 3V3 (Pin 1) ──┬───────────────────────────────── ADS1115 VDD
                 │
                 ├── R_fixed ──┬── Kabel ──> NTC-Geber ──> Masse (Geber-Pol 2 bzw. Motormasse)
                 │             │
                 │             └── 1 kΩ ──┬── ADS1115 A0
                 │                        └── 100 nF ── GND
                 │
                 └───────────────────────────────── ADS1115 A3   (Referenz: misst die 3V3)

Pi GND (Pin 6) ──── ADS1115 GND, ADDR      Pi SDA (Pin 3) ── SDA      Pi SCL (Pin 5) ── SCL
```

- **Ratiometrisch:** A3 misst die Versorgung mit. Schwankt die 3,3-V-Schiene,
  rechnet die Software das heraus.
- **Masse:** Ein 1-poliger Geber schliesst über den Motorblock. Zwischen
  Motormasse und Pi-Masse kann bei laufendem Motor ein Spannungsunterschied
  liegen, der die Messung verfälscht. Ein 2-poliger Geber mit eigener
  Rückleitung zum ADS1115-GND vermeidet das. Mit 1-poligem Geber: gute
  Masseverbindung Motor–Karosserie prüfen und den Effekt in Phase 4 messen
  (Wert bei Zündung an vs. Motor läuft).
- Lenkradtasten kommen später auf A1, Öldruck optional auf A2.

## Phasen

### Phase 0 — Teile beschaffen
1. Adapter wählen, Gewinde bestätigen, dann den passenden Geber bestellen.
2. Datenblatt des Gebers ablegen (Widerstand–Temperatur-Tabelle).

### Phase 1 — Auf dem Tisch (Pi, ohne Auto)
1. I²C aktivieren: `sudo raspi-config` → Interface → I2C, oder in
   `/boot/firmware/config.txt`: `dtparam=i2c_arm=on`. Dann `sudo reboot`.
2. Prüfen: `sudo apt install i2c-tools` und `i2cdetect -y 1` → **48** muss erscheinen.
3. `pip install smbus2`
4. Geberwiderstand mit dem Multimeter messen: einmal bei Raumtemperatur, einmal
   in heissem Wasser **mit Küchenthermometer** (Wasser kocht in Zürich bei
   ca. 98,5 °C, nicht 100 °C — das Thermometer zählt).
5. `R_fixed` ≈ Widerstand bei ~100 °C wählen (beste Auflösung im Arbeitsbereich).
6. Beta berechnen:
   `py tools/oil_temp_cal.py beta <T1> <R1> <T2> <R2>`
   → gibt `r0`, `t0`, `beta` für die Konfiguration aus.
7. Schaltung aufbauen, Geber im Wasserbad, live ablesen:
   `python3 tools/oil_temp_cal.py read --r-fixed <R> --r0 <..> --t0 <..> --beta <..>`
   Abweichung zum Thermometer < 2 °C = gut.

### Phase 2 — Einbau Motorraum
1. Ölfilter ab, Sandwich-Adapter montieren, Geber eindichten, Filter wieder an
   (Anzugsmomente laut Adapter-/Filterhersteller).
2. Motor laufen lassen, auf Dichtheit prüfen, Ölstand kontrollieren.
3. Kabel abgeschirmt, weg von Zündspulen und Auspuff, durch eine
   Spritzwand-Tülle in den Innenraum (Stelle am Auto bestimmen).

### Phase 3 — Anschluss und Konfiguration
In `~/.rx8_headunit/config.json`:
```json
"oil_temp": {
  "source": "ads1115",
  "channel": 0, "ref_channel": 3,
  "r_fixed": 470, "r0": 2500, "t0": 20, "beta": 3450,
  "smooth_s": 3
}
```
(Zahlen sind Beispiele — eigene Messwerte aus Phase 1 eintragen.)
Zum Entwickeln ohne Hardware: `"source": "simulated"`.

### Phase 4 — Testfahrt
1. Kaltstart: Öltemperatur steigt langsamer als Kühlwasser — beide loggen.
2. Prüfen: Wert bei Zündung an vs. Motor läuft (Masseeffekt, siehe oben).
3. Warn-/Gefahrenschwellen der Anzeige (aktuell 120 / 135 °C) anhand
   RX-8-Quellen festlegen, bevor man sich darauf verlässt.

## Software (umgesetzt, 5. Nov 2026)

| Datei | Inhalt |
|---|---|
| `core/oil_temp.py` | `OilTempSource`: liest den ADS1115 alle 0,5 s in einem Hintergrund-Thread (UI friert nie ein), Beta-Modell, Glättung über 3 s, erkennt Kabelbruch / Kurzschluss / unplausible Werte → N/A mit Meldung. Modus `simulated` zum Entwickeln |
| `core/data_manager.py` | Legt `OIL_TEMP` über die Hauptquelle: OBD live, Replay oder Simulation liefern den Rest, der Sensor die Öltemperatur |
| `tools/oil_temp_cal.py` | Beta aus 2 Messpunkten, Ω → °C, Live-Ablesung am Pi |
| `core/app_state.py` | Konfigurationsblock `oil_temp` (Standard: `off`) |

Fehler und Messzeiten erscheinen im Debug-Panel (`oil_temp.read`).

## Später: passiv am Fahrzeug-CAN mithören (eigene Ausbaustufe)

Die Idee aus dem ersten Entwurf, an OBD-Pin 6/14 anzuschliessen, hat einen
guten Kern — aber nur **lesend**:

- Ein CAN-HAT im **Listen-only-Modus** sendet nie, hört nur zu.
- Das RX-8 sendet Drehzahl, Geschwindigkeit, Kühlwasser usw. ohnehin laufend
  auf dem Bus — vermutlich deutlich schneller als die ~2,2 s pro Wert, die
  wir per OBD-Abfrage mit dem Clone bekommen.
- Vorher nötig: recherchieren, welche CAN-IDs das RX-8 verwendet; dann eine
  `CanSource` im bestehenden Datenmodell.
- Nie eigene Frames auf den Fahrzeugbus senden.
