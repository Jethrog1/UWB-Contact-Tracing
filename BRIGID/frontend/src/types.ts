// ── Application-wide Types ────────────────────────────────────────

export type AppModule = 'profile' | 'calibration' | 'cad' | 'anchors' | 'rtls'

export interface WorkspaceTab {
  id: string
  name: string
  module: AppModule
  modified: boolean
}
