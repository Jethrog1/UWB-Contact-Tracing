export interface CADViewport {
  scale: number
  offx: number
  offy: number
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
  label?: [number, number] | null
}

export interface AngleConstraint {
  idx: number
  line_a_id: string | null
  line_b_id: string | null
  vx: number
  vy: number
  deg: number
  side: number
  off: number
}

export interface DistanceConstraint {
  idx: number
  line_a_id: string | null
  line_b_id: string | null
  dist: number
  Pa?: [number, number] | null
  Pb?: [number, number] | null
  label?: [number, number] | null
}

export type SnapHint = { kind: string; x: number; y: number } | null

export interface AlignmentGuide {
  x1: number
  y1: number
  x2: number
  y2: number
  type: string
}

export interface MatchGuide {
  x1: number
  y1: number
  x2: number
  y2: number
  line_id?: string | null
}

export type ToolMode = 'cursor' | 'line' | 'vertex' | 'dim'

export interface CADFeatureNode {
  id: string
  text: string
  open: boolean
  values: string[]
  children: CADFeatureNode[]
}

export interface CADRenderPrimitive {
  kind: 'line' | 'oval' | 'rect' | 'polygon' | 'text' | 'arc'
  points: number[]
  options: Record<string, any>
}

export interface CADContextMenuItem {
  id: string
  label: string
  kind: 'action' | 'toggle'
  disabled?: boolean
  checked?: boolean
}

export interface CADContextMenuSection {
  title: string
  items: CADContextMenuItem[]
}

export interface CADContextMenu {
  x: number
  y: number
  sections: CADContextMenuSection[]
}

export interface TrimState {
  active: boolean
  selected_line_id: string | null
  line_length: number
  trim_point_1: number | null
  trim_point_2: number | null
  selecting_point: number
  hover_position: number | null
  cursor_near_line: boolean
  trim1_text: string
  trim2_text: string
  distance_text: string
}

export interface RotateState {
  active: boolean
  state: string
  pivot_point: [number, number] | null
  axis_point: [number, number] | null
  current_angle_deg: number
  selected_line_ids: (string | null)[]
}

export interface CADClipboardState {
  has_data: boolean
  line_count: number
}

export interface CADNotice {
  kind: 'info' | 'error'
  title: string
  message: string
}

export interface CADState {
  lines: CADLine[]
  fixed_lengths: Record<string, FixedLengthMeta>
  angle_constraints: AngleConstraint[]
  distance_constraints: DistanceConstraint[]
  selected_id: string | null
  multi_selected_ids: (string | null)[]
  hovered_id: string | null
  tool_mode: ToolMode
  drawing_line: boolean
  temp_line_start: [number, number] | null
  paste_active: boolean
  rotate_active: boolean
  trim_active: boolean
  vertex_hover: [number, number] | null
  cursor_world: [number, number]
  cursor_world_snapped: [number, number]
  snap_hint: SnapHint
  alignment_guides: AlignmentGuide[]
  parallel_guides: MatchGuide[]
  equal_length_guides: MatchGuide[]
  vp: CADViewport
  manipulate_line: boolean
  snap_axis: boolean
  line_match: boolean
  disable_vpoint: boolean
  angle_snap_values: string[]
  selected_dim_kinds: string[]
  feature_tree: CADFeatureNode[]
  render_primitives: CADRenderPrimitive[]
  context_menu?: CADContextMenu | null
  trim_state: TrimState
  rotate_state: RotateState
  clipboard: CADClipboardState
  pending_dialog?: {
    kind: 'prompt_float'
    title: string
    label: string
    initial: number
    request_id: string
  }
  last_error?: string
  last_notice?: CADNotice
}

export type CADCommand =
  | { type: 'mouse_down'; x: number; y: number; button: number; ctrl: boolean; shift: boolean; buttons: number }
  | { type: 'mouse_move'; x: number; y: number; ctrl: boolean; shift: boolean; buttons: number }
  | { type: 'mouse_up'; x: number; y: number; button: number; ctrl: boolean; shift: boolean; buttons: number }
  | { type: 'mouse_leave' }
  | { type: 'double_click'; x: number; y: number }
  | { type: 'right_click'; x: number; y: number }
  | { type: 'wheel'; x: number; y: number; delta: number }
  | { type: 'key_press'; key: string; ctrl: boolean; shift: boolean }
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
  | { type: 'context_action'; action: string }
  | { type: 'context_close' }
  | { type: 'trim_value_set'; point: 1 | 2; value: string }
  | { type: 'trim_apply' }

