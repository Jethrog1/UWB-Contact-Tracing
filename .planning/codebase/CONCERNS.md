# Concerns

Current findings, tech debt assessments, and potential fragility points observed within the codebase environment.

## Monolithic / Legacy Tech Debt
**2DLCAD App Volume:**
- `main_cad.py`, `main_qt.py`, `home.py`, and `rtls_dashboard.py` all sit at roughly 100kb in size individually. These represent monolithic files which could be highly susceptible to regressions and difficult to cleanly orchestrate complex UI changes across.
- Functionality is spread across multiple potential "main" execution scripts (`rtls_main_official.py`, `main_cad.py`, `run_app.sh`), causing potential confusion regarding the true source of truth or singular entry portal.

## Code Separation & Redundancy
- Maintaining two entirely disparate UI systems (React/FastAPI vs PyQt6/Matplotlib) creates feature fragmentation. A feature developed mathematically in `2DLCAD` will require custom interface bridges to bring into `BRIGID`.

## Security & Reliability Vulnerabilities
- Raw file handling: Native importing of `.svg` and `.pdf` files without clear comprehensive bounding sandboxes (`svg_importer.py`) could cause parsing panics or UI locks locally if the files are heavily malformed or overly dense.
- Direct Serial Reads (`serial_reader.py`): Parsing arbitrary data over serial connections can silently crash loops if exceptional conditions aren't rigidly caught. 

## Build Confidence
- The complete lack of automated CI pipelines or test harnesses places high burdens on end-of-stage manual UAT testing. Moving forwards, any core geometry changes in `cad_core.py` hold high risk levels.
