"""
room_io.py — JSON persistence for Room data (BRIGID).
Adapted from 2DLCAD/room_profiles.py (no PyQt6 dependency).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .room_data import Anchor, Room


def _slugify(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip())
    return slug.strip("._-") or "room"


def _primary_rooms_dir(profile_dir: str) -> Path:
    base = Path(profile_dir)
    return base if base.name.lower() == "rooms" else base / "Rooms"


def _candidate_rooms_dirs(profile_dir: str) -> list[Path]:
    primary = _primary_rooms_dir(profile_dir)
    candidates = [primary]
    legacy = primary.parent if primary.name.lower() == "rooms" else Path(profile_dir)
    if legacy not in candidates:
        candidates.append(legacy)
    return candidates


# ---------------------------------------------------------------------------
# Single-room helpers
# ---------------------------------------------------------------------------

def create_empty_room(name: str = "Room") -> Room:
    return Room(name=name, segments=[], rtls_settings={
        "tag_height_ft": 0.0,
        "filter_mode": "None",
        "ble_module_port": "",
    })


def _room_path(room_name: str, profile_dir: str) -> Path:
    return _primary_rooms_dir(profile_dir) / f"{_slugify(room_name)}.json"


def save_room_profile(room: Room, profile_dir: str,
                      filepath: Optional[str] = None) -> Tuple[bool, str]:
    """Save a single room to JSON.  Returns (success, path_or_error)."""
    if filepath is None:
        _primary_rooms_dir(profile_dir).mkdir(parents=True, exist_ok=True)
        filepath = _room_path(room.name, profile_dir)
    else:
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = room.to_dict()
        payload["saved_at"] = datetime.now().isoformat(timespec="seconds")
        with filepath.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)
        return True, str(filepath)
    except OSError as e:
        return False, str(e)


def load_room_profile(filepath: str) -> Tuple[Optional[Room], str]:
    """Load a single room from a JSON file.  Returns (room, error)."""
    path = Path(filepath)
    if not path.is_file():
        return None, f"File not found: {filepath}"
    try:
        with path.open("r", encoding="utf-8") as f:
            d = json.load(f)
        return Room.from_dict(d), ""
    except Exception as exc:
        return None, f"Could not read room: {exc}"


def delete_room_profile(room_name: str, profile_dir: str) -> Tuple[bool, str]:
    for directory in _candidate_rooms_dirs(profile_dir):
        path = directory / f"{_slugify(room_name)}.json"
        if not path.is_file():
            continue
        try:
            path.unlink()
            return True, ""
        except OSError as e:
            return False, str(e)
    return False, f"Room profile not found: {room_name}"


def list_room_profiles(profile_dir: str) -> List[str]:
    """Return stem names of all .rooms.json files in profile_dir."""
    result: set[str] = set()
    for directory in _candidate_rooms_dirs(profile_dir):
        if not directory.is_dir():
            continue
        for entry in directory.iterdir():
            if entry.is_file() and entry.name.lower().endswith(".rooms.json"):
                result.add(entry.name[: -len(".rooms.json")])
    return sorted(result)


# ---------------------------------------------------------------------------
# Manifest (multi-room JSON)
# ---------------------------------------------------------------------------

def build_floorplan_manifest(project_name: str,
                              svg_path: str,
                              rooms: List[Room]) -> dict:
    return {
        "project_name": project_name,
        "svg_file": Path(svg_path).name if svg_path else "",
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "units": "ft",
        "rooms": [r.to_dict() for r in rooms],
    }


def manifest_path(project_name: str, profile_dir: str) -> Path:
    return _primary_rooms_dir(profile_dir) / f"{_slugify(project_name)}.rooms.json"


def save_floorplan_manifest(project_name: str, svg_path: str,
                             rooms: List[Room], profile_dir: str,
                             filepath: Optional[str] = None) -> Tuple[bool, str]:
    """Save a full manifest (multiple rooms) as {project_name}.rooms.json."""
    if filepath is None:
        _primary_rooms_dir(profile_dir).mkdir(parents=True, exist_ok=True)
        filepath = manifest_path(project_name, profile_dir)
    else:
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = build_floorplan_manifest(project_name, svg_path, rooms)
        with filepath.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)
        return True, str(filepath)
    except OSError as e:
        return False, str(e)


def load_floorplan_manifest(filepath: str) -> Tuple[Optional[dict], List[Room], str]:
    """Load manifest JSON.  Returns (manifest_dict, [Room, ...], error_str)."""
    path = Path(filepath)
    if not path.is_file():
        return None, [], f"File not found: {filepath}"
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        rooms = [Room.from_dict(r) for r in payload.get("rooms", [])]
        return payload, rooms, ""
    except Exception as exc:
        return None, [], f"Could not read manifest: {exc}"
