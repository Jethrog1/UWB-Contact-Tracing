# Architecture

The system is undergoing a massive architectural shift from a monolithic legacy application to a decoupled, modern stack.

## BRIGID Architecture (New Rebuild)
A modern distributed layout optimized for decoupled engineering, representing a complete from-scratch rebuild of the platform.
- **Frontend Layer (TypeScript/React):**
  - **Runtime:** Electron + Node.js shell.
  - **UI Thread:** React rendering the user views, utilizing `vite` for fast hot reload.
  - **Entry Points:** `src/main.tsx` (React), `electron/main` (Electron lifecycle).
- **Backend Layer (Python/FastAPI):**
  - **Runtime:** Python process running FastAPI.
  - **Service Boundries:** Decoupled via `cad_server.py` and `cad_engine.py` connecting to endpoints in `main.py`. This backend will inherit and improve upon the logic from the legacy project.
- **Data Flow:**
  UWB tags -> Serial Stream -> BRIGID Backend (Python) -> WebSocket / REST -> BRIGID Frontend (React).

## 2DLCAD Architecture (Legacy)
A traditional heavy-client desktop application built entirely in Python (PyQt6).
- **Core Logic:** A monolithic desktop loop handling hardware connectivity, plotting, and UI events simultaneously.
- **Component Separation:** 
  - *Data Layer:* `room_data.py`, `room_profiles.py` map the spatial data.
  - *Compute:* Mathematics mapping handles constraints (`geometry.py`, `rotate.py`, `calibration_utils.py`).
  - *Hardware:* `serial_reader.py` consumes physical data and pushes it up to the UI state.
