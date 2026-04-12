from __future__ import annotations

import json
import os
from typing import Dict

from calibration_utils import compile_manual_equation


TAG_PROFILE_DIR = os.path.join(os.path.dirname(__file__), "tag_profiles")
DEVICE_HEIGHT_FIELD_MAP = {
    "Wrist Band": "wrist_to_floor_ft",
    "Arm Band": "arm_to_floor_ft",
    "Belt Clip-on": "hip_to_floor_ft",
    "Breast Pocket": "breast_to_floor_ft",
}


def load_tag_profile_lookup(profile_dir: str = TAG_PROFILE_DIR) -> Dict[str, dict]:
    lookup: Dict[str, dict] = {}
    if not os.path.isdir(profile_dir):
        return lookup

    for filename in os.listdir(profile_dir):
        if not filename.lower().endswith(".json"):
            continue
        filepath = os.path.join(profile_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            continue

        tag_id = str(payload.get("tag_id", "")).strip()
        if tag_id:
            lookup[tag_id] = payload
    return lookup


def resolve_tag_height(tag_id: str, lookup: Dict[str, dict], default_height: float = 0.0) -> float:
    payload = lookup.get(str(tag_id).strip())
    if not payload:
        return default_height

    device = payload.get("device", {})
    device_type = str(device.get("device_type", "")).strip()
    height_field = DEVICE_HEIGHT_FIELD_MAP.get(device_type)
    if not height_field:
        return default_height

    raw_value = str(device.get(height_field, "")).strip()
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return default_height
    return value if value > 0.0 else default_height


def resolve_tag_anchor_correction(
    tag_id: str,
    anchor_id: str,
    raw_distance: float,
    lookup: Dict[str, dict],
) -> float:
    payload = lookup.get(str(tag_id).strip())
    if not payload:
        return raw_distance

    calibration = payload.get("calibration", {})
    equations = calibration.get("equations", {})
    expr = str(equations.get(str(anchor_id).strip(), "")).strip()
    if not expr:
        return raw_distance

    cache = payload.setdefault("_compiled_calibration", {})
    func = cache.get(anchor_id)
    if func is None:
        try:
            func = compile_manual_equation(expr)
        except Exception:
            cache[anchor_id] = False
            return raw_distance
        cache[anchor_id] = func
    elif func is False:
        return raw_distance

    try:
        corrected = float(func(float(raw_distance)))
    except Exception:
        return raw_distance
    return corrected if corrected > 0.0 else raw_distance
