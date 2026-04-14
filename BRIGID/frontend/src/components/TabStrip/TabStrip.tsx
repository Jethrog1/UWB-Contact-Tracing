import React, { useEffect, useRef, useState } from 'react'
import { Icon } from '@blueprintjs/core'
import { AnimatePresence, motion } from 'motion/react'
import { AppModule, WorkspaceTab } from '../../types'
import './TabStrip.css'

interface TabStripProps {
  tabs: WorkspaceTab[]
  activeTabId: string | null
  activeModule: AppModule | null
  onTabSelect: (id: string) => void
  onTabClose: (id: string) => void
  onTabReorder: (draggedId: string, targetId: string) => void
  onNewTab: () => void
  // View commands forwarded to the active CAD module via context/event
  onViewCommand?: (cmd: string) => void
}

const VIEW_CONTROLS: { cmd: string; icon: string; label: string; title: string }[] = [
  { cmd: 'undo',       icon: 'undo',        label: '',           title: 'Undo (Ctrl+Z)' },
  { cmd: 'redo',       icon: 'redo',        label: '',           title: 'Redo (Ctrl+Y)' },
  { cmd: 'zoom_in',   icon: 'zoom-in',     label: '',           title: 'Zoom In' },
  { cmd: 'zoom_out',  icon: 'zoom-out',    label: '',           title: 'Zoom Out' },
  { cmd: 'zoom_reset', icon: 'zoom-to-fit', label: 'Reset View', title: 'Reset View (0)' },
]

const TabStrip: React.FC<TabStripProps> = ({
  tabs,
  activeTabId,
  activeModule,
  onTabSelect,
  onTabClose,
  onTabReorder,
  onNewTab,
  onViewCommand,
}) => {
  const showViewControls = activeModule === 'cad' || activeModule === 'anchors'
  const [searchVisible, setSearchVisible] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  const filtered = searchQuery
    ? tabs.filter(tab => tab.name.toLowerCase().includes(searchQuery.toLowerCase()))
    : []

  useEffect(() => {
    if (searchVisible) searchRef.current?.focus()
  }, [searchVisible])

  const handleViewCmd = (cmd: string) => {
    if (onViewCommand) {
      onViewCommand(cmd)
      return
    }
    if (!activeTabId) return
    const eventName = activeModule === 'anchors' ? 'anchor-view-command' : 'cad-view-command'
    window.dispatchEvent(new CustomEvent(eventName, { detail: { cmd, workspaceId: activeTabId } }))
  }

  return (
    <div className="tab-strip electron-drag">
      {/* Tab list */}
      <div className="tab-strip__left electron-no-drag">
        <div className="tab-strip__tabs">
          <AnimatePresence initial={false}>
            {tabs.map(tab => (
              <motion.button
                key={tab.id}
                layout
                draggable
                className={[
                  'tab-strip__tab',
                  activeTabId === tab.id ? 'tab-strip__tab--active' : '',
                  draggingId === tab.id ? 'tab-strip__tab--dragging' : '',
                ].filter(Boolean).join(' ')}
                initial={{ opacity: 0, x: -12, scale: 0.96 }}
                animate={{ opacity: 1, x: 0, scale: 1 }}
                exit={{ opacity: 0, x: -8, scale: 0.96 }}
                transition={{ duration: 0.18 }}
                onClick={() => onTabSelect(tab.id)}
                onDragStartCapture={event => {
                  setDraggingId(tab.id)
                  event.dataTransfer.effectAllowed = 'move'
                  event.dataTransfer.setData('text/plain', tab.id)
                }}
                onDragOverCapture={event => {
                  event.preventDefault()
                  if (draggingId && draggingId !== tab.id) onTabReorder(draggingId, tab.id)
                }}
                onDragEndCapture={() => setDraggingId(null)}
                title={tab.name}
              >
                {activeTabId === tab.id && (
                  <motion.div
                    className="tab-strip__tab-active-bg"
                    layoutId="tab-active-bg"
                    transition={{ type: 'spring', stiffness: 500, damping: 42 }}
                  />
                )}
                <span className={`tab-strip__tab-dot ${tab.modified ? 'tab-strip__tab-dot--modified' : ''}`} />
                <span className="tab-strip__tab-name">{tab.name}</span>
                <button
                  className="tab-strip__tab-close"
                  onClick={event => {
                    event.stopPropagation()
                    onTabClose(tab.id)
                  }}
                  title="Close tab"
                >
                  <Icon icon="cross" size={9} />
                </button>
              </motion.button>
            ))}
          </AnimatePresence>
        </div>

        <button className="tab-strip__new-tab" onClick={onNewTab} title="New workspace">
          <Icon icon="plus" size={11} />
        </button>
      </div>

      <div className="tab-strip__spacer" />

      {/* View control cluster — only shown for CAD workspaces */}
      {showViewControls && (
        <div className="tab-strip__view-controls electron-no-drag">
          {VIEW_CONTROLS.map(vc => (
            <button
              key={vc.cmd}
              className="tab-strip__view-btn"
              title={vc.title}
              onClick={() => handleViewCmd(vc.cmd)}
              disabled={!activeTabId}
            >
              <Icon icon={vc.icon as any} size={11} />
              {vc.label && <span className="tab-strip__view-label">{vc.label}</span>}
            </button>
          ))}
          <div className="tab-strip__view-sep" />
        </div>
      )}

      {/* Search */}
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
              onBlur={() => {
                setSearchVisible(false)
                setSearchQuery('')
              }}
              onKeyDown={e => e.key === 'Escape' && searchRef.current?.blur()}
            />
            {searchQuery && filtered.length > 0 && (
              <div className="tab-strip__search-results">
                {filtered.map(tab => (
                  <button
                    key={tab.id}
                    className="tab-strip__search-result"
                    onMouseDown={() => {
                      onTabSelect(tab.id)
                      setSearchVisible(false)
                      setSearchQuery('')
                    }}
                  >
                    <Icon icon="document" size={10} />
                    <span>{tab.name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <button className="tab-strip__search-btn" onClick={() => setSearchVisible(true)} title="Search tabs">
            <Icon icon="search" size={11} />
          </button>
        )}
      </div>
    </div>
  )
}

export default TabStrip
