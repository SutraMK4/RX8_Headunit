"""
screens/audio_screen.py
------------------------
Audio control screen.
Skeleton with source selection and volume control.

Integration path:
- Volume: amixer / PulseAudio via subprocess or pulsectl library
- Source switching: depends on hardware (AUX input relay, USB audio)
- Metadata: if streaming, use python-vlc or mpd for track info

TODO:
- Wire volume slider to amixer/PulseAudio
- Implement source switching logic
- Add track metadata display if using USB/Bluetooth
- Bose EQ preset controls (if amp control is implemented)
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QFrame
)
from PyQt5.QtCore import Qt
from core import theme


class AudioScreen(QWidget):
    def __init__(self, state, main_window):
        super().__init__()
        self.state = state
        self.main_window = main_window
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 8)
        layout.setSpacing(16)

        # ── Title ──────────────────────────────────────────────────
        title = QLabel("AUDIO")
        title.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_SM}pt; letter-spacing: 4px;")
        layout.addWidget(title)

        # ── Now playing (metadata placeholder) ────────────────────
        self._now_playing = NowPlayingCard()
        layout.addWidget(self._now_playing)

        # ── Source selector ────────────────────────────────────────
        source_row = SourceSelector(self.state)
        layout.addWidget(source_row)

        # ── Volume control ─────────────────────────────────────────
        volume = VolumeControl(self.state)
        layout.addWidget(volume)

        # ── Playback controls ──────────────────────────────────────
        playback = PlaybackControls()
        layout.addWidget(playback)

        layout.addStretch()


class NowPlayingCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(70)
        self.setStyleSheet(f"""
            background-color: {theme.BG_CARD};
            border: 1px solid {theme.BORDER};
            border-radius: 8px;
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)

        # Album art placeholder
        art = QLabel("♪")
        art.setFixedSize(48, 48)
        art.setAlignment(Qt.AlignCenter)
        art.setStyleSheet(f"""
            color: {theme.ACCENT};
            font-size: 22pt;
            background-color: {theme.BG_SECONDARY};
            border-radius: 4px;
        """)
        layout.addWidget(art)

        meta = QVBoxLayout()
        meta.setSpacing(2)
        self._track = QLabel("No source active")
        self._track.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: {theme.FONT_SIZE_MD}pt;")
        self._artist = QLabel("—")
        self._artist.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_SM}pt;")
        meta.addWidget(self._track)
        meta.addWidget(self._artist)
        layout.addLayout(meta)
        layout.addStretch()

        # Source badge
        self._source_badge = QLabel("AUX")
        self._source_badge.setStyleSheet(f"""
            color: {theme.ACCENT};
            font-size: {theme.FONT_SIZE_SM}pt;
            border: 1px solid {theme.ACCENT_DIM};
            border-radius: 3px;
            padding: 2px 6px;
            letter-spacing: 1px;
        """)
        layout.addWidget(self._source_badge)


class SourceSelector(QWidget):
    SOURCES = ["AUX", "USB", "BLUETOOTH", "FM RADIO", "ANDROID AUTO"]

    def __init__(self, state):
        super().__init__()
        self.state = state
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel("SOURCE")
        label.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: {theme.FONT_SIZE_SM}pt; letter-spacing: 2px;")
        label.setFixedWidth(70)
        layout.addWidget(label)

        self._buttons = {}
        current = state.get("audio", "source", default="aux").upper()

        for src in self.SOURCES:
            btn = QPushButton(src)
            btn.setFixedHeight(32)
            active = (src == current)
            btn.setStyleSheet(self._btn_style(active))
            btn.clicked.connect(lambda _, s=src: self._select(s))
            layout.addWidget(btn)
            self._buttons[src] = btn

        layout.addStretch()

    def _select(self, source):
        self.state.set("audio", "source", source.lower())
        for src, btn in self._buttons.items():
            btn.setStyleSheet(self._btn_style(src == source))
        # TODO: trigger actual source switch here

    def _btn_style(self, active):
        bg     = theme.ACCENT_DIM if active else theme.BG_CARD
        border = theme.ACCENT if active else theme.BORDER
        color  = theme.TEXT_PRIMARY if active else theme.TEXT_SECONDARY
        return f"""
            QPushButton {{
                background-color: {bg};
                color: {color};
                border: 1px solid {border};
                border-radius: 4px;
                font-size: {theme.FONT_SIZE_SM}pt;
                padding: 4px 10px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ background-color: {theme.BG_HOVER}; }}
        """


class VolumeControl(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        label = QLabel("VOLUME")
        label.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: {theme.FONT_SIZE_SM}pt; letter-spacing: 2px;")
        label.setFixedWidth(70)
        layout.addWidget(label)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 100)
        self._slider.setValue(state.get("audio", "default_volume", default=50))
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {theme.BG_CARD};
                height: 6px;
                border-radius: 3px;
                border: 1px solid {theme.BORDER};
            }}
            QSlider::handle:horizontal {{
                background: {theme.ACCENT};
                width: 18px;
                height: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }}
            QSlider::sub-page:horizontal {{
                background: {theme.ACCENT_DIM};
                border-radius: 3px;
            }}
        """)
        self._slider.valueChanged.connect(self._on_volume_change)
        layout.addWidget(self._slider, stretch=1)

        self._vol_label = QLabel(f"{self._slider.value()}%")
        self._vol_label.setFixedWidth(40)
        self._vol_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: {theme.FONT_SIZE_SM}pt;")
        layout.addWidget(self._vol_label)

    def _on_volume_change(self, value):
        self._vol_label.setText(f"{value}%")
        self.state.set("audio", "default_volume", value)
        # TODO: call amixer / pulsectl here


class PlaybackControls(QWidget):
    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        controls = [("⏮", "prev"), ("⏪", "rew"), ("⏯", "play"), ("⏩", "fwd"), ("⏭", "next")]
        for icon, action in controls:
            btn = QPushButton(icon)
            btn.setFixedSize(48, 40)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {theme.BG_CARD};
                    color: {theme.TEXT_PRIMARY};
                    border: 1px solid {theme.BORDER};
                    border-radius: 6px;
                    font-size: 14pt;
                }}
                QPushButton:hover {{ background-color: {theme.BG_HOVER}; }}
                QPushButton:pressed {{ background-color: {theme.ACCENT_DIM}; }}
            """)
            # TODO: wire to playback backend
            layout.addWidget(btn)

        layout.addStretch()
