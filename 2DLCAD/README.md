# 2DLCAD RTLS Dashboard & Planner

A fully integrated Python ecosystem designed to draft, map, and track RTLS (Real-Time Location System) tags across custom physical floor plans. 
This application seamlessly links a 2D Vector CAD drafting system to a live RTLS Map Dashboard.

## Features
- **Central Homepage**: Launch either the live RTLS Dashboard or the Vector CAD Drafting Program.
- **2DLCAD Mapping**: Import PNG, JPG, PDF, and SVG structural references into a highly interactive vector physics grid.
- **Room Manager**: Click to map geometric walls into formalized, interactive designated room areas.
- **Anchor Management**: Set up fixed physical hardware anchors inside rooms. Adjust dimensions via smart inter-distance routing, and manage numbering strictly by local topology (`R[X]A[Y]`).
- **Live RTLS Real-Time Tracking**: A multi-threaded `QThread` PyQt dashboard connects to PySerial, translating live hardware `(X, Y)` frames seamlessly onto the graphical structural blueprints mapping moving tags instantly.
- **Simulations**: Capable of streaming a virtual `MOCK_RTLS` serial payload overlaying oscillating tags natively into the display wrapper for testing without physical connections.

## Installation
It is crucial to run this application utilizing its embedded Python environment `.venv`.
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the App
Use the included shell wrapper to safely set the Python Path and load the Homepage:
```bash
./run_app.sh
```

Or to jump directly to the individual nodes:
```bash
./run_dashboard.sh    # Main Tracking Console
python main_qt.py     # Legacy Full CAD Draw System
```
