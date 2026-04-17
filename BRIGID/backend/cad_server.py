"""
cad_server.py — FastAPI WebSocket + REST server for BRIGID
============================================================
Run with:
    uvicorn cad_server:app --host 127.0.0.1 --port 8765 --reload

The Electron main process spawns this as a subprocess on startup.

Workspace sessions: each tab connects with its own workspace_id.
The engine for that workspace_id is kept alive between reconnects so
switching tabs never resets CAD state.
"""

import json
import logging
import os
import pathlib
import re
from typing import List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from cad_engine import CADEngine
from config import (
    TAGS_DIR, ROOMS_DIR, TEMP_EXTRACT_DIR, ensure_profile_dirs,
    workspace_tags_dir, workspace_rooms_dir, workspace_rtls_dir,
    workspace_projects_dir,
    ensure_workspace_dirs, delete_workspace_if_empty,
    rename_workspace_folder, list_existing_workspaces,
)
from RTLSDashboard.rtls_runtime import RTLSRuntime
from utilities.profilers.tag_profile_io import (
    create_empty_profile,
    save_profile,
    load_profile,
    list_profiles,
    delete_profile,
)
from utilities.profilers.tag_profiler import validate_profile, serialize_profile
from utilities.profilers.calibration_math import build_eval_func
from utilities.calibration.runtime import CalibrationRuntime
from utilities.rooms.room_data import Anchor, Room, segments_match
from utilities.rooms.room_io import (
    create_empty_room,
    save_floorplan_manifest,
    load_floorplan_manifest,
    list_room_profiles,
)
from utilities.rooms.project_io import PROJECT_EXTENSION, save_project_package, load_project_package
from utilities.rooms.geometry_utils import (
    find_connected_segments as _find_connected,
    detect_room_boundary as _detect_boundary,
    compute_subsegment as _compute_subsegment,
)
from utilities.importers.svg_importer import extract_styled_segments_from_svg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cad_server")

ensure_profile_dirs()

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="BRIGID CAD Server", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Per-workspace engine registry — survives between frontend reconnects
_workspace_engines: dict[str, CADEngine] = {}
_calibration_runtime = CalibrationRuntime()
_rtls_runtime = RTLSRuntime()
_WALK_ANIM_DIR = pathlib.Path(__file__).parent.parent / "assets" / "Walking animation"

# Workspace registry: workspace_id → workspace_name (for path resolution)
_workspace_names: dict[str, str] = {}


def _resolve_tags_dir(workspace_id: Optional[str], workspace_name: Optional[str] = None) -> str:
    """Resolve the tags directory. workspace_name takes priority over the registry lookup."""
    name = workspace_name or (workspace_id and _workspace_names.get(workspace_id))
    if name:
        d = workspace_tags_dir(name)
        d.mkdir(parents=True, exist_ok=True)
        return str(d)
    return str(TAGS_DIR)


def _resolve_rooms_dir(workspace_id: Optional[str], workspace_name: Optional[str] = None) -> str:
    """Resolve the rooms directory. workspace_name takes priority over the registry lookup."""
    name = workspace_name or (workspace_id and _workspace_names.get(workspace_id))
    if name:
        d = workspace_rooms_dir(name)
        d.mkdir(parents=True, exist_ok=True)
        return str(d)
    return str(ROOMS_DIR)


def _resolve_projects_dir(workspace_id: Optional[str], workspace_name: Optional[str] = None) -> str:
    """Resolve the workspace-local projects directory for packaged .rtls saves."""
    name = workspace_name or (workspace_id and _workspace_names.get(workspace_id))
    if name:
        d = workspace_projects_dir(name)
        d.mkdir(parents=True, exist_ok=True)
        return str(d)
    d = os.path.join(os.path.dirname(str(ROOMS_DIR)), "projects")
    os.makedirs(d, exist_ok=True)
    return d


def _slugify_filename(name: str, fallback: str = "project") -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip())
    return slug.strip("._-") or fallback


@app.get("/api/workspace/paths/{workspace_id}")
async def api_workspace_paths(workspace_id: str, workspace_name: Optional[str] = None):
    """Return workspace-specific file paths for a given workspace_id."""
    from config import workspace_svg_dir, workspace_pdf_dir
    name = workspace_name or _workspace_names.get(workspace_id)
    if not name:
        return {"success": False, "error": "Workspace not registered"}
    # Auto-register if workspace_name provided
    if workspace_name and workspace_id not in _workspace_names:
        _workspace_names[workspace_id] = workspace_name
    ensure_workspace_dirs(name)
    return {
        "success": True,
        "tags": str(workspace_tags_dir(name)),
        "rooms": str(workspace_rooms_dir(name)),
        "svg": str(workspace_svg_dir(name)),
        "pdf": str(workspace_pdf_dir(name)),
        "projects": str(workspace_projects_dir(name)),
        "rtls": str(workspace_rtls_dir(name)),
    }


@app.on_event("shutdown")
async def shutdown_runtime() -> None:
    _calibration_runtime.shutdown()
    _rtls_runtime.shutdown()
    _workspace_engines.clear()


def _get_engine(workspace_id: str) -> CADEngine:
    if workspace_id not in _workspace_engines:
        _workspace_engines[workspace_id] = CADEngine()
        logger.info("Created new engine for workspace %r", workspace_id)
    return _workspace_engines[workspace_id]


def _load_all_profiles(workspace_id: Optional[str] = None, workspace_name: Optional[str] = None) -> list[dict]:
    tags_dir = _resolve_tags_dir(workspace_id, workspace_name)
    profiles: list[dict] = []
    for tag_id in list_profiles(tags_dir):
        profile, error = load_profile(tag_id, tags_dir)
        if profile is None or error:
            logger.warning("Skipping unreadable profile %r: %s", tag_id, error)
            continue
        profiles.append(serialize_profile(profile))
    return profiles


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "cad-server", "workspaces": len(_workspace_engines)}


@app.get("/assets/walk/{filename}")
async def get_walk_asset(filename: str):
    safe_name = pathlib.Path(filename).name
    file_path = _WALK_ANIM_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Asset not found: {safe_name}")
    return FileResponse(str(file_path))


# ---------------------------------------------------------------------------
# CAD WebSocket
# ---------------------------------------------------------------------------

async def _run_session(websocket: WebSocket, engine: CADEngine, label: str) -> None:
    await websocket.send_text(json.dumps(engine.to_state_dict()))
    try:
        async for raw in websocket.iter_text():
            try:
                cmd = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("[%s] Non-JSON message: %r", label, raw)
                continue
            state = engine.handle_command(cmd)
            try:
                await websocket.send_text(json.dumps(state))
            except Exception as send_err:
                logger.error("[%s] Failed to send state: %s", label, send_err)
                break
    except WebSocketDisconnect:
        logger.info("[%s] Client disconnected", label)
    except Exception as exc:
        logger.exception("[%s] Unexpected error: %s", label, exc)


@app.websocket("/cad/ws/{workspace_id}")
async def cad_ws_workspace(websocket: WebSocket, workspace_id: str):
    await websocket.accept()
    engine = _get_engine(workspace_id)
    await _run_session(websocket, engine, workspace_id)


@app.websocket("/cad/ws")
async def cad_ws(websocket: WebSocket):
    await websocket.accept()
    engine = _get_engine("__default__")
    await _run_session(websocket, engine, "default")


# ===========================================================================
# Tag Profiler REST endpoints
# ===========================================================================

class SaveProfileRequest(BaseModel):
    profile: dict


class ExportProfileRequest(BaseModel):
    profile: dict
    filepath: str


class CalibrationGenerateRequest(BaseModel):
    points: List[List[float]]   # [[measured, true], ...]
    fit_mode: str = "Linear"
    poly_deg: int = 4
    ma_period: int = 4
    ma_type: str = "Trailing"


class CalibrationTransportConnectRequest(BaseModel):
    mode: str
    port: str = ""


class CalibrationMapUpdateRequest(BaseModel):
    anchors: dict[str, list[float]]
    lines: list[list[str]]
    height_offset: float = 0.0


class CalibrationReferenceUpdateRequest(BaseModel):
    tag_id: str
    distances: dict[str, Optional[float]]
    height: float = 0.0


class CalibrationReferencePlaceRequest(BaseModel):
    tag_id: str
    x: float
    y: float


class CalibrationReferenceCalculateRequest(BaseModel):
    tag_id: str


class CalibrationFitSettingsRequest(BaseModel):
    tag_id: str
    anchor_id: str
    auto: Optional[bool] = None
    fit_mode: Optional[str] = None
    poly_deg: Optional[int] = None
    ma_period: Optional[int] = None
    ma_type: Optional[str] = None


class CalibrationEquationUpdateRequest(BaseModel):
    tag_id: str
    anchor_id: str
    equation: str


class CalibrationCaptureRequest(BaseModel):
    tag_id: str
    sample_count: int = 20


class CalibrationFilterRequest(BaseModel):
    mode: str
    ema_alpha: Optional[float] = None
    roll_n: Optional[int] = None
    kal_q: Optional[float] = None
    kal_r: Optional[float] = None


@app.post("/api/profile/new")
async def api_profile_new():
    return {"success": True, "profile": create_empty_profile()}


@app.get("/api/profile/list")
async def api_profile_list(workspace_id: Optional[str] = None):
    tags_dir = _resolve_tags_dir(workspace_id)
    profiles = list_profiles(tags_dir)
    return {"success": True, "profiles": profiles}


@app.get("/api/profile/{tag_id}")
async def api_profile_load(tag_id: str, workspace_id: Optional[str] = None):
    tags_dir = _resolve_tags_dir(workspace_id)
    profile, error = load_profile(tag_id, tags_dir)
    if error:
        return {"success": False, "error": error}
    return {"success": True, "profile": serialize_profile(profile)}


@app.post("/api/profile/save")
async def api_profile_save(req: SaveProfileRequest, workspace_id: Optional[str] = None):
    errors = validate_profile(req.profile)
    if errors:
        return {"success": False, "error": "; ".join(errors)}
    tags_dir = _resolve_tags_dir(workspace_id)
    ok, result = save_profile(req.profile, tags_dir)
    if not ok:
        return {"success": False, "error": result}
    return {"success": True, "tag_id": req.profile.get("tag_id", ""), "path": result}


@app.post("/api/profile/export")
async def api_profile_export(req: ExportProfileRequest):
    errors = validate_profile(req.profile)
    if errors:
        return {"success": False, "error": "; ".join(errors)}
    try:
        parent = os.path.dirname(req.filepath) or "."
        os.makedirs(parent, exist_ok=True)
        with open(req.filepath, "w", encoding="utf-8") as f:
            json.dump(req.profile, f, indent=4)
        return {"success": True, "path": req.filepath}
    except OSError as exc:
        return {"success": False, "error": str(exc)}


@app.delete("/api/profile/{tag_id}")
async def api_profile_delete(tag_id: str, workspace_id: Optional[str] = None):
    tags_dir = _resolve_tags_dir(workspace_id)
    ok, error = delete_profile(tag_id, tags_dir)
    if not ok:
        return {"success": False, "error": error}
    return {"success": True}


@app.post("/api/profile/calibration/generate")
async def api_calibration_generate(req: CalibrationGenerateRequest):
    if not req.points:
        return {"success": False, "error": "No calibration points provided."}
    try:
        X = [float(p[0]) for p in req.points]
        Y = [float(p[1]) for p in req.points]
        _, expr = build_eval_func(
            req.fit_mode, X, Y,
            poly_deg=req.poly_deg,
            ma_period=req.ma_period,
            ma_type=req.ma_type,
        )
        equation = f"[Auto:{req.fit_mode}] {expr}"
        return {"success": True, "equation": equation}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@app.get("/api/calibration/runtime")
async def api_calibration_runtime(workspace_id: Optional[str] = None, workspace_name: Optional[str] = None):
    # Auto-register workspace name if provided (survives server restarts without needing /register)
    if workspace_id and workspace_name and workspace_id not in _workspace_names:
        _workspace_names[workspace_id] = workspace_name
    return {"success": True, **_calibration_runtime.snapshot(_load_all_profiles(workspace_id, workspace_name))}


@app.get("/api/calibration/serial/ports")
async def api_calibration_serial_ports():
    return {
        "success": True,
        "ports": _calibration_runtime.get_serial_ports(),
        "auto_detect_port": _calibration_runtime.auto_detect_serial_port(),
    }


@app.post("/api/calibration/transport/connect")
async def api_calibration_transport_connect(req: CalibrationTransportConnectRequest, workspace_id: Optional[str] = None, workspace_name: Optional[str] = None):
    if workspace_id and workspace_name and workspace_id not in _workspace_names:
        _workspace_names[workspace_id] = workspace_name
    profiles = _load_all_profiles(workspace_id, workspace_name)
    ok, detail = _calibration_runtime.connect(req.mode, profiles, req.port)
    if not ok:
        return {"success": False, "error": detail}
    return {"success": True, "detail": detail, **_calibration_runtime.snapshot(profiles)}


@app.post("/api/calibration/transport/disconnect")
async def api_calibration_transport_disconnect(workspace_id: Optional[str] = None, workspace_name: Optional[str] = None):
    _calibration_runtime.disconnect()
    return {"success": True, **_calibration_runtime.snapshot(_load_all_profiles(workspace_id, workspace_name))}


@app.post("/api/calibration/map")
async def api_calibration_map(req: CalibrationMapUpdateRequest):
    ok, detail = _calibration_runtime.update_map(req.anchors, req.lines, req.height_offset)
    if not ok:
        return {"success": False, "error": detail}
    return {"success": True, "detail": detail, **_calibration_runtime.snapshot(_load_all_profiles())}


@app.post("/api/calibration/reference")
async def api_calibration_reference(req: CalibrationReferenceUpdateRequest):
    ok, detail = _calibration_runtime.set_reference_distances(req.tag_id, req.distances, req.height)
    if not ok:
        return {"success": False, "error": detail}
    return {"success": True, "detail": detail, **_calibration_runtime.snapshot(_load_all_profiles())}


@app.post("/api/calibration/reference/place")
async def api_calibration_reference_place(req: CalibrationReferencePlaceRequest):
    distances = _calibration_runtime.place_reference_dot(req.tag_id, req.x, req.y)
    return {"success": True, "distances": distances, **_calibration_runtime.snapshot(_load_all_profiles())}


@app.post("/api/calibration/reference/calculate")
async def api_calibration_reference_calculate(req: CalibrationReferenceCalculateRequest):
    ok, detail, locked = _calibration_runtime.calculate_reference(req.tag_id)
    if not ok:
        return {"success": False, "error": detail}
    return {"success": True, "detail": detail, "locked": locked, **_calibration_runtime.snapshot(_load_all_profiles())}


@app.post("/api/calibration/fit")
async def api_calibration_fit(req: CalibrationFitSettingsRequest):
    ok, detail = _calibration_runtime.update_fit_settings(
        req.tag_id,
        req.anchor_id,
        auto=req.auto,
        fit_mode=req.fit_mode,
        poly_deg=req.poly_deg,
        ma_period=req.ma_period,
        ma_type=req.ma_type,
    )
    if not ok:
        return {"success": False, "error": detail}
    return {"success": True, "detail": detail, **_calibration_runtime.snapshot(_load_all_profiles())}


@app.post("/api/calibration/equation")
async def api_calibration_equation(req: CalibrationEquationUpdateRequest):
    ok, detail = _calibration_runtime.set_manual_equation(req.tag_id, req.anchor_id, req.equation)
    if not ok:
        return {"success": False, "error": detail}
    return {"success": True, "detail": detail, **_calibration_runtime.snapshot(_load_all_profiles())}


@app.post("/api/calibration/capture/start")
async def api_calibration_capture_start(req: CalibrationCaptureRequest):
    ok, detail = _calibration_runtime.start_capture(req.tag_id, req.sample_count)
    if not ok:
        return {"success": False, "error": detail}
    return {"success": True, "detail": detail, **_calibration_runtime.snapshot(_load_all_profiles())}


@app.post("/api/calibration/capture/cancel")
async def api_calibration_capture_cancel():
    _calibration_runtime.cancel_capture()
    return {"success": True, **_calibration_runtime.snapshot(_load_all_profiles())}


@app.post("/api/calibration/points/clear/{tag_id}")
async def api_calibration_points_clear(tag_id: str):
    _calibration_runtime.clear_points(tag_id)
    return {"success": True, **_calibration_runtime.snapshot(_load_all_profiles())}


@app.post("/api/calibration/filter")
async def api_calibration_filter(req: CalibrationFilterRequest):
    ok, detail = _calibration_runtime.update_filter(
        req.mode,
        ema_alpha=req.ema_alpha,
        roll_n=req.roll_n,
        kal_q=req.kal_q,
        kal_r=req.kal_r,
    )
    if not ok:
        return {"success": False, "error": detail}
    return {"success": True, "detail": detail, **_calibration_runtime.snapshot(_load_all_profiles())}


@app.post("/api/calibration/tag/save/{tag_id}")
async def api_calibration_tag_save(tag_id: str, workspace_id: Optional[str] = None):
    tags_dir = _resolve_tags_dir(workspace_id)
    profile, error = load_profile(tag_id, tags_dir)
    if profile is None or error:
        return {"success": False, "error": error or f"Profile not found: {tag_id}"}

    calibration_data = _calibration_runtime.export_profile_equations(tag_id)
    profile["calibration"] = calibration_data
    ok, result = save_profile(profile, tags_dir)
    if not ok:
        return {"success": False, "error": result}
    return {
        "success": True,
        "path": result,
        "calibration_date": calibration_data.get("last_calibration_date", ""),
        **_calibration_runtime.snapshot(_load_all_profiles(workspace_id)),
    }


# ===========================================================================
# Room / Anchor Manager REST endpoints
# ===========================================================================

class CreateRoomRequest(BaseModel):
    name: str
    segments: List[List[float]]    # [[x1,y1,x2,y2], ...]
    interior_segments: List[List[float]] = []
    existing_rooms: List[dict] = []


class SaveManifestRequest(BaseModel):
    project_name: str
    svg_path: str = ""
    rooms: List[dict]


class LoadManifestRequest(BaseModel):
    filepath: str


class SaveProjectRequest(BaseModel):
    project_path: str = ""
    svg_path: str = ""
    svg_content: str = ""
    svg_filename: str = ""
    project_name: str
    rooms: List[dict]
    workspace_id: Optional[str] = None
    workspace_name: Optional[str] = None


class LoadProjectRequest(BaseModel):
    project_path: str


class AddAnchorRequest(BaseModel):
    room_name: str
    world_x: float
    world_y: float
    z: float = 0.0
    hw_id: str = ""
    room_index: int = 1


class UpdateAnchorRequest(BaseModel):
    anchor_id: str
    hw_id: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None


class FindSegmentsRequest(BaseModel):
    all_segments: List[List[float]]   # [[x1,y1,x2,y2], ...]
    start_idx: int


class DetectBoundaryRequest(BaseModel):
    segments: List[List[float]]   # [[x1,y1,x2,y2], ...]
    click_x: float
    click_y: float


class ComputeSubsegmentRequest(BaseModel):
    all_segments: List[List[float]]   # [[x1,y1,x2,y2], ...]
    seg_idx: int
    click_x: float
    click_y: float


def _segs_from_list(raw: List[List[float]]):
    return [(float(s[0]), float(s[1]), float(s[2]), float(s[3])) for s in raw]


@app.get("/api/rooms/list")
async def api_rooms_list(workspace_id: Optional[str] = None):
    rooms_dir = _resolve_rooms_dir(workspace_id)
    manifests = list_room_profiles(rooms_dir)
    return {"success": True, "manifests": manifests}


@app.post("/api/rooms/create")
async def api_rooms_create(req: CreateRoomRequest):
    segs = _segs_from_list(req.segments)
    interior = _segs_from_list(req.interior_segments)
    existing_rooms: List[Room] = []
    try:
        existing_rooms = [Room.from_dict(room) for room in req.existing_rooms]
    except Exception as exc:
        return {"success": False, "error": f"Invalid existing room data: {exc}"}

    for existing_room in existing_rooms:
        if segments_match(existing_room.segments, segs):
            return {"success": False, "error": f"Room already defined: {existing_room.name}"}

    room = Room(name=req.name, segments=segs, interior_segments=interior,
                rtls_settings={"tag_height_ft": 0.0, "filter_mode": "None", "ble_module_port": ""})
    return {"success": True, "room": room.to_dict()}


@app.post("/api/rooms/manifest/save")
async def api_rooms_manifest_save(
    req: SaveManifestRequest,
    workspace_id: Optional[str] = None,
    workspace_name: Optional[str] = None,
):
    if workspace_id and workspace_name:
        _workspace_names[workspace_id] = workspace_name
    try:
        rooms = [Room.from_dict(r) for r in req.rooms]
    except Exception as exc:
        return {"success": False, "error": f"Invalid room data: {exc}"}
    rooms_dir = _resolve_rooms_dir(workspace_id, workspace_name)
    ok, result = save_floorplan_manifest(
        req.project_name, req.svg_path, rooms, rooms_dir
    )
    if not ok:
        return {"success": False, "error": result}
    return {"success": True, "path": result}


@app.post("/api/rooms/manifest/load")
async def api_rooms_manifest_load(req: LoadManifestRequest):
    manifest, rooms, error = load_floorplan_manifest(req.filepath)
    if error:
        return {"success": False, "error": error}
    return {
        "success": True,
        "manifest": manifest,
        "rooms": [r.to_dict() for r in rooms],
    }


@app.post("/api/rooms/project/save")
async def api_rooms_project_save(req: SaveProjectRequest):
    effective_workspace_id = req.workspace_id
    effective_workspace_name = req.workspace_name
    if effective_workspace_id and effective_workspace_name:
        _workspace_names[effective_workspace_id] = effective_workspace_name
    try:
        rooms = [Room.from_dict(r) for r in req.rooms]
    except Exception as exc:
        return {"success": False, "error": f"Invalid room data: {exc}"}
    project_path = req.project_path.strip()
    if not project_path:
        projects_dir = _resolve_projects_dir(effective_workspace_id, effective_workspace_name)
        filename = f"{_slugify_filename(req.project_name, 'project')}{PROJECT_EXTENSION}"
        project_path = os.path.join(projects_dir, filename)
    ok, result = save_project_package(
        project_path,
        req.svg_path,
        req.svg_content,
        req.svg_filename,
        req.project_name,
        rooms,
    )
    if not ok:
        return {"success": False, "error": result}
    return {"success": True, "path": result}


@app.post("/api/rooms/project/load")
async def api_rooms_project_load(req: LoadProjectRequest):
    svg_path, manifest, rooms, error = load_project_package(
        req.project_path, TEMP_EXTRACT_DIR
    )
    if error:
        return {"success": False, "error": error}
    return {
        "success": True,
        "svg_path": svg_path or "",
        "manifest": manifest,
        "rooms": [r.to_dict() for r in rooms],
    }


@app.post("/api/rooms/anchor/add")
async def api_anchor_add(req: AddAnchorRequest):
    # Find manifest for this room and update it (stateless — caller passes rooms)
    # This endpoint validates position; state is managed on the frontend.
    anchor_id = f"R{req.room_index}A0"  # placeholder — real ID assigned by frontend state
    anchor = Anchor(
        id=anchor_id,
        x=round(req.world_x, 3),
        y=round(req.world_y, 3),
        hw_id=req.hw_id,
        z=round(req.z, 3),
    )
    return {"success": True, "anchor": anchor.to_dict()}


@app.post("/api/rooms/geometry/find-segments")
async def api_find_segments(req: FindSegmentsRequest):
    segs = _segs_from_list(req.all_segments)
    indices = _find_connected(segs, req.start_idx)
    connected = [list(segs[i]) for i in indices]
    return {"success": True, "indices": indices, "segments": connected}


@app.post("/api/rooms/geometry/detect-boundary")
async def api_detect_boundary(req: DetectBoundaryRequest):
    segs = _segs_from_list(req.segments)
    boundary = _detect_boundary(segs, req.click_x, req.click_y)
    if boundary is None:
        return {"success": False, "boundary": []}
    return {"success": True, "boundary": [list(s) for s in boundary]}


@app.post("/api/rooms/geometry/compute-subsegment")
async def api_compute_subsegment(req: ComputeSubsegmentRequest):
    segs = _segs_from_list(req.all_segments)
    if req.seg_idx < 0 or req.seg_idx >= len(segs):
        return {"success": False, "error": "seg_idx out of range"}
    subseg = _compute_subsegment(segs, req.seg_idx, req.click_x, req.click_y)
    return {"success": True, "subsegment": list(subseg)}


# ===========================================================================
# Workspace Management endpoints
# ===========================================================================

class WorkspaceRegisterRequest(BaseModel):
    workspace_id: str
    workspace_name: str


class WorkspaceRenameRequest(BaseModel):
    workspace_id: str
    old_name: str
    new_name: str


class WorkspaceDeleteRequest(BaseModel):
    workspace_id: str
    workspace_name: str


@app.post("/api/workspace/register")
async def api_workspace_register(req: WorkspaceRegisterRequest):
    """Called when a workspace tab is created. Creates folder on disk."""
    _workspace_names[req.workspace_id] = req.workspace_name
    root = ensure_workspace_dirs(req.workspace_name)
    return {"success": True, "path": str(root)}


@app.post("/api/workspace/rename")
async def api_workspace_rename(req: WorkspaceRenameRequest):
    """Called when a workspace tab is renamed. Renames folder on disk."""
    ok = rename_workspace_folder(req.old_name, req.new_name)
    if ok:
        _workspace_names[req.workspace_id] = req.new_name
    return {"success": ok}


@app.post("/api/workspace/delete")
async def api_workspace_delete(req: WorkspaceDeleteRequest):
    """Called on tab close. Deletes folder if empty."""
    deleted = delete_workspace_if_empty(req.workspace_name)
    if req.workspace_id in _workspace_names:
        del _workspace_names[req.workspace_id]
    return {"success": True, "deleted": deleted}


@app.get("/api/workspace/list")
async def api_workspace_list():
    """Returns all persisted workspace folder names."""
    return {"success": True, "workspaces": list_existing_workspaces()}


# ===========================================================================
# RTLS Dashboard endpoints
# ===========================================================================

class RtlsConnectRequest(BaseModel):
    mode: Optional[str] = "serial"
    port: str


class RtlsWorkspaceLoadRequest(BaseModel):
    workspace_id: Optional[str] = None
    workspace_name: Optional[str] = None  # passed directly — survives server restarts
    manifest_path: Optional[str] = None   # manual override
    room_name: Optional[str] = None       # which room to use (first if omitted)
    folder_path: Optional[str] = None     # browse-folder override (discover manifest/tags inside)
    svg_folder: Optional[str] = None      # direct path to an svg/ folder
    rooms_folder: Optional[str] = None    # direct path to a rooms/ folder
    tags_folder: Optional[str] = None     # direct path to a tags/ folder
    project_path: Optional[str] = None    # .rtls ZIP project file


class RtlsFilterRequest(BaseModel):
    mode: Optional[str] = None
    ema_alpha: Optional[float] = None
    roll_n: Optional[int] = None
    kal_q: Optional[float] = None
    kal_r: Optional[float] = None


class RtlsElevationRequest(BaseModel):
    override: bool
    value_ft: Optional[float] = None


def _load_workspace_profiles(workspace_id: Optional[str], workspace_name: Optional[str] = None) -> list[dict]:
    """Load all tag profiles from workspace-specific or global tags dir."""
    tags_dir = _resolve_tags_dir(workspace_id, workspace_name)
    profiles: list[dict] = []
    for tag_id in list_profiles(tags_dir):
        profile, error = load_profile(tag_id, tags_dir)
        if profile and not error:
            profiles.append(profile)
    return profiles


def _find_workspace_manifest(workspace_id: Optional[str], workspace_name: Optional[str] = None) -> Optional[str]:
    """Find the most recently saved rooms manifest in a workspace."""
    rooms_dir = _resolve_rooms_dir(workspace_id, workspace_name)
    import glob
    pattern = str(rooms_dir) + "/*.rooms.json"
    matches = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    return matches[0] if matches else None


def _find_workspace_svg(workspace_id: Optional[str], workspace_name: Optional[str] = None) -> Optional[str]:
    """Find the most recently saved SVG in a workspace svg/ dir."""
    from config import workspace_svg_dir
    name = workspace_name or (workspace_id and _workspace_names.get(workspace_id))
    if not name:
        return None
    svg_dir = workspace_svg_dir(name)
    if not svg_dir.exists():
        return None
    import glob
    matches = sorted(glob.glob(str(svg_dir / "*.svg")), key=os.path.getmtime, reverse=True)
    return matches[0] if matches else None


def _find_manifest_in_folder(folder_path: str) -> Optional[str]:
    """Find the most recent rooms manifest in a user-selected folder."""
    import glob
    # Check rooms/ subdir first, then the folder itself
    rooms_sub = os.path.join(folder_path, "rooms")
    for search_dir in [rooms_sub, folder_path]:
        if not os.path.isdir(search_dir):
            continue
        matches = sorted(
            glob.glob(os.path.join(search_dir, "*.rooms.json")),
            key=os.path.getmtime,
            reverse=True,
        )
        if matches:
            return matches[0]
    return None


def _load_profiles_from_folder(folder_path: str) -> list[dict]:
    """Load tag profiles from a user-selected folder's tags/ subdir."""
    tags_sub = os.path.join(folder_path, "tags")
    if not os.path.isdir(tags_sub):
        return []
    profiles: list[dict] = []
    for tag_id in list_profiles(tags_sub):
        profile, error = load_profile(tag_id, tags_sub)
        if profile and not error:
            profiles.append(profile)
    return profiles


def _find_svg_in_folder(folder_path: str) -> Optional[str]:
    """Find the most recent SVG in a folder's svg/ subdir."""
    import glob
    svg_sub = os.path.join(folder_path, "svg")
    if not os.path.isdir(svg_sub):
        return None
    matches = sorted(glob.glob(os.path.join(svg_sub, "*.svg")), key=os.path.getmtime, reverse=True)
    return matches[0] if matches else None


def _read_svg_content(svg_path: Optional[str]) -> Optional[str]:
    """Read SVG file content for frontend rendering."""
    if not svg_path or not os.path.isfile(svg_path):
        return None
    try:
        with open(svg_path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _read_floorplan_segments(svg_path: Optional[str]) -> list[dict]:
    """Read full floor-plan linework from the SVG in world coordinates."""
    if not svg_path or not os.path.isfile(svg_path):
        return []
    entries, error = extract_styled_segments_from_svg(svg_path)
    if error:
        return []
    segments: list[dict] = []
    for entry in entries:
        x1, y1, x2, y2 = entry.get("segment", (0, 0, 0, 0))
        segments.append({
            "x1": round(float(x1), 3),
            "y1": round(float(y1), 3),
            "x2": round(float(x2), 3),
            "y2": round(float(y2), 3),
            "role": entry.get("role", "wall"),
        })
    return segments


def _normalize_optional_path(path: Optional[str]) -> Optional[str]:
    """Normalize optional request paths so blank strings behave like unset values."""
    if path is None:
        return None
    stripped = path.strip()
    return stripped or None


def _resolve_rtls_output_dir(
    workspace_id: Optional[str],
    workspace_name: Optional[str],
    folder_path: Optional[str],
    project_path: Optional[str],
) -> Optional[str]:
    """Choose a stable RTLS output directory for CSV/logging state."""
    ws_name = workspace_name or (workspace_id and _workspace_names.get(workspace_id))
    if ws_name:
        rtls_dir = str(workspace_rtls_dir(ws_name))
    elif folder_path:
        rtls_dir = os.path.join(folder_path, "RTLS")
    elif project_path:
        rtls_dir = os.path.join(os.path.dirname(project_path), "RTLS")
    else:
        return None
    os.makedirs(rtls_dir, exist_ok=True)
    return rtls_dir


def _normalize_room_rtls_settings(room_payload: dict) -> dict:
    settings = {
        "tag_height_ft": 0.0,
        "filter_mode": "Raw",
        "ble_module_port": "",
        **dict(room_payload.get("rtls_settings", {})),
    }
    filter_mode = str(settings.get("filter_mode", "Raw") or "Raw").strip() or "Raw"
    if filter_mode.lower() == "none":
        filter_mode = "Raw"
    settings["filter_mode"] = filter_mode
    return settings


def _build_room_summary(room: Room) -> dict:
    payload = room.to_dict()
    settings = _normalize_room_rtls_settings(payload)
    return {
        "room_name": room.name,
        "anchor_count": len(room.anchors),
        "reference_anchor_id": payload.get("reference_anchor_id") or "",
        "ble_module_port": str(settings.get("ble_module_port", "") or "").strip(),
        "filter_mode": str(settings.get("filter_mode", "Raw") or "Raw"),
        "tag_height_ft": float(settings.get("tag_height_ft", 0.0) or 0.0),
    }


@app.get("/api/rtls/snapshot")
async def api_rtls_snapshot():
    """Poll current RTLS state (20 Hz safe — cheap dict copy)."""
    return {"success": True, **_rtls_runtime.snapshot()}


@app.post("/api/rtls/workspace/load")
async def api_rtls_workspace_load(req: RtlsWorkspaceLoadRequest):
    """
    Load room + tag + SVG data into RTLS runtime from workspace.

    Sources are composable so the frontend can keep a stable session:
      - project_path provides packaged room manifest + SVG
      - folder_path provides workspace-style defaults
      - manifest_path / rooms_folder / svg_folder / tags_folder override individually
      - workspace data remains the final fallback
    """
    # Auto-register workspace name so registry survives server restarts
    if req.workspace_id and req.workspace_name:
        _workspace_names[req.workspace_id] = req.workspace_name

    project_path = _normalize_optional_path(req.project_path)
    folder_path = _normalize_optional_path(req.folder_path)
    manifest_path = _normalize_optional_path(req.manifest_path)
    svg_folder = _normalize_optional_path(req.svg_folder)
    rooms_folder = _normalize_optional_path(req.rooms_folder)
    tags_folder = _normalize_optional_path(req.tags_folder)

    tag_profiles: list[dict] = []
    svg_path: Optional[str] = None

    if project_path:
        # A packaged project supplies room geometry and floor-plan SVG.
        project_svg_path, _, _, error = load_project_package(project_path, TEMP_EXTRACT_DIR)
        if error:
            return {"success": False, "error": error}
        if not manifest_path:
            manifest_path = os.path.join(TEMP_EXTRACT_DIR, "room_data.json")
        svg_path = project_svg_path

    if folder_path:
        # A selected workspace folder acts as the default source for all resources
        # unless a more specific override is supplied.
        if not manifest_path:
            manifest_path = _find_manifest_in_folder(folder_path)
        if not svg_path:
            svg_path = _find_svg_in_folder(folder_path)
        if not tags_folder:
            tag_profiles = _load_profiles_from_folder(folder_path)

    if rooms_folder:
        import glob as _glob

        matches = sorted(
            _glob.glob(os.path.join(rooms_folder, "*.rooms.json")),
            key=os.path.getmtime,
            reverse=True,
        )
        if matches:
            manifest_path = matches[0]

    if tags_folder:
        for tag_id in list_profiles(tags_folder):
            profile, error = load_profile(tag_id, tags_folder)
            if profile and not error:
                tag_profiles.append(profile)

    if svg_folder:
        import glob as _glob

        matches = sorted(
            _glob.glob(os.path.join(svg_folder, "*.svg")),
            key=os.path.getmtime,
            reverse=True,
        )
        if matches:
            svg_path = matches[0]

    if not manifest_path:
        manifest_path = _find_workspace_manifest(req.workspace_id, req.workspace_name)
    if not svg_path:
        svg_path = _find_workspace_svg(req.workspace_id, req.workspace_name)
    if not tag_profiles:
        tag_profiles = _load_workspace_profiles(req.workspace_id, req.workspace_name)

    rtls_dir = _resolve_rtls_output_dir(req.workspace_id, req.workspace_name, folder_path, project_path)
    if rtls_dir:
        _rtls_runtime.set_rtls_dir(rtls_dir)

    if not manifest_path:
        return {"success": False, "error": "No rooms manifest found in workspace. Save rooms in Anchor Manager first."}

    manifest, rooms, error = load_floorplan_manifest(manifest_path)
    if error:
        return {"success": False, "error": error}
    if not rooms:
        return {"success": False, "error": "No rooms in manifest."}

    # Pick the requested room or the first
    target_room = rooms[0]
    if req.room_name:
        for r in rooms:
            if r.name == req.room_name:
                target_room = r
                break

    target_room_payload = target_room.to_dict()
    room_payloads = [room.to_dict() for room in rooms]
    room_summaries = [_build_room_summary(room) for room in rooms]
    room_settings = _normalize_room_rtls_settings(target_room_payload)

    _rtls_runtime.update_from_workspace(target_room_payload, tag_profiles)

    # Read SVG content for frontend rendering
    svg_content = _read_svg_content(svg_path)
    floorplan_segments = _read_floorplan_segments(svg_path)

    return {
        "success": True,
        "project_name": str((manifest or {}).get("project_name", "") or ""),
        "room_name": target_room.name,
        "anchor_count": len(target_room.anchors),
        "tag_count": len(tag_profiles),
        "available_rooms": [r.name for r in rooms],
        "rooms": room_payloads,
        "room_summaries": room_summaries,
        "room_settings": room_settings,
        "floorplan_segments": floorplan_segments,
        "svg_content": svg_content,
        "svg_path": svg_path or "",
        **_rtls_runtime.snapshot(),
    }


@app.post("/api/rtls/transport/connect")
async def api_rtls_transport_connect(req: RtlsConnectRequest):
    ok, detail = _rtls_runtime.connect(req.mode or "serial", req.port)
    return {"success": ok, "error": None if ok else detail, **_rtls_runtime.snapshot()}


@app.post("/api/rtls/transport/disconnect")
async def api_rtls_transport_disconnect():
    _rtls_runtime.disconnect()
    return {"success": True, **_rtls_runtime.snapshot()}


@app.post("/api/rtls/serial/connect")
async def api_rtls_serial_connect(req: RtlsConnectRequest):
    ok, detail = _rtls_runtime.connect("serial", req.port)
    return {"success": ok, "error": None if ok else detail, **_rtls_runtime.snapshot()}


@app.post("/api/rtls/serial/disconnect")
async def api_rtls_serial_disconnect():
    _rtls_runtime.disconnect()
    return {"success": True, **_rtls_runtime.snapshot()}


@app.get("/api/rtls/serial/ports")
async def api_rtls_serial_ports():
    from RTLSDashboard.rtls_runtime import auto_detect_esp32_port
    return {
        "success": True,
        "ports": _rtls_runtime.get_serial_ports(),
        "auto_detect_port": auto_detect_esp32_port() or "",
    }


@app.post("/api/rtls/filter")
async def api_rtls_filter(req: RtlsFilterRequest):
    _rtls_runtime.set_filter(
        mode=req.mode,
        ema_alpha=req.ema_alpha,
        roll_n=req.roll_n,
        kal_q=req.kal_q,
        kal_r=req.kal_r,
    )
    return {"success": True, **_rtls_runtime.snapshot()}


@app.post("/api/rtls/elevation")
async def api_rtls_elevation(req: RtlsElevationRequest):
    _rtls_runtime.set_elevation(req.override, req.value_ft)
    return {"success": True, **_rtls_runtime.snapshot()}


@app.post("/api/rtls/csv/start")
async def api_rtls_csv_start():
    """Start CSV distance logging into workspace RTLS/ folder."""
    ok, detail = _rtls_runtime.start_csv_logging()
    if not ok:
        return {"success": False, "error": detail}
    return {"success": True, "path": detail, **_rtls_runtime.snapshot()}


@app.post("/api/rtls/csv/stop")
async def api_rtls_csv_stop():
    """Stop CSV distance logging."""
    _rtls_runtime.stop_csv_logging()
    return {"success": True, **_rtls_runtime.snapshot()}
