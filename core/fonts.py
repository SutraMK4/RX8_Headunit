"""
core/fonts.py
-------------
Loads the fonts bundled in assets/fonts/ so the UI looks the same on
Windows, the VM and the Pi (no system fonts needed).

    from core import fonts
    fonts.load()                      # once, after QApplication exists
    f = fonts.font("mono", 11)        # QFont, size in pixels

Families (all SIL Open Font License, licence files next to the fonts):
    display   Orbitron   — logo, "RX-8" hero
    heading   Rajdhani   — titles, values, clock
    mono      IBM Plex Mono — labels, small technical text
"""

import logging
import os

from PyQt5.QtGui import QFont, QFontDatabase

log = logging.getLogger("rx8.fonts")

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "assets", "fonts")

FILES = {
    "display": ["Orbitron-Variable.ttf", "Orbitron-Bold.ttf"],
    "heading": ["Rajdhani-SemiBold.ttf"],
    "mono":    ["IBMPlexMono-Regular.ttf", "IBMPlexMono-Medium.ttf"],
}
FALLBACK = {"display": "Arial", "heading": "Arial", "mono": "Courier New"}

_families = {}


def load():
    """Register bundled fonts with Qt. Safe to call more than once."""
    if _families:
        return dict(_families)
    for role, files in FILES.items():
        family = None
        for name in files:
            path = os.path.join(FONT_DIR, name)
            fid = QFontDatabase.addApplicationFont(path)
            if fid < 0:
                log.warning("font not loaded: %s", path)
                continue
            fams = QFontDatabase.applicationFontFamilies(fid)
            if fams and family is None:
                family = fams[0]
        _families[role] = family or FALLBACK[role]
    log.info("fonts: %s", _families)
    return dict(_families)


def family(role):
    if not _families:
        load()
    return _families.get(role, FALLBACK.get(role, "Arial"))


def font(role, px, weight=None, letter_spacing=None):
    """QFont for a role at a pixel size. weight: QFont.Bold, QFont.Medium, ..."""
    f = QFont(family(role))
    f.setPixelSize(max(1, int(round(px))))
    if weight is not None:
        f.setWeight(weight)
    if letter_spacing is not None:
        f.setLetterSpacing(QFont.AbsoluteSpacing, letter_spacing)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f
