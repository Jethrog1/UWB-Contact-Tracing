# Architecture

The system is undergoing a massive architectural shift from a monolithic legacy application to a decoupled, modern stack. 2DLCAD is the legacy model and BRIGID is the future model.

## BRIGID Architecture (New Rebuild)
A modern distributed layout optimized for decoupled engineering, representing a complete rebuild of the platform.

- **Frontend Layer (TypeScript/React):**
  - **Runtime:** Electron + Node.js shell.
  - **UI Thread:** React rendering the user views, utilizing `vite` for fast hot reload.
  - **Core Router:** Tab-based workspace routing where each tab manages a discrete `workspace_id`.
  - **Modules:** The platform is segmented into 5 core modules:
    - `Profile Manager`: Device profiling and default settings.
    - `Calibration Tool`: Tool to capture serial data, calculate mathematical fits, and generate curve formulas for tags.
    - `2D CAD Modeling`: Real-time plotting and vector floorplan creation, communicating via WebSockets.
    - `Anchor Manager`: Tool to locate and manage UWB anchors on maps.
    - `RTLS Dashboard`: Real-time location tracking monitor visualizing serial streams.
- **Backend Layer (Python/FastAPI):**
  - **Runtime:** Python process via `cad_server.py`.
  - **Service Boundaries:** The REST endpoints serve the Profile, Calibration, Anchor, and RTLS Dashboard modules. 2D CAD uses a persistent WebSocket (`/cad/ws/{workspace_id}`) hooked to a `CADEngine`.
- **Data Flow:**
  UWB tags -> Serial Stream -> Python Backend -> WebSocket/REST -> React Frontend.

## The Workspace Workflow
The core organizing principle in BRIGID is the "Workspace" (`App.tsx` and `cad_server.py`). Each open tab represents a Workspace. 
- A Workspace manages its own state, CAD engine instance, and local file storage (`tags/`, `rooms/`, `svg/`, `pdf/`).
- Switching tabs does not destroy the engine; `cad_server.py` keeps `_workspace_engines` in memory.
- Folders are auto-generated when a new Workspace tab is opened.

## 2DLCAD Architecture (Legacy)
A traditional heavy-client desktop application built entirely in Python (PyQt6).
- **Core Logic:** A monolithic desktop loop handling hardware connectivity, plotting, and UI events simultaneously.
- **Legacy Modules:** Scripts like `rtls_dashboard.py`, `tag_profiler.py`, and `main_cad.py` all overlap inside the same monolithic GUI.
