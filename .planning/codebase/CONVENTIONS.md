# Conventions

This section defines the observed implementation styles, file structures, and code behavior within the core applications.

## Development Stack Conventions
- **Python Formatting (2DLCAD & BRIGID-Backend):**
  - **Naming:** Consistent usage of `snake_case` for filenames, variables, and standard functions. `PascalCase` is reserved mainly for PyQt Custom Widgets and Classes (`room_detail_view.py` containing Python classes for widget overlays).
  - **Module Separation:** In the CAD app, tools are extensively decoupled into single functional scripts (`rotate.py`, `trim.py`, `dimension_tool.py`), keeping main canvases clean.

## UI/UX Engineering Conventions
- **BRIGID (Electron/React):**
  - Blueprint.js is used to provide an enterprise, high-density dashboard feel.
  - Framer Motion is utilized to ensure smooth, dynamic transitions.
  - The application adheres to a Dark Theme paradigm (referred to as a "premium, dark-themed, fully offline-capable aesthetic").
  - Tooling relies heavily on Vite for rapid frontend module reloading.

## Backend APIs
- **FastAPI Models:**
  - Modern, async approach to web server management. Expected usage includes Pydantic models for explicit schema validation in `cad_server.py`.

## General Code Practices
- The project is split into distinct functional "modules" or sub-apps.
- Environment logic attempts to stay fully offline, isolating logic internally rather than dispatching calls over WAN networks.
- Reliance on exact dependency locking (e.g., specific `PyQt6` and `contourpy` versions tracked inside requirements files).
