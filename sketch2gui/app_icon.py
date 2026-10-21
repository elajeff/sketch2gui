"""Locate and load the same app icon in source and frozen Windows builds."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon


def app_icon_path() -> Path:
    """Return the bundled/source icon path without depending on the current directory."""
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        root = Path(__file__).resolve().parent.parent
    return root / "assets" / "app_icon.ico"


def load_app_icon() -> QIcon:
    """Load the app icon; QIcon remains null only if the packaged asset is missing."""
    path = app_icon_path()
    return QIcon(str(path)) if path.is_file() else QIcon()
