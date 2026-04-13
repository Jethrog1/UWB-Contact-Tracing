# BRIGID Anchor Manager Feature Implementation

## System Instructions for Agent

### Context
We are building the **Anchor Manager** for BRIGID—a workspace that allows operators to:
1. **Load floor plans** (SVG files from CAD or imported geometry)
2. **Create rooms** by selecting geometry from the floor plan
3. **Place anchors** on rooms (RTLS reference points)
4. **Edit room metadata** (name, RTLS settings)
5. **Manage anchor details** (hardware ID, position, height)
6. **Save room+anchor data** as JSON for downstream RTLS operations

The Anchor Manager is a **graphical room/anchor editor**, not a CAD program. It reuses SVG import logic from the Import/Export feature (NEXTSTEP.md) and extends it with room management UI.

**CRITICAL:** Study `2DLCAD/room_data.py`, `room_detail_view.py`, and `room_profiles.py`. Extract the Room/Anchor data structures and JSON serialization logic. **DO NOT COPY PyQt6 UI code** – rebuild with React components.

### Key Principles
- **Canvas-based:** Floor plan displayed in central canvas with viewport/zoom controls
- **Right Panel:** Room list + anchor editor (active when room selected)
- **Hot Bar Integration:** File menu with Load SVG, Load Room Data, Save Room Data, Save Project
- **No Simulation:** No fake tag playback, distance visualization, or live RTLS (for future expansion)
- **JSON Persistence:** Save rooms to `BRIGID/profile/{project_name}.rooms.json`
- **Reusable Import:** Leverage SVG import from NEXTSTEP.md (segments → geometry display)
- **Coordinate System:** World-space for floor plan, local-space for each room

### Data Structures

**Room Object:**
```python
{
    "name": str,
    "segments": List[(x1, y1, x2, y2)],        # boundary in world coords
    "interior_segments": List[(x1, y1, x2, y2)],
    "anchors": List[Anchor],
    "rtls_settings": {
        "tag_height_ft": float,
        "filter_mode": str,
        "ble_module_port": str
    },
    "min_x": float, "min_y": float,
    "max_x": float, "max_y": float
}
```

**Anchor Object:**
```python
{
    "id": str,              # "R1A0", "R1A1" (room + index)
    "hw_id": str,           # "A0", "A3" (physical device ID, user-set)
    "x": float,             # local x in room
    "y": float,             # local y in room
    "z": float              # height from floor (feet)
}
```

**Project Manifest:**
```json
{
    "project_name": "Floor_1",
    "svg_file": "floor_1.svg",
    "saved_at": "2026-04-13T14:30:00",
    "units": "ft",
    "rooms": [{ Room object }, ...]
}
```

### For the Implementer

1. **Understand the workflow:**
   - Load SVG → Parse segments → Display on canvas
   - Select geometry segments → Create room → Name it
   - Click on room canvas → Place anchors (Ctrl+Click)
   - Select anchor → Edit properties (x, y, z, hw_id) in right panel
   - Save room data → JSON file in `BRIGID/profile/`

2. **Coordinate System Details:**
   - **World-space:** SVG coordinates, shared across all rooms
   - **Local-space:** Room's bounding box origin at (min_x, min_y)
   - Anchors stored in local-space to support room repositioning
   - World ↔ Local transforms: `local_x = world_x - room.min_x`

3. **Room Creation Strategy:**
   - User selects segments on canvas (by clicking/dragging)
   - Backend finds connected chains of segments
   - User confirms room name + boundary
   - Segments marked as "room boundary"
   - Remaining segments = "interior" (optional)

4. **Canvas Rendering:**
   - Background: imported SVG geometry (light gray #8E949C)
   - Room boundaries: highlighted in cyan/blue
   - Selected room: brighter blue with control points
   - Anchors: circular pins with labels (A0, A1, etc.)
   - Grid overlay (optional, configurable)

5. **File Operations:**
   - **Load SVG:** File dialog → segments → display
   - **Load Room Data:** File dialog → parse JSON → load rooms
   - **Save Room Data:** Save current project to JSON
   - **Save Project:** Export as `.rtlsproj` (ZIP: SVG + JSON)

6. **Right Panel Editor:**
   - When no room selected: "Select a room to edit"
   - When room selected:
     - Room name (editable text)
     - Anchor list (table)
     - Selected anchor properties (x, y, z, hw_id, color picker)
     - "Add Anchor" button (Ctrl+Click on canvas)
     - "Delete Anchor" button (Del key)

### Design Guidance
- **Canvas:** Full-width, centered, with zoom/pan
- **Hot bar:** File menu with 4 options + Tools submenu (Show Grid, Lock Anchors)
- **Right panel:** 250px wide, scrollable, collapsible sections
- **Colors:** Walls #4A9EFF, anchors #FF8C00 (orange), selected #FFD700 (gold)
- **Snap-to-grid:** Optional, 0.5 ft increments
- **Undo/Redo:** Track anchor placements and room modifications

---

## Implementation Plan

### Phase 1: Backend Infrastructure & Data Models
**Duration:** 25 min

1. **Create room management module:**
   - `BRIGID/backend/utilities/rooms/__init__.py`
   - `BRIGID/backend/utilities/rooms/room_data.py`
     - Port `Room` and `Anchor` dataclasses from 2DLCAD
     - Include coordinate transform methods
     - Implement polygon containment checking
   - `BRIGID/backend/utilities/rooms/room_io.py`
     - `create_empty_room(name: str) → Room`
     - `save_room_profile(room: Room, filepath: str) → Tuple[bool, str]`
     - `load_room_profile(filepath: str) → Tuple[Room, str]`
     - `list_rooms(profile_dir: str) → List[str]`

2. **Create room geometry utilities:**
   - `BRIGID/backend/utilities/rooms/geometry_utils.py`
     - `find_connected_segments(all_segments, start_seg) → List[Tuple]`
     - `build_room_bounds(segments) → (min_x, max_x, min_y, max_y)`
     - `point_to_segment_distance(px, py, x1, y1, x2, y2) → float`
     - `point_in_polygon(px, py, polygon_points) → bool`

3. **Create project manifest module:**
   - `BRIGID/backend/utilities/rooms/project_io.py`
     - `build_project_manifest(project_name, svg_path, rooms) → dict`
     - `save_project_manifest(manifest, filepath) → Tuple[bool, str]`
     - `load_project_manifest(filepath) → Tuple[dict, List[Room], str]`
     - `save_project_package(filepath, svg_content, rooms) → Tuple[bool, str]` (ZIP export)
     - `load_project_package(filepath, extract_dir) → Tuple[svg_path, rooms, str]`

### Phase 2: Wire Backend API Endpoints
**Duration:** 20 min

1. **Add REST endpoints to `cad_server.py`:**

   ```python
   @app.post("/api/rooms/create")
   async def create_room(request: CreateRoomRequest):
       # request.name, request.segments
       room = create_empty_room(request.name)
       room.segments = request.segments
       return {"success": True, "room": serialize_room(room)}
   
   @app.post("/api/rooms/save")
   async def save_room(request: SaveRoomRequest):
       # request.room, request.project_dir
       success, error = save_room_profile(request.room, ...)
       if not success:
           return {"success": False, "error": error}
       return {"success": True}
   
   @app.post("/api/rooms/list")
   async def list_rooms(request: ListRoomsRequest):
       # request.project_dir
       rooms = list_rooms(request.project_dir)
       return {"success": True, "rooms": rooms}
   
   @app.post("/api/rooms/load")
   async def load_room(request: LoadRoomRequest):
       # request.room_id, request.project_dir
       room, error = load_room_profile(room_id, request.project_dir)
       if error:
           return {"success": False, "error": error}
       return {"success": True, "room": serialize_room(room)}
   
   @app.post("/api/rooms/delete")
   async def delete_room(request: DeleteRoomRequest):
       # request.room_id, request.project_dir
       success, error = delete_room_profile(request.room_id, ...)
       return {"success": success, "error": error or ""}
   
   @app.post("/api/rooms/project/save")
   async def save_project(request: SaveProjectRequest):
       # request.project_name, request.svg_content, request.rooms
       manifest = build_project_manifest(...)
       success, error = save_project_manifest(manifest, filepath)
       return {"success": success, "error": error or ""}
   
   @app.post("/api/rooms/project/load")
   async def load_project(request: LoadProjectRequest):
       # request.filepath
       manifest, rooms, error = load_project_manifest(filepath)
       if error:
           return {"success": False, "error": error}
       return {"success": True, "manifest": manifest, "rooms": serialize_rooms(rooms)}
   
   @app.post("/api/rooms/anchor/add")
   async def add_anchor(request: AddAnchorRequest):
       # request.room_id, request.anchor (x, y, z, hw_id)
       # Validate position in room, assign ID (R1A0, R1A1, etc.)
       return {"success": True, "anchor": anchor}
   
   @app.post("/api/rooms/anchor/update")
   async def update_anchor(request: UpdateAnchorRequest):
       # request.room_id, request.anchor_id, request.updates
       return {"success": True, "anchor": anchor}
   
   @app.post("/api/rooms/anchor/delete")
   async def delete_anchor(request: DeleteAnchorRequest):
       # request.room_id, request.anchor_id
       return {"success": True}
   
   @app.post("/api/rooms/geometry/find-segments")
   async def find_connected_segments(request: FindSegmentsRequest):
       # request.all_segments, request.start_seg_index
       segments = find_connected_segments(request.all_segments, request.start_seg_index)
       return {"success": True, "segments": segments}
   ```

2. **Define request/response types in TypeScript and Python**

3. **Project directory:** `BRIGID/profile/` for room JSON files

### Phase 3: Build Frontend Canvas & Room Manager UI
**Duration:** 50 min

1. **Canvas Component: `AnchorManagerCanvas.tsx`**
   - Displays floor plan (SVG segments)
   - Mouse controls: pan (middle-click), zoom (scroll)
   - Click to select segments (multi-select with Shift)
   - Ctrl+Click to place anchors
   - Right-click context menu (Delete, Properties)
   - Keyboard shortcuts (F=fit view, Delete=remove, Arrow keys=nudge)

2. **Room Manager: `RoomManager.tsx`**
   - Room list (left panel, 150px)
   - "New Room" button
   - Room name editor
   - Load/Save project buttons (top)
   - Canvas area (center, takes remaining space)
   - Right panel (250px) with anchor editor

3. **Right Panel: `AnchorEditPanel.tsx`**
   - Room info card (name, bounds, anchor count)
   - Anchor list table:
     - Columns: ID, hw_id, X, Y, Z
     - Click row to select
     - Delete button per row
   - Selected anchor properties:
     - hw_id input
     - x, y, z numeric inputs
     - "Apply" button
   - "Add Anchor" hint (Ctrl+Click on canvas)
   - "Delete Anchor" hint (Delete key)

4. **Geometry Browser: `GeometryPanel.tsx`** (optional left panel)
   - File info (name, segment count)
   - Layer visibility toggle (walls, interior, anchors)
   - Grid toggle

5. **CSS Styling: `AnchorManager.css`**
   - Canvas styling (dark background, border)
   - Hot bar buttons
   - Right panel styling
   - Room list styling
   - Scrollbars

### Phase 4: Hot Bar & File Menu Integration
**Duration:** 15 min

1. **Update Hot Bar:**
   - Add "File" menu with:
     - Load SVG... (Ctrl+O)
     - Load Room Data... (Ctrl+Shift+O)
     - Save Room Data (Ctrl+S)
     - Save Project As... (Ctrl+Shift+S)
   - Add "Tools" submenu:
     - Show Grid (toggle)
     - Snap to Grid (toggle)
     - Lock Anchors (toggle)

2. **Keyboard shortcuts:**
   - Ctrl+O: Open SVG
   - Ctrl+S: Save rooms
   - Ctrl+Shift+S: Save project
   - F: Fit view
   - Delete: Remove selected anchor
   - Ctrl+Z: Undo
   - Ctrl+Y: Redo

3. **File dialogs (Electron):**
   - Load SVG: `.svg` files
   - Load Room Data: `.rooms.json` files
   - Save Project: `.rtlsproj` (ZIP) or `.rooms.json`

### Phase 5: Canvas Interaction & Selection
**Duration:** 30 min

1. **Mouse event handlers:**
   - `mousePressEvent` – start selection/pan
   - `mouseMoveEvent` – pan/select box
   - `mouseReleaseEvent` – finalize selection
   - `wheelEvent` – zoom
   - `dblClickEvent` – fit room in view

2. **Selection logic:**
   - Single click: select one segment
   - Shift+click: toggle segment in selection
   - Drag: select rectangle of segments
   - Selected segments: highlight in blue/cyan

3. **Anchor placement:**
   - Ctrl+click on canvas: place anchor at world position
   - Validate position is within room bounds
   - Auto-assign ID (R1A0, R1A1, etc.)
   - Update right panel

4. **Undo/Redo stack:**
   - Track room creations, anchor additions/deletions, property changes
   - Store snapshots of room state
   - Max 50 entries

### Phase 6: Room Creation Workflow
**Duration:** 20 min

1. **Create room dialog:**
   - User selects segments on canvas
   - Clicks "Create Room" button
   - Dialog pops up with:
     - Room name input (auto: "Room_1", "Room_2", etc.)
     - Segment count display
     - "Create" / "Cancel" buttons

2. **Backend processing:**
   - Validate segments form a closed loop (or accept open chains)
   - Compute bounding box
   - Build polygon for containment testing
   - Separate boundary vs. interior segments

3. **Frontend state update:**
   - New room added to list
   - Canvas redrawn with highlighted boundary
   - Right panel shows new room editors

### Phase 7: Save/Load Functionality
**Duration:** 25 min

1. **Load SVG:**
   - File dialog → path
   - API call to import segments
   - Canvas displays geometry
   - User can now create rooms

2. **Load Room Data:**
   - File dialog → `.rooms.json` or `.rtlsproj`
   - API call to load manifest + rooms
   - Rooms loaded into state
   - Canvas displays geometry + room boundaries + anchors

3. **Save Room Data:**
   - API call with current rooms
   - Saves to `BRIGID/profile/{project_name}.rooms.json`
   - Show confirmation

4. **Save Project (ZIP):**
   - Bundles SVG + rooms JSON into `.rtlsproj`
   - User chooses download location
   - Extract-friendly format for portability

### Phase 8: Anchor Property Editor
**Duration:** 15 min

1. **Validation:**
   - hw_id: alphanumeric (A0, A1, etc.)
   - x, y: numeric, bounded by room bounds
   - z: numeric, non-negative (height)

2. **Real-time sync:**
   - Changes saved to room state immediately
   - Canvas updates anchor visual position
   - List updates selected anchor highlight

3. **Color coding:**
   - Each anchor gets deterministic color based on hw_id
   - Color picker for visual assignment (optional)

### Phase 9: Integration & Error Handling
**Duration:** 20 min

1. **Error scenarios:**
   - Invalid SVG file → show message
   - Corrupted room JSON → recovery dialog
   - Anchor outside room → validation warning
   - Duplicate hw_id → auto-rename hint
   - File permissions → "Could not save" message

2. **State persistence:**
   - Auto-save to temp file every 30 seconds
   - Recover on crash/reload
   - User warning if unsaved changes

3. **Testing scenarios:**
   - Load SVG → create room → place 4 anchors → save
   - Load project → modify anchors → save
   - Multi-room project (3+ rooms) with cross-references
   - Edge case: very large SVG (10K+ segments)

---

## File Checklist

### New Backend Files
- [ ] `BRIGID/backend/utilities/rooms/__init__.py`
- [ ] `BRIGID/backend/utilities/rooms/room_data.py`
- [ ] `BRIGID/backend/utilities/rooms/room_io.py`
- [ ] `BRIGID/backend/utilities/rooms/geometry_utils.py`
- [ ] `BRIGID/backend/utilities/rooms/project_io.py`

### New Frontend Files
- [ ] `BRIGID/frontend/src/components/modules/AnchorManagerModule/AnchorManager.tsx`
- [ ] `BRIGID/frontend/src/components/modules/AnchorManagerModule/AnchorManagerCanvas.tsx`
- [ ] `BRIGID/frontend/src/components/modules/AnchorManagerModule/RoomManager.tsx`
- [ ] `BRIGID/frontend/src/components/modules/AnchorManagerModule/AnchorEditPanel.tsx`
- [ ] `BRIGID/frontend/src/components/modules/AnchorManagerModule/GeometryPanel.tsx` (optional)
- [ ] `BRIGID/frontend/src/components/modules/AnchorManagerModule/AnchorManager.css`

### Backend Files to Modify
- [ ] `BRIGID/backend/main.py` – Register new API routes
- [ ] `BRIGID/backend/cad_server.py` – Add room management endpoints
- [ ] `BRIGID/backend/utilities/__init__.py` – Export room modules

### Frontend Files to Modify
- [ ] `BRIGID/frontend/src/components/TopBar/TopBar.tsx` – Add File menu
- [ ] `BRIGID/frontend/src/App.tsx` – Register AnchorManager workspace route
- [ ] `BRIGID/frontend/src/types.ts` – Add AnchorManagerState, Room, Anchor types

### Reference Files (2DL CAD)
- `2DLCAD/room_data.py` – Room/Anchor dataclasses
- `2DLCAD/room_detail_view.py` – Room canvas & editor UI (study UX)
- `2DLCAD/room_profiles.py` – JSON serialization
- `2DLCAD/map_canvas.py` – Floor plan canvas rendering

---

## Success Criteria

- [ ] Load SVG file → geometry displays on canvas
- [ ] Create room → select segments → name → room created
- [ ] List shows all created rooms
- [ ] Select room → boundaries highlight on canvas
- [ ] Place anchor → Ctrl+Click on canvas → anchor created
- [ ] Anchor list shows all anchors in room
- [ ] Edit anchor → modify x/y/z/hw_id → canvas updates
- [ ] Delete anchor → button or Delete key → removed
- [ ] Save room data → JSON file created in `BRIGID/profile/`
- [ ] Load room data → JSON parsed → rooms and anchors restored
- [ ] Save project → `.rtlsproj` file created (ZIP format)
- [ ] Load project → ZIP extracted → SVG and rooms loaded
- [ ] Hot bar: File menu visible with 4 actions
- [ ] Keyboard shortcuts: Ctrl+O/S, F, Del all work
- [ ] Pan/zoom canvas: middle-click pan, scroll zoom, F fits
- [ ] Multi-room project: 3+ rooms, independent anchors
- [ ] Undo/Redo: add/delete anchors reversible
- [ ] Error handling: graceful messages for all error cases
- [ ] Right panel: visible when room selected, hidden otherwise
- [ ] Scrollbars: visible when content exceeds viewport
- [ ] Coordinate transforms: local↔world consistent
- [ ] Roundtrip: create → save → load → matches original

---

## Technical Notes

### Coordinate System
- **World-space:** SVG import coordinates, shared canvas
- **Local-space:** Room origin at (min_x, min_y) of bounding box
- **Transforms:**
  ```
  local_x = world_x - room.min_x
  local_y = world_y - room.min_y
  world_x = local_x + room.min_x
  world_y = local_y + room.min_y
  ```

### Room Boundaries vs. Interior
- **Boundary segments:** User-selected, form closed polygon
- **Interior segments:** Non-wall geometry (doors, fixtures, optional)
- Both stored separately in Room.segments and Room.interior_segments

### Anchor ID Naming
- Pattern: `{room_id}{index}` e.g., "R1A0", "R1A1", "R2A0"
- hw_id: User-assigned physical identifier (A0, A3, etc.)
- Supports up to 26 anchors per room (A-Z)

### Project Structure
```
BRIGID/profile/
├── project_name.rooms.json       # Manifest + room data
├── project_name.rtlsproj         # ZIP: SVG + JSON
└── floorplan.svg                 # Original floor plan
```

### File Formats
- **SVG:** Vector geometry (reuses CAD/Import logic)
- **rooms.json:** Manifest with array of Room objects
- **rtlsproj:** ZIP archive containing SVG + rooms.json

### Render Pipeline
1. Load SVG → parse segments
2. Display segments on canvas (light gray)
3. User creates rooms → segments grouped
4. Display room boundaries (dark blue)
5. Display anchors (orange pins with labels)
6. Highlight selected room/anchor (yellow/gold)

---

## Notes for Agent

- **Do not** copy PyQt6 UI code from 2DL CAD room_detail_view.py
- **Do** extract Room/Anchor data structures and JSON logic
- **Match** BRIGID's existing dark theme and component patterns
- **Test** multi-room scenarios with 3+ rooms and varying segment counts
- **Handle** edge cases: empty SVG, single-segment room, overlapping rooms
- **Provide** clear visual feedback for anchor placement (cursor changes, hints)
- **Ensure** right panel hides when no room selected (clean workspace)
- **Document** coordinate transforms thoroughly (source of common bugs)
- **Profile directory** must be writable; gracefully handle permission errors
- **Reuse** SVG import logic from NEXTSTEP.md (don't reimplement)
