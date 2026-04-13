"""
cad_server.py — FastAPI WebSocket server for the CAD engine
============================================================
Run with:
    uvicorn cad_server:app --host 127.0.0.1 --port 8765 --reload

The Electron main process spawns this as a subprocess on startup.
"""

import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from cad_engine import CADEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cad_server")

app = FastAPI(title="BRIGID CAD Server", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "cad-server"}


@app.websocket("/cad/ws")
async def cad_ws(websocket: WebSocket):
    await websocket.accept()
    logger.info("CAD client connected")

    engine = CADEngine()

    # Send initial state immediately so the frontend has something to render
    await websocket.send_text(json.dumps(engine.to_state_dict()))

    try:
        async for raw in websocket.iter_text():
            try:
                cmd = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Received non-JSON message: %r", raw)
                continue

            state = engine.handle_command(cmd)

            try:
                await websocket.send_text(json.dumps(state))
            except Exception as send_err:
                logger.error("Failed to send state: %s", send_err)
                break

    except WebSocketDisconnect:
        logger.info("CAD client disconnected")
    except Exception as exc:
        logger.exception("Unexpected error in CAD WS: %s", exc)
