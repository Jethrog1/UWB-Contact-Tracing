import React, { useCallback, useMemo, useState } from 'react'
import { FocusStyleManager } from '@blueprintjs/core'
import { motion } from 'motion/react'

import HotBar from './components/HotBar/HotBar'
import LeftRail from './components/LeftRail/LeftRail'
import TabStrip from './components/TabStrip/TabStrip'
import CADModule from './components/modules/CADModule/CADModule'
import { AppModule, WorkspaceTab } from './types'
import './App.css'

FocusStyleManager.onlyShowFocusOnTabs()

let nextTabId = 1

const MODULE_LABELS: Record<AppModule, { title: string; sub: string; icon: string }> = {
  profile: { title: 'Profile Manager', sub: 'Workspace defaults land here so CAD is entered intentionally.', icon: '◎' },
  calibration: { title: 'Calibration Tool', sub: 'Tag distance correction and fitting.', icon: '◇' },
  cad: { title: '2D CAD Modeling', sub: 'Restored Python CAD backend inside the new shell.', icon: '□' },
  anchors: { title: 'Anchor Manager', sub: 'UWB anchor configuration and layout.', icon: '⊕' },
  rtls: { title: 'RTLS Dashboard', sub: 'Real-time location tracking monitor.', icon: '⊗' },
}

const EmptyWorkspacePanel: React.FC = () => (
  <div className="app-empty-state">
    <div className="app-empty-icon">＋</div>
    <div className="app-empty-title">No Workspace Open</div>
    <div className="app-empty-sub">Start from File / New Workspace or use the + button in the tab strip.</div>
  </div>
)

const EmptyModulePanel: React.FC<{ module: AppModule }> = ({ module }) => {
  const info = MODULE_LABELS[module]
  return (
    <div className="app-module-placeholder">
      <div className="app-module-icon">{info.icon}</div>
      <div className="app-module-title">{info.title}</div>
      <div className="app-module-sub">{info.sub}</div>
      {module !== 'cad' && <div className="app-module-pill">Module shell ready</div>}
    </div>
  )
}

// StubRightPanel removed — right panel is now floating inside canvas area for all views

const App: React.FC = () => {
  const [tabs, setTabs] = useState<WorkspaceTab[]>([])
  const [activeTabId, setActiveTabId] = useState<string | null>(null)

  const activeTab = useMemo(
    () => tabs.find(tab => tab.id === activeTabId) ?? null,
    [activeTabId, tabs],
  )

  const handleNewTab = useCallback(() => {
    const id = `ws-${nextTabId++}`
    const newTab: WorkspaceTab = {
      id,
      name: `Workspace ${nextTabId - 1}`,
      module: 'profile',
      modified: false,
    }
    setTabs(prev => [...prev, newTab])
    setActiveTabId(id)
  }, [])

  const handleTabClose = useCallback((id: string) => {
    setTabs(prev => {
      const index = prev.findIndex(tab => tab.id === id)
      const remaining = prev.filter(tab => tab.id !== id)
      if (activeTabId === id) {
        const fallback = remaining[index] ?? remaining[index - 1] ?? null
        setActiveTabId(fallback?.id ?? null)
      }
      return remaining
    })
  }, [activeTabId])

  const handleTabReorder = useCallback((draggedId: string, targetId: string) => {
    setTabs(prev => {
      const from = prev.findIndex(tab => tab.id === draggedId)
      const to = prev.findIndex(tab => tab.id === targetId)
      if (from === -1 || to === -1 || from === to) return prev
      const next = [...prev]
      const [moved] = next.splice(from, 1)
      next.splice(to, 0, moved)
      return next
    })
  }, [])

  const handleModuleChange = useCallback((module: AppModule) => {
    if (!activeTabId) return
    setTabs(prev => prev.map(tab => (tab.id === activeTabId ? { ...tab, module } : tab)))
  }, [activeTabId])

  const canCloseTab = tabs.length > 0 && activeTabId !== null
  const activeModule = activeTab?.module ?? null

  // CAD tabs that have ever been active — keep mounted to preserve WS state
  const cadTabs = useMemo(() => tabs.filter(t => t.module === 'cad'), [tabs])

  return (
    <div className="bp5-dark app-root">
      <motion.div className="app-shell" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.35 }}>
        <HotBar
          canCloseTab={canCloseTab}
          onNewWorkspace={handleNewTab}
          onCloseTab={() => activeTabId && handleTabClose(activeTabId)}
        />

        <TabStrip
          tabs={tabs}
          activeTabId={activeTabId}
          onTabSelect={setActiveTabId}
          onTabClose={handleTabClose}
          onTabReorder={handleTabReorder}
          onNewTab={handleNewTab}
        />

        <LeftRail activeModule={activeModule} onModuleChange={handleModuleChange} disabled={!activeTab} />

        {/* Keep ALL CAD modules mounted so WS connections and engine state persist.
            Hide inactive ones with display:none — canvas skips rendering but stays connected. */}
        {cadTabs.map(tab => (
          <div
            key={tab.id}
            style={{ display: tab.id === activeTabId ? 'contents' : 'none' }}
          >
            <CADModule workspaceId={tab.id} />
          </div>
        ))}

        {/* Non-CAD views */}
        {!activeTab && <EmptyWorkspacePanel />}
        {activeTab && activeTab.module !== 'cad' && (
          <EmptyModulePanel module={activeTab.module} />
        )}
      </motion.div>
    </div>
  )
}

export default App
