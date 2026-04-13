import React from 'react'
import { Icon, IconName, Tooltip } from '@blueprintjs/core'
import { motion } from 'motion/react'
import { AppModule } from '../../types'
import './LeftRail.css'

interface ModuleItem {
  id: AppModule
  icon: IconName
  label: string
  color?: string
}

const MODULE_ITEMS: ModuleItem[] = [
  { id: 'profile',     icon: 'person',           label: 'Profile Manager' },
  { id: 'calibration', icon: 'regression-chart',  label: 'Calibration Tool' },
  { id: 'cad',         icon: 'draw',              label: '2D CAD Modeling' },
  { id: 'anchors',     icon: 'cell-tower',        label: 'Anchor Manager' },
  { id: 'rtls',        icon: 'pulse',             label: 'RTLS Dashboard' },
]

interface LeftRailProps {
  activeModule: AppModule | null
  onModuleChange: (module: AppModule) => void
  disabled?: boolean
}

const LeftRail: React.FC<LeftRailProps> = ({ activeModule, onModuleChange, disabled = false }) => {
  return (
    <motion.aside
      className="left-rail"
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4, delay: 0.1, ease: [0.4, 0, 0.2, 1] }}
    >
      {/* ── App icon / home ── */}
      <div className="left-rail__logo">
        <Icon icon="locate" size={18} color="#38bdf8" />
      </div>

      <div className="left-rail__divider" />

      {/* ── 5 Module Buttons ── */}
      <nav className="left-rail__nav">
        {MODULE_ITEMS.map((item) => {
          const isActive = activeModule === item.id
          return (
            <Tooltip
              key={item.id}
              content={
                <span style={{ fontSize: 12 }}>{item.label}</span>
              }
              placement="right"
              minimal
              hoverOpenDelay={400}
            >
              <button
                className={`left-rail__btn ${isActive ? 'left-rail__btn--active' : ''}`}
                onClick={() => onModuleChange(item.id)}
                aria-label={item.label}
                disabled={disabled}
              >
                {isActive && (
                  <motion.div
                    className="left-rail__active-bar"
                    layoutId="left-rail-active"
                    transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                  />
                )}
                <span className="left-rail__btn-icon">
                  <Icon icon={item.icon} size={17} />
                </span>
              </button>
            </Tooltip>
          )
        })}
      </nav>

      {/* ── Bottom: Settings ── */}
      <div className="left-rail__bottom">
        <Tooltip
          content={<span style={{ fontSize: 12 }}>Settings</span>}
          placement="right"
          minimal
          hoverOpenDelay={400}
        >
          <button className="left-rail__btn left-rail__btn--bottom" aria-label="Settings">
            <Icon icon="cog" size={16} />
          </button>
        </Tooltip>
      </div>
    </motion.aside>
  )
}

export default LeftRail
