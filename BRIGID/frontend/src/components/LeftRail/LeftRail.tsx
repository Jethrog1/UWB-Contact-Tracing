import React from 'react'
import { Tooltip } from '@blueprintjs/core'
import { motion } from 'motion/react'
import { AppModule } from '../../types'
import homeLogo from '../../assets/icons/home-logo.png'
import profileManagerIcon from '../../assets/icons/profile-manager.png'
import calibrationToolIcon from '../../assets/icons/calibration-tool.png'
import cadModelingIcon from '../../assets/icons/cad-modeling.png'
import anchorManagerIcon from '../../assets/icons/anchor-manager.png'
import rtlsDashboardIcon from '../../assets/icons/rtls-dashboard.png'
import './LeftRail.css'

interface ModuleItem {
  id: AppModule
  iconSrc: string
  label: string
}

const MODULE_ITEMS: ModuleItem[] = [
  { id: 'profile',     iconSrc: profileManagerIcon,  label: 'Profile Manager' },
  { id: 'calibration', iconSrc: calibrationToolIcon, label: 'Calibration Tool' },
  { id: 'cad',         iconSrc: cadModelingIcon,      label: '2D CAD Modeling' },
  { id: 'anchors',     iconSrc: anchorManagerIcon,    label: 'Anchor Manager' },
  { id: 'rtls',        iconSrc: rtlsDashboardIcon,    label: 'RTLS Dashboard' },
]

interface LeftRailProps {
  activeModule: AppModule | null
  onModuleChange: (module: AppModule) => void
  onHomeClick: () => void
  disabled?: boolean
}

const LeftRail: React.FC<LeftRailProps> = ({ activeModule, onModuleChange, onHomeClick, disabled = false }) => {
  return (
    <motion.aside
      className="left-rail"
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4, delay: 0.1, ease: [0.4, 0, 0.2, 1] }}
    >
      {/* ── App icon / home ── */}
      <Tooltip
        content={<span style={{ fontSize: 10, letterSpacing: '0.05em' }}>Home</span>}
        placement="right"
        minimal
        hoverOpenDelay={200}
      >
        <button className="left-rail__logo-btn" onClick={onHomeClick}>
          <img src={homeLogo} className="left-rail__icon-img left-rail__icon-img--home" alt="Home" />
        </button>
      </Tooltip>

      <div className="left-rail__divider" />

      {/* ── 5 Module Buttons ── */}
      <nav className="left-rail__nav">
        {MODULE_ITEMS.map((item) => {
          const isActive = activeModule === item.id
          return (
            <Tooltip
              key={item.id}
              content={
                <span style={{ fontSize: 10, letterSpacing: '0.05em' }}>{item.label}</span>
              }
              placement="right"
              minimal
              hoverOpenDelay={200}
            >
              <button
                className={`left-rail__btn ${isActive ? 'left-rail__btn--active' : ''}`}
                onClick={() => onModuleChange(item.id)}
                aria-label={item.label}
                disabled={disabled}
              >
                {isActive && (
                  <motion.div
                    className="left-rail__active-bg"
                    layoutId="left-rail-active"
                    transition={{ type: 'spring', stiffness: 350, damping: 28 }}
                  />
                )}
                <span className="left-rail__btn-icon">
                  <img
                    src={item.iconSrc}
                    className={`left-rail__icon-img${isActive ? ' left-rail__icon-img--active' : ''}`}
                    alt={item.label}
                  />
                </span>
              </button>
            </Tooltip>
          )
        })}
      </nav>

    </motion.aside>
  )
}

export default LeftRail
