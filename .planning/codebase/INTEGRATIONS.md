# Integrations

Across the UWB-Contact-Tracing project, integrations span between hardware layers and local network applications, currently migrating from a monolithic integration (2DLCAD) to a decoupled integration (BRIGID).

## Hardware Integrations
- **UWB Hardware:** The system interacts natively with UWB tags and anchors via serial lines. The `2DLCAD/serial_reader.py` directly handles byte streams from hardware devices to read RTLS coordinates or contact-tracing distances.

## Desktop Integrations
- **Electron API (BRIGID):** The new frontend connects deeply with OS-level integrations via `@electron-toolkit/utils` and standard `electron` IPC capabilities.
- **PyQt Web Integration (Legacy):** `PyQt6-WebEngine` was used within 2DLCAD to embed chromium-based web-view components.

## Local Services & IPC (BRIGID Rebuild)
- **Websockets Base:** FastAPI WebSockets is leveraged in the new BRIGID backend to push high-frequency RTLS data to the React UI in real-time.
- **REST APIs:** FastAPI acts as the primary boundary interface between the python engine (migrated from legacy) and the modern React application.

The primary integrations are internal (between React frontend and FastAPI backend), and physical (between the UWB hardware tags and python serial reading daemons). There are currently no apparent third-party cloud service integrations.
