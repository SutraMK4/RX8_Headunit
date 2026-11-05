# Projektplan: RX-8 S1 Öltemperatur-Integration via CAN-Bus

Hier ist der strukturierte Projektplan zur Erfassung der Öltemperatur bei einem Mazda RX-8 Series 1 (S1) und der nahtlosen Integration in ein Raspberry Pi Cockpit-Dashboard mittels eines 10-Hz-Broadcasts.

---

## 📦 Teile-Liste (Parts List)

### 1. Hardware am Motor (Datenerfassung)
* **Wankelshop Öl-Sandwich-Adapter S1** (wird unter den Ölfilter geschraubt). Alternativ: Racing Beat Adapter.
* **Öltemperatursensor (NTC 1/8" NPT oder 3/8" NPT)** – Passend zum Gewinde des Adapters (z. B. Standard-VDO-Sensor 0–150 °C).
* **Mikrocontroller:** *Arduino Nano* oder *ESP32* (als robuster Sensor-Übersetzer im spritzwassergeschützten Gehäuse).
* **Widerstand (Präzision, 4.7 kOhm oder 10 kOhm)** – Für den Spannungsteiler des NTC-Sensors.
* **CAN-Bus-Modul für den Controller:** *MCP2515 CAN-Board* (Anschluss per SPI an den Mikrocontroller).

### 2. Hardware im Cockpit (Dashboard)
* **Raspberry Pi** (Zentrale des Custom-Dashboards).
* **CAN-Bus-Interface für den Raspberry Pi:** *InnoMaker Raspberry Pi CAN-Hat* oder *Waveshare CAN-Hat* (wird direkt auf die GPIO-Leiste gesteckt). Alternativ ein USB-zu-CAN-Adapter (z. B. *Canable*).
* **Kabel & Stecker:** 2-adriges, verdrilltes Kabel (Twisted Pair) für die CAN-Leitung vom Motorraum zum Cockpit.

---

## 🗺️ Der Projektplan (Schritt für Schritt)

```
[ Sensor ] ──(Analog)──> [ Arduino + MCP2515 ] ──(CAN-Bus High/Low)──> [ Raspberry Pi + CAN-Hat ] ──> [ Dashboard UI ]
```

### Phase 1: Mechanischer & Elektrischer Einbau (Motorraum)
1. **Öl-Adapter montieren:** Ölfilter abschrauben, Sandwichplatte montieren, Sensor mit Dichtmittel (z. B. Teflonband) einschrauben, Filter wieder aufsetzen.
2. **Kabel verlegen:** Sensorkabel vom Filter durch die Spritzwand in den Innenraum führen (Nutze den Gummistopfen nahe dem Sicherungskasten im Fahrerfussraum).
3. **Sensor-Box aufbauen:** Arduino und MCP2515-Modul in ein kleines Schutzgehäuse setzen. Den Sensor über den Präzisionswiderstand als Spannungsteiler an einen analogen Pin (z. B. `A0`) anschliessen.

### Phase 2: Sensor-Controller programmieren (Arduino/ESP32)
1. **Kalibrierung:** Hinterlege die Steinhart-Hart-Werte deines NTC-Sensors im Code, um aus der analogen Spannung die exakte Celsius-Temperatur zu berechnen.
2. **CAN-Initialisierung:** Programmiere das MCP2515-Modul auf eine Baudrate von **500 kbps** (die native Geschwindigkeit des RX-8 S1 CAN-Busses).
3. **Der 10-Hz-Broadcast:** Schreibe eine Schleife mit einem `delay(100)`, die alle 100 ms ein Datenpaket mit einer freien ID (z. B. `0x3F0`) abschickt. 
   * *Datenformat-Tipp:* Sende die Temperatur einfach als Ganzzahl (z. B. `95` für 95 °C) im ersten Byte des CAN-Frames.

### Phase 3: CAN-Bus-Verbindung & Konfiguration am Raspberry Pi
1. **CAN-Hat montieren:** Stecke das CAN-Hat auf die GPIO-Leiste deines Raspberry Pi.
2. **Physische Integration:** Verbinde `CAN_H` und `CAN_L` des Motorraum-Controllers mit `CAN_H` und `CAN_L` des Raspberry Pi CAN-Hats.
   * *Tipp für Vollintegration:* Klemme die Leitungen direkt hinten an die Pins 6 (CAN-H) und 14 (CAN-L) des originalen OBD2-Steckers deines RX-8. Dann sieht dein Pi die Daten deines Controllers **und** alle originalen fahrzeugeigenen Daten (Drehzahl, Wassertemperatur) auf derselben Schnittstelle.
3. **Pi OS konfigurieren:** Aktiviere das CAN-Interface in der `/boot/firmware/config.txt` (bzw. `/boot/config.txt` bei älteren Systemen):
   ```bash
   dtoverlay=mcp2515-can0,oscillator=12000000,interrupt=25
   dtoverlay=spi-bcm2835-overlay
   ```
4. **Schnittstelle starten:** Starte das Interface im Terminal mit 500k Baudrate:
   ```bash
   sudo ip link set can0 up type can bitrate 500000
   ```

### Phase 4: Software & Dashboard-Einbindung (Raspberry Pi)
1. **Testlauf:** Nutze die `can-utils` auf dem Pi, um den Datenstrom zu prüfen:
   ```bash
   candump can0 | grep 3F0
   ```
2. **Python-Skript zur Einbindung (`python-can`):**
   ```python
   import can

   # Initialisiere den SocketCAN-Bus
   bus = can.interface.Bus(channel='can0', bustype='socketcan')

   print("Lausche auf CAN-Bus nach Öltemperatur (ID: 0x3F0)...")

   while True:
       message = bus.recv()
       if message.arbitration_id == 0x3F0:
           oil_temp = message.data[0] # Liest das erste Byte des Frames
           print(f"Live Öltemperatur: {oil_temp} °C")
           # Hier den Wert an die GUI-Variable deines Dashboards übergeben
   ```