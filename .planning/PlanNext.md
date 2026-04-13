# BRIGID Next Generation — System Instructions & Implementation Plan

## System Instructions for Agent

### Context & Vision
BRIGID is evolving from a modular toolset into a **unified, persistent workspace platform** where users can seamlessly switch between programs (CAD, Anchor Manager, Tag Profiler, Calibration Tool) without losing work. Each program maintains its own state independently, allowing non-linear workflows: edit anchor placement → check tag profile → adjust room geometry → recalibrate → save.

This document addresses critical architectural improvements, UX enhancements, and new features needed for production-grade RTLS management.

### Core Problems to Solve

#### 1. **State Persistence Across Workspace Switching**
**Issue:** Switching between CAD ↔ Anchor Manager ↔ Tag Profiler resets all unsaved work.
**Root Cause:** Each workspace component is unmounted/remounted, losing React state.
**Solution:** Global Redux/Zustand store with snapshot-based state management.

#### 2. **Anchor Manager UX Deficiencies**
**Issues:**
- No visual feedback before placing anchors
- No prevention of out-of-bounds placements
- No snapping to geometric features
- Static anchors (cannot drag to adjust)
- Missing viewport controls after load
- Grid noise obscures geometry

#### 3. **Coordinate System Confusion**
**Issue:** Two overlapping coordinate systems (room world-space vs. anchor reference-frame)
**Solution:** Explicit anchor coordinate system with selectable origin (A0 default, user-switchable)

#### 4. **Calibration Tool Missing**
**Issue:** No in-app calibration UI; users must launch external tools.
**Solution:** Integrated Calibration Tool workspace supporting both BLE and Serial Port connectivity.

#### 5. **Data Organization**
**Issue:** All profiles jumbled in single directory.
**Solution:** Hierarchical structure: `profile/Tags/` and `profile/Rooms/`

### Key Architecture Principles

1. **Persistent Global State**
   - Single Redux store manages all workspace data
   - Each workspace (CAD, Anchor Manager, etc.) subscribes to relevant slices
   - Undo/Redo stack per-workspace (independent history)
   - Auto-save every 30 seconds to IndexedDB + backend

2. **Workspace Isolation with Shared Data**
   - Workspaces are **decoupled components**, not full-page replacements
   - Room data shared between Anchor Manager and RTLS visualization
   - Tag profiles shared between Tag Profiler and Calibration Tool
   - No component unmounting on workspace switch

3. **Anchor Coordinate System Duality**
   - **Room World-Space:** SVG-imported geometry, building layout
   - **Anchor Reference-Frame:** Local coordinate system with origin at selected anchor
   - Visual feedback switches between both on demand
   - All anchor positions stored in world-space, transformed for display

4. **Viewport Management**
   - Each workspace has independent viewport (pan, zoom, fit)
   - Preserved across switches
   - Smart fit-to-content after file load

5. **UI/UX Consistency**
   - Floating panels (not docked sidebars)
   - Keyboard shortcuts unified across workspaces
   - Consistent color scheme, button placement
   - Progressive disclosure: show controls only when relevant

### Data Flow & Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    BRIGID Frontend Root                      │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Redux Store (Global Persistent State)               │  │
│  │  ├─ cad.state (geometry, lines, undo/redo)          │  │
│  │  ├─ anchorManager.state (rooms, anchors, vp)        │  │
│  │  ├─ tagProfiler.state (profiles, forms)             │  │
│  │  ├─ calibration.state (sessions, equations)         │  │
│  │  └─ ui.state (activeWorkspace, floating panels)     │  │
│  └──────────────────────────────────────────────────────┘  │
│           ▲                    ▲                             │
│          ─┼─────┬──────┬──────┬────────────┴─────────────┐ │
│                 │      │      │                           │ │
│  ┌──────────┐  │  ┌──────────────┐  ┌──────────────┐     │ │
│  │   CAD    │◄─┘  │AnchorManager◄───│  TagProfiler │     │ │
│  └──────────┘     └──────────────┘  └──────────────┘     │ │
│                        ▲                                    │ │
│                        │                                    │ │
│                   ┌────────────────┐                        │ │
│                   │ CalibrationTool◄────────────────────────┘ │
│                   └────────────────┘                          │
└─────────────────────────────────────────────────────────────┘

Backend Persistence:
┌────────────────────────────────────────────────────┐
│  BRIGID/profile/                                   │
│  ├─ Tags/          (tag_*.json)                    │
│  │  ├─ tag_001.json                                │
│  │  └─ tag_002.json                                │
│  ├─ Rooms/         (room_*.json, *.rooms.json)     │
│  │  ├─ room_A.json                                 │
│  │  └─ project_x.rooms.json (manifest)            │
│  └─ CADExports/    (*.svg, *.pdf)                  │
└────────────────────────────────────────────────────┘
```

---

## System Instructions: Detailed Breakdown

### 1. State Persistence Architecture

**Goal:** Ensure that switching between workspaces preserves all unsaved changes.

**Implementation Strategy:**

- **Redux Store Structure:**
  ```typescript
  interface BrigidGlobalState {
    cad: {
      lines: Line[]
      viewport: Viewport
      selectedLines: Set<string>
      undoStack: Action[]
      redoStack: Action[]
      history: { timestamp, action, snapshot }[]
      isSaved: boolean
      lastSaveTime: number
    }
    
    anchorManager: {
      rooms: Room[]
      currentRoomId: string | null
      selectedAnchorId: string | null
      viewportState: { panX, panY, zoom }
      referenceAnchorId: string  // A0 by default
      anchorCoordinateSystem: AnchorCoordSys  // computed
      undoStack: Action[]
      redoStack: Action[]
      isSaved: boolean
    }
    
    tagProfiler: {
      profiles: { [tagId]: TagProfile }
      currentTagId: string | null
      activeTab: "profile" | "calibration_lab"
      formData: { [field]: value }
      unsavedFields: Set<string>
    }
    
    calibration: {
      sessions: { [sessionId]: CalibrationSession }
      currentSessionId: string | null
      connectivityMode: "ble" | "serial"
      serialPort: string
      activeTags: string[]  // loaded from Tags profile dir
      tagDistances: { [tagId]: { [anchorId]: float } }
      equations: { [tagId]: { [anchorId]: string } }
    }
    
    ui: {
      activeWorkspace: "home" | "cad" | "anchor_manager" | "tag_profiler" | "calibration"
      floatingPanels: {
        anchorEditPanel: { visible, x, y, width, height }
        tagProfilePanel: { visible, x, y, width, height }
        calibrationPanel: { visible, x, y, width, height }
      }
      dialogOpen: null | "create_room" | "save_project" | "confirm_exit"
    }
    
    files: {
      loadedSvgPath: string | null
      loadedProjectPath: string | null
      profilesDir: string  // "BRIGID/profile"
    }
  }
  ```

- **Persistence Strategy:**
  - IndexedDB for local fast caching (entire state serialized)
  - Auto-sync to backend every 30 seconds
  - On workspace switch: read from Redux (always in-memory)
  - On page reload: restore from IndexedDB → Redux
  - On backend update: merge conflict resolution (last-write-wins for now)

- **Undo/Redo per Workspace:**
  - Each workspace maintains independent undo stack
  - Max 50 entries per workspace
  - Snapshots captured on anchor placement, room creation, profile edit
  - Ctrl+Z / Ctrl+Y work within current workspace only

### 2. Anchor Manager: Viewport & Controls

**File Load Workflow:**
1. User loads SVG via File menu
2. API call: `POST /api/rooms/load-svg` with file content
3. Backend parses segments, returns bounding box
4. Frontend receives geometry data
5. Viewport auto-fit: zoom to show all segments with 5% margin
6. Canvas rescale & repaint
7. Show Undo/Redo/Zoom/Reset buttons (were previously hidden)

**Viewport Controls (only visible post-SVG load):**
- **Reset View (F key):** Center and fit all geometry
- **Zoom In (Ctrl++):** 1.2× current zoom around cursor
- **Zoom Out (Ctrl+-):** 0.8× current zoom around cursor
- **Undo (Ctrl+Z):** Revert last anchor or room action
- **Redo (Ctrl+Y):** Redo last undone action
- **FIT button:** Same as F key
- **+/- buttons:** Visual zoom controls

**Canvas Interaction:**
- Pan: Middle-mouse drag or Space+Left-drag
- Zoom: Mouse wheel (scroll up=in, down=out)
- Keyboard: Arrow keys nudge selected anchor by 0.1 ft

**Grid Removal:**
- Delete all grid rendering code from AnchorManagerCanvas.tsx
- Remove `showGrid` property from state
- Cleaner canvas displays geometry only (walls, anchors, rooms)

### 3. Floating Right Panel (Anchor Manager)

**Layout Changes:**
```
┌─────────────────────────────────────────────────────────┐
│  TOP BAR: File | Tools | Undo | Redo | Zoom | Reset    │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│                                                          │
│                   CANVAS (full width)                   │
│                                                          │
│                                                          │
│                                   ┌──────────────────┐  │
│                                   │ Right Panel      │  │
│                                   │ (floating,       │  │
│                                   │ draggable,       │  │
│                                   │ 280px wide)      │  │
│                                   │                  │  │
│                                   │ ┌──────────────┐ │  │
│                                   │ │Room List     │ │  │
│                                   │ ├──────────────┤ │  │
│                                   │ │Anchor Editor │ │  │
│                                   │ │- hw_id       │ │  │
│                                   │ │- x, y, z     │ │  │
│                                   │ │- Reference ▼ │ │  │
│                                   │ │- Coord Sys   │ │  │
│                                   │ │  (visual)    │ │  │
│                                   │ │- Undo/Redo   │ │  │
│                                   │ │- Save        │ │  │
│                                   │ └──────────────┘ │  │
│                                   └──────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**Right Panel Features:**
- **Room List:** Scrollable room buttons (click to select)
- **Anchor List (when room selected):** Table of anchors with properties
- **Anchor Editor:** Editable fields for x, y, z, hw_id
- **Reference Anchor Selector:** Dropdown to change A0/A1/A2/A3 reference
- **Anchor Coordinate System Display:**
  - Shows bounds of all anchors (e.g., 4ft × 4ft)
  - Visual grid showing anchor positions relative to first anchor
  - Yellow highlight area between anchors
- **Undo/Redo buttons:** Per-workspace history
- **Save button:** Write rooms.json

**Floating Panel Implementation:**
- React Draggable library for drag-to-move
- Store position in `anchorManager.ui.floatingPanels.x, y`
- Persist position across sessions
- Z-index managed to stay above canvas
- Optional: Collapse/expand toggle

### 4. Anchor Placement Enhancements

#### **A. Hover Circle Preview**
- Track mouse position in canvas
- Render semi-transparent circle (radius = 6 inches, configurable)
- Show on canvas only when in "place anchor" mode
- Circle color: light blue, alpha 0.3
- Updates live as cursor moves
- Visual hint: "Click to place anchor here (Ctrl+Click)"

**Implementation:**
```typescript
function renderHoverPreview(ctx, mouseWorldX, mouseWorldY, viewport) {
  const previewRadius = 0.5;  // ft
  const screenRadius = previewRadius * viewport.scale;
  ctx.fillStyle = "rgba(100, 180, 255, 0.2)";
  ctx.beginPath();
  ctx.arc(viewport.worldToScreen(mouseWorldX, mouseWorldY), screenRadius, 0, 2*Math.PI);
  ctx.fill();
  ctx.strokeStyle = "rgba(100, 180, 255, 0.5)";
  ctx.lineWidth = 2;
  ctx.stroke();
}
```

#### **B. Out-of-Bounds Prevention**
- **Validation on placement:**
  - Check if anchor world position falls inside any room
  - Use `room.contains_world_point(wx, wy)` from backend
  - If invalid: show error toast "Anchor must be placed inside a room"
  - Do not create anchor on invalid placement
  
- **Alternative UX:** Make "unplaced" anchors visually distinct until placed correctly
  - Anchor outline style while dragging (not filled)
  - Red border if outside bounds
  - Green when valid position

#### **C. Snap to Walls/Corners**
- **Snap Tolerance:** 0.3 ft (configurable)
- **Snap Points:**
  - Segment endpoints (corners)
  - Midpoints of segments (wall center)
  - Perpendicular projection to segment (closest point on wall)

**Algorithm:**
```python
def find_snap_target(anchor_wx, anchor_wy, room, snap_tol=0.3):
    best_snap = None
    best_dist = snap_tol
    
    for seg_idx, (x1, y1, x2, y2) in enumerate(room.segments):
        # Check endpoints
        for pt in [(x1, y1), (x2, y2)]:
            d = dist(anchor_wx, anchor_wy, pt[0], pt[1])
            if d < best_dist:
                best_snap = pt
                best_dist = d
        
        # Check perpendicular to segment
        closest_x, closest_y = project_point_on_segment(
            anchor_wx, anchor_wy, x1, y1, x2, y2
        )
        d = dist(anchor_wx, anchor_wy, closest_x, closest_y)
        if d < best_dist:
            best_snap = (closest_x, closest_y)
            best_dist = d
    
    return best_snap

# On anchor placement, if snap < tol, snap to target
if snap_point:
    anchor.x, anchor.y = snap_point
```

- **Visual Feedback:**
  - When snappable point nearby: highlight it (blue circle at snap point)
  - Show snap distance: "Snap to wall (0.1 ft)"
  - Draw line from anchor to snap target while dragging

#### **D. Anchor Drag-to-Move**
- **Activation:** Left-click + hold on anchor circle
- **Behavior:**
  - Anchor follows cursor
  - Maintains snap-to-walls while dragging
  - Hover preview shows new position in real-time
  - Invalid positions: red outline, no snap
  - Release to finalize
  
- **Keyboard modifier:**
  - Shift+drag: free move (ignores snap)
  - Ctrl+drag: fine adjustment (0.01 ft steps)

- **Undo Entry:** Single undo for entire drag sequence (not per-movement)

**Implementation:**
```typescript
const [draggingAnchorId, setDraggingAnchorId] = useState(null);
const [dragStartPos, setDragStartPos] = useState(null);

function handleAnchorMouseDown(e, anchorId) {
  setDraggingAnchorId(anchorId);
  setDragStartPos({ x: e.clientX, y: e.clientY });
  recordUndoSnapshot();  // before move
}

function handleCanvasMouseMove(e) {
  if (!draggingAnchorId) return;
  
  const worldPos = screenToWorldCoords(e.clientX, e.clientY, viewport);
  const snapTarget = findSnapTarget(worldPos.x, worldPos.y, currentRoom);
  const finalPos = snapTarget || worldPos;
  
  updateAnchorInState(draggingAnchorId, finalPos);
  redraw();  // live preview
}

function handleCanvasMouseUp(e) {
  if (draggingAnchorId) {
    recordRedoSnapshot();  // after move
  }
  setDraggingAnchorId(null);
}
```

### 5. Anchor Coordinate System (Advanced)

**Problem:** Two overlapping coordinate systems confuse users.
**Solution:** Dual-mode display with explicit toggle.

#### **Coordinate System Duality**

1. **Room World-Space** (default, SVG import):
   - Origin: bottom-left of room bounding box
   - Axes: X (right), Y (up) in feet
   - Displays SVG geometry exactly as imported
   - User can see room corners and walls

2. **Anchor Reference-Frame** (new):
   - Origin: at reference anchor (A0 by default)
   - Axes: same as world-space but shifted
   - Only visible when "Show Anchor Coordinates" toggled ON
   - Computed as: `anchor_coord = anchor_world_pos - anchor_A0_world_pos`
   - Shows as overlay grid/axes

#### **Reference Anchor Selection**

- Right panel: Dropdown "Reference Anchor"
- Options: "A0 (default)", "A1", "A2", "A3"
- When changed:
  1. Recompute all anchor coordinates relative to new origin
  2. Update visual display
  3. Rebuild coordinate system grid
  4. Record in state: `anchorManager.referenceAnchorId`
  5. Save to room JSON: `"reference_anchor_id": "A1"`

**Visual Indication:**
```
Anchor Display (when reference = A1):
┌────────────────────────────────────┐
│ Reference Anchor: A1 @ (2.5, 1.0)  │
│ Coordinate System: 4.0 ft × 3.5 ft │
│                                    │
│     A0 @ (-2.5,-1.0)  [room: 0,1] │
│     A1 @ (0, 0)       [ORIGIN]    │
│     A2 @ (1.5, 3.5)               │
│     A3 @ (-1.0, 3.5)              │
│                                    │
│ ┌─ Anchor Coord System (yellow) ─┐ │
│ │     A3        A2               │ │
│ │     ├──────────┤               │ │
│ │     │          │  4 ft         │ │
│ │ A1  │ ORIGIN   │               │ │
│ │     │          │  3.5 ft       │ │
│ │     ├──────────┤               │ │
│ │     A0   3.5ft                 │ │
│ └────────────────────────────────┘ │
└────────────────────────────────────┘
```

#### **Anchor Coordinate System Display**

- **Yellow Highlight Area:** Bounding box of all anchors in anchor-space
- **Grid Overlay (optional):** 1 ft grid lines in anchor-space
- **Axes Labels:** X and Y axes with scale ticks
- **Anchor Positions:** Each anchor labeled with relay ID (A0, A1, etc.)
- **Coordinate Labels:** Each anchor shows both:
  - Room coordinates: (x_room, y_room) in gray
  - Anchor coordinates: (x_anchor, y_anchor) in yellow

#### **History Navigation (Undo/Redo for Anchor Placement)**

- Back arrow (◀): Revert to previous anchor configuration
- Forward arrow (▶): Redo to next configuration
- Timeline shows all snapshots (max 20)
- On-hover: Preview that configuration
- Click: Jump to that point in history

**Storage:**
```typescript
interface AnchorPlacementSnapshot {
  timestamp: number
  description: string  // "Placed A0", "Moved A2", etc.
  anchors: Anchor[]
  referenceAnchorId: string
  viewport: ViewportState
}

anchorManager.placementHistory: AnchorPlacementSnapshot[] = []
anchorManager.historyIndex: number = 0
```

### 6. File Organization Structure

**New directory layout:**
```
BRIGID/profile/
├── Tags/
│   ├── tag_001.json          # Tag profile: identity, device, calibration
│   ├── tag_002.json
│   └── tag_003.json
├── Rooms/
│   ├── room_office.json       # Single room (legacy, single-room save)
│   ├── project_floor_1.rooms.json   # Manifest: multi-room + SVG ref
│   └── project_floor_1.rtlsproj     # ZIP: SVG + rooms.json
└── CADExports/
    ├── floorplan_v1.svg
    ├── floorplan_v1.pdf
    └── floorplan_v2.svg
```

**Backend changes:**
- `PROFILE_DIR = "BRIGID/profile"`
- Tag save: `f"{PROFILE_DIR}/Tags/{tag_id}.json"`
- Room save: `f"{PROFILE_DIR}/Rooms/{room_name}.json"`
- Manifest save: `f"{PROFILE_DIR}/Rooms/{project_name}.rooms.json"`

**API updates:**
```python
@app.post("/api/profile/tags/save")
async def save_tag(request):
    # Saves to BRIGID/profile/Tags/{tag_id}.json
    ...

@app.post("/api/rooms/save")
async def save_rooms(request):
    # Saves to BRIGID/profile/Rooms/{project_name}.rooms.json
    ...
```

### 7. Calibration Tool (New Workspace)

#### **Vision**
A unified UI for performing RTLS anchor calibration using real-time distance measurements. Supports:
- **Connectivity Modes:** BLE (direct to tags) or Serial Port (via dongle)
- **Multi-Tag Calibration:** Simultaneously calibrate all tags in profile database
- **Auto Equation Generation:** Fit models (Linear, Polynomial, etc.)
- **Save to Profile:** Equations written back to tag JSON files

#### **Data Sources**

**Tag Profile Data (read-only):**
- Load all tags from `BRIGID/profile/Tags/`
- Display tag list (tag_id, name, device type)
- Show existing equations (if any)

**Connectivity:**
- **BLE:** Direct connection to tag MAC addresses
  - Uses PyBluez / asyncio-based BLE scanning
  - Query: "give me distance to all anchors"
  - Response: `{"A0": 5.2, "A1": 8.1, "A2": 3.9, "A3": 6.5}`
  
- **Serial Port:** Dongle communication (ESP32-C6)
  - Listens on COM port
  - Auto-detect port with ESP32 VID/PID
  - Parses line protocol: `TAG:T1,A0:5.2,A1:8.1,...`

#### **Calibration Workflow**

1. **Setup Phase:**
   - Select connectivity mode (BLE / Serial)
   - If Serial: select COM port (auto-populated list)
   - If BLE: confirm Bluetooth is enabled
   - Load all tags from profile database
   - Display tag list with connection status

2. **Measurement Phase:**
   - Select a tag to calibrate
   - Display current anchor distances (live, refreshing)
   - Operator inputs true distance (measured with tape measure) or ground truth
   - Can iterate: move tag to known distance → record
   - Accumulate point pairs: (measured_distance, true_distance)
   - Up to 20 points per anchor

3. **Fitting Phase:**
   - Select fit mode: Linear, Polynomial, Logarithmic, Power Series, Exponential, Moving Average
   - For Polynomial: select degree (2-4)
   - Click "Generate Equations"
   - Backend calls `build_eval_func()` for each anchor
   - Returns equations: e.g., "(0.95*Raw)+0.2"

4. **Review & Save Phase:**
   - Display generated equations for each anchor
   - Option to accept or re-fit
   - Click "Save to Profile" → writes to `Tags/{tag_id}.json`
   - Tag updated with new equations + timestamp

#### **UI Layout**

```
┌──────────────────────────────────────────────────────────┐
│ TOP BAR: Calibration Tool | Home | Save                 │
├──────────────────────────────────────────────────────────┤
│ Connectivity: [ BLE    ] [ Serial ▼ ] [ COM port ▼ ]   │
│               [Active  ] [            ] [Auto-detect]   │
├──────────────────────────────────────────────────────────┤
│                                                          │
│ ┌─ Tag Selection ──────────────┐  ┌──DistanceLive────┐│
│ │ Tags: [Tag 001] Tag 002 Tag  │  │ A0: 5.2 ft      ││
│ │ (BLE) (Serial)               │  │ A1: 8.1 ft      ││
│ │                              │  │ A2: 3.9 ft      ││
│ │ Name: John Doe               │  │ A3: 6.5 ft      ││
│ │ Type: Wrist Band             │  │ [Refresh: Auto] ││
│ │ Status: Connected            │  │                 ││
│ └──────────────────────────────┘  └─────────────────┘│
│                                                          │
│ ┌─ Measurement Points ───────────────────────────────┐ │
│ │ Anchor A0                                          │ │
│ │ ┌──────────────────────────┐  [+Add] [Clear]     │ │
│ │ │ Measured │ True | Error  │                      │ │
│ │ │ 5.1      │ 5.0  │ +0.1   │                      │ │
│ │ │ 5.3      │ 5.0  │ +0.3   │                      │ │
│ │ │ 5.2      │ 5.0  │ +0.2   │                      │ │
│ │ └──────────────────────────┘                      │ │
│ │ [Fit Mode: Linear] [Poly Deg: 2] [Generate EQ]   │ │
│ └────────────────────────────────────────────────────┘ │
│                                                          │
│ ┌─ Generated Equations ──────────────────────────────┐ │
│ │ A0: (0.95*Raw)+0.25     [Copy] [Accept]           │ │
│ │ A1: (0.97*Raw)-0.10     [Copy] [Accept]           │ │
│ │ A2: (0.92*Raw)+0.35     [Copy] [Accept]           │ │
│ │ A3: (0.96*Raw)+0.05     [Copy] [Accept]           │ │
│ │                                                     │ │
│ │ Fit Quality: R² = 0.998 (Excellent)                │ │
│ │ [Save to Profile]  [Discard]  [Fit Again]         │ │
│ └────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

#### **Backend Implementation**

**New Calibration Endpoints:**
```python
@app.post("/api/calibration/detect-ports")
async def detect_ports():
    """Auto-detect serial ports with ESP32 signatures."""
    return {"ports": ["COM3", "COM5", ...]}

@app.post("/api/calibration/ble/scan")
async def scan_ble_devices():
    """Scan for nearby BLE devices, return MACs + names."""
    return {"devices": [{"mac": "...", "name": "..."}, ...]}

@app.post("/api/calibration/ble/connect")
async def ble_connect(request: BLEConnectRequest):
    """Connect to BLE tag and stream distances."""
    # Start background thread listening to characteristic
    # WebSocket stream: {"A0": 5.2, "A1": 8.1, ...}
    ...

@app.post("/api/calibration/serial/connect")
async def serial_connect(request: SerialConnectRequest):
    """Connect to serial port (dongle) and stream distances."""
    # Start background thread reading serial
    # WebSocket stream: lines parsed to distances
    ...

@app.post("/api/calibration/fit-equations")
async def fit_equations(request: FitEquationsRequest):
    # request.tag_id, request.measurements: {A0: [(measure, true), ...], ...}
    # request.fit_mode, request.poly_deg
    equations = {}
    for anchor_id, points in request.measurements.items():
        X = [p[0] for p in points]
        Y = [p[1] for p in points]
        func, expr = build_eval_func(request.fit_mode, X, Y, request.poly_deg)
        equations[anchor_id] = expr
    return {"equations": equations, "quality": r_squared}

@app.post("/api/calibration/save-equations")
async def save_equations(request: SaveEquationsRequest):
    # request.tag_id, request.equations
    profile, _ = load_profile(request.tag_id, PROFILE_DIR)
    profile["calibration"]["equations"] = request.equations
    profile["calibration"]["last_calibration_date"] = datetime.now().isoformat()
    success, _ = save_profile(profile, PROFILE_DIR)
    return {"success": success}
```

**Connectivity Backend (Adapting Existing Code):**
- Port `home.py` BLE logic → `BRIGID/backend/utilities/calibration/ble_connector.py`
- Port `home_rtls.py` Serial logic → `BRIGID/backend/utilities/calibration/serial_connector.py`
- Both export async generators: `listen_for_distances(tag_id, callback)`

---

## Implementation Plan (9 Major Phases)

### Phase 1: Global State Management Architecture
**Duration:** 35 min

1. **Set up Redux store structure:**
   - Create `BRIGID/frontend/src/store/` directory
   - `store/root.ts` – root reducer combining all slices
   - `store/slices/cad.ts` – CAD state & reducers
   - `store/slices/anchorManager.ts` – Anchor Manager state
   - `store/slices/tagProfiler.ts` – Tag Profiler state
   - `store/slices/calibration.ts` – Calibration state
   - `store/slices/ui.ts` – Global UI state (active workspace, floating panels)
   - `store/hooks.ts` – useAppDispatch, useAppSelector hooks

2. **Implement Undo/Redo per-workspace:**
   - Create `store/utils/undoRedo.ts` with:
     - `createUndoableSlice()` – HOF to add undo/redo to any slice
     - `recordSnapshot(state)` – snapshot capture
     - `undo() / redo()` actions
     - Max 50 entries per workspace
   
3. **Implement persistence layer:**
   - Create `store/persistence.ts`:
     - `saveStateToIndexedDB(state)` – serialize & store
     - `loadStateFromIndexedDB()` – async restore
     - Auto-save timer (30s interval)
   - Create `store/api.ts`:
     - `syncStateToBackend(state)` – POST to backend
     - `conflictResolution()` – merge if both modified

4. **Connect workspaces to Redux:**
   - Wrap App with `<Provider store={store}>`
   - Each workspace component subscribes to store slices
   - Replace local useState with useAppSelector

### Phase 2: Anchor Manager Canvas Refactoring
**Duration:** 40 min

1. **Remove grid rendering:**
   - Delete all `renderGrid()` calls
   - Remove `showGrid` state variable
   - Remove grid toggle from UI

2. **Add viewport controls (post-load):**
   - Create `ViewportControls.tsx` component
   - Buttons: FIT (F), Zoom In (+), Zoom Out (-), Undo, Redo
   - Start hidden by default: `visibility: hidden`
   - Show after SVG loaded: `visibility: visible`
   - Wire to Redux actions

3. **Implement auto-fit on SVG load:**
   - In `loadSvg()` API handler:
     - Compute bounding box of all segments
     - Calculate viewport scale & offset for 5% margin
     - Dispatch Redux action: `setViewport({ scale, offx, offy })`
     - Trigger repaint

4. **Refactor canvas interaction:**
   - Move all mouse handlers to use Redux state
   - Pan/zoom already Redux-powered
   - F key listener: dispatch `fitInView()` action

### Phase 3: Anchor Manager — Floating Right Panel
**Duration:** 35 min

1. **Create floating panel component:**
   - `BRIGID/frontend/src/components/modules/AnchorManagerModule/FloatingAnchorPanel.tsx`
   - Use React Draggable library
   - Store position in Redux: `ui.floatingPanels.anchorEditPanel`
   - CSS: high z-index, semi-transparent background, rounded corners

2. **Move content from left panel to right:**
   - Room list (top section)
   - Anchor list (middle)
   - Anchor editor (bottom, scrollable)

3. **Add Anchor Coordinate System Display:**
   - New component: `AnchorCoordinateSystemDisplay.tsx`
   - Shows:
     - Selected reference anchor (dropdown)
     - Anchor coordinate bounds (e.g., "4.0 ft × 3.5 ft")
     - Yellow highlight area (visual grid)
     - Anchor position labels (both room & anchor coords)
   - Re-renders when anchors change or reference anchor changes

4. **Add History Navigation:**
   - Left/right arrow buttons
   - Timeline showing last 20 snapshots
   - On-hover: preview
   - On-click: jump to that state

5. **Styling:**
   - Match BRIGID dark theme
   - Nice shadows for floating panel
   - Scrollable content area
   - Highlight selected room/anchor

### Phase 4: Anchor Placement Enhancements (Part 1 — Preview & Bounds)
**Duration:** 30 min

1. **Implement hover circle preview:**
   - Add to canvas render loop:
     ```typescript
     if (inPlaceMode && mouseWorldPos) {
       renderHoverPreview(ctx, mouseWorldPos, viewport);
     }
     ```
   - Draw semi-transparent circle
   - Update on mousemove

2. **Implement out-of-bounds prevention:**
   - Before finalizing anchor placement:
     ```typescript
     if (!room.contains_world_point(anchor.x, anchor.y)) {
       showError("Anchor must be placed inside a room");
       return;  // don't create
     }
     ```
   - Call backend: `POST /api/rooms/validate-point`
   - Return bool + error message

3. **Visual validation feedback:**
   - Red outline while invalid
   - Green/blue while valid
   - Flip allowed on valid position only

### Phase 5: Anchor Placement Enhancements (Part 2 — Snap & Drag)
**Duration:** 40 min

1. **Implement snap-to-walls:**
   - Create `snapEngine.ts`:
     - `findSnapTarget(point, room, tolerance)` – returns snapped point or null
     - Check endpoints, midpoints, perpendicular projections
   - Call on anchor placement and during drag
   - Visual feedback: blue circle at snap point

2. **Implement anchor drag-to-move:**
   - Add state: `draggingAnchorId`, `dragStartPos`
   - Mouse down → record undo snapshot
   - Mouse move → update anchor position in Redux
   - Mouse up → record redo snapshot
   - Canvas: render dragging anchor with different style

3. **Keyboard modifiers:**
   - Shift+drag: bypass snap
   - Ctrl+drag: fine adjustment (0.01 ft steps)
   - Arrow keys: nudge by 0.1 ft

4. **Real-time feedback:**
   - Show snap distance indicator
   - Highlight snap target
   - Update right panel in real-time

### Phase 6: Anchor Coordinate System Implementation
**Duration:** 45 min

1. **Add reference anchor concept:**
   - Redux state: `anchorManager.referenceAnchorId` (default "A0")
   - Room data: `room.reference_anchor_id`
   - API update: save/load includes reference_anchor_id

2. **Implement coordinate transforms:**
   - `getRoomCoordinates(anchor, room)` – world-space coords
   - `getAnchorCoordinates(anchor, reference, room)` – relative to reference
   - Both stored in Redux & computed on-demand

3. **Build coordinate system visualization:**
   - Bounding box of all anchors
   - Grid overlay (1 ft increments)
   - Axes labels
   - Anchor position display (both coord systems)
   - Yellow highlight area between anchors

4. **Reference anchor selector:**
   - Dropdown in right panel
   - OnChange: dispatch Redux action
   - Triggers recomputation & redraw
   - Persists to room JSON

5. **History snapshots:**
   - Each snapshot records:
     - Anchor positions
     - Reference anchor ID
     - Viewport state
   - Display in timeline

### Phase 7: Tag Profiler Directory Reorganization & Profile Loading
**Duration:** 20 min

1. **Update file paths:**
   - Tag loads from: `BRIGID/profile/Tags/{tag_id}.json`
   - Room loads from: `BRIGID/profile/Rooms/{room_name}.json`
   - Manifest loads from: `BRIGID/profile/Rooms/{project_name}.rooms.json`

2. **Update backend APIs:**
   - Modify save/load endpoints to use new paths
   - Auto-create directories if missing
   - Handle legacy profiles in old location (optional migration)

3. **Update frontend:**
   - Tag Profiler loads from new path
   - Calibration Tool loads from new path
   - Both API calls include correct path param

### Phase 8: Calibration Tool — UI & Backend Setup
**Duration:** 60 min

1. **Create Calibration Tool workspace:**
   - `BRIGID/frontend/src/components/modules/CalibrationToolModule/`
   - `CalibrationTool.tsx` – root component
   - `TagSelector.tsx` – tag list + connection status
   - `ConnectivityModeToggle.tsx` – BLE / Serial selector
   - `SerialPortSelector.tsx` – COM port dropdown
   - `DistanceLiveDisplay.tsx` – real-time distances
   - `MeasurementPointsTable.tsx` – input table
   - `EquationFitter.tsx` – fit mode selector + generator
   - `EquationDisplay.tsx` – show results + save button

2. **Wire Redux for Calibration state:**
   - `store/slices/calibration.ts`:
     - `sessions: { [sessionId]: CalibrationSession }`
     - `activeTags: string[]`
     - `tagDistances: { [tagId]: { [anchorId]: float } }`
     - `equations: { [tagId]: { [anchorId]: string } }`

3. **Create backend calibration utilities:**
   - `BRIGID/backend/utilities/calibration/__init__.py`
   - `BRIGID/backend/utilities/calibration/ble_connector.py`
   - `BRIGID/backend/utilities/calibration/serial_connector.py`
   - Both export: `async def listen_for_distances(tag_id, callback)`

4. **Implement connectivity toggle:**
   - Button: "BLE" | "Serial"
   - OnClick: dispatch Redux action: `setConnectivityMode("ble" | "serial")`
   - UI shows relevant controls (BLE: device list; Serial: COM port)

### Phase 9: Calibration Tool — Connectivity & Equation Generation
**Duration:** 50 min

1. **Implement BLE connectivity:**
   - Backend: `/api/calibration/ble/scan` – list nearby devices
   - Frontend: display devices with MAC + name
   - OnConnect: backend spawns `listen_for_distances()` coroutine
   - Stream distances via WebSocket to frontend
   - Frontend dispatches Redux action to update `tagDistances`
   - Real-time display in UI

2. **Implement Serial Port connectivity:**
   - Backend: `/api/calibration/serial/detect-ports` – auto-detect COM ports
   - Frontend: dropdown selector
   - OnConnect: backend spawns serial reader thread
   - Parse lines: `TAG:T1,A0:5.2,A1:8.1,...`
   - Stream to WebSocket same as BLE
   - Same frontend handling

3. **Implement measurement point input:**
   - Table: [Measured] [True Distance]
   - "Add Row" button: add blank row
   - Blur handler: parse input, compute error
   - "Clear" button: reset all rows
   - Validation: warn if too few points (< 3)

4. **Implement equation fitting:**
   - OnClick "Generate Equations":
     - Collect all point pairs for all anchors
     - POST `/api/calibration/fit-equations` with tag_id, measurements, fit_mode
     - Backend: calls `build_eval_func()` for each anchor
     - Returns: equations + R² quality metric
   - Frontend: dispatch Redux to update `equations`
   - Display results with quality indicator

5. **Implement save to profile:**
   - OnClick "Save to Profile":
     - POST `/api/calibration/save-equations` with tag_id, equations
     - Backend: loads tag JSON, updates equations, writes back to file
     - Frontend: show success toast
     - Update local Redux: mark tag as calibrated + timestamp
     - Can close calibration, switch workspaces, later reload tag to see equations

### Phase 10: File Export Removal & State Persistence Integration
**Duration:** 20 min

1. **Remove Export from Anchor Manager:**
   - Delete "Export" button from right panel
   - Remove export menu item from File menu
   - Remove export API endpoint (or leave as no-op)

2. **Finalize state persistence:**
   - Auto-save to IndexedDB every 30s
   - Sync to backend every 5 minutes
   - On workspace switch: persist current workspace state before unmounting
   - On workspace switch back: restore from Redux (already in memory)
   - On page reload: hydrate Redux from IndexedDB

3. **Add conflict resolution UI (optional):**
   - If backend has newer version: prompt user
   - "Keep local" vs. "Load server" button
   - For MVP: always keep local (no multi-user)

### Phase 11: Testing & Integration
**Duration:** 40 min

1. **Test state persistence:**
   - Edit anchor → switch to Profile Manager → switch back
   - Verify anchor position unchanged
   - Test Ctrl+Z / Ctrl+Y after switch
   - Test page reload: all state restored

2. **Test Anchor Manager features:**
   - Load SVG → verify viewport fit
   - Place anchor → verify out-of-bounds check
   - Hover → verify circle preview
   - Drag anchor → verify snap + live update
   - Change reference anchor → verify coordinate system update
   - Navigate history → verify snapshots work

3. **Test Calibration Tool:**
   - BLE mode: connect tag → receive distances
   - Serial mode: connect dongle → receive distances
   - Enter points → generate equations
   - Save equations → verify in tag JSON
   - Load tag in Profile Manager → verify equations present

4. **Test file organization:**
   - Tags save to `profile/Tags/`
   - Rooms save to `profile/Rooms/`
   - Load from correct paths

5. **Integration testing:**
   - Full workflow: Create room → Place anchors → Save → Load tag → Calibrate → Save equations → View in Profile Manager

---

## File Checklist (Comprehensive)

### Frontend Files (New)
- [ ] `BRIGID/frontend/src/store/root.ts`
- [ ] `BRIGID/frontend/src/store/hooks.ts`
- [ ] `BRIGID/frontend/src/store/slices/cad.ts`
- [ ] `BRIGID/frontend/src/store/slices/anchorManager.ts`
- [ ] `BRIGID/frontend/src/store/slices/tagProfiler.ts`
- [ ] `BRIGID/frontend/src/store/slices/calibration.ts`
- [ ] `BRIGID/frontend/src/store/slices/ui.ts`
- [ ] `BRIGID/frontend/src/store/utils/undoRedo.ts`
- [ ] `BRIGID/frontend/src/store/persistence.ts`
- [ ] `BRIGID/frontend/src/store/api.ts`
- [ ] `BRIGID/frontend/src/components/modules/AnchorManagerModule/ViewportControls.tsx`
- [ ] `BRIGID/frontend/src/components/modules/AnchorManagerModule/FloatingAnchorPanel.tsx`
- [ ] `BRIGID/frontend/src/components/modules/AnchorManagerModule/AnchorCoordinateSystemDisplay.tsx`
- [ ] `BRIGID/frontend/src/components/modules/AnchorManagerModule/HistoryTimeline.tsx`
- [ ] `BRIGID/frontend/src/components/modules/AnchorManagerModule/snapEngine.ts`
- [ ] `BRIGID/frontend/src/components/modules/CalibrationToolModule/CalibrationTool.tsx`
- [ ] `BRIGID/frontend/src/components/modules/CalibrationToolModule/TagSelector.tsx`
- [ ] `BRIGID/frontend/src/components/modules/CalibrationToolModule/ConnectivityModeToggle.tsx`
- [ ] `BRIGID/frontend/src/components/modules/CalibrationToolModule/SerialPortSelector.tsx`
- [ ] `BRIGID/frontend/src/components/modules/CalibrationToolModule/DistanceLiveDisplay.tsx`
- [ ] `BRIGID/frontend/src/components/modules/CalibrationToolModule/MeasurementPointsTable.tsx`
- [ ] `BRIGID/frontend/src/components/modules/CalibrationToolModule/EquationFitter.tsx`
- [ ] `BRIGID/frontend/src/components/modules/CalibrationToolModule/EquationDisplay.tsx`
- [ ] `BRIGID/frontend/src/components/modules/CalibrationToolModule/CalibrationTool.css`

### Frontend Files (Modified)
- [ ] `BRIGID/frontend/src/App.tsx` – Register CalibrationTool route, wrap with Redux Provider
- [ ] `BRIGID/frontend/src/components/TopBar/TopBar.tsx` – Update File menu (remove export)
- [ ] `BRIGID/frontend/src/components/modules/AnchorManagerModule/AnchorManager.tsx` – Use floating panel, Redux
- [ ] `BRIGID/frontend/src/components/modules/AnchorManagerModule/AnchorManagerCanvas.tsx` – Remove grid, add snap/drag/preview
- [ ] `BRIGID/frontend/src/components/modules/AnchorManagerModule/AnchorManager.css` – Hide left panel, reposition
- [ ] `BRIGID/frontend/src/components/modules/TagProfilerModule/TagProfiler.tsx` – Load from `profile/Tags/`

### Backend Files (New)
- [ ] `BRIGID/backend/utilities/calibration/__init__.py`
- [ ] `BRIGID/backend/utilities/calibration/ble_connector.py`
- [ ] `BRIGID/backend/utilities/calibration/serial_connector.py`
- [ ] `BRIGID/backend/utilities/calibration/calibration_math.py` (or reuse existing)

### Backend Files (Modified)
- [ ] `BRIGID/backend/main.py` – Register calibration routes
- [ ] `BRIGID/backend/cad_server.py` – Update profile paths, add calibration endpoints
- [ ] `BRIGID/backend/utilities/profilers/tag_profile_io.py` – Change save path to `profile/Tags/`
- [ ] `BRIGID/backend/utilities/rooms/room_io.py` – Change save path to `profile/Rooms/`

### Configuration
- [ ] `.env` or `config.py` – Define `PROFILE_DIR`, `TAGS_DIR`, `ROOMS_DIR`, `CAD_EXPORTS_DIR`

---

## Success Criteria (Comprehensive)

### State Persistence (Phase 1)
- [ ] Switch CAD → Anchor Manager → CAD: all lines preserved
- [ ] Switch Anchor Manager → Profile Manager → Anchor Manager: all anchors + room data preserved
- [ ] Page reload: all state restored from IndexedDB
- [ ] Undo/Redo per-workspace independent (Ctrl+Z in CAD doesn't affect Anchor Manager)
- [ ] Auto-save every 30s (verify in IndexedDB Dev Tools)
- [ ] No component unmounting on workspace switch (verify in React DevTools)

### Anchor Manager Viewport (Phases 2-3)
- [ ] Load SVG → auto-fit with 5% margin
- [ ] F key → fit view
- [ ] Ctrl++ / Ctrl+- → zoom in/out
- [ ] Middle-click drag → pan
- [ ] Undo/Redo buttons visible only after SVG load
- [ ] Grid lines removed (no grid rendering)
- [ ] Reset button → same as F key
- [ ] Keyboard shortcuts working (F, Ctrl+Z, Ctrl+Y)

### Floating Right Panel (Phase 3)
- [ ] Panel drags smoothly without lag
- [ ] Position persists across sessions
- [ ] Room list visible, clickable
- [ ] Anchor list shows all anchors in room
- [ ] Anchor editor: x, y, z, hw_id fields editable
- [ ] Reference anchor dropdown works
- [ ] Coordinate system display shows bounds + anchors
- [ ] Yellow highlight area visible
- [ ] History timeline visible + clickable
- [ ] No left panel visible

### Anchor Placement (Phases 4-5)
- [ ] Hover over canvas → circle preview appears
- [ ] Preview updates live with cursor
- [ ] Try placing outside room → error toast "Anchor must be placed inside room"
- [ ] Try placing inside room → anchor created
- [ ] Snap to wall endpoint → visual feedback (blue circle)
- [ ] Snap threshold 0.3 ft working
- [ ] Drag anchor → moves with cursor
- [ ] Snap active while dragging
- [ ] Shift+drag → bypass snap
- [ ] Ctrl+drag → fine adjustment
- [ ] Release drag → anchor finalizes
- [ ] Undo drag → reverts to before position
- [ ] Arrow keys → nudge anchor by 0.1 ft

### Anchor Coordinate System (Phase 6)
- [ ] Change reference anchor → coordinates recompute
- [ ] First anchor (A0) is 0,0 by default
- [ ] Select different reference → display updates
- [ ] JSON saves reference_anchor_id
- [ ] History timeline shows snapshots
- [ ] Click snapshot → jump to that state
- [ ] Preview on hover
- [ ] History back/forward arrows functional

### File Organization (Phase 7)
- [ ] Tags save to `BRIGID/profile/Tags/{tag_id}.json`
- [ ] Rooms save to `BRIGID/profile/Rooms/{room_name}.json`
- [ ] Manifest saves to `BRIGID/profile/Rooms/{project_name}.rooms.json`
- [ ] Directories auto-created if missing
- [ ] Profile Manager loads tags from Tags/
- [ ] Anchor Manager loads rooms from Rooms/

### Calibration Tool (Phases 8-9)
- [ ] Calibration Tool accessible from Home
- [ ] BLE mode: detect devices, list them
- [ ] Serial mode: detect COM ports, list them
- [ ] Toggle BLE/Serial: UI updates
- [ ] BLE connect: receive live distances
- [ ] Serial connect: receive live distances
- [ ] Measurement table: add rows, input pairs
- [ ] Generate equations: backend fits curves
- [ ] Display equations with quality (R²)
- [ ] Save to profile: writes equations to tag JSON
- [ ] Equations persist: reload tag → equations still there
- [ ] Load all tags from profile database
- [ ] Show count of tags: "3 profiles loaded"
- [ ] Calibrate multiple tags: each independently

### Overall Integration
- [ ] Non-linear workflow: CAD → Anchor Manager → Profile Manager → Calibration → back
- [ ] No data loss on any switch
- [ ] All saves consistent (Tags/, Rooms/ directories)
- [ ] Undo/Redo work independently per-workspace
- [ ] Page reload: all state restored
- [ ] Export removed from Anchor Manager UI
- [ ] All keyboard shortcuts functional
- [ ] Floating panels draggable
- [ ] UI responsive (no lag on zoom/pan/drag)

---

## Technical Architecture Notes

### Redux Store Subscriptions
```typescript
// Each workspace subscribes to relevant slices
function CADComponent() {
  const lines = useAppSelector(state => state.cad.lines);
  const viewport = useAppSelector(state => state.cad.viewport);
  // Only re-renders when these slices change
}

function AnchorManagerComponent() {
  const rooms = useAppSelector(state => state.anchorManager.rooms);
  const referenceAnchorId = useAppSelector(state => state.anchorManager.referenceAnchorId);
  // Independent of CAD changes
}
```

### Undo/Redo Implementation
```typescript
// Each workspace has independent stack
interface CadState {
  lines: Line[]
  undoStack: CadState[]  // max 50
  redoStack: CadState[]  // max 50
}

// On anchor placement:
const placeAnchor = (anchor) => {
  // 1. Snapshot before
  const before = { ...state.anchorManager };
  
  // 2. Mutate
  state.anchorManager.anchors.push(anchor);
  
  // 3. Push to undo
  undoStack.push(before);
  redoStack.length = 0;  // clear redo
};

// On Ctrl+Z:
const undo = () => {
  if (undoStack.length > 0) {
    const before = { ...state };
    state = undoStack.pop();
    redoStack.push(before);
  }
};
```

### Coordinate Transformation
```typescript
// World-space: room bounding box origin
function worldToLocal(room, wx, wy) {
  return [wx - room.min_x, wy - room.min_y];
}

// Anchor-space: reference anchor is origin
function worldToAnchorCoords(anchors, refAnchorId, wx, wy) {
  const refAnchor = anchors.find(a => a.id === refAnchorId);
  return [wx - refAnchor.x, wy - refAnchor.y];
}

// Display both
function renderAnchorLabel(anchor, room, refAnchorId) {
  const rcoord = worldToLocal(room, anchor.x, anchor.y);
  const acoord = worldToAnchorCoords(room.anchors, refAnchorId, anchor.x, anchor.y);
  return `(${rcoord[0]}, ${rcoord[1]}) [${acoord[0]}, ${acoord[1]}]`;
}
```

### Snap-to-Walls Algorithm
```typescript
function findSnapTarget(anchorX, anchorY, room, tolerance = 0.3) {
  let best = null;
  let bestDist = tolerance;
  
  // Check endpoints
  for (const seg of room.segments) {
    for (const pt of [[seg.x1, seg.y1], [seg.x2, seg.y2]]) {
      const d = dist(anchorX, anchorY, pt[0], pt[1]);
      if (d < bestDist) { best = pt; bestDist = d; }
    }
    
    // Check perpendicular
    const closest = projectPointOnSegment(anchorX, anchorY, seg);
    const d = dist(anchorX, anchorY, closest[0], closest[1]);
    if (d < bestDist) { best = closest; bestDist = d; }
  }
  
  return best;
}
```

### BLE Distance Streaming
```python
# Backend: listen_for_distances() coroutine
async def listen_for_ble_distances(tag_mac):
    async with client.connect(tag_mac) as conn:
        while True:
            data = await conn.read_characteristic(CHAR_UUID)
            distances = parse_distance_data(data)  # {"A0": 5.2, ...}
            await broadcast_to_websocket(distances)

# Frontend: WebSocket listener
socket.on('calibration:distances', (data) => {
  dispatch(updateTagDistances({
    tagId: currentTag,
    distances: data
  }));
});
```

### Equation Saving to Profile
```python
@app.post("/api/calibration/save-equations")
async def save_equations(request):
    profile, _ = load_profile(request.tag_id, TAGS_DIR)
    profile["calibration"]["equations"] = {
        "A0": "(0.95*Raw)+0.25",
        "A1": "(0.97*Raw)-0.10",
        "A2": "(0.92*Raw)+0.35",
        "A3": "(0.96*Raw)+0.05",
    }
    profile["calibration"]["last_calibration_date"] = datetime.now().isoformat()
    save_profile(profile, TAGS_DIR)
    return {"success": True}
```

---

## Notes for Implementation Team

1. **Start with Phase 1 (Redux architecture)** – this unblocks everything else
2. **Test state persistence heavily** – the biggest win for UX
3. **Anchor coordinate system is complex** – document well, test carefully
4. **BLE/Serial connectivity can be finicky** – add robust error handling + logging
5. **Persist UI state (floating panel positions)** – users appreciate it
6. **Keyboard shortcuts must work reliably** – test across workspaces
7. **Profile directory structure** – create directories on startup if missing
8. **Auto-save every 30s** – avoid data loss
9. **Snap tolerance 0.3 ft** – tunable if users find it too wide/narrow
10. **Yellow anchor highlight area** – make it obvious but not overwhelming

---

## Final Workflow Summary

**Complete User Journey:**
1. Open Anchor Manager
2. Load SVG (floor plan) → viewport auto-fits
3. Create room → select boundary segments
4. Place 4 anchors → snap to corners, drag to adjust
5. Change reference anchor A1 → see coordinate system update
6. Save rooms → JSON in `profile/Rooms/`
7. Open Tag Profiler
8. Create tag profile for John Doe
9. Open Calibration Tool
10. Connect via Serial port → dongle detected
11. Select tag "John" → distances streaming
12. Measure distances at known points → add to table
13. Generate equations → Linear fit
14. Save equations → written to `profile/Tags/john.json`
15. Back to Anchor Manager → update room coordinates if needed
16. Save final configuration
17. Workflow complete: room geometry + anchor positions + tag calibration all persisted, independent, resumable

This is the vision we're building toward.
