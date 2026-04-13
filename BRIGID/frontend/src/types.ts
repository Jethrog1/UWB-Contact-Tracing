// ── Application-wide Types ────────────────────────────────────────

export type AppModule = 'profile' | 'calibration' | 'cad' | 'anchors' | 'rtls'

export interface WorkspaceTab {
  id: string
  name: string
  module: AppModule
  modified: boolean
}

// ── Tag Profiler ─────────────────────────────────────────────────

export interface TagProfileIdentity {
  profile_id: string
  name: string
  description: string
}

export interface TagProfileDevice {
  mac_address: string
  device_type: string
  wrist_to_floor_ft: number
  arm_to_floor_ft: number
  hip_to_floor_ft: number
  breast_to_floor_ft: number
  description: string
}

export interface TagProfileCalibration {
  equations: Record<string, string>   // "A0" | "A1" | "A2" | "A3" → equation string
  last_calibration_date: string
  equations_enabled: boolean          // whether equation fields are editable (default false)
}

export interface TagProfile {
  tag_id: string
  identity: TagProfileIdentity
  device: TagProfileDevice
  calibration: TagProfileCalibration
  notes: string
}

export interface CalibrationPoint {
  measured: number   // raw UWB distance
  true_dist: number  // ground truth distance
}

// ── Room / Anchor Manager ────────────────────────────────────────

export interface AnchorData {
  id: string
  hw_id: string
  x_ft: number
  y_ft: number
  z_ft: number
}

export interface RoomBounds {
  min_x: number
  min_y: number
  max_x: number
  max_y: number
  width: number
  height: number
}

export interface RtlsSettings {
  tag_height_ft: number
  filter_mode: string
  ble_module_port: string
}

export interface SegmentData {
  x1: number
  y1: number
  x2: number
  y2: number
}

export interface RoomData {
  room_name: string
  units: string
  rtls_settings: RtlsSettings
  reference_anchor_id?: string | null
  room_bounds_ft: RoomBounds
  anchors: AnchorData[]
  segments_ft: SegmentData[]
  interior_segments_ft: SegmentData[]
}

export interface FloorplanManifest {
  project_name: string
  svg_file: string
  saved_at: string
  units: string
  rooms: RoomData[]
}
