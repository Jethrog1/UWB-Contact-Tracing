# Tech Stack

This document outlines the core technologies used across the UWB-Contact-Tracing project repositories, representing the transition from a legacy Python UI to a modern web-desktop platform.

## BRIGID (New Rebuild Architecture)
This is the modernized, from-scratch rebuild of the platform.

### Frontend Environment
- **Framework:** React 18.x
- **Build & Desktop Environment:** Electron via `electron-vite` with `electron` v33
- **Language:** TypeScript
- **UI & Components:** BlueprintJS (`@blueprintjs/core` and `@blueprintjs/icons`)
- **Animations:** Framer Motion (`motion`) package
- **Typography:** Inter (`@fontsource/inter`)

### Backend Environment
- **Core Framework:** FastAPI (v0.109+)
- **ASGI Server:** Uvicorn (standard v0.27+)
- **Real-time Comms:** WebSockets (v12.0+)
- **Language:** Python

## 2DLCAD (Legacy Application)
This is the previous application architecture. It contains the legacy backend logic and frontend UI.
- **Legacy UI/GUI Framework:** PyQt6 standard library (Python)
- **Legacy Web Elements:** PyQt6-WebEngine
- **Hardware Comm:** pyserial (Serial port hardware integration)
- **Mathematical & Data:** numpy, matplotlib, opencv-python, pyparsing, contourpy
- **File handling:** PyMuPDF, pillow, PyYAML

The strategy moving forward utilizes the legacy computation algorithms and features within 2DLCAD as a reference while rebuilding the application as BRIGID using a strict FastAPI + TypeScript/React + Electron paradigm.
