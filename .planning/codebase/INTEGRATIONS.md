# Integrations

## External Services and Integrations

Across the UWB-Contact-Tracing project, integrations span between hardware layers and local network applications.

### Hardware Integrations
- **UWB Hardware:** The system interacts natively with UWB tags and anchors via serial lines. The `2DLCAD/serial_reader.py` directly handles byte streams from hardware devices to read RTLS coordinates or contact-tracing distances. Requirements like `pyserial` show deep integration with comm ports.

### Desktop Integrations
- **Electron API:** The frontend (BRIGID) connects deeply with OS-level integrations via `@electron-toolkit/utils` and standard `electron` IPC capabilities.
- **PyQt Web Integration:** `PyQt6-WebEngine` is used within 2DLCAD to embed chromium-based web-view components or integrate rich HTML widgets.

### Local Services & IPC
- **Websockets Base:** FastAPI WebSockets is leveraged in the BRIGID backend to push high-frequency RTLS data to the React UI in real-time.
- **REST APIs:** FastAPI acts as the boundary interface between the python engine models and the React application.

### File I/O Integrations
- **SVG & PDF Ingestion:** `svg_importer.py` and `pdf_importer.py` within `2DLCAD` demonstrate data ingestion paths where facility floor plans or architectures from 3rd party CAD systems are parsed and brought into the environment. 

The primary integrations are internal (between React frontend and FastAPI backend), and physical (between the UWB hardware tags and python serial reading daemons). There are currently no apparent third-party cloud service integrations (such as Firebase, AWS, etc.).
