"""
screens/navigation_screen.py
-----------------------------
Navigation screen.

Implements Option 2: launch Organic Maps as a full-screen subprocess
from within the head unit. While Organic Maps runs, a lightweight overlay
offers a "RETURN TO HEAD UNIT" button that kills the subprocess and
restores the PyQt5 UI.

GPS status / speed in the TopBar read from gpsd (via gpsd-py3) when
available, falling back gracefully to "GPS: NO FIX" when gpsd is not
running — without crashing.

TODO:
- Wire RECALC / NORTH-up controls to the active map app (Organic Maps has
  no IPC hook for this yet — these remain stubs)
- Add an on-screen search bar that forwards a query to Organic Maps
"""

import shutil
import subprocess

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PyQt5.QtCore import Qt, QTimer
from core import theme

# ── gpsd (optional) ───────────────────────────────────────────────────
# gpsd-py3 exposes a module-level singleton connection. Import is guarded
# so the screen still works on a dev machine with no GPS / no gpsd.
try:
    import gpsd as _gpsd
    _HAS_GPSD = True
except ImportError:
    _gpsd = None
    _HAS_GPSD = False


# ── Organic Maps launch command discovery ─────────────────────────────
def _find_organic_maps():
    """Return the command list to launch Organic Maps, or None if absent."""
    # Native package binaries (name varies by distro / build)
    for cmd in (["organicmaps"], ["OMaps"], ["omaps"]):
        if shutil.which(cmd[0]):
            return cmd
    # AppImage — look for it in common locations
    import os
    appimage_paths = [
        os.path.expanduser("~/OrganicMaps.AppImage"),
        os.path.expanduser("~/apps/OrganicMaps.AppImage"),
        "/opt/OrganicMaps.AppImage",
    ]
    for path in appimage_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return [path]
    # Flatpak fallback (less likely on Pi but worth checking)
    if shutil.which("flatpak"):
        try:
            out = subprocess.run(
                ["flatpak", "list", "--app", "--columns=application"],
                capture_output=True, text=True, timeout=5,
            )
            if "app.organicmaps.desktop" in out.stdout:
                return ["flatpak", "run", "app.organicmaps.desktop"]
        except Exception:
            pass
    return None


class NavigationScreen(QWidget):
    def __init__(self, state, main_window):
        super().__init__()
        self.state = state
        self.main_window = main_window
        self._build_ui()

        # ── GPS polling (every 2 s) ───────────────────────────────────
        self._gps_connected = False
        self._gps_timer = QTimer(self)
        self._gps_timer.setInterval(2000)
        self._gps_timer.timeout.connect(self._poll_gps)
        self._gps_timer.start()
        self._poll_gps()  # immediate first read

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Top bar ────────────────────────────────────────────────
        self._top_bar = TopBar(self.state)
        layout.addWidget(self._top_bar)

        # ── Map area ───────────────────────────────────────────────
        self._map_area = MapPlaceholder()
        layout.addWidget(self._map_area, stretch=1)

        # ── Bottom controls ────────────────────────────────────────
        self._bottom = BottomControls(
            on_back=lambda: self.main_window.switch_screen("home"),
            on_home=lambda: self.main_window.switch_screen("home"),
            on_gps=self._map_area.launch_navigation,
        )
        layout.addWidget(self._bottom)

    # ── GPS ───────────────────────────────────────────────────────────
    def _ensure_gpsd(self):
        """Lazily (re)connect to gpsd. Returns True if connected."""
        if not _HAS_GPSD:
            return False
        if self._gps_connected:
            return True
        try:
            _gpsd.connect()          # defaults to localhost:2947
            self._gps_connected = True
        except Exception:
            self._gps_connected = False
        return self._gps_connected

    def _poll_gps(self):
        """Read a packet from gpsd and update the TopBar. Never raises."""
        if not self._ensure_gpsd():
            self._top_bar.set_gps(fix=False)
            return
        try:
            packet = _gpsd.get_current()
            # mode: 0=no mode, 1=no fix, 2=2D fix, 3=3D fix
            if getattr(packet, "mode", 0) >= 2:
                speed_kmh = None
                try:
                    speed_kmh = packet.hspeed * 3.6  # m/s → km/h
                except Exception:
                    speed_kmh = None
                self._top_bar.set_gps(fix=True, mode=packet.mode, speed_kmh=speed_kmh)
            else:
                self._top_bar.set_gps(fix=False)
        except Exception:
            # Lost the connection / no data yet — drop to NO FIX, retry next tick
            self._gps_connected = False
            self._top_bar.set_gps(fix=False)


class TopBar(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.setFixedHeight(44)
        self.setStyleSheet(f"background-color: {theme.BG_SECONDARY}; border-bottom: 1px solid {theme.BORDER};")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)

        # GPS status
        self._gps_label = QLabel("GPS: NO FIX")
        self._gps_label.setStyleSheet(f"color: {theme.WARN_ORANGE}; font-size: {theme.FONT_SIZE_SM}pt; letter-spacing: 2px;")
        layout.addWidget(self._gps_label)

        layout.addStretch()

        # Search bar placeholder
        search = QLabel("[ Search destination ]")
        search.setStyleSheet(f"""
            color: {theme.TEXT_DIM};
            font-size: {theme.FONT_SIZE_SM}pt;
            background-color: {theme.BG_CARD};
            border: 1px solid {theme.BORDER};
            border-radius: 4px;
            padding: 4px 12px;
        """)
        layout.addWidget(search)

        layout.addStretch()

        # Speed display
        self._speed_label = QLabel("-- km/h")
        self._speed_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_SM}pt;")
        layout.addWidget(self._speed_label)

    def set_gps(self, fix, mode=0, speed_kmh=None):
        """Update GPS status + speed labels. Called by the poll timer."""
        if fix:
            kind = "3D" if mode >= 3 else "2D"
            self._gps_label.setText(f"GPS: {kind} FIX")
            self._gps_label.setStyleSheet(
                f"color: {theme.SUCCESS_GREEN}; font-size: {theme.FONT_SIZE_SM}pt; letter-spacing: 2px;"
            )
            if speed_kmh is not None:
                self._speed_label.setText(f"{speed_kmh:.0f} km/h")
            else:
                self._speed_label.setText("-- km/h")
        else:
            self._gps_label.setText("GPS: NO FIX")
            self._gps_label.setStyleSheet(
                f"color: {theme.WARN_ORANGE}; font-size: {theme.FONT_SIZE_SM}pt; letter-spacing: 2px;"
            )
            self._speed_label.setText("-- km/h")


class MapPlaceholder(QFrame):
    """
    Hosts the LAUNCH NAVIGATION control and manages the Organic Maps
    subprocess. Three visual states:
      • launch    — big "LAUNCH NAVIGATION" button
      • active    — "Navigation active…" + "RETURN TO HEAD UNIT"
      • not-found — install instructions (Organic Maps missing)
    """
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: #0d1117; border: none;")

        self._proc = None
        self._cmd = _find_organic_maps()

        # Watches for the subprocess exiting on its own (user closed OM)
        self._proc_timer = QTimer(self)
        self._proc_timer.setInterval(1000)
        self._proc_timer.timeout.connect(self._check_proc)

        self._layout = QVBoxLayout(self)
        self._layout.setAlignment(Qt.AlignCenter)
        self._layout.setSpacing(16)

        self._show_launch()

    # ── State rendering ───────────────────────────────────────────────
    def _clear(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _show_launch(self):
        self._clear()

        icon = QLabel("⊕")
        icon.setStyleSheet(f"color: {theme.ACCENT_DIM}; font-size: 48pt;")
        icon.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(icon)

        msg = QLabel("OFFLINE NAVIGATION")
        msg.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: {theme.FONT_SIZE_LG}pt; letter-spacing: 4px;")
        msg.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(msg)

        launch_btn = QPushButton("LAUNCH NAVIGATION")
        launch_btn.setFixedSize(280, 64)
        launch_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.ACCENT};
                color: {theme.TEXT_PRIMARY};
                border: none;
                border-radius: 8px;
                font-size: {theme.FONT_SIZE_MD}pt;
                font-weight: bold;
                letter-spacing: 3px;
            }}
            QPushButton:hover  {{ background-color: {theme.ACCENT_DIM}; }}
            QPushButton:pressed {{ background-color: {theme.BG_HOVER}; }}
        """)
        launch_btn.clicked.connect(self.launch_navigation)
        self._layout.addWidget(launch_btn, alignment=Qt.AlignCenter)

    def _show_active(self):
        self._clear()

        icon = QLabel("⊚")
        icon.setStyleSheet(f"color: {theme.SUCCESS_GREEN}; font-size: 48pt;")
        icon.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(icon)

        msg = QLabel("Navigation active…")
        msg.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_LG}pt; letter-spacing: 2px;")
        msg.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(msg)

        sub = QLabel("Organic Maps is running in front of the head unit.")
        sub.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: {theme.FONT_SIZE_SM}pt;")
        sub.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(sub)

        return_btn = QPushButton("RETURN TO HEAD UNIT")
        return_btn.setFixedSize(280, 64)
        return_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.BG_CARD};
                color: {theme.TEXT_PRIMARY};
                border: 1px solid {theme.ACCENT};
                border-radius: 8px;
                font-size: {theme.FONT_SIZE_MD}pt;
                font-weight: bold;
                letter-spacing: 3px;
            }}
            QPushButton:hover  {{ background-color: {theme.BG_HOVER}; }}
            QPushButton:pressed {{ background-color: {theme.ACCENT_DIM}; }}
        """)
        return_btn.clicked.connect(self.return_to_head_unit)
        self._layout.addWidget(return_btn, alignment=Qt.AlignCenter)

    def _show_not_found(self):
        self._clear()

        icon = QLabel("⚠")
        icon.setStyleSheet(f"color: {theme.WARN_ORANGE}; font-size: 48pt;")
        icon.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(icon)

        msg = QLabel("APP NOT FOUND")
        msg.setStyleSheet(f"color: {theme.WARN_ORANGE}; font-size: {theme.FONT_SIZE_LG}pt; letter-spacing: 4px;")
        msg.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(msg)

        sub = QLabel("Organic Maps AppImage not found. Download and install it with:")
        sub.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: {theme.FONT_SIZE_SM}pt;")
        sub.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(sub)

        # FIX 1: AppImage instructions instead of Flatpak
        cmd = QLabel(
            "wget https://github.com/organicmaps/organicmaps/releases/latest/download/OrganicMaps-aarch64.AppImage\n"
            "chmod +x OrganicMaps-aarch64.AppImage\n"
            "mv OrganicMaps-aarch64.AppImage ~/OrganicMaps.AppImage"
        )
        cmd.setStyleSheet(f"""
            color: {theme.TEXT_SECONDARY};
            font-size: {theme.FONT_SIZE_SM}pt;
            font-family: monospace;
            background-color: {theme.BG_CARD};
            border: 1px solid {theme.BORDER};
            border-radius: 4px;
            padding: 8px 14px;
        """)
        cmd.setAlignment(Qt.AlignLeft)
        cmd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._layout.addWidget(cmd, alignment=Qt.AlignCenter)

        retry_btn = QPushButton("RETRY")
        retry_btn.setFixedSize(160, 44)
        retry_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.BG_CARD};
                color: {theme.TEXT_SECONDARY};
                border: 1px solid {theme.BORDER};
                border-radius: 4px;
                font-size: {theme.FONT_SIZE_SM}pt;
                letter-spacing: 2px;
            }}
            QPushButton:hover {{ background-color: {theme.BG_HOVER}; color: {theme.TEXT_PRIMARY}; }}
        """)
        retry_btn.clicked.connect(self._retry_find)
        self._layout.addWidget(retry_btn, alignment=Qt.AlignCenter)

    def _retry_find(self):
        self._cmd = _find_organic_maps()
        self._show_launch() if self._cmd else self._show_not_found()

    # ── Subprocess control ────────────────────────────────────────────
    def launch_navigation(self):
        """Spawn Organic Maps full-screen. Called by button or GPS control."""
        # Already running? Just keep the active overlay.
        if self._proc is not None and self._proc.poll() is None:
            self._show_active()
            return

        if self._cmd is None:
            self._cmd = _find_organic_maps()
        if self._cmd is None:
            self._show_not_found()
            return

        try:
            self._proc = subprocess.Popen(self._cmd)
        except Exception:
            self._proc = None
            self._show_not_found()
            return

        self._show_active()
        self._proc_timer.start()

    def return_to_head_unit(self):
        """Kill the Organic Maps subprocess and restore the head-unit UI."""
        self._proc_timer.stop()
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        self._proc = None
        self._show_launch()

    def _check_proc(self):
        """Detect Organic Maps closing on its own and restore the UI."""
        if self._proc is not None and self._proc.poll() is not None:
            self._proc = None
            self._proc_timer.stop()
            self._show_launch()


class BottomControls(QWidget):
    # FIX 2: on_home added as separate parameter — navigates to head unit home screen
    def __init__(self, on_back=None, on_home=None, on_gps=None):
        super().__init__()
        self._on_back = on_back
        self._on_home = on_home
        self._on_gps = on_gps

        self.setFixedHeight(48)
        self.setStyleSheet(f"background-color: {theme.BG_SECONDARY}; border-top: 1px solid {theme.BORDER};")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        # (label, handler)
        buttons = [
            ("◂ BACK",  self._handle_back),
            ("⌂ HOME",  self._handle_home),
            ("RECALC",  self._handle_recalc),
            ("▴ NORTH", self._handle_north),
            ("⊕ GPS",   self._handle_gps),
        ]
        for label, handler in buttons:
            btn = QPushButton(label)
            btn.setFixedHeight(36)
            btn.clicked.connect(handler)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {theme.BG_CARD};
                    color: {theme.TEXT_SECONDARY};
                    border: 1px solid {theme.BORDER};
                    border-radius: 4px;
                    font-size: {theme.FONT_SIZE_SM}pt;
                    padding: 4px 10px;
                    letter-spacing: 1px;
                }}
                QPushButton:hover {{
                    background-color: {theme.BG_HOVER};
                    color: {theme.TEXT_PRIMARY};
                }}
            """)
            layout.addWidget(btn)

        layout.addStretch()

    # ── Handlers ──────────────────────────────────────────────────────
    def _handle_back(self):
        if self._on_back:
            self._on_back()

    def _handle_home(self):
        # FIX 2: navigates to head unit home screen (was incorrectly a map stub)
        if self._on_home:
            self._on_home()

    def _handle_gps(self):
        # Centre on GPS / (re)launch the map app
        if self._on_gps:
            self._on_gps()

    def _handle_recalc(self):
        # TODO: trigger route recalculation in the active map app
        pass

    def _handle_north(self):
        # TODO: toggle north-up / heading-up orientation in the active map app
        pass