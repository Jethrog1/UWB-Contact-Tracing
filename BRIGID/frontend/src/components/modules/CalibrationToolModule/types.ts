export const ANCHOR_IDS = ['A0', 'A1', 'A2', 'A3'] as const

export type AnchorId = (typeof ANCHOR_IDS)[number]
export type CalibrationTransportMode = 'ble' | 'serial'

export interface CalibrationPointXY {
  x: number
  y: number
}

export interface CalibrationGraphSeries {
  points: CalibrationPointXY[]
  fit_line: CalibrationPointXY[]
  capture: CalibrationPointXY[]
  live_raw: CalibrationPointXY | null
  live_cal: CalibrationPointXY | null
}

export interface CalibrationFitOptions {
  auto: boolean
  fit_mode: string
  poly_deg: number
  ma_period: number
  ma_type: string
}

export interface CalibrationPointRecord {
  measured: number
  true_dist: number
}

export interface CalibrationTagRuntime {
  tag_id: string
  name: string
  device_type: string
  mac_address: string
  status: string
  last_seen_seconds: number | null
  raw_distances: Record<string, number>
  calibrated_distances: Record<string, number>
  raw_xy: [number, number] | null
  calibrated_xy: [number, number] | null
  reference_floor: Record<string, number | null>
  reference_height: number
  locked_reference: Record<string, number | null>
  equations: Record<string, string>
  saved_profile_equations: Record<string, string>
  fit_options: Record<string, CalibrationFitOptions>
  points: Record<string, CalibrationPointRecord[]>
  captured_points_log: string[]
  graph: Record<string, CalibrationGraphSeries>
}

export interface CalibrationMapRuntime {
  anchors: Record<string, [number, number]>
  lines: string[][]
  height_offset: number
}

export interface CalibrationFilterRuntime {
  mode: string
  ema_alpha: number
  roll_n: number
  kal_q: number
  kal_r: number
}

export interface CalibrationCaptureRuntime {
  active: boolean
  phase: string
  tag_id: string | null
  target: number
  counts: Record<string, number>
}

export interface CalibrationRuntimeSnapshot {
  success: boolean
  mode: CalibrationTransportMode | null
  transport_status: string
  transport_detail: string
  selected_port: string
  ble_available: boolean
  serial_available: boolean
  ports: string[]
  auto_detect_port: string
  capture: CalibrationCaptureRuntime
  map: CalibrationMapRuntime
  filter: CalibrationFilterRuntime
  tags: CalibrationTagRuntime[]
}
