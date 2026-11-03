"""
screens/settings_screen.py
---------------------------
Settings screen with all configuration sections:
  - OBD (port, connect/disconnect, PID scan)
  - Display (brightness, timeout, fullscreen)
  - Audio (default volume, source)
  - Navigation (maps path, GPS device, units)
  - System (Pi temp/CPU, hostname, shutdown/reboot)
  - Startup (default screen, fullscreen on boot)

Changes are saved to ~/.rx8_headunit/config.json via AppState.
"""

import subprocess
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QComboBox, QSlider, QLineEdit,
    QCheckBox, QSpacerItem, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer
from core import theme


class SettingsScreen(QWidget):
    def __init__(self, state, main_window):
        super().__init__()
        self.state = state
        self.main_window = main_window
        self._build_ui()

        # Refresh system stats every 3s
        self._sys_timer = QTimer(self)
        self._sys_timer.setInterval(3000)
        self._sys_timer.timeout.connect(self._refresh_system_stats)
        self._sys_timer.start()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Header ─────────────────────────────────────────────────
        header = QLabel("  ⚙  SETTINGS")
        header.setFixedHeight(36)
        header.setStyleSheet(f"""
            background-color: {theme.BG_SECONDARY};
            color: {theme.TEXT_SECONDARY};
            font-size: {theme.FONT_SIZE_SM}pt;
            letter-spacing: 3px;
            border-bottom: 1px solid {theme.BORDER};
            padding-left: 12px;
        """)
        outer.addWidget(header)

        # ── Scrollable content ─────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # ── Sections ───────────────────────────────────────────────
        layout.addWidget(self._section_obd())
        layout.addWidget(self._section_display())
        layout.addWidget(self._section_audio())
        layout.addWidget(self._section_navigation())
        layout.addWidget(self._section_startup())
        self._system_section = self._section_system()
        layout.addWidget(self._system_section)

        # Save button
        save_btn = QPushButton("SAVE ALL SETTINGS")
        save_btn.setFixedHeight(40)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.ACCENT_DIM};
                color: {theme.TEXT_PRIMARY};
                border: 1px solid {theme.ACCENT};
                border-radius: 6px;
                font-size: {theme.FONT_SIZE_MD}pt;
                font-weight: bold;
                letter-spacing: 2px;
            }}
            QPushButton:hover {{ background-color: {theme.ACCENT}; }}
        """)
        save_btn.clicked.connect(self._save_all)
        layout.addWidget(save_btn)
        layout.addStretch()

    # ── Section builders ───────────────────────────────────────────

    def _section_obd(self):
        section = Section("OBD-II")

        # Port selection
        port_row = Row("Port")
        self._obd_port = QComboBox()
        self._obd_port.addItems(["auto", "/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0"])
        self._obd_port.setCurrentText(self.state.get("obd", "port", default="auto"))
        self._obd_port.setStyleSheet(combo_style())
        port_row.add(self._obd_port)
        section.add(port_row)

        # Connection status + buttons
        ctrl_row = Row("Connection")
        self._obd_status_lbl = QLabel(self.state.obd_status.upper())
        self._obd_status_lbl.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_SM}pt;")
        ctrl_row.add(self._obd_status_lbl)

        connect_btn = QPushButton("CONNECT")
        connect_btn.setStyleSheet(small_btn_style(theme.SUCCESS_GREEN))
        connect_btn.clicked.connect(self._obd_connect)
        ctrl_row.add(connect_btn)

        disconnect_btn = QPushButton("DISCONNECT")
        disconnect_btn.setStyleSheet(small_btn_style(theme.WARN_RED))
        disconnect_btn.clicked.connect(self._obd_disconnect)
        ctrl_row.add(disconnect_btn)

        scan_btn = QPushButton("SCAN PIDs")
        scan_btn.setStyleSheet(small_btn_style(theme.ACCENT))
        scan_btn.clicked.connect(self._obd_scan)
        ctrl_row.add(scan_btn)

        section.add(ctrl_row)
        return section

    def _section_display(self):
        section = Section("DISPLAY")

        bright_row = Row("Brightness")
        self._brightness = QSlider(Qt.Horizontal)
        self._brightness.setRange(10, 100)
        self._brightness.setValue(self.state.get("display", "brightness", default=80))
        self._brightness.setStyleSheet(slider_style())
        self._brightness.setFixedWidth(180)
        self._bright_lbl = QLabel(f"{self._brightness.value()}%")
        self._bright_lbl.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_SM}pt;")
        self._brightness.valueChanged.connect(lambda v: self._bright_lbl.setText(f"{v}%"))
        bright_row.add(self._brightness)
        bright_row.add(self._bright_lbl)
        section.add(bright_row)

        timeout_row = Row("Screen timeout")
        self._timeout = QComboBox()
        self._timeout.addItems(["Never", "30s", "1 min", "2 min", "5 min"])
        self._timeout.setStyleSheet(combo_style())
        timeout_row.add(self._timeout)
        section.add(timeout_row)

        full_row = Row("Fullscreen")
        self._fullscreen_cb = QCheckBox()
        self._fullscreen_cb.setChecked(self.state.get("display", "fullscreen", default=False))
        self._fullscreen_cb.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
        self._fullscreen_cb.stateChanged.connect(
            lambda s: self.main_window.showFullScreen() if s else self.main_window.showNormal()
        )
        full_row.add(self._fullscreen_cb)
        section.add(full_row)

        return section

    def _section_audio(self):
        section = Section("AUDIO")

        vol_row = Row("Default volume")
        self._audio_vol = QSlider(Qt.Horizontal)
        self._audio_vol.setRange(0, 100)
        self._audio_vol.setValue(self.state.get("audio", "default_volume", default=50))
        self._audio_vol.setStyleSheet(slider_style())
        self._audio_vol.setFixedWidth(180)
        self._audio_vol_lbl = QLabel(f"{self._audio_vol.value()}%")
        self._audio_vol_lbl.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_SM}pt;")
        self._audio_vol.valueChanged.connect(lambda v: self._audio_vol_lbl.setText(f"{v}%"))
        vol_row.add(self._audio_vol)
        vol_row.add(self._audio_vol_lbl)
        section.add(vol_row)

        return section

    def _section_navigation(self):
        section = Section("NAVIGATION")

        maps_row = Row("Maps path")
        self._maps_path = QLineEdit(self.state.get("navigation", "maps_path", default="/home/mazda/maps"))
        self._maps_path.setStyleSheet(lineedit_style())
        self._maps_path.setFixedWidth(220)
        maps_row.add(self._maps_path)
        section.add(maps_row)

        gps_row = Row("GPS device")
        self._gps_dev = QComboBox()
        self._gps_dev.addItems(["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyAMA0", "gpsd"])
        self._gps_dev.setCurrentText(self.state.get("navigation", "gps_device", default="/dev/ttyUSB0"))
        self._gps_dev.setStyleSheet(combo_style())
        gps_row.add(self._gps_dev)
        section.add(gps_row)

        units_row = Row("Units")
        self._units = QComboBox()
        self._units.addItems(["metric", "imperial"])
        self._units.setCurrentText(self.state.get("navigation", "units", default="metric"))
        self._units.setStyleSheet(combo_style())
        units_row.add(self._units)
        section.add(units_row)

        return section

    def _section_startup(self):
        section = Section("STARTUP")

        screen_row = Row("Default screen")
        self._default_screen = QComboBox()
        self._default_screen.addItems(["home", "gauges", "navigation", "audio"])
        self._default_screen.setCurrentText(self.state.get("startup", "default_screen", default="home"))
        self._default_screen.setStyleSheet(combo_style())
        screen_row.add(self._default_screen)
        section.add(screen_row)

        boot_full_row = Row("Fullscreen on boot")
        self._boot_fullscreen = QCheckBox()
        self._boot_fullscreen.setChecked(self.state.get("startup", "fullscreen", default=False))
        self._boot_fullscreen.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
        boot_full_row.add(self._boot_fullscreen)
        section.add(boot_full_row)

        return section

    def _section_system(self):
        section = Section("SYSTEM")

        # Pi stats
        stats_row = Row("Pi stats")
        self._cpu_lbl = QLabel("CPU: --%  TEMP: --°C")
        self._cpu_lbl.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_SM}pt;")
        stats_row.add(self._cpu_lbl)
        section.add(stats_row)

        # Hostname
        host_row = Row("Hostname")
        self._hostname = QLineEdit(self.state.get("system", "hostname", default="rx8-headunit"))
        self._hostname.setStyleSheet(lineedit_style())
        self._hostname.setFixedWidth(180)
        host_row.add(self._hostname)
        section.add(host_row)

        # Shutdown / Reboot
        power_row = Row("Power")
        reboot_btn = QPushButton("REBOOT")
        reboot_btn.setStyleSheet(small_btn_style(theme.WARN_ORANGE))
        reboot_btn.clicked.connect(self._reboot)
        power_row.add(reboot_btn)

        shutdown_btn = QPushButton("SHUTDOWN")
        shutdown_btn.setStyleSheet(small_btn_style(theme.WARN_RED))
        shutdown_btn.clicked.connect(self._shutdown)
        power_row.add(shutdown_btn)
        section.add(power_row)

        self._refresh_system_stats()
        return section

    # ── Actions ────────────────────────────────────────────────────

    def _save_all(self):
        self.state.set("obd",        "port",           self._obd_port.currentText())
        self.state.set("display",    "brightness",     self._brightness.value())
        self.state.set("display",    "fullscreen",     self._fullscreen_cb.isChecked())
        self.state.set("audio",      "default_volume", self._audio_vol.value())
        self.state.set("navigation", "maps_path",      self._maps_path.text())
        self.state.set("navigation", "gps_device",     self._gps_dev.currentText())
        self.state.set("navigation", "units",          self._units.currentText())
        self.state.set("startup",    "default_screen", self._default_screen.currentText())
        self.state.set("startup",    "fullscreen",     self._boot_fullscreen.isChecked())
        self.state.set("system",     "hostname",       self._hostname.text())
        self.state.save_config()

    def _obd_connect(self):
        from core.obd_manager import OBDManager
        self._obd_manager = OBDManager(self.state)
        self._obd_manager.status_changed.connect(self._on_obd_status)
        self._obd_manager.start()

    def _obd_disconnect(self):
        if hasattr(self, "_obd_manager"):
            self._obd_manager.disconnect()
        self._obd_status_lbl.setText("DISCONNECTED")

    def _obd_scan(self):
        conn = self.state.obd_connection
        if conn:
            cmds = conn.supported_commands
            print("[PID Scan] Supported commands:")
            for cmd in sorted(cmds, key=lambda c: c.name):
                print(f"  {cmd.name}")
        else:
            print("[PID Scan] Not connected")

    def _on_obd_status(self, status):
        self._obd_status_lbl.setText(status.upper())

    def _refresh_system_stats(self):
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                temp = int(f.read().strip()) / 1000
            # CPU usage via /proc/stat (simple one-shot, not averaged)
            self._cpu_lbl.setText(f"TEMP: {temp:.0f}°C")
        except Exception:
            self._cpu_lbl.setText("TEMP: N/A")

    def _reboot(self):
        self._save_all()
        subprocess.call(["sudo", "reboot"])

    def _shutdown(self):
        self._save_all()
        subprocess.call(["sudo", "shutdown", "now"])


# ──────────────────────────────────────────────────────────────────
#  Reusable layout helpers
# ──────────────────────────────────────────────────────────────────

class Section(QFrame):
    def __init__(self, title):
        super().__init__()
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.BG_CARD};
                border: 1px solid {theme.BORDER};
                border-radius: 6px;
            }}
        """)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 8, 12, 8)
        self._layout.setSpacing(6)

        heading = QLabel(title)
        heading.setStyleSheet(f"""
            color: {theme.ACCENT};
            font-size: {theme.FONT_SIZE_SM}pt;
            font-weight: bold;
            letter-spacing: 3px;
            border: none;
            background: transparent;
        """)
        self._layout.addWidget(heading)

    def add(self, widget):
        self._layout.addWidget(widget)


class Row(QWidget):
    def __init__(self, label_text):
        super().__init__()
        self.setStyleSheet("background: transparent; border: none;")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)

        lbl = QLabel(label_text)
        lbl.setFixedWidth(110)
        lbl.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: {theme.FONT_SIZE_SM}pt; background: transparent;")
        self._layout.addWidget(lbl)

    def add(self, widget):
        self._layout.addWidget(widget)
        return self


# ── Style helpers ──────────────────────────────────────────────────

def combo_style():
    return f"""
        QComboBox {{
            background-color: {theme.BG_SECONDARY};
            color: {theme.TEXT_PRIMARY};
            border: 1px solid {theme.BORDER};
            border-radius: 4px;
            padding: 3px 8px;
            font-size: {theme.FONT_SIZE_SM}pt;
        }}
        QComboBox::drop-down {{ border: none; }}
        QComboBox QAbstractItemView {{
            background-color: {theme.BG_SECONDARY};
            color: {theme.TEXT_PRIMARY};
            selection-background-color: {theme.ACCENT_DIM};
        }}
    """

def lineedit_style():
    return f"""
        QLineEdit {{
            background-color: {theme.BG_SECONDARY};
            color: {theme.TEXT_PRIMARY};
            border: 1px solid {theme.BORDER};
            border-radius: 4px;
            padding: 3px 8px;
            font-size: {theme.FONT_SIZE_SM}pt;
        }}
        QLineEdit:focus {{ border: 1px solid {theme.ACCENT}; }}
    """

def slider_style():
    return f"""
        QSlider::groove:horizontal {{
            background: {theme.BG_SECONDARY};
            height: 4px;
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {theme.ACCENT};
            width: 14px;
            height: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }}
        QSlider::sub-page:horizontal {{
            background: {theme.ACCENT_DIM};
            border-radius: 2px;
        }}
    """

def small_btn_style(color):
    return f"""
        QPushButton {{
            background-color: transparent;
            color: {color};
            border: 1px solid {color};
            border-radius: 4px;
            font-size: {theme.FONT_SIZE_SM}pt;
            padding: 3px 10px;
            letter-spacing: 1px;
        }}
        QPushButton:hover {{ background-color: {color}; color: #000; }}
    """
