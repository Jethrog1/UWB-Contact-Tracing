import json
import os
import re
import zipfile
from datetime import datetime

from room_data import Room, Anchor

PROFILE_DIR = os.path.join(os.path.dirname(__file__), "room_profiles")
PROJECT_EXTENSION = ".rtlsproj"


def ensure_profile_dir():
    os.makedirs(PROFILE_DIR, exist_ok=True)


def _slugify_room_name(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip())
    slug = slug.strip("._-")
    return slug or "room"


def build_room_profile(room, tag_height_ft=0.0, filter_mode="None"):
    rtls_settings = dict(room.rtls_settings)
    rtls_settings["tag_height_ft"] = round(float(tag_height_ft), 3)
    rtls_settings["filter_mode"] = filter_mode
    rtls_settings.setdefault("ble_module_port", "")
    return {
        "room_name": room.name,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "units": "ft",
        "rtls_settings": rtls_settings,
        "room_bounds_ft": {
            "min_x": round(float(room.min_x), 3),
            "min_y": round(float(room.min_y), 3),
            "max_x": round(float(room.max_x), 3),
            "max_y": round(float(room.max_y), 3),
            "width": round(float(room.width), 3),
            "height": round(float(room.height), 3),
        },
        "anchors": [
            {
                "id": anchor.id,
                "hardware_id": anchor.hw_id or "",
                "x_ft": round(float(anchor.x), 3),
                "y_ft": round(float(anchor.y), 3),
                "z_ft": round(float(anchor.z), 3),
            }
            for anchor in room.anchors
        ],
        "segments_ft": [
            {
                "x1": round(float(x1), 3),
                "y1": round(float(y1), 3),
                "x2": round(float(x2), 3),
                "y2": round(float(y2), 3),
            }
            for x1, y1, x2, y2 in room.segments
        ],
        "interior_segments_ft": [
            {
                "x1": round(float(x1), 3),
                "y1": round(float(y1), 3),
                "x2": round(float(x2), 3),
                "y2": round(float(y2), 3),
            }
            for x1, y1, x2, y2 in room.interior_segments
        ],
    }


def default_room_profile_path(room_name: str) -> str:
    ensure_profile_dir()
    filename = f"{_slugify_room_name(room_name)}.json"
    return os.path.join(PROFILE_DIR, filename)


def save_room_profile(room, tag_height_ft=0.0, filter_mode="None", filepath=None):
    if filepath is None:
        filepath = default_room_profile_path(room.name)
    else:
        directory = os.path.dirname(filepath)
        if directory:
            os.makedirs(directory, exist_ok=True)
    payload = build_room_profile(
        room,
        tag_height_ft=tag_height_ft,
        filter_mode=filter_mode,
    )
    with open(filepath, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=4)
    return filepath


def build_floorplan_manifest(svg_path, rooms):
    return {
        "svg_file": os.path.basename(svg_path) if svg_path else "",
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "units": "ft",
        "rooms": [
            build_room_profile(
                room,
                tag_height_ft=room.rtls_settings.get("tag_height_ft", 0.0),
                filter_mode=room.rtls_settings.get("filter_mode", "None"),
            )
            for room in rooms
        ],
    }


def manifest_path_for_svg(svg_path: str) -> str:
    base, _ = os.path.splitext(svg_path)
    return f"{base}.rooms.json"


def save_floorplan_manifest(svg_path, rooms):
    filepath = manifest_path_for_svg(svg_path)
    payload = build_floorplan_manifest(svg_path, rooms)
    with open(filepath, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=4)
    return filepath


def load_floorplan_manifest(filepath):
    with open(filepath, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    rooms = []
    for room_payload in payload.get("rooms", []):
        segments = []
        for seg in room_payload.get("segments_ft", []):
            segments.append((
                float(seg.get("x1", 0.0)),
                float(seg.get("y1", 0.0)),
                float(seg.get("x2", 0.0)),
                float(seg.get("y2", 0.0)),
            ))

        interior_segments = []
        for seg in room_payload.get("interior_segments_ft", []):
            interior_segments.append((
                float(seg.get("x1", 0.0)),
                float(seg.get("y1", 0.0)),
                float(seg.get("x2", 0.0)),
                float(seg.get("y2", 0.0)),
            ))

        room = Room(
            name=room_payload.get("room_name", "Room"),
            segments=segments,
            interior_segments=interior_segments,
            rtls_settings=dict(room_payload.get("rtls_settings", {})),
        )

        anchors = []
        for anchor_payload in room_payload.get("anchors", []):
            anchors.append(Anchor(
                id=anchor_payload.get("id", ""),
                hw_id=anchor_payload.get("hardware_id", ""),
                x=float(anchor_payload.get("x_ft", 0.0)),
                y=float(anchor_payload.get("y_ft", 0.0)),
                z=float(anchor_payload.get("z_ft", 0.0)),
            ))
        room.anchors = anchors
        rooms.append(room)

    return payload, rooms


def save_project_package(project_path, svg_path, rooms):
    manifest = build_floorplan_manifest(svg_path, rooms)
    with zipfile.ZipFile(project_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(svg_path, arcname="floorplan.svg")
        archive.writestr("room_data.json", json.dumps(manifest, indent=4))
    return project_path


def load_project_package(project_path, extract_dir):
    with zipfile.ZipFile(project_path, "r") as archive:
        names = set(archive.namelist())
        if "floorplan.svg" not in names or "room_data.json" not in names:
            raise ValueError("Project file must contain floorplan.svg and room_data.json")
        archive.extract("floorplan.svg", path=extract_dir)
        archive.extract("room_data.json", path=extract_dir)

    svg_path = os.path.join(extract_dir, "floorplan.svg")
    manifest_path = os.path.join(extract_dir, "room_data.json")
    payload, rooms = load_floorplan_manifest(manifest_path)
    return svg_path, payload, rooms
