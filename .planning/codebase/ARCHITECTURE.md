# Architecture

The system is split into two primary paradigms: a legacy / robust PyQt6 application (2DLCAD) and a modernized web-desktop overlay (BRIGID).

## 2DLCAD Architecture
A traditional heavy-client desktop application built entirely in Python.
- **Core Logic:** A monolithic desktop loop handling hardware connectivity, plotting, and UI events simultaneously.
- **Entry Points:** Primarily `main_cad.py`, `main_qt.py`, and `rtls_dashboard.py`.
- **Component Separation:** 
  - *Data Layer:* `room_data.py`, `room_profiles.py` map the spatial data.
  - *Compute:* Mathematics for location mapping handles constraints (`geometry.py`, `rotate.py`, `calibration_utils.py`).
  - *Hardware:* `serial_reader.py` consumes physical data and pushes it up to the UI state.
  - *UI Render:* Canvas and rendering abstractions (`map_canvas.py`, `room_detail_view.py`).

## BRIGID Architecture
A modern distributed layout optimized for decoupled engineering and cross-platform native feel.
- **Frontend Layer:**
  - **Runtime:** Electron + Node.js shell.
  - **UI Thread:** React rendering the user views, utilizing `vite` for fast hot reload.
  - **Entry Points:** `src/main.tsx` (React), `electron/main` (Electron lifecycle).
- **Backend Layer:**
  - **Runtime:** Python process running FastAPI.
  - **Service Boundries:** Decoupled via `cad_server.py` and `cad_engine.py` connecting to endpoints in `main.py`.
- **Data Flow:**
  UWB tags -> Serial Stream -> BRIGID Backend (Python engine) -> WebSocket / REST -> BRIGID Frontend (React).
