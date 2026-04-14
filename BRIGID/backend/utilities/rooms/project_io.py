"""
project_io.py — ZIP project packaging for Anchor Manager (BRIGID).
Adapted from 2DLCAD/room_profiles.py save/load_project_package.
"""

from __future__ import annotations

import json
import os
import zipfile
from datetime import datetime
from typing import List, Optional, Tuple

from .room_data import Room
from .room_io import build_floorplan_manifest, load_floorplan_manifest

PROJECT_EXTENSION = ".rtlsproj"


def save_project_package(
    project_path: str,
    svg_path: str,
    project_name: str,
    rooms: List[Room],
) -> Tuple[bool, str]:
    """
    Bundle SVG + room manifest into a .rtlsproj ZIP file.
    Returns (success, path_or_error).
    """
    try:
        parent = os.path.dirname(project_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        manifest = build_floorplan_manifest(project_name, svg_path, rooms)
        with zipfile.ZipFile(project_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if svg_path and os.path.isfile(svg_path):
                archive.write(svg_path, arcname="floorplan.svg")
            archive.writestr("room_data.json", json.dumps(manifest, indent=4))
        return True, project_path
    except Exception as exc:
        return False, str(exc)


def load_project_package(
    project_path: str,
    extract_dir: str,
) -> Tuple[Optional[str], Optional[dict], List[Room], str]:
    """
    Extract a .rtlsproj ZIP and return (svg_path, manifest, [Room...], error).
    svg_path is None if not present in the archive.
    """
    if not os.path.isfile(project_path):
        return None, None, [], f"File not found: {project_path}"
    try:
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(project_path, "r") as archive:
            names = set(archive.namelist())
            if "room_data.json" not in names:
                return None, None, [], "Invalid project file: missing room_data.json"
            archive.extract("room_data.json", path=extract_dir)
            svg_extracted = None
            if "floorplan.svg" in names:
                archive.extract("floorplan.svg", path=extract_dir)
                svg_extracted = os.path.join(extract_dir, "floorplan.svg")

        manifest_path = os.path.join(extract_dir, "room_data.json")
        manifest, rooms, error = load_floorplan_manifest(manifest_path)
        if error:
            return svg_extracted, None, [], error
        return svg_extracted, manifest, rooms, ""
    except Exception as exc:
        return None, None, [], str(exc)
