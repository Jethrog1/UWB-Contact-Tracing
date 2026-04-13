// ── CAD Module — TypeScript Types ────────────────────────────────────

export interface CADViewport {
  scale: number   // pixels per world unit
  offx: number    // screen origin X  (world 0 → screen offx)
  offy: number    // screen origin Y
}

export interface CADLine {
  id: string
  x1: number
  y1: number
  x2: number
  y2: number
  color: string
}

export interface FixedLengthMeta {
  len: number
  label?: [number, number]
}

export interface AngleConstraint {
  idx: number
  line_a_id: string
  line_b_id: string
  vx: number
  vy: number
  deg: number
  side: number
  off: number
}

export interface DistanceConstraint {
  idx: number
  line_a_id: string
  line_b_id: string
  dist: number
  Pa?: [number, number]
  Pb?: [number, number]
  label?: [number, number]
}

export type SnapHint = { kind: 'endpoint' | 'line'; x: number; y: number } | null

export interface AlignmentGuide {
  x1: number; y1: number
  x2: number; y2: number
  type: 'x' | 'y'
}

export type ToolMode = 'cursor' | 'line' | 'vertex' | 'dim'

export interface CADState {
  // Geometry
  lines: CADLine[]
  fixed_lengths: Record<string, FixedLengthMeta>
  angle_constraints: AngleConstraint[]
  distance_constraints: DistanceConstraint[]

  // Selection / hover
  selected_id: string | null
  multi_selected_ids: string[]
  hovered_id: string | null

  // Tool state
  tool_mode: ToolMode
  drawing_line: boolean
  temp_line_start: [number, number] | null
  paste_active: boolean
  rotate_active: boolean
  trim_active: boolean
  vertex_hover: [number, number] | null

  // Cursor / snapping
  cursor_world: [number, number]
  cursor_world_snapped: [number, number]
  snap_hint: SnapHint
  alignment_guides: AlignmentGuide[]
  parallel_guides: any[]
  equal_length_guides: any[]

  // Viewport
  vp: CADViewport

  // Feature flags
  manipulate_line: boolean
  snap_axis: boolean
  line_match: boolean
  disable_vpoint: boolean

  // Angle snap entries
  angle_snap_values: string[]

  // Active dimension selection (for copy/paste)
  selected_dim_kinds: string[]  // e.g. ['len:lineId', 'ang:0']

  // Dialog from backend
  pending_dialog?: {
    kind: 'prompt_float'
    title: string
    label: string
    initial: number
    request_id: string
  }

  // Error from backend
  last_error?: string
}

// Commands sent to Python backend
export type CADCommand =
  | { type: 'mouse_down';  x: number; y: number; button: number; ctrl: boolean; shift: boolean }
  | { type: 'mouse_move';  x: number; y: number }
  | { type: 'mouse_up';    x: number; y: number; button: number }
  | { type: 'double_click'; x: number; y: number }
  | { type: 'right_click'; x: number; y: number }
  | { type: 'wheel';       x: number; y: number; delta: number }
  | { type: 'key_press';   key: string; ctrl: boolean; shift: boolean }
  | { type: 'tool_change'; tool: ToolMode }
  | { type: 'viewport_resize'; width: number; height: number }
  | { type: 'dialog_response'; request_id: string; value: number | null }
  | { type: 'toggle_flag'; flag: 'manipulate_line' | 'snap_axis' | 'line_match' | 'disable_vpoint'; value: boolean }
  | { type: 'angle_snap_set'; index: number; value: string }
  | { type: 'undo' }
  | { type: 'redo' }
  | { type: 'copy' }
  | { type: 'paste' }
  | { type: 'delete' }
  | { type: 'escape' }
  | { type: 'zoom_in' }
  | { type: 'zoom_out' }
  | { type: 'zoom_reset' }
