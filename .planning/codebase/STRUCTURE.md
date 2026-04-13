# Structure

The repository split primarily between the legacy system and the new rebuild.

## Root Level
- `BRIGID/`: Modernized web-desktop platform (Active Rebuild Target).
- `2DLCAD/`: Legacy feature-dense python desktop suite (Reference/Legacy).

## `BRIGID/` Layout (Active Rebuild)
- **`backend/`:** 
  - Contains the new Python-specific FastAPI logic (`main.py`, `cad_server.py`, `cad_engine.py`) designed to replace legacy 2DLCAD backend processing.
- **`frontend/`:** 
  - `src/`: TypeScript/React GUI code replacing PyQt6. Primary entry point `main.tsx`.
  - `electron/`: Shell runtime wrappers.
  - `out/` and `dist/`: Build artifacts targets.

## `2DLCAD/` Layout (Legacy)
- **Entry Points:** `main_cad.py`, `rtls_main_official.py`, `rtls_dashboard.py`
- **Importers:** `pdf_importer.py`, `svg_importer.py`
- **Core Geometry logic & CAD:** `cad_core.py`, `geometry.py`, `dimension_tool.py`, `trim.py`
- **Hardware Connect:** `serial_reader.py`

Code in `BRIGID` follows modern standard web-conventions (`camelCase` or `PascalCase`) for TS/JS and Python `snake_case` for backend, while `2DLCAD` relies entirely on Python conventions intermixed with PyQt6 structural norms.
