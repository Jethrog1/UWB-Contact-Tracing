# Structure

The repository is modularly structured, split primarily by major application variants.

## Root Level
- `BRIGID/`: Modernized web-desktop platform.
- `2DLCAD/`: Legacy feature-dense python desktop suite.

## `2DLCAD/` Layout
- **Entry Points:** `main_cad.py`, `rtls_main_official.py`, `rtls_dashboard.py`
- **Importers:** `pdf_importer.py`, `svg_importer.py`
- **CAD Tools:** `dimension_tool.py`, `copy_paste.py`, `rotate.py`, `trim.py`
- **Core Geometry logic:** `cad_core.py`, `geometry.py`, `map_canvas.py`, `qt_snap.py`
- **Hardware Connect:** `serial_reader.py`
- **SVG Assets:** Various test `.svg` maps (`demotest.svg`, `roomtest.svg`)
- **Shell Hooks:** `run_app.sh`, `run_dashboard.sh` serving as quickstarts.

## `BRIGID/` Layout
- **`backend/`:** 
  - Contains Python-specific FASTAPI logic (`main.py`, `cad_server.py`, `cad_engine.py`).
- **`frontend/`:** 
  - `src/`: React GUI code containing the primary entry point `main.tsx`.
  - `electron/`: Shell runtime wrappers.
  - `out/` and `dist/`: Build artifacts targets.

File names largely stick to `snake_case` in Python contexts (`2DLCAD/` and `BRIGID/backend/`) and standard web-conventions (`camelCase` or `PascalCase` depending on JS/TS context) in `BRIGID/frontend`.
