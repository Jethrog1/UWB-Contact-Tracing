"""
BRIGID Backend — FastAPI Stub
============================
This is a placeholder backend for the BRIGID RTLS Desktop Platform.
No real functionality is implemented yet.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="BRIGID API",
    description="BRIGID RTLS Platform Backend — Stub",
    version="0.1.0",
)

# CORS for Electron renderer
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "brigid-api", "version": "0.1.0"}


@app.get("/api/v1/status")
async def system_status():
    """Placeholder system status endpoint."""
    return {
        "system": "online",
        "modules": {
            "rtls": "standby",
            "analytics": "standby",
            "detection": "standby",
        },
        "message": "Backend stub — no real functionality yet.",
    }
