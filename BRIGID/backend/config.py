from __future__ import annotations

import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
BRIGID_ROOT = BACKEND_DIR.parent

PROFILE_ROOT = BRIGID_ROOT / "Profile"

PROFILE_DIR = BRIGID_ROOT / "profile"
TAGS_DIR = PROFILE_DIR / "Tags"
ROOMS_DIR = PROFILE_DIR / "Rooms"
CAD_EXPORTS_DIR = PROFILE_DIR / "CADExports"
TEMP_EXTRACT_DIR = BRIGID_ROOT / ".tmp_project"

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

def _safe_folder_name(name: str) -> str:
    return _UNSAFE.sub("_", name).strip(" .") or "Workspace"

def workspace_dir(workspace_name: str) -> Path:
    return PROFILE_ROOT / _safe_folder_name(workspace_name)

def workspace_tags_dir(workspace_name: str) -> Path:
    return workspace_dir(workspace_name) / "tags"

def workspace_rooms_dir(workspace_name: str) -> Path:
    return workspace_dir(workspace_name) / "rooms"

def workspace_rtls_dir(workspace_name: str) -> Path:
    return workspace_dir(workspace_name) / "RTLS"

def workspace_svg_dir(workspace_name: str) -> Path:
    return workspace_dir(workspace_name) / "svg"

def workspace_pdf_dir(workspace_name: str) -> Path:
    return workspace_dir(workspace_name) / "pdf"

def workspace_projects_dir(workspace_name: str) -> Path:
    return workspace_dir(workspace_name) / "projects"

def ensure_workspace_dirs(workspace_name: str) -> Path:
    root = workspace_dir(workspace_name)
    for sub in ("tags", "rooms", "RTLS", "svg", "pdf", "projects"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root

def delete_workspace_if_empty(workspace_name: str) -> bool:
    root = workspace_dir(workspace_name)
    if not root.exists():
        return False
    for item in root.rglob("*"):
        if item.is_file():
            return False                       
    import shutil
    shutil.rmtree(root, ignore_errors=True)
    return True

def rename_workspace_folder(old_name: str, new_name: str) -> bool:
    old_path = workspace_dir(old_name)
    new_path = workspace_dir(new_name)
    if not old_path.exists():

        ensure_workspace_dirs(new_name)
        return True
    if new_path.exists():
        return False                  
    try:
        old_path.rename(new_path)
        return True
    except OSError:
        return False

def list_existing_workspaces() -> list[dict]:
    if not PROFILE_ROOT.exists():
        return []

    workspaces = []
    for p in PROFILE_ROOT.iterdir():
        if p.is_dir() and not p.name.startswith("."):
            try:
                mod_time = p.stat().st_mtime
            except OSError:
                mod_time = 0.0
            workspaces.append({"name": p.name, "modified": mod_time})

    workspaces.sort(key=lambda x: x["modified"], reverse=True)
    return workspaces

def ensure_profile_dirs() -> None:
    for directory in (PROFILE_DIR, TAGS_DIR, ROOMS_DIR, CAD_EXPORTS_DIR, TEMP_EXTRACT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
