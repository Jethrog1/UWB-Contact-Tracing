# -*- coding: utf-8 -*-
"""Utility functions for font handling across the 2DLCAD application.
Provides a function to retrieve a suitable default font family based on the
current operating system, falling back to common fonts when the preferred one
is not available.
"""
import sys
from PyQt6.QtGui import QFontDatabase

def get_default_font_family() -> str:
    """Return a font family name that exists on the current platform.
    - macOS: Prefer "SF Pro Display" or the system UI font.
    - Windows: "Segoe UI".
    - Linux/others: "Ubuntu" or "DejaVu Sans" as fallback.
    """
    platform = sys.platform
    if platform == "darwin":
        # macOS system font
        preferred = "SF Pro Display"
        if preferred in QFontDatabase.families():
            return preferred
        # Fallback to generic Apple system UI font
        return ".AppleSystemUIFont"
    elif platform == "win32":
        return "Segoe UI"
    else:
        # Linux/other
        preferred = "Ubuntu"
        if preferred in QFontDatabase.families():
            return preferred
        return "DejaVu Sans"
