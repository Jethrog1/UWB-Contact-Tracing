from __future__ import annotations

import re
from pathlib import Path

# ── Root paths ────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent
BRIGID_ROOT = BACKEND_DIR.parent

# ── New workspace-based root ──────────────────────────────────────────────────
# Profile/
#   Workspace 1/
#     tags/   rooms/   RTLS/   svg/   pdf/
#   Workspace 2/
#     ...
PROFILE_ROOT = BRIGID_ROOT / "Profile"

# ── Legacy flat paths (kept for backwards compatibility / fallback reads) ──────
PROFILE_DIR = BRIGID_ROOT / "profile"
TAGS_DIR = PROFILE_DIR / "Tags"
ROOMS_DIR = PROFILE_DIR / "Rooms"
CAD_EXPORTS_DIR = PROFILE_DIR / "CADExports"
TEMP_EXTRACT_DIR = BRIGID_ROOT / ".tmp_project"

# ── Safe folder-name regex ────────────────────────────────────────────────────
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_folder_name(name: str) -> str:
    """Strip filesystem-unsafe characters from a workspace name."""
    return _UNSAFE.sub("_", name).strip(" .") or "Workspace"


# ── Workspace path helpers ────────────────────────────────────────────────────

def workspace_dir(workspace_name: str) -> Path:
    """Return  Profile/{workspace_name}/  (not yet created)."""
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


def ensure_workspace_dirs(workspace_name: str) -> Path:
    """Create all sub-folders for a workspace and return the workspace root."""
    root = workspace_dir(workspace_name)
    for sub in ("tags", "rooms", "RTLS", "svg", "pdf"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def delete_workspace_if_empty(workspace_name: str) -> bool:
    """
    Delete the workspace folder if all its sub-directories are empty.
    Returns True if deleted, False otherwise.
    """
    root = workspace_dir(workspace_name)
    if not root.exists():
        return False
    for item in root.rglob("*"):
        if item.is_file():
            return False  # Has files — keep it
    import shutil
    shutil.rmtree(root, ignore_errors=True)
    return True


def rename_workspace_folder(old_name: str, new_name: str) -> bool:
    """
    Rename Profile/{old_name}/ → Profile/{new_name}/.
    Returns True on success.
    """
    old_path = workspace_dir(old_name)
    new_path = workspace_dir(new_name)
    if not old_path.exists():
        # Nothing to rename — create fresh
        ensure_workspace_dirs(new_name)
        return True
    if new_path.exists():
        return False  # Name collision
    try:
        old_path.rename(new_path)
        return True
    except OSError:
        return False


def list_existing_workspaces() -> list[str]:
    """Return sorted list of existing workspace folder names under Profile/."""
    if not PROFILE_ROOT.exists():
        return []
    return sorted(
        p.name for p in PROFILE_ROOT.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


# ── Legacy ensure (kept for old code paths) ───────────────────────────────────
def ensure_profile_dirs() -> None:
    for directory in (PROFILE_DIR, TAGS_DIR, ROOMS_DIR, CAD_EXPORTS_DIR, TEMP_EXTRACT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
