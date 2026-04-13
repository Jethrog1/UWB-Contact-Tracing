from __future__ import annotations

from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
BRIGID_ROOT = BACKEND_DIR.parent
PROFILE_DIR = BRIGID_ROOT / "profile"
TAGS_DIR = PROFILE_DIR / "Tags"
ROOMS_DIR = PROFILE_DIR / "Rooms"
CAD_EXPORTS_DIR = PROFILE_DIR / "CADExports"
TEMP_EXTRACT_DIR = BRIGID_ROOT / ".tmp_project"


def ensure_profile_dirs() -> None:
    for directory in (PROFILE_DIR, TAGS_DIR, ROOMS_DIR, CAD_EXPORTS_DIR, TEMP_EXTRACT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
