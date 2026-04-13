# Tech Stack

This document outlines the core technologies used across the UWB-Contact-Tracing project repositories.

## BRIGID (Web/Desktop Platform)

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

## 2DLCAD (Desktop RTLS/CAD Tools)

### GUI & Interactivity
- **GUI Framework:** PyQt6 standard library
- **Web Elements:** PyQt6-WebEngine
- **Language:** Python

### Computation, Hardware, & Rendering
- **Hardware Comm:** pyserial (Serial port hardware integration)
- **Mathematical & Data:** numpy, matplotlib, opencv-python, pyparsing, contourpy
- **File handling:** PyMuPDF, pillow, PyYAML

### Package Management
- Standard `pip` and `requirements.txt` based builds with standard setuptools dependencies.

These modules show a heavy reliance on Python combined with a modern TypeScript/React web-desktop UI overlay via Electron/FastAPI architectures.
