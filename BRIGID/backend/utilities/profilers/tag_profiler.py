"""
tag_profiler.py — Tag profile validation and utility logic (BRIGID).
"""

from __future__ import annotations

import re
from typing import Any

from .constants import DEVICE_TYPES, DEVICE_HEIGHT_FIELD_MAP, ANCHOR_IDS


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_profile(profile: dict) -> list[str]:
    """
    Validate a tag profile dict.  Returns a list of error strings.
    Empty list → valid.
    """
    errors: list[str] = []

    tag_id = str(profile.get("tag_id", "")).strip()
    if not tag_id:
        errors.append("tag_id is required.")
    elif not re.match(r"^[A-Za-z0-9._-]+$", tag_id):
        errors.append("tag_id may only contain letters, digits, '.', '_', and '-'.")

    device = profile.get("device", {})
    dtype = device.get("device_type", "")
    if dtype not in DEVICE_TYPES:
        errors.append(f"device_type must be one of: {DEVICE_TYPES!r}.")

    mac = str(device.get("mac_address", "")).strip()
    if mac and not re.match(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", mac):
        errors.append("mac_address must be in AA:BB:CC:DD:EE:FF format (or empty).")

    # Height fields — all must be non-negative floats
    height_fields = ["wrist_to_floor_ft", "arm_to_floor_ft", "hip_to_floor_ft", "breast_to_floor_ft"]
    for hf in height_fields:
        try:
            v = float(device.get(hf, 0))
            if v < 0:
                errors.append(f"{hf} must be >= 0.")
        except (TypeError, ValueError):
            errors.append(f"{hf} must be a numeric value.")

    # Calibration equations — validate each is parseable if non-empty
    calibration = profile.get("calibration", {})
    equations = calibration.get("equations", {})
    for aid in ANCHOR_IDS:
        eq = str(equations.get(aid, "")).strip()
        if eq:
            try:
                from .calibration_math import compile_manual_equation
                compile_manual_equation(eq)
            except Exception as exc:
                errors.append(f"Calibration equation for {aid} is invalid: {exc}")

    return errors


# ---------------------------------------------------------------------------
# Device height field helpers
# ---------------------------------------------------------------------------

def get_active_height_field(device_type: str) -> str:
    """Return the height field name for the given device type."""
    return DEVICE_HEIGHT_FIELD_MAP.get(device_type, "wrist_to_floor_ft")


def get_active_height_value(profile: dict) -> float:
    """Return the height (ft) for the device type specified in the profile."""
    device = profile.get("device", {})
    field = get_active_height_field(device.get("device_type", DEVICE_TYPES[0]))
    try:
        return float(device.get(field, 0.0))
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Serialization helpers (for REST API responses)
# ---------------------------------------------------------------------------

def serialize_profile(profile: dict) -> dict:
    """Return a JSON-safe copy with coerced numeric values."""
    p = dict(profile)

    # Coerce device height fields
    device = dict(p.get("device", {}))
    for hf in ["wrist_to_floor_ft", "arm_to_floor_ft", "hip_to_floor_ft", "breast_to_floor_ft"]:
        try:
            device[hf] = round(float(device.get(hf, 0.0)), 4)
        except (TypeError, ValueError):
            device[hf] = 0.0
    p["device"] = device

    # Calibration equations as strings
    calibration = dict(p.get("calibration", {}))
    equations = dict(calibration.get("equations", {}))
    for aid in ANCHOR_IDS:
        equations[aid] = str(equations.get(aid, ""))
    calibration["equations"] = equations
    p["calibration"] = calibration

    return p
