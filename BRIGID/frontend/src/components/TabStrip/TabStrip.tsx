import React, { useState, useRef, useEffect } from 'react'
import { Icon } from '@blueprintjs/core'
import { motion, AnimatePresence } from 'motion/react'
import './TabStrip.css'

export interface WorkspaceTab {
  id: string
  name: string
  modified: boolean
}

interface TabStripProps {
  tabs: WorkspaceTab[]
  activeTabId: string
  onTabSelect: (id: string) => void
  onTabClose: (id: string) => void
  onNewTab: () => void
}

const TabStrip: React.FC<TabStripProps> = ({
  tabs,
  activeTabId,
  onTabSelect,
  onTabClose,
  onNewTab,
}) => {
  const [searchVisible, setSearchVisible] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)

  const filtered = searchQuery
    ? tabs.filter(t => t.name.toLowerCase().includes(searchQuery.toLowerCase()))
    : []

  useEffect(() => {
    if (searchVisible) searchRef.current?.focus()
  }, [searchVisible])

  return (
    <div className="tab-strip electron-drag">
      {/* ── Tabs ─────────────────────────────────────────── */}
      <div className="tab-strip__tabs electron-no-drag">
        <AnimatePresence initial={false}>
          {tabs.map(tab => (
            <motion.button
              key={tab.id}
              className={`tab-strip__tab ${activeTabId === tab.id ? 'tab-strip__tab--active' : ''}`}
              initial={{ opacity: 0, x: -12, width: 0 }}
              animate={{ opacity: 1, x: 0, width: 'auto' }}
              exit={{ opacity: 0, x: -8, width: 0 }}
              transition={{ duration: 0.18 }}
              onClick={() => onTabSelect(tab.id)}
              title={tab.name}
            >
              {activeTabId === tab.id && (
                <motion.div
                  className="tab-strip__tab-active-bg"
                  layoutId="tab-active-bg"
                  transition={{ type: 'spring', stiffness: 500, damping: 40 }}
                />
              )}
              <span className={`tab-strip__tab-dot ${tab.modified ? 'tab-strip__tab-dot--modified' : ''}`} />
              <span className="tab-strip__tab-name">{tab.name}</span>
              <button
                className="tab-strip__tab-close"
                onClick={(e) => { e.stopPropagation(); onTabClose(tab.id) }}
                title="Close tab"
              >
                <Icon icon="cross" size={10} />
              </button>
            </motion.button>
          ))}
        </AnimatePresence>

        {/* New tab button */}
        <button className="tab-strip__new-tab electron-no-drag" onClick={onNewTab} title="New workspace">
          <Icon icon="plus" size={12} />
        </button>
      </div>

      {/* ── Spacer ─────────────────────────────────────── */}
      <div className="tab-strip__spacer" />

      {/* ── Tab Search ─────────────────────────────────── */}
      <div className="tab-strip__search electron-no-drag">
        {searchVisible ? (
          <div className="tab-strip__search-input-wrap">
            <Icon icon="search" size={11} className="tab-strip__search-icon" />
            <input
              ref={searchRef}
              className="tab-strip__search-input"
              placeholder="Search tabs..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onBlur={() => { setSearchVisible(false); setSearchQuery('') }}
              onKeyDown={e => e.key === 'Escape' && searchRef.current?.blur()}
            />
            {/* Search results dropdown */}
            {searchQuery && filtered.length > 0 && (
              <div className="tab-strip__search-results">
                {filtered.map(tab => (
                  <button
                    key={tab.id}
                    className="tab-strip__search-result"
                    onMouseDown={() => { onTabSelect(tab.id); setSearchVisible(false); setSearchQuery('') }}
                  >
                    <Icon icon="document" size={11} />
                    <span>{tab.name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <button
            className="tab-strip__search-btn"
            onClick={() => setSearchVisible(true)}
            title="Search tabs"
          >
            <Icon icon="search" size={12} />
          </button>
        )}
      </div>
    </div>
  )
}

export default TabStrip
