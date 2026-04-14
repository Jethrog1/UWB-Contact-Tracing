# Tech Stack

This document outlines the core technologies used across the UWB-Contact-Tracing project repositories, mapping the migration from the 2DLCAD legacy model to the BRIGID future model.

## BRIGID (Future Model)
This is the modernized, from-scratch rebuild of the platform.

### Frontend Environment
- **Framework:** React 18.x
- **Build & Desktop Environment:** Electron via `electron-vite`
- **Language:** TypeScript
- **UI & Components:** BlueprintJS (`@blueprintjs/core`), SCSS/CSS grid layouts.
- **Animations:** Framer Motion (`motion`) package.
- **Visual Presentation:** A highly polished, dark-themed, premium interface design.

### Backend Environment
- **Core Framework:** FastAPI
- **ASGI Server:** Uvicorn
- **Real-time Comms:** WebSockets (For 2D CAD updates) and HTTP REST (For Profiles, Calibration, Profiles, Anchor Manager).
- **Language:** Python
- **Key Python Libraries:** `pydantic` (Data Validation).

## 2DLCAD (Legacy Model)
This is the previous application architecture. It contains the legacy monolithic backend logic and frontend UI.
- **Legacy UI/GUI Framework:** PyQt6 standard library (Python)
- **Hardware Comm:** pyserial (Serial port hardware integration)
- **Mathematical & Data:** numpy, matplotlib, opencv-python, pyparsing, contourpy
- **File handling:** PyMuPDF, pillow, PyYAML

The transition actively deprecates PyQt6 logic, preferring standard HTTP flows backed by React views, while retaining the deep math algorithms inside the new BRIGID Python Backend.
