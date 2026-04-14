import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FocusStyleManager } from '@blueprintjs/core'
import { motion } from 'motion/react'

import HotBar from './components/HotBar/HotBar'
import LeftRail from './components/LeftRail/LeftRail'
import TabStrip from './components/TabStrip/TabStrip'
import CADModule from './components/modules/CADModule/CADModule'
import TagProfiler from './components/modules/TagProfilerModule/TagProfiler'
import AnchorManager from './components/modules/AnchorManagerModule/AnchorManager'
import CalibrationTool from './components/modules/CalibrationToolModule/CalibrationTool'
import { AppModule, WorkspaceTab } from './types'
import './App.css'

FocusStyleManager.onlyShowFocusOnTabs()

const MODULE_LABELS: Record<AppModule, { title: string; sub: string; icon: string }> = {
  profile: { title: 'Profile Manager', sub: 'Workspace defaults land here so CAD is entered intentionally.', icon: 'P' },
  calibration: { title: 'Calibration Tool', sub: 'Tag distance correction and fitting.', icon: 'C' },
  cad: { title: '2D CAD Modeling', sub: 'Restored Python CAD backend inside the new shell.', icon: 'Q' },
  anchors: { title: 'Anchor Manager', sub: 'UWB anchor configuration and layout.', icon: 'A' },
  rtls: { title: 'RTLS Dashboard', sub: 'Real-time location tracking monitor.', icon: 'R' },
}

const EmptyWorkspacePanel: React.FC = () => (
  <div className="app-empty-state">
    <div className="app-empty-icon">+</div>
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

const WorkspaceHost: React.FC<{
  workspace: WorkspaceTab
  isActive: boolean
}> = ({ workspace, isActive }) => {
  const [mountedModules, setMountedModules] = useState<Set<AppModule>>(() => new Set([workspace.module]))

  useEffect(() => {
    setMountedModules(current => {
      if (current.has(workspace.module)) return current
      return new Set([...current, workspace.module])
    })
  }, [workspace.module])

  const showModule = (module: AppModule) => workspace.module === module
  const shouldMountModule = (module: AppModule) => mountedModules.has(module)

  return (
    <div className={`app-workspace-host${isActive ? ' app-workspace-host--active' : ''}`}>
      {shouldMountModule('cad') && (
        <div className={`app-workspace-module${showModule('cad') ? ' app-workspace-module--visible' : ''}`}>
          <CADModule workspaceId={workspace.id} />
        </div>
      )}

      {shouldMountModule('profile') && (
        <div className={`app-workspace-module${showModule('profile') ? ' app-workspace-module--visible' : ''}`}>
          <TagProfiler workspaceId={workspace.id} />
        </div>
      )}

      {shouldMountModule('anchors') && (
        <div className={`app-workspace-module${showModule('anchors') ? ' app-workspace-module--visible' : ''}`}>
          <AnchorManager workspaceId={workspace.id} />
        </div>
      )}

      {shouldMountModule('calibration') && (
        <div className={`app-workspace-module${showModule('calibration') ? ' app-workspace-module--visible' : ''}`}>
          <CalibrationTool workspaceId={workspace.id} />
        </div>
      )}

      {shouldMountModule('rtls') && (
        <div className={`app-workspace-module${showModule('rtls') ? ' app-workspace-module--visible' : ''}`}>
          <EmptyModulePanel module="rtls" />
        </div>
      )}
    </div>
  )
}

const App: React.FC = () => {
  const nextTabIdRef = useRef(1)
  const [tabs, setTabs] = useState<WorkspaceTab[]>([])
  const [activeTabId, setActiveTabId] = useState<string | null>(null)

  const activeTab = useMemo(
    () => tabs.find(tab => tab.id === activeTabId) ?? null,
    [activeTabId, tabs],
  )

  const handleNewTab = useCallback(() => {
    const id = `ws-${nextTabIdRef.current++}`
    const newTab: WorkspaceTab = {
      id,
      name: `Workspace ${nextTabIdRef.current - 1}`,
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
          activeModule={activeModule}
          onTabSelect={setActiveTabId}
          onTabClose={handleTabClose}
          onTabReorder={handleTabReorder}
          onNewTab={handleNewTab}
        />

        <LeftRail activeModule={activeModule} onModuleChange={handleModuleChange} disabled={!activeTab} />

        {tabs.map(tab => (
          <WorkspaceHost key={tab.id} workspace={tab} isActive={tab.id === activeTabId} />
        ))}

        {!activeTab && <EmptyWorkspacePanel />}
      </motion.div>
    </div>
  )
}

export default App
