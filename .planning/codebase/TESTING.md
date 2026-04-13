# Testing

An analysis of testing patterns across the legacy structure and the new architectural direction.

## BRIGID (New Rebuild)
- **Frontend Validation:** Currently, the Vite environment (`electron-vite dev`) allows hot-reloading for UI adjustments. Moving forward, the TypeScript/React layer should integrate tools like `vitest` or `@testing-library/react` to enforce stability lacking in the previous project.
- **Backend Validation:** As FastAPI components are constructed, `pytest` coverage should be mandated on the endpoint architectures routing data to the client.

## 2DLCAD (Legacy)
- **Exploratory Testing:** The legacy Python system heavily relied on visual/manual ad-hoc testing (`dumb stuff 3.py` and vectors like `*test*.svg`).
- **Hardware Test Vectors:** Serial comm testing via physical anchors connected through `serial_reader.py`. Test rooms are modeled inside the legacy code to verify plotting paths visually.
