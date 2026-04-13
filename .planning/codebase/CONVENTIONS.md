# Conventions

This section defines the observed implementation styles for both the legacy system and the new rebuild target.

## Rebuild Target: BRIGID
### UI/UX Engineering (Frontend)
- **TypeScript:** The primary language for all frontend logic, shifting away from Python.
- **Frameworks:** React/Electron relies on Blueprint.js to provide an enterprise, high-density dashboard feel. Framer Motion is utilized to ensure smooth transitions.
- **Aesthetic:** The application adheres to a Dark Theme paradigm, targeting a premium, dark-themed, fully offline-capable aesthetic.

### Backend APIs
- **Python / FastAPI:** The backend uses a modern, async approach, utilizing Pydantic models for explicit schema validation in `cad_server.py`. Functions and classes use standard python `snake_case` and `PascalCase`.

## Legacy Baseline: 2DLCAD
- **Framework:** The previous frontend was written entirely in Python using PyQt6.
- **Naming:** Usage of `snake_case` for filenames, variables, and `PascalCase` reserved mainly for PyQt Custom Widgets and Classes (`room_detail_view.py` containing Python classes for widget overlays).
- **Module Separation:** Over-reliance on decoupled scripting (`rotate.py`, `trim.py`) bridging directly into monolithic UIs.
