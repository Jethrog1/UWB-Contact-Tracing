"""
tag_profile_io.py — Tag profile JSON persistence (BRIGID).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Tuple

from .constants import DEVICE_TYPES, ANCHOR_IDS


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    return slug.strip("._-") or "tag"


def _primary_profile_dir(profile_dir: str) -> Path:
    base = Path(profile_dir)
    return base if base.name.lower() == "tags" else base / "Tags"


def _candidate_profile_dirs(profile_dir: str) -> list[Path]:
    primary = _primary_profile_dir(profile_dir)
    candidates = [primary]
    legacy = primary.parent if primary.name.lower() == "tags" else Path(profile_dir)
    if legacy not in candidates:
        candidates.append(legacy)
    return candidates


def create_empty_profile() -> dict:
    return {
        "tag_id": "",
        "identity": {
            "profile_id": "",
            "name": "",
            "description": "",
        },
        "device": {
            "mac_address": "",
            "device_type": DEVICE_TYPES[0],
            "wrist_to_floor_ft": 0.0,
            "arm_to_floor_ft": 0.0,
            "hip_to_floor_ft": 0.0,
            "breast_to_floor_ft": 0.0,
            "description": "",
        },
        "calibration": {
            "equations": {aid: "" for aid in ANCHOR_IDS},
            "last_calibration_date": "",
            "equations_enabled": False,
        },
        "notes": "",
    }


def _profile_path(tag_id: str, profile_dir: str) -> Path:
    return _primary_profile_dir(profile_dir) / f"{_slugify(tag_id)}.json"


def save_profile(profile: dict, profile_dir: str) -> Tuple[bool, str]:
    tag_id = str(profile.get("tag_id", "")).strip()
    if not tag_id:
        return False, "tag_id is required."
    primary_dir = _primary_profile_dir(profile_dir)
    primary_dir.mkdir(parents=True, exist_ok=True)
    path = _profile_path(tag_id, profile_dir)
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(profile, f, indent=4)
        return True, str(path)
    except OSError as e:
        return False, str(e)


def load_profile(tag_id: str, profile_dir: str) -> Tuple[dict | None, str]:
    for directory in _candidate_profile_dirs(profile_dir):
        path = directory / f"{_slugify(tag_id)}.json"
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data, ""
        except Exception as e:
            return None, f"Could not read profile: {e}"
    return None, f"Profile not found: {tag_id}"


def load_profile_by_path(filepath: str) -> Tuple[dict | None, str]:
    try:
        with Path(filepath).open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data, ""
    except Exception as e:
        return None, f"Could not read profile: {e}"


def list_profiles(profile_dir: str) -> list[str]:
    result: set[str] = set()
    for directory in _candidate_profile_dirs(profile_dir):
        if not directory.is_dir():
            continue
        for entry in directory.iterdir():
            if entry.is_file() and entry.suffix.lower() == ".json" and not entry.name.endswith(".rooms.json"):
                result.add(entry.stem)
    return sorted(result)


def delete_profile(tag_id: str, profile_dir: str) -> Tuple[bool, str]:
    for directory in _candidate_profile_dirs(profile_dir):
        path = directory / f"{_slugify(tag_id)}.json"
        if not path.is_file():
            continue
        try:
            path.unlink()
            return True, ""
        except OSError as e:
            return False, str(e)
    return False, f"Profile not found: {tag_id}"
