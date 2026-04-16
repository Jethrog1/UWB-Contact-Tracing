import React, { useState } from 'react'
import { Icon } from '@blueprintjs/core'
import { motion } from 'motion/react'
import './TopBar.css'

export type AppModule = 'rtls' | 'cad' | 'anchors' | 'profiling'

interface TopBarProps {
  activeModule: AppModule
  onModuleChange: (module: AppModule) => void
}

const modules: { id: AppModule; label: string }[] = [
  { id: 'rtls', label: 'RTLS Dashboard' },
  { id: 'cad', label: 'CAD Modeling' },
  { id: 'anchors', label: 'Anchor Placement' },
  { id: 'profiling', label: 'Profiling' }
]

const TopBar: React.FC<TopBarProps> = ({ activeModule, onModuleChange }) => {
  return (
    <motion.header
      className="topbar"
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
    >
      {/* ---- Left: App Brand + Search ---- */}
      <div className="topbar__left electron-no-drag">
        <div className="topbar__brand-mark">
          <span className="topbar__brand-name">BRIGID</span>
        </div>
        <div className="topbar__search">
          <Icon icon="search" size={13} className="topbar__search-icon" />
          <span className="topbar__search-text">Search workspace...</span>
          <kbd className="topbar__search-kbd">Ctrl+K</kbd>
        </div>
      </div>

      {/* ---- Center: Module Tabs ---- */}
      <nav className="topbar__center electron-no-drag">
        {modules.map((mod) => (
          <button
            key={mod.id}
            className={`topbar__tab ${activeModule === mod.id ? 'topbar__tab--active' : ''}`}
            onClick={() => onModuleChange(mod.id)}
          >
            {activeModule === mod.id && (
              <motion.div
                className="topbar__tab-indicator"
                layoutId="topbar-tab-indicator"
                transition={{ type: 'spring', stiffness: 400, damping: 35 }}
              />
            )}
            <span className="topbar__tab-label">{mod.label}</span>
          </button>
        ))}
      </nav>

      {/* ---- Right: Workspace Info + Actions ---- */}
      <div className="topbar__right electron-no-drag">
        <div className="topbar__save-indicator">
          <Icon icon="tick-circle" size={12} className="topbar__save-icon" />
          <span>Saved</span>
        </div>
        <div className="topbar__separator" />
        <div className="topbar__workspace">
          <Icon icon="projects" size={13} />
          <span>Default Workspace</span>
          <Icon icon="chevron-down" size={12} />
        </div>
        <div className="topbar__separator" />
        <div className="topbar__actions">
          <button className="topbar__icon-btn" title="Connections">
            <Icon icon="feed" size={14} />
          </button>
          <button className="topbar__icon-btn topbar__icon-btn--circle" title="System Status">
            <Icon icon="pulse" size={14} />
          </button>
          <button className="topbar__icon-btn topbar__icon-btn--circle" title="Settings">
            <Icon icon="cog" size={14} />
          </button>
        </div>
      </div>
    </motion.header>
  )
}

export default TopBar
