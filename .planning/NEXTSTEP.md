# BRIGID Import/Export Feature Implementation

## System Instructions for Agent

### Context
We are porting three critical features from the legacy 2DL CAD application to BRIGID:
1. **Import Files** – Load PDF/SVG floor plans into the CAD editor
2. **Save as SVG** – Export CAD models to vector SVG format with metadata for re-import
3. **Save as PDF** – Export CAD models to printable PDF format

**CRITICAL:** Study the backend logic in `2DLCAD/pdf_importer.py`, `2DLCAD/svg_importer.py`, and the import/save methods in `2DLCAD/main_qt.py`. **DO NOT COPY the old PyQt6 CAD model code** – only extract the import/export backend logic and adapt it to BRIGID's architecture.

### Key Principles
- **Backend-Driven:** All file I/O and coordinate transformations happen in Python (`BRIGID/backend/`)
- **API-Exposed:** Import/export endpoints are REST/WebSocket APIs in `cad_server.py`
- **UI in Right Panel:** Add three buttons (Import, Save SVG, Save PDF) at the bottom of `CADRightPanel.tsx`
- **No Old Code:** The new CAD logic in BRIGID is cleaner; only port the utility functions
- **Color Preservation:** SVG import/export must preserve line colors (wall vs. non-wall distinction)
- **Coordinate Safety:** All coordinate transforms must match between import and export (roundtrip consistency)

### For the Implementer
1. **Understand the flow first:**
   - Import: File → Parse segments → Center on viewport → Create Line objects → Update state
   - SVG Export: Lines → Bounding box → Normalize to 1000x1000 canvas → Add metadata → Write file
   - PDF Export: Lines → A4 page layout → Transform coordinates → Render with QPainter

2. **Copy these specific utilities from 2DLCAD:**
   - `pdf_importer.py` → `BRIGID/backend/utilities/importers/pdf_importer.py`
   - `svg_importer.py` → `BRIGID/backend/utilities/importers/svg_importer.py`
   - SVG export logic from `main_qt.py::save_as_svg()` → New backend function
   - PDF export logic from `main_qt.py::save_as_pdf()` → New backend function

3. **Adapt for BRIGID:**
   - Remove PyQt6 imports and replace with Python standard library equivalents
   - Use `CADLine` TypeScript interface for communication
   - Return JSON-serializable data from backend
   - Wire up endpoints in `cad_server.py` with proper error handling

4. **Frontend Integration:**
   - File dialogs handled by Electron (`ipcRenderer.invoke()`)
   - Send file paths to backend via POST/WebSocket
   - Display error/success messages via toast notifications
   - UI buttons placed in right panel (bottom section)

### Color Preservation
- Wall segments: Default blue `#4A9EFF`
- Non-wall segments: Gray `#8E949C`
- SVG export must embed CAD metadata (scale, offset, min_x, min_y) as SVG attributes for perfect re-import
- PDF uses black lines (white background incompatible with light colors)

---

## Implementation Plan

### Phase 1: Prepare Backend Infrastructure
**Duration:** 15 min

1. **Create utility directory structure:**
   ```
   BRIGID/backend/utilities/
   ├── importers/
   │   ├── __init__.py
   │   ├── pdf_importer.py      (adapted from 2DLCAD)
   │   ├── svg_importer.py      (adapted from 2DLCAD)
   │   └── coordinate_transforms.py (new utility)
   └── exporters/
       ├── __init__.py
       ├── svg_exporter.py       (new)
       └── pdf_exporter.py       (new)
   ```

2. **Copy and adapt importer modules:**
   - Copy `2DLCAD/pdf_importer.py` → `BRIGID/backend/utilities/importers/pdf_importer.py`
   - Copy `2DLCAD/svg_importer.py` → `BRIGID/backend/utilities/importers/svg_importer.py`
   - Remove/update imports: keep only standard library (no PyQt6/Qt imports)
   - Ensure functions return plain tuples/lists, not Qt objects

3. **Create coordinate_transforms.py:**
   - Helper functions for viewport centering logic
   - Bounding box calculations (min/max extraction)
   - Offset calculation for centering geometry

### Phase 2: Implement Export Logic
**Duration:** 20 min

1. **SVG Exporter (`svg_exporter.py`):**
   - **Function:** `export_lines_to_svg(lines: List[Line], filepath: str) -> Tuple[bool, str]`
   - Compute bounding box from all lines
   - Transform coordinates to 1000×1000 canvas with 5% margin
   - For each line:
     - Use line.color (preserve color metadata)
     - Handle Spline vs. Line rendering (Spline → cubic Bezier path, Line → `<line>`)
   - Embed CAD metadata as SVG attributes: `data-cad-scale`, `data-cad-min-x`, `data-cad-min-y`, `data-cad-offset-x`, `data-cad-offset-y`
   - Write to file; return success/error

2. **PDF Exporter (`pdf_exporter.py`):**
   - **Function:** `export_lines_to_pdf(lines: List[Line], filepath: str) -> Tuple[bool, str]`
   - Use PyQt6 `QPdfWriter` (already available)
   - Standard A4 Landscape (297×210 mm)
   - Transform coordinates to PDF page space
   - Draw lines with appropriate stroke width
   - Lines with color `#FFFFFF` → convert to `#000000` (black for visibility on white background)
   - Handle Spline rendering via `QPainterPath.cubicTo()`
   - Write to file; return success/error

### Phase 3: Wire Backend Endpoints
**Duration:** 15 min

1. **Add to `cad_server.py` or create handler file:**

   ```python
   @app.post("/api/cad/import")
   async def import_file(request: ImportRequest):  # filepath, file_type="pdf"|"svg"
       try:
           filepath = request.filepath
           if filepath.endswith(".pdf"):
               segments, error = extract_lines_from_pdf(filepath)
           elif filepath.endswith(".svg"):
               segments, error = extract_styled_segments_from_svg(filepath)
           
           if error:
               return {"success": False, "error": error}
           
           if not segments:
               return {"success": False, "error": "No geometry found"}
           
           # Return segments + metadata for frontend to create Line objects
           return {"success": True, "segments": segments, "count": len(segments)}
       except Exception as e:
           return {"success": False, "error": str(e)}
   
   @app.post("/api/cad/export")
   async def export_file(request: ExportRequest):  # lines, filepath, format="svg"|"pdf"
       try:
           if request.format == "svg":
               success, error = export_lines_to_svg(request.lines, request.filepath)
           elif request.format == "pdf":
               success, error = export_lines_to_pdf(request.lines, request.filepath)
           
           if not success:
               return {"success": False, "error": error}
           return {"success": True, "filepath": request.filepath}
       except Exception as e:
           return {"success": False, "error": str(e)}
   ```

2. **Add request/response types:**
   - `ImportRequest` – filepath, file_type
   - `ExportRequest` – lines (list of dicts), filepath, format

### Phase 4: Create Frontend UI Components
**Duration:** 15 min

1. **Add buttons to `CADRightPanel.tsx`:**
   ```tsx
   <div className="cad-bottom-panel">
     <button onClick={handleImport}>Import File</button>
     <button onClick={handleSaveSVG}>Save as SVG</button>
     <button onClick={handleSavePDF}>Save as PDF</button>
   </div>
   ```

2. **Implement handlers:**
   - `handleImport()` – Opens file dialog, calls `/api/cad/import`, processes segments
   - `handleSaveSVG()` – Opens file dialog, calls `/api/cad/export` with format="svg"
   - `handleSavePDF()` – Opens file dialog, calls `/api/cad/export` with format="pdf"

3. **File dialog integration (Electron):**
   ```tsx
   const { dialog } = require('electron');
   
   const result = await ipcRenderer.invoke('open-file-dialog', {
     filters: [
       { name: 'Vector Files', extensions: ['pdf', 'svg'] },
     ]
   });
   ```

   Add to `electron/main.ts` preload:
   ```ts
   ipcMain.handle('open-file-dialog', async () => {
     return dialog.showOpenDialog(mainWindow, {...});
   });
   ```

### Phase 5: Integration & Testing
**Duration:** 20 min

1. **Viewport Centering:**
   - Import: Calculate current viewport center → geometry bounding center → offset
   - Resulting offset applied to all imported line coords

2. **Error Handling:**
   - Empty files → "No geometry found"
   - Unsupported formats → "Invalid file format"
   - File I/O errors → Display error toast

3. **Test Roundtrip:**
   - Create lines in CAD → Save as SVG → Reimport → Verify geometry matches
   - Verify colors preserved through SVG export/import
   - Verify PDF renders correctly (visually)

4. **UI Polish:**
   - Disable buttons during processing
   - Show progress toast during import
   - Success/error notifications

---

## File Checklist

### New Files to Create
- [ ] `BRIGID/backend/utilities/__init__.py`
- [ ] `BRIGID/backend/utilities/importers/__init__.py`
- [ ] `BRIGID/backend/utilities/importers/pdf_importer.py` (adapted)
- [ ] `BRIGID/backend/utilities/importers/svg_importer.py` (adapted)
- [ ] `BRIGID/backend/utilities/importers/coordinate_transforms.py` (new)
- [ ] `BRIGID/backend/utilities/exporters/__init__.py`
- [ ] `BRIGID/backend/utilities/exporters/svg_exporter.py` (new)
- [ ] `BRIGID/backend/utilities/exporters/pdf_exporter.py` (new)

### Files to Modify
- [ ] `BRIGID/backend/cad_server.py` – Add `/api/cad/import` and `/api/cad/export` endpoints
- [ ] `BRIGID/frontend/src/components/modules/CADModule/CADRightPanel.tsx` – Add bottom panel with buttons
- [ ] `BRIGID/frontend/src/components/modules/CADModule/useCADWebSocket.ts` – Add import/export event handlers
- [ ] `BRIGID/frontend/electron/main.ts` – Add file dialog IPC handlers
- [ ] `BRIGID/backend/main.py` – Import new modules and register routes

### Reference Files (Legacy)
- `2DLCAD/pdf_importer.py` – Source for PDF extraction
- `2DLCAD/svg_importer.py` – Source for SVG parsing
- `2DLCAD/main_qt.py` (lines 2464-2628) – SVG/PDF export logic

---

## Success Criteria
- [ ] Import PDF: Opens file dialog, parses PDF, displays geometry in CAD
- [ ] Import SVG: Opens file dialog, parses SVG with colors, displays geometry
- [ ] Save SVG: Exports CAD model to SVG with metadata, can be re-imported
- [ ] Save PDF: Exports CAD model to printable PDF (A4 landscape)
- [ ] Roundtrip: SVG export → SVG import produces identical geometry
- [ ] Colors: Wall (blue) and non-wall (gray) segments preserved through import/export
- [ ] UI: Three buttons in right panel, functional, proper error messages
- [ ] No crashes on edge cases: empty files, unsupported formats, file system errors

---

## Notes for Agent
- **Do not** copy old CAD UI code (main_qt.py main window, PyQt6 widgets)
- **Do** extract and adapt the file I/O and coordinate transformation logic
- **Match** the existing CAD types (use `CADLine` interface for communication)
- **Test** SVG roundtrip: export → reimport must produce identical geometry
- **Handle** color preservation: `#4A9EFF` (wall), `#8E949C` (non-wall)
- **Ensure** PDF uses black strokes on white background (inverse from SVG/CAD canvas)
