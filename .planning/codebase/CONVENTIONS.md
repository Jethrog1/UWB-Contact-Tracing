# Conventions

This section defines the observed implementation styles for both the legacy system and the new rebuild target.

## Rebuild Target: BRIGID

### Workspace Paradigm
- A Workspace tab (`workspace_id`) is the binding context for everything. Operations spanning Profile Management, CAD, Calibration, and RTLS must always inject `workspace_id` to ensure isolated state management. Folders are isolated.

### Frontend Conventions (React)
- **Component Strictness:** UI states are isolated inside their module directories (e.g., `CalibrationToolModule/`). 
- **Tab Lifecycle:** Tabs are rendered and persisted using memoized and lazy-loaded structures. Moving between Tabs keeps their previous state intact. Focus limits module un-mounting.
- **Type Safety:** High reliance on TypeScript interfaces inside `src/types.ts`.

### Backend Conventions (FastAPI)
- **Namespaces:** Endpoints are rigorously separated by module: `/api/workspace/*`, `/api/profile/*`, `/api/calibration/*`, `/api/rooms/*`.
- **State Management:** Backend uses global persistence variables (e.g., `_workspace_engines`, `_calibration_runtime`) safely segregated by `workspace_id` mappings behind the scenes.
- **Naming Constraints:** Backend uses `snake_case` for variables, `PascalCase` for Pydantic Models.

## Legacy Baseline: 2DLCAD
- Scripts act both as runners and modules.
- Mixed `snake_case` and `PascalCase` due to PyQt's C++ roots overlapping with Python idioms.
- Data context is frequently global or passed indiscriminately down large class trees.
