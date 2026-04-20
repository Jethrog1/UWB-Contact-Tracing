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
  onTabRename?: (id: string, newName: string) => void
  onRefresh?: () => void
  onOpenFolder?: () => void
  // View commands forwarded to the active CAD module via context/event
  onViewCommand?: (cmd: string) => void
}

const VIEW_CONTROLS: { cmd: string; icon: string; label: string; title: string; hideIcon?: boolean }[] = [
  { cmd: 'undo',       icon: 'undo',        label: '',           title: 'Undo (Ctrl+Z)' },
  { cmd: 'redo',       icon: 'redo',        label: '',           title: 'Redo (Ctrl+Y)' },
  { cmd: 'zoom_in',   icon: 'zoom-in',     label: '',           title: 'Zoom In' },
  { cmd: 'zoom_out',  icon: 'zoom-out',    label: '',           title: 'Zoom Out' },
  { cmd: 'zoom_reset', icon: 'zoom-to-fit', label: 'Reset View', title: 'Reset View (0)', hideIcon: true },
]

const TabStrip: React.FC<TabStripProps> = ({
  tabs,
  activeTabId,
  activeModule,
  onTabSelect,
  onTabClose,
  onTabReorder,
  onNewTab,
  onTabRename,
  onRefresh,
  onOpenFolder,
  onViewCommand,
}) => {
  // Show view controls for all canvas-based modules; undo/redo only where supported
  const showViewControls = activeModule === 'cad' || activeModule === 'calibration' || activeModule === 'rtls' || activeModule === 'anchors'
  const showUndoRedo = activeModule === 'cad' || activeModule === 'anchors'
  const showWorkspaceActions = activeModule === 'rtls'
  const [searchVisible, setSearchVisible] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const renameRef = useRef<HTMLInputElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (renamingId) renameRef.current?.focus()
  }, [renamingId])

  const startRename = (tab: WorkspaceTab) => {
    setRenamingId(tab.id)
    setRenameValue(tab.name)
  }

  const commitRename = () => {
    if (renamingId && renameValue.trim() && onTabRename) {
      onTabRename(renamingId, renameValue.trim())
    }
    setRenamingId(null)
    setRenameValue('')
  }

  const cancelRename = () => {
    setRenamingId(null)
    setRenameValue('')
  }

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
    const eventName = activeModule === 'anchors'
      ? 'anchor-view-command'
      : activeModule === 'calibration'
        ? 'calibration-view-command'
        : activeModule === 'rtls'
          ? 'rtls-view-command'
          : 'cad-view-command'
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
                {renamingId === tab.id ? (
                  <input
                    ref={renameRef}
                    className="tab-strip__tab-rename-input"
                    value={renameValue}
                    onChange={e => setRenameValue(e.target.value)}
                    onBlur={commitRename}
                    onKeyDown={e => {
                      if (e.key === 'Enter') commitRename()
                      if (e.key === 'Escape') cancelRename()
                    }}
                    onClick={e => e.stopPropagation()}
                  />
                ) : (
                  <span
                    className="tab-strip__tab-name"
                    onDoubleClick={e => { e.stopPropagation(); startRename(tab) }}
                    title="Double-click to rename"
                  >
                    {tab.name}
                  </span>
                )}
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
          {showWorkspaceActions && (
            <>
              <button
                className="tab-strip__view-btn"
                title="Refresh"
                onClick={onRefresh}
                disabled={!activeTabId}
              >
                <Icon icon="refresh" size={11} />
              </button>
              <button
                className="tab-strip__view-btn"
                title="Open Tags Folder"
                onClick={onOpenFolder}
                disabled={!activeTabId}
              >
                <Icon icon="folder-open" size={11} />
              </button>
              <div className="tab-strip__view-sep" />
            </>
          )}
          {VIEW_CONTROLS.map(vc => {
            if ((vc.cmd === 'undo' || vc.cmd === 'redo') && !showUndoRedo) return null
            return (
              <button
                key={vc.cmd}
                className="tab-strip__view-btn"
                title={vc.title}
                onClick={() => handleViewCmd(vc.cmd)}
                disabled={!activeTabId}
              >
                {!vc.hideIcon && <Icon icon={vc.icon as any} size={11} />}
                {vc.label && <span className="tab-strip__view-label">{vc.label}</span>}
              </button>
            )
          })}
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
