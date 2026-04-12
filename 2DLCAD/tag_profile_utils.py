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


def _normalize_lookup_key(value: str) -> str:
    return str(value or "").strip().casefold()


def _anchor_key_candidates(anchor_id: str) -> list[str]:
    raw = str(anchor_id or "").strip()
    if not raw:
        return []

    candidates: list[str] = []
    seen: set[str] = set()

    def _add(candidate: str):
        candidate = str(candidate or "").strip()
        if candidate and candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)

    _add(raw)
    upper = raw.upper()
    _add(upper)

    if "A" in upper:
        suffix = upper[upper.rfind("A") :]
        _add(suffix)

    return candidates


def _lookup_tag_payload(tag_id: str, lookup: Dict[str, dict]) -> dict | None:
    raw = str(tag_id or "").strip()
    if not raw or not lookup:
        return None

    payload = lookup.get(raw)
    if payload:
        return payload

    normalized = _normalize_lookup_key(raw)
    for key, value in lookup.items():
        if _normalize_lookup_key(key) == normalized:
            return value
    return None


def _lookup_anchor_expression(equations: dict, anchor_id: str) -> tuple[str, str]:
    if not isinstance(equations, dict):
        return "", ""

    for candidate in _anchor_key_candidates(anchor_id):
        expr = str(equations.get(candidate, "")).strip()
        if expr:
            return candidate, expr

    normalized_candidates = {_normalize_lookup_key(candidate) for candidate in _anchor_key_candidates(anchor_id)}
    for key, expr in equations.items():
        key_text = str(key or "").strip()
        if not key_text:
            continue
        if _normalize_lookup_key(key_text) in normalized_candidates:
            expr_text = str(expr or "").strip()
            if expr_text:
                return key_text, expr_text

    return "", ""


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
    payload = _lookup_tag_payload(tag_id, lookup)
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
    payload = _lookup_tag_payload(tag_id, lookup)
    if not payload:
        return raw_distance

    calibration = payload.get("calibration", {})
    equations = calibration.get("equations", {})
    resolved_anchor_id, expr = _lookup_anchor_expression(equations, anchor_id)
    if not expr:
        return raw_distance

    cache = payload.setdefault("_compiled_calibration", {})
    cache_key = resolved_anchor_id or str(anchor_id).strip()
    func = cache.get(cache_key)
    if func is None:
        try:
            func = compile_manual_equation(expr)
        except Exception:
            cache[cache_key] = False
            return raw_distance
        cache[cache_key] = func
    elif func is False:
        return raw_distance

    try:
        corrected = float(func(float(raw_distance)))
    except Exception:
        return raw_distance
    return corrected if corrected > 0.0 else raw_distance
