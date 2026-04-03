# -*- coding: utf-8 -*-
"""Utility functions for font handling across the 2DLCAD application.
Provides a function to retrieve a suitable default font family based on the
current operating system, falling back to common fonts when the preferred one
is not available.
"""
import sys
from PyQt6.QtGui import QFontDatabase, QGuiApplication


def _available_families() -> set[str]:
    app = QGuiApplication.instance()
    if app is None:
        return set()
    return set(QFontDatabase.families())

def get_default_font_family() -> str:
    """Return a font family name that exists on the current platform.
    - macOS: Prefer "SF Pro Display" or the system UI font.
    - Windows: "Segoe UI".
    - Linux/others: "Ubuntu" or "DejaVu Sans" as fallback.
    """
    platform = sys.platform
    families = _available_families()
    if platform == "darwin":
        for preferred in ("SF Pro Display", "SF Pro Text", "Helvetica Neue", "Arial"):
            if not families or preferred in families:
                return preferred
        return "Helvetica Neue"
    elif platform == "win32":
        return "Segoe UI"
    else:
        preferred = "Ubuntu"
        if not families or preferred in families:
            return preferred
        return "DejaVu Sans"
