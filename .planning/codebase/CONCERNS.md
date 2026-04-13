# Concerns

Current findings, tech debt assessments, and potential specific pitfalls to avoid during the BRIGID rebuild process.

## Legacy Monolithic Tech Debt
**2DLCAD Overlap:**
- The legacy PyQt6 project suffered from monolithic files (`main_cad.py`, `rtls_dashboard.py` > 100kb), making it difficult to maintain and scale. The BRIGID rebuild must actively avoid recreating these monolithic structures by tightly enforcing React component paradigms and strict separation of concerns in the FastAPI backend.

## Rebuild Transition Risks
- **Extraction Accuracy:** Rebuilding the mathematical logic, serial parsers, and UI mechanics from 2DLCAD into the cleanly separated BRIGID (TypeScript Frontend + Python Backend) carries a high risk of feature degradation or logical transcription errors during porting.
- **IPC Latency:** Transitioning from a Python-only memory thread base to Python backend -> WebSocket -> TypeScript Electron renderer introduces IPC (Inter-Process Communication) and networking latency that must be monitored tightly, especially given real-time UWB tracking frequencies.

## Build Confidence
- The legacy project showed a complete lack of automated CI pipelines or test harnesses. Establishing strong test practices early in the BRIGID lifecycle translates into higher velocity down the road.
