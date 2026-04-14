# Testing

An analysis of testing patterns across the legacy structure and the new architectural direction.

## BRIGID (Future Model)
- **Exploratory testing focus:** Testing is currently visual and explorative via the Electron sandbox (`npm run dev`).
- **Hardware Mocking:** Serial systems typically mock inputs or rely on developers plugging physical anchors into COM ports to verify the Calibration Tool and RTLS Dashboard streams.
- **File System Testing:** Validation involves tracing `tags/`, `rooms/` outputs through standard JSON viewers to ensure the Workspace persistence layer saves cleanly.
- No unit-testing libraries (`jest`, `pytest`) are currently enforced. Building complex math (like polygon intersections in 2D CAD or polynomial fitting in Calibration) carries the burden of manual QA.

## 2DLCAD (Legacy Model)
- **Ad-Hoc Vectors:** Heavy reliance on specific SVG layout files (`roomtest.svg`, `demotest.svg`) to debug visual CAD processing bugs.
- **Scratchpads:** Files like `dumb stuff 3.py` represented iterative local developer tests that were never cleaned up.

**Recommendation:** For future structural integrity of the BRIGID backend CAD Engine and Calibration math, automated tests on pure calculation functions are heavily recommended.
