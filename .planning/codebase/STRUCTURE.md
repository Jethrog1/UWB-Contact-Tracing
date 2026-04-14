# Structure

The repository splits between the legacy system and the new rebuild.

## Root Level
- `BRIGID/`: Modernized web-desktop platform (Active Rebuild Target).
- `2DLCAD/`: Legacy feature-dense python desktop suite (Reference/Legacy).

## `BRIGID/` Layout (Active Rebuild)
- **`backend/`:** 
  - `cad_server.py`: The FastAPI monolithic entrypoint serving all endpoints.
  - `cad_engine.py`: The persistent socket engine for CAD Modeling.
  - `config.py`: Path definitions and Workspace folder generation logic.
  - `CAD/`: Backend parsing for 2D CAD.
  - `RTLSDashboard/`: Handlers for the real-time tracking dashboard (`rtls_runtime.py`, `rtls_main_official.py`).
  - `utilities/`: Python module encapsulating Calibration (`utilities/calibration`), Profiler (`utilities/profilers`), and Rooms/Anchors (`utilities/rooms`).

- **`frontend/`:** 
  - `src/App.tsx`: The main Workspace host and Tab manager.
  - `src/components/modules/`: The core frontend implementations:
    - `AnchorManagerModule/`
    - `CADModule/`
    - `CalibrationToolModule/`
    - `RTLSDashboardModule/`
    - `TagProfilerModule/`
  - `electron/`: Shell runtime scripts.

## `2DLCAD/` Layout (Legacy)
- **Entry Points:** `main_cad.py`, `rtls_main_official.py`, `rtls_dashboard.py`
- **Modules (Monolithic):** `tag_profiler.py`, `calibration_utils.py`
- **Importers:** `pdf_importer.py`, `svg_importer.py`
- **Core Geometry logic & CAD:** `cad_core.py`, `geometry.py`, `dimension_tool.py`, `trim.py`
- **Hardware Connect:** `serial_reader.py`
