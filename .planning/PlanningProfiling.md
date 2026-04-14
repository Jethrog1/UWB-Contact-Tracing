# BRIGID Tag Profiler Feature Implementation

## System Instructions for Agent

### Context
We are porting the **Tag Profiler** from the legacy 2DL CAD application to BRIGID. This feature enables operators to create, manage, and export tag (device) profiles as JSON files for RTLS operations.

A tag profile contains:
- **Identity**: Profile ID, name, tag ID, description
- **Device**: MAC address, device type, height measurements (wrist/arm/hip/breast-to-floor)
- **Calibration**: Distance correction equations for anchors A0-A3, calibration date
- **Calibration Lab**: Live distance capture, point entry, equation generation with multiple fit modes
- **Notes**: Optional operational notes

**CRITICAL:** Study `2DLCAD/tag_profiler.py`, `tag_profile_utils.py`, and `calibration_utils.py`. **DO NOT COPY the PyQt6 UI code** – only extract and adapt the profile data structure, JSON serialization, and calibration equation logic.

### Key Principles
- **Backend-Driven:** All file I/O, profile management, and calibration math happen in Python
- **No Old UI:** Build from scratch with React components; use BRIGID design system
- **Scrollable Content:** Main workspace is vertically scrollable (ScrollArea equivalent)
- **No Right Panel:** Tag Profiler occupies the full central area
- **Hot Bar Integration:** Add File menu items (New Profile, Open Profile, Save Profile, Export Profile)
- **Profile Storage:** Save to `BRIGID/profile/` directory as JSON files (one per tag)
- **Validation:** Form validation with helpful error messages
- **Calibration Math:** Inherit NumPy-based fit modes (Linear, Polynomial, Logarithmic, Power Series, Exponential, Moving Average)

### Module Organization

**Backend Structure:**
```
BRIGID/backend/
├── utilities/
│   ├── profilers/
│   │   ├── __init__.py
│   │   ├── tag_profiler.py       (profile creation/management logic)
│   │   ├── tag_profile_io.py      (JSON load/save)
│   │   ├── calibration_math.py    (equation generation, fit modes)
│   │   └── constants.py           (device types, field help, defaults)
│   └── [existing importers/exporters...]
```

**Frontend Structure:**
```
BRIGID/frontend/src/
├── components/
│   └── modules/
│       └── TagProfilerModule/
│           ├── TagProfiler.tsx          (root container, tabs)
│           ├── ProfileFormSection.tsx   (Identity, Device, Calibration, Notes cards)
│           ├── CalibrationLabTab.tsx    (live capture, point entry, equation generation)
│           ├── FieldInput.tsx           (reusable text input with help icon)
│           ├── SectionCard.tsx          (card wrapper for form sections)
│           └── TagProfiler.css
```

### For the Implementer

1. **Backend Profile Schema:**
   ```python
   {
       "tag_id": str,
       "identity": {
           "profile_id": str,
           "name": str,
           "description": str
       },
       "device": {
           "mac_address": str,
           "device_type": "Wrist Band" | "Arm Band" | "Belt Clip-on" | "Breast Pocket",
           "wrist_to_floor_ft": float,
           "arm_to_floor_ft": float,
           "hip_to_floor_ft": float,
           "breast_to_floor_ft": float,
           "description": str
       },
       "calibration": {
           "equations": {
               "A0": str,  # e.g., "(0.95*Raw)+0.5" or "[Auto:Linear] (0.95*Raw)+0.5"
               "A1": str,
               "A2": str,
               "A3": str
           },
           "last_calibration_date": str  # ISO format
       },
       "notes": str
   }
   ```

2. **API Endpoints (REST):**
   - `POST /api/profile/new` → Create new empty profile
   - `GET /api/profile/<tag_id>` → Load profile JSON
   - `POST /api/profile/save` → Save profile to disk
   - `POST /api/profile/export` → Export as JSON file (download)
   - `GET /api/profile/list` → List all saved profiles
   - `POST /api/profile/delete/<tag_id>` → Delete profile
   - `POST /api/profile/calibration/generate` → Generate equations from point data

3. **Frontend State (React):**
   - Current profile (identity, device, calibration, notes)
   - Tab state (Profile vs. Calibration Lab)
   - Unsaved changes tracking
   - Calibration Lab state (points buffer, selected fit mode, equation output)

4. **Hot Bar Integration:**
   In the top bar, add a **File** menu with:
   - New Profile (Ctrl+N)
   - Open Profile... (Ctrl+O) → file browser
   - Save Profile (Ctrl+S)
   - Export Profile As... (Ctrl+Shift+E) → save dialog
   - Recent Profiles (submenu)

5. **Calibration Lab Features:**
   - Serial port selector (dropdown)
   - Live distance capture button (toggles on/off)
   - Progress bar during capture
   - Manual point entry (distance vs. true distance pairs)
   - Fit mode selector (Linear, Polynomial degree, etc.)
   - Generate calibration button
   - Auto-equations display with [Auto:Mode] prefix
   - Apply calibration button

6. **Validation & Error Handling:**
   - Tag ID required (unique identifier)
   - Device type determines visible height field
   - Only selected height field is populated
   - Calibration equations are optional (can be empty)
   - Show validation errors as inline messages or toast notifications

### Design Guidance
- Use BRIGID's existing dark theme colors
- Section cards with subtle borders (gradient backgrounds optional)
- Help icons (?) with tooltips on hover
- Tab interface at top of scrollable content
- Buttons for: New Profile, Export, Generate Equations, Apply Calibration
- Form layout: 2-column grid for sections
- Scrollbar visible on right when content overflows

---

## Implementation Plan

### Phase 1: Backend Infrastructure
**Duration:** 20 min

1. **Create profile constants and data structure:**
   - `BRIGID/backend/utilities/profilers/constants.py`
     - `DEVICE_TYPES` = ["Wrist Band", "Arm Band", "Belt Clip-on", "Breast Pocket"]
     - `FIELD_HELP` dict with tooltips for each field
     - `DEVICE_HEIGHT_FIELD_MAP` (device type → field name)
     - `FIT_MODES` = ["Linear", "Polynomial", "Logarithmic", "Power Series", "Exponential", "Moving Average"]

2. **Create profile I/O module:**
   - `BRIGID/backend/utilities/profilers/tag_profile_io.py`
     - `create_empty_profile() → dict`
     - `save_profile(profile: dict, profile_dir: str) → Tuple[bool, str]`
     - `load_profile(tag_id: str, profile_dir: str) → Tuple[dict, str]`
     - `list_profiles(profile_dir: str) → List[str]`
     - `delete_profile(tag_id: str, profile_dir: str) → Tuple[bool, str]`

3. **Create calibration math module:**
   - `BRIGID/backend/utilities/profilers/calibration_math.py`
     - Adapt from `2DLCAD/calibration_utils.py`
     - `build_eval_func(mode: str, X: list, Y: list, **kwargs) → Tuple[Callable, str]`
     - `compile_manual_equation(expr: str) → Callable`
     - Support all 6 fit modes with numpy operations

4. **Create tag profiler logic module:**
   - `BRIGID/backend/utilities/profilers/tag_profiler.py`
     - `TagProfile` class or dict-based utilities
     - Methods: validate(), get_device_height_field(), serialize(), deserialize()
     - Handle device type changes and field updates

### Phase 2: Wire Backend API Endpoints
**Duration:** 20 min

1. **Add routes to `BRIGID/backend/cad_server.py` (or new `profile_server.py`):**

   ```python
   @app.post("/api/profile/new")
   async def create_new_profile():
       profile = create_empty_profile()
       return {"success": True, "profile": profile}
   
   @app.get("/api/profile/{tag_id}")
   async def load_profile(tag_id: str):
       profile, error = load_profile(tag_id, PROFILE_DIR)
       if error:
           return {"success": False, "error": error}
       return {"success": True, "profile": profile}
   
   @app.post("/api/profile/save")
   async def save_profile(request: SaveProfileRequest):
       success, error = save_profile(request.profile, PROFILE_DIR)
       if not success:
           return {"success": False, "error": error}
       return {"success": True, "tag_id": request.profile["tag_id"]}
   
   @app.post("/api/profile/export")
   async def export_profile(request: ExportProfileRequest):
       # Save to user's Downloads folder or Desktop
       # Return filepath for download
       ...
   
   @app.get("/api/profile/list")
   async def list_profiles():
       profiles = list_profiles(PROFILE_DIR)
       return {"success": True, "profiles": profiles}
   
   @app.post("/api/profile/delete/{tag_id}")
   async def delete_profile(tag_id: str):
       success, error = delete_profile(tag_id, PROFILE_DIR)
       if not success:
           return {"success": False, "error": error}
       return {"success": True}
   
   @app.post("/api/profile/calibration/generate")
   async def generate_calibration(request: CalibrationGenerateRequest):
       # request.points = List[(distance, true_distance)]
       # request.fit_mode = "Linear" | "Polynomial" | etc.
       # request.poly_deg = 4 (for polynomial)
       func, expr = build_eval_func(request.fit_mode, X, Y, poly_deg=request.poly_deg)
       return {"success": True, "equation": expr, "func_expr": expr}
   ```

2. **Define request/response types:**
   - `SaveProfileRequest` – profile: dict
   - `ExportProfileRequest` – profile: dict, filepath: str
   - `CalibrationGenerateRequest` – points: List[Tuple[float, float]], fit_mode: str, poly_deg: int

3. **Profile directory setup:**
   - Create `BRIGID/profile/` directory if not exists
   - Store profiles as `{tag_id}.json` files

### Phase 3: Build Frontend React Components
**Duration:** 40 min

1. **Root component: `TagProfiler.tsx`**
   - Header with title, subtitle, buttons (New, Export, Save)
   - Tab interface (Profile | Calibration Lab)
   - ScrollArea wrapper around tabs
   - Load/save/new/export event handlers

2. **Profile Tab: `ProfileFormSection.tsx`**
   - Summary card (profile name + tag ID display)
   - 2-column grid layout:
     - Left column: Identity card, Calibration card
     - Right column: Device card, Notes card
   - Each card has form fields with help icons

3. **Field Components: `FieldInput.tsx`**
   - Text input with label + optional help icon
   - Dropdown for device type
   - Textarea for descriptions/notes
   - Numeric input for heights
   - Help text tooltip on hover

4. **Card Wrapper: `SectionCard.tsx`**
   - Styled container (gradient background, border)
   - Title + subtitle
   - Body layout for form fields

5. **Calibration Lab Tab: `CalibrationLabTab.tsx`**
   - Serial port selector + Connect/Disconnect buttons
   - Live distance capture interface:
     - Progress bar per anchor
     - Sample count display
     - Status labels (Idle, Capturing, Done)
   - Points input area:
     - Table of (distance, true_distance) pairs
     - Add/remove row buttons
   - Fit mode selector (dropdown + optional poly_deg)
   - Generate Equations button
   - Equation output display per anchor
   - Apply Calibration button

6. **Styling: `TagProfiler.css`**
   - Dark theme matching BRIGID design
   - Scrollable container with visible scrollbar
   - Card styling (gradients, borders)
   - Form field styling
   - Tab styling
   - Button styling (primary, secondary)

### Phase 4: Hot Bar Integration
**Duration:** 15 min

1. **Update `TopBar.tsx` or menu component:**
   - Add "File" dropdown menu if not exists
   - Add menu items:
     ```
     File
     ├─ New Profile (Ctrl+N)
     ├─ Open Profile... (Ctrl+O)
     ├─ Save Profile (Ctrl+S)
     ├─ Export Profile As... (Ctrl+Shift+E)
     ├─ ─────────────────────
     └─ Recent Profiles (submenu)
     ```

2. **Wire menu actions to tag profiler:**
   - New Profile → API call, load empty form
   - Open Profile → File dialog, load JSON
   - Save Profile → API call, show confirmation
   - Export → File dialog, trigger download
   - Recent → Quick-load list

3. **Keyboard shortcuts:**
   - Ctrl+N → New Profile
   - Ctrl+O → Open Profile
   - Ctrl+S → Save Profile
   - Ctrl+Shift+E → Export Profile

### Phase 5: State Management & Persistence
**Duration:** 20 min

1. **React Context or State Hook:**
   - `useTagProfile()` hook with methods:
     - `newProfile()`
     - `loadProfile(tag_id)`
     - `saveProfile(profile)`
     - `getUnsavedChanges() → boolean`
     - `setCurrentProfile(profile)`

2. **Unsaved changes tracking:**
   - Show warning dialog on route change if unsaved
   - Disable close/new buttons if unsaved (or confirm)

3. **Recent profiles:**
   - Store recent tag_ids in localStorage
   - Populate submenu with quick-access links

### Phase 6: Calibration Lab Features
**Duration:** 30 min

1. **Live distance capture (serial):**
   - Button to toggle capture on/off
   - Backend spawns RawDistanceReaderThread (port from 2DLCAD)
   - WebSocket stream of distance updates
   - Frontend accumulates samples per anchor
   - Progress bar shows count per anchor

2. **Manual point entry:**
   - Text area or table for entering pairs
   - Format: "distance true_distance" per line
   - Parse and validate on blur
   - Show validation errors

3. **Equation generation:**
   - Send points + fit mode to backend
   - Backend calls `build_eval_func()`
   - Return equation string + function code
   - Display with [Auto:Mode] prefix

4. **Equation application:**
   - Store generated equation in profile
   - Mark as auto-calibrated
   - Update calibration date

### Phase 7: Integration & Testing
**Duration:** 20 min

1. **Profile directory initialization:**
   - Create `BRIGID/profile/` on first run
   - Handle missing directory gracefully

2. **Error handling:**
   - Invalid JSON on load → show error
   - Duplicate tag_id → warn user
   - File I/O errors → show toast
   - Calibration errors → show validation feedback

3. **Test scenarios:**
   - Create new profile → fill form → save
   - Load profile → modify → save changes
   - Export profile → verify JSON structure
   - Calibration Lab: enter points → generate → apply
   - Recent profiles: open → verify persistence
   - Device type change: wrist → arm → verify height field

4. **Edge cases:**
   - Empty tag_id
   - Special characters in tag_id (sanitize filename)
   - Very large point datasets (> 1000 points)
   - Corrupted JSON file recovery

---

## File Checklist

### New Backend Files
- [ ] `BRIGID/backend/utilities/profilers/__init__.py`
- [ ] `BRIGID/backend/utilities/profilers/constants.py`
- [ ] `BRIGID/backend/utilities/profilers/tag_profile_io.py`
- [ ] `BRIGID/backend/utilities/profilers/calibration_math.py`
- [ ] `BRIGID/backend/utilities/profilers/tag_profiler.py`

### New Frontend Files
- [ ] `BRIGID/frontend/src/components/modules/TagProfilerModule/TagProfiler.tsx`
- [ ] `BRIGID/frontend/src/components/modules/TagProfilerModule/ProfileFormSection.tsx`
- [ ] `BRIGID/frontend/src/components/modules/TagProfilerModule/CalibrationLabTab.tsx`
- [ ] `BRIGID/frontend/src/components/modules/TagProfilerModule/FieldInput.tsx`
- [ ] `BRIGID/frontend/src/components/modules/TagProfilerModule/SectionCard.tsx`
- [ ] `BRIGID/frontend/src/components/modules/TagProfilerModule/TagProfiler.css`

### Backend Files to Modify
- [ ] `BRIGID/backend/main.py` – Register new API routes
- [ ] `BRIGID/backend/cad_server.py` – Add profile endpoints (or create new `profile_server.py`)
- [ ] Optional: `BRIGID/backend/utilities/__init__.py` – Export profiler modules

### Frontend Files to Modify
- [ ] `BRIGID/frontend/src/components/TopBar/TopBar.tsx` – Add File menu
- [ ] `BRIGID/frontend/src/components/HotBar/HotBar.tsx` – Add menu items (if separate)
- [ ] `BRIGID/frontend/src/App.tsx` – Register TagProfiler workspace route
- [ ] `BRIGID/frontend/src/types.ts` – Add ProfileState, CalibrationPoint types

### Legacy Reference Files (2DL CAD)
- `2DLCAD/tag_profiler.py` – PyQt6 UI (study for UX, not code)
- `2DLCAD/tag_profile_utils.py` – Profile I/O logic (port logic)
- `2DLCAD/calibration_utils.py` – Calibration math (port functions)
- `2DLCAD/serial_reader.py` – Serial streaming (adapt for backend)

---

## Success Criteria

- [ ] Create new profile → empty form loads
- [ ] Fill form fields → data updates in real-time
- [ ] Save profile → JSON file created in `BRIGID/profile/`
- [ ] Load profile → form populates correctly
- [ ] Export profile → downloads JSON file to user's machine
- [ ] List profiles → shows all saved profiles
- [ ] Delete profile → file removed, list updates
- [ ] Device type change → height field switches correctly
- [ ] Calibration Lab: manual points → generate linear/polynomial equations
- [ ] Calibration Lab: live capture → accumulates distances per anchor
- [ ] Hot bar: File menu visible with all 4 actions
- [ ] Keyboard shortcuts: Ctrl+N, Ctrl+O, Ctrl+S, Ctrl+Shift+E work
- [ ] Unsaved changes → warning on navigation
- [ ] Recent profiles → submenu shows recent tag_ids
- [ ] Scrollbar visible → content scrolls vertically
- [ ] No right panel → full width workspace
- [ ] Error handling → graceful messages for all error cases
- [ ] Form validation → required fields enforced, helpful messages
- [ ] Roundtrip: create → save → load → result matches original

---

## Technical Notes

### Calibration Math Reference
- **Linear:** $y = mx + b$
- **Polynomial:** $\sum_{i=0}^{n} c_i \cdot x^{i}$ (degree 1-4)
- **Logarithmic:** $a \cdot \ln(x) + b$ (requires $x > 0$)
- **Power Series:** $a \cdot x^b$ (requires $x > 0, y > 0$)
- **Exponential:** $a \cdot e^{bx}$ (requires $y > 0$)
- **Moving Average:** Trailing or centered window (configurable period)

### Device Height Field Mapping
```python
{
    "Wrist Band": "wrist_to_floor_ft",
    "Arm Band": "arm_to_floor_ft",
    "Belt Clip-on": "hip_to_floor_ft",
    "Breast Pocket": "breast_to_floor_ft",
}
```

### Profile Directory Structure
```
BRIGID/profile/
├── tag_123.json
├── tag_456.json
└── tag_789.json
```

Each file contains the full profile JSON for that tag_id.

### Serial Port Integration
- Reuse `RawDistanceReaderThread` from `2DLCAD/serial_reader.py`
- Adapt to work with backend process
- Stream distances via WebSocket to frontend
- Format: `{"tag_id": "...", "distances": {"A0": float, "A1": float, ...}}`

---

## Notes for Agent

- **Do not** copy PyQt6 UI code from `tag_profiler.py`
- **Do** extract profile schema and calibration math logic
- **Match** the existing BRIGID UI patterns (no right panels for workspaces)
- **Use** existing React hooks and styling system
- **Test** all device type combinations and calibration modes
- **Handle** edge cases: empty files, corrupted JSON, special characters
- **Document** API contracts in swagger/OpenAPI if applicable
- **Provide** inline help text via tooltips (no separate help window)
- **Profile directory** must be user-writable; handle permissions gracefully
