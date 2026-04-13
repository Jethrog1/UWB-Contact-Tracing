import React from 'react'
import { Icon } from '@blueprintjs/core'
import { motion } from 'motion/react'
import { AppModule } from '../TopBar/TopBar'
import './CentralCanvas.css'

interface CentralCanvasProps {
  activeModule: AppModule
}

const moduleInfo: Record<AppModule, { title: string; subtitle: string; icon: string }> = {
  rtls: {
    title: 'RTLS Live Tracking',
    subtitle: 'Real-time UWB/BLE tag position monitoring',
    icon: '◉'
  },
  cad: {
    title: 'CAD Floor Plan Editor',
    subtitle: 'Draw, import, and edit facility geometry',
    icon: '⬡'
  },
  anchors: {
    title: 'Anchor Placement Workspace',
    subtitle: 'Position anchors on the floor plan',
    icon: '⊕'
  },
  profiling: {
    title: 'Calibration & Profiling',
    subtitle: 'Tag profiling and distance correction',
    icon: '◈'
  }
}

const CentralCanvas: React.FC<CentralCanvasProps> = ({ activeModule }) => {
  const info = moduleInfo[activeModule]

  return (
    <motion.section
      className="central-canvas"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.8, delay: 0.2 }}
    >
      {/* ---- Grid pattern overlay ---- */}
      <div className="central-canvas__grid" />
      <div className="central-canvas__vignette" />
      <div className="central-canvas__glow" />

      {/* ---- Module workspace indicator ---- */}
      <div className="central-canvas__module-label">
        <span className="central-canvas__module-icon">{info.icon}</span>
        <span className="central-canvas__module-title">{info.title}</span>
      </div>

      {/* ---- Center crosshair / workspace prompt ---- */}
      <div className="central-canvas__center-prompt">
        <div className="central-canvas__crosshair">
          <div className="central-canvas__crosshair-h" />
          <div className="central-canvas__crosshair-v" />
          <div className="central-canvas__crosshair-dot" />
        </div>
        <motion.div
          className="central-canvas__prompt-text"
          key={activeModule}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.3 }}
        >
          {activeModule === 'rtls' && 'Load a floor plan project to begin live tracking'}
          {activeModule === 'cad' && 'Import an SVG floor plan or start a new drawing'}
          {activeModule === 'anchors' && 'Load a floor plan, then place anchors on the layout'}
          {activeModule === 'profiling' && 'Connect a BLE module to begin tag profiling'}
        </motion.div>
      </div>

      {/* ---- Coordinate overlays ---- */}
      <div className="central-canvas__coord central-canvas__coord--tl">
        <span className="central-canvas__coord-text">0.000 ft</span>
      </div>
      <div className="central-canvas__coord central-canvas__coord--tr">
        <span className="central-canvas__coord-text">0.000 ft</span>
      </div>

      {/* ---- Status bar ---- */}
      <div className="central-canvas__status-bar">
        <div className="central-canvas__status-item">
          <span className="central-canvas__status-dot central-canvas__status-dot--online" />
          <span>System Idle</span>
        </div>
        <div className="central-canvas__status-separator" />
        <div className="central-canvas__status-item">
          <Icon icon="layers" size={11} />
          <span>No Floor Plan</span>
        </div>
        <div className="central-canvas__status-separator" />
        <div className="central-canvas__status-item">
          <Icon icon="cell-tower" size={11} />
          <span>0 Anchors</span>
        </div>
        <div className="central-canvas__status-separator" />
        <div className="central-canvas__status-item">
          <Icon icon="locate" size={11} />
          <span>0 Tags</span>
        </div>
        <div className="central-canvas__status-separator" />
        <div className="central-canvas__status-item">
          <Icon icon="feed" size={11} />
          <span>No Serial</span>
        </div>
      </div>
    </motion.section>
  )
}

export default CentralCanvas
