"""
cad_server.py — FastAPI WebSocket server for the CAD engine
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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from cad_engine import CADEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cad_server")

app = FastAPI(title="BRIGID CAD Server", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Per-workspace engine registry — survives between frontend reconnects
_workspace_engines: dict[str, CADEngine] = {}


def _get_engine(workspace_id: str) -> CADEngine:
    if workspace_id not in _workspace_engines:
        _workspace_engines[workspace_id] = CADEngine()
        logger.info("Created new engine for workspace %r", workspace_id)
    return _workspace_engines[workspace_id]


@app.get("/health")
async def health():
    return {"status": "ok", "service": "cad-server", "workspaces": len(_workspace_engines)}


async def _run_session(websocket: WebSocket, engine: CADEngine, label: str) -> None:
    """Shared session loop: send initial state then process commands."""
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
    """Workspace-scoped endpoint — engine persists between reconnects."""
    await websocket.accept()
    logger.info("CAD client connected (workspace=%r)", workspace_id)
    engine = _get_engine(workspace_id)
    await _run_session(websocket, engine, workspace_id)


@app.websocket("/cad/ws")
async def cad_ws(websocket: WebSocket):
    """Legacy single-session endpoint (anonymous workspace)."""
    await websocket.accept()
    logger.info("CAD client connected (legacy/anonymous)")
    engine = _get_engine("__default__")
    await _run_session(websocket, engine, "default")
