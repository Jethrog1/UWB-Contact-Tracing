import React, { useState } from 'react'
import { Icon, IconName, Tooltip } from '@blueprintjs/core'
import { motion } from 'motion/react'
import './LeftRail.css'

interface NavItem {
  id: string
  icon: IconName
  label: string
}

const navItems: NavItem[] = [
  { id: 'dashboard', icon: 'dashboard', label: 'Dashboard Overview' },
  { id: 'floorplan', icon: 'map', label: 'Floor Plan View' },
  { id: 'anchors', icon: 'cell-tower', label: 'Anchor Manager' },
  { id: 'tags', icon: 'locate', label: 'Tag Tracker' },
  { id: 'calibration', icon: 'regression-chart', label: 'Calibration Tools' },
  { id: 'serial', icon: 'feed', label: 'Serial Monitor' },
  { id: 'profiles', icon: 'people', label: 'Profile Manager' },
  { id: 'layers', icon: 'layers', label: 'Layers & Overlays' },
]

const bottomItems: NavItem[] = [
  { id: 'docs', icon: 'manual', label: 'Documentation' },
  { id: 'settings', icon: 'cog', label: 'Settings' },
]

const LeftRail: React.FC = () => {
  const [activeItem, setActiveItem] = useState('dashboard')

  return (
    <motion.aside
      className="left-rail"
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4, delay: 0.1, ease: [0.4, 0, 0.2, 1] }}
    >
      {/* ---- Navigation ---- */}
      <nav className="left-rail__nav">
        {navItems.map((item) => (
          <Tooltip
            key={item.id}
            content={item.label}
            placement="right"
            minimal
            hoverOpenDelay={300}
          >
            <button
              className={`left-rail__btn ${activeItem === item.id ? 'left-rail__btn--active' : ''}`}
              onClick={() => setActiveItem(item.id)}
              aria-label={item.label}
            >
              {activeItem === item.id && (
                <motion.div
                  className="left-rail__active-bar"
                  layoutId="left-rail-active"
                  transition={{ type: 'spring', stiffness: 350, damping: 30 }}
                />
              )}
              <Icon icon={item.icon} size={16} />
            </button>
          </Tooltip>
        ))}
      </nav>

      {/* ---- Bottom Actions ---- */}
      <div className="left-rail__bottom">
        {bottomItems.map((item) => (
          <Tooltip
            key={item.id}
            content={item.label}
            placement="right"
            minimal
            hoverOpenDelay={300}
          >
            <button
              className={`left-rail__btn ${activeItem === item.id ? 'left-rail__btn--active' : ''}`}
              onClick={() => setActiveItem(item.id)}
              aria-label={item.label}
            >
              <Icon icon={item.icon} size={16} />
            </button>
          </Tooltip>
        ))}
      </div>
    </motion.aside>
  )
}

export default LeftRail
