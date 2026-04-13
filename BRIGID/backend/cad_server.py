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
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from cad_engine import CADEngine
from config import TAGS_DIR, ROOMS_DIR, TEMP_EXTRACT_DIR, ensure_profile_dirs
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
from utilities.rooms.room_data import Anchor, Room
from utilities.rooms.room_io import (
    create_empty_room,
    save_floorplan_manifest,
    load_floorplan_manifest,
    list_room_profiles,
)
from utilities.rooms.project_io import save_project_package, load_project_package
from utilities.rooms.geometry_utils import find_connected_segments as _find_connected

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


@app.on_event("shutdown")
async def shutdown_runtime() -> None:
    _calibration_runtime.shutdown()
    _workspace_engines.clear()


def _get_engine(workspace_id: str) -> CADEngine:
    if workspace_id not in _workspace_engines:
        _workspace_engines[workspace_id] = CADEngine()
        logger.info("Created new engine for workspace %r", workspace_id)
    return _workspace_engines[workspace_id]


def _load_all_profiles() -> list[dict]:
    profiles: list[dict] = []
    for tag_id in list_profiles(str(TAGS_DIR)):
        profile, error = load_profile(tag_id, str(TAGS_DIR))
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
    distances: dict[str, float | None]
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
async def api_profile_list():
    profiles = list_profiles(str(TAGS_DIR))
    return {"success": True, "profiles": profiles}


@app.get("/api/profile/{tag_id}")
async def api_profile_load(tag_id: str):
    profile, error = load_profile(tag_id, str(TAGS_DIR))
    if error:
        return {"success": False, "error": error}
    return {"success": True, "profile": serialize_profile(profile)}


@app.post("/api/profile/save")
async def api_profile_save(req: SaveProfileRequest):
    errors = validate_profile(req.profile)
    if errors:
        return {"success": False, "error": "; ".join(errors)}
    ok, result = save_profile(req.profile, str(TAGS_DIR))
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
async def api_profile_delete(tag_id: str):
    ok, error = delete_profile(tag_id, str(TAGS_DIR))
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
async def api_calibration_runtime():
    return {"success": True, **_calibration_runtime.snapshot(_load_all_profiles())}


@app.get("/api/calibration/serial/ports")
async def api_calibration_serial_ports():
    return {
        "success": True,
        "ports": _calibration_runtime.get_serial_ports(),
        "auto_detect_port": _calibration_runtime.auto_detect_serial_port(),
    }


@app.post("/api/calibration/transport/connect")
async def api_calibration_transport_connect(req: CalibrationTransportConnectRequest):
    ok, detail = _calibration_runtime.connect(req.mode, _load_all_profiles(), req.port)
    if not ok:
        return {"success": False, "error": detail}
    return {"success": True, "detail": detail, **_calibration_runtime.snapshot(_load_all_profiles())}


@app.post("/api/calibration/transport/disconnect")
async def api_calibration_transport_disconnect():
    _calibration_runtime.disconnect()
    return {"success": True, **_calibration_runtime.snapshot(_load_all_profiles())}


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
async def api_calibration_tag_save(tag_id: str):
    profile, error = load_profile(tag_id, str(TAGS_DIR))
    if profile is None or error:
        return {"success": False, "error": error or f"Profile not found: {tag_id}"}

    profile["calibration"] = _calibration_runtime.export_profile_equations(tag_id)
    ok, result = save_profile(profile, str(TAGS_DIR))
    if not ok:
        return {"success": False, "error": result}
    return {"success": True, "path": result, **_calibration_runtime.snapshot(_load_all_profiles())}


# ===========================================================================
# Room / Anchor Manager REST endpoints
# ===========================================================================

class CreateRoomRequest(BaseModel):
    name: str
    segments: List[List[float]]    # [[x1,y1,x2,y2], ...]
    interior_segments: List[List[float]] = []


class SaveManifestRequest(BaseModel):
    project_name: str
    svg_path: str = ""
    rooms: List[dict]


class LoadManifestRequest(BaseModel):
    filepath: str


class SaveProjectRequest(BaseModel):
    project_path: str
    svg_path: str = ""
    project_name: str
    rooms: List[dict]


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


def _segs_from_list(raw: List[List[float]]):
    return [(float(s[0]), float(s[1]), float(s[2]), float(s[3])) for s in raw]


@app.get("/api/rooms/list")
async def api_rooms_list():
    manifests = list_room_profiles(str(ROOMS_DIR))
    return {"success": True, "manifests": manifests}


@app.post("/api/rooms/create")
async def api_rooms_create(req: CreateRoomRequest):
    segs = _segs_from_list(req.segments)
    interior = _segs_from_list(req.interior_segments)
    room = Room(name=req.name, segments=segs, interior_segments=interior,
                rtls_settings={"tag_height_ft": 0.0, "filter_mode": "None", "ble_module_port": ""})
    return {"success": True, "room": room.to_dict()}


@app.post("/api/rooms/manifest/save")
async def api_rooms_manifest_save(req: SaveManifestRequest):
    try:
        rooms = [Room.from_dict(r) for r in req.rooms]
    except Exception as exc:
        return {"success": False, "error": f"Invalid room data: {exc}"}
    ok, result = save_floorplan_manifest(
        req.project_name, req.svg_path, rooms, str(ROOMS_DIR)
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
    try:
        rooms = [Room.from_dict(r) for r in req.rooms]
    except Exception as exc:
        return {"success": False, "error": f"Invalid room data: {exc}"}
    ok, result = save_project_package(
        req.project_path, req.svg_path, req.project_name, rooms
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
