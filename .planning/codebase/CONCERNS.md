# Concerns

Current findings, tech debt assessments, and potential specific pitfalls to avoid during the BRIGID rebuild process.

## The BRIGID Transition Checklist
The primary concern across the codebase is ensuring the 5 main workflows accurately match or exceed legacy 2DLCAD behaviors while remaining decoupled.

1. **Workspace Architecture:** As `cad_server.py` relies on `_workspace_engines` global dictionaries, memory leaks can occur if Workspaces are constantly created and deleted without a cleanup garbage collection logic inside Python.
2. **Calibration Engine Math:** Migrating Python `numpy` and `pandas` polyfit models over to the new `/api/calibration` endpoints requires severe strictness. Small math errors multiply fast when generating tags for an RTLS floorplan.
3. **2D CAD Real-Time Sockets:** WebSockets connecting `cad_engine.py` to React require fast ping/pong thresholds. Rapidly clicking CAD elements could overwhelm an unthrottled socket, leading to sync desynchronization.
4. **Anchor Tracking UI:** The React UI must maintain a 60FPS DOM refresh when rendering the RTLS Dashboard while streaming high-velocity serial tracking events. If not batched properly, the React reconciler will crash.

## Legacy Code Debt
- Do not import directly from `2DLCAD/` into `BRIGID/`. All legacy math or parsers must be cleanly reconstructed in `BRIGID/backend/utilities/` and typed via Pydantic forms to enforce the new architectural mandate.
