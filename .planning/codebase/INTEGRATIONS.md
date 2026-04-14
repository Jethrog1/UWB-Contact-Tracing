# Integrations

Across the UWB-Contact-Tracing project, integrations span between hardware layers and local network applications. The system focuses entirely on hardware and local IO integration.

## UWB Hardware Integration
- **Legacy (2DLCAD):** The `serial_reader.py` directly handles byte streams from hardware devices to read RTLS coordinates or contact-tracing distances, pushing directly into PyQt variables.
- **Future (BRIGID):** The Python backend uses `utilities/calibration/runtime.py` and `RTLSDashboard/rtls_runtime.py` to stream serial data. This data is fed through filtering algorithms (Kalman, EMA) and piped to the React Frontend either via WebSocket streams or REST polling methods.

## Data Workflows & Workspaces
- **Workspace Integration:** BRIGID integrates deeply with the local filesystem. Every new tab creates a discrete `Workspace N` folder on disc containing `tags/`, `rooms/`, `svg/`, and `pdf/`. The backend acts as a file server interface mapping the frontend UI interactions seamlessly to local disc persistence.
  
## Module IPC Integrations (BRIGID)
- **Profile Manager:** Integrates with `tags/` JSON payloads via `/api/profile/*`.
- **Calibration Tool:** Direct serial integration converting raw anchor feeds to polynomial regression models via `/api/calibration/*`.
- **2D CAD Modeling:** Live memory mirroring via `/cad/ws/{workspace_id}` to sync engine plot commands.
- **Anchor Manager:** Integrates with `.rooms.json` parsing.
- **RTLS Dashboard:** Stream consumption via `rtls_runtime.py`.

There are no apparent third-party cloud service endpoints involved in this system; it is purely an offline desktop tool integration flow.
