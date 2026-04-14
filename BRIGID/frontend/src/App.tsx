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
import RTLSDashboard from './components/modules/RTLSDashboardModule/RTLSDashboard'
import { AppModule, WorkspaceTab } from './types'
import './App.css'

FocusStyleManager.onlyShowFocusOnTabs()

const API = 'http://localhost:8765'

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
          <CADModule workspaceId={workspace.id} workspaceName={workspace.name} />
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
          <CalibrationTool workspaceId={workspace.id} workspaceName={workspace.name} />
        </div>
      )}

      {shouldMountModule('rtls') && (
        <div className={`app-workspace-module${showModule('rtls') ? ' app-workspace-module--visible' : ''}`}>
          <RTLSDashboard workspaceId={workspace.id} workspaceName={workspace.name} />
        </div>
      )}
    </div>
  )
}

// ── Workspace folder helpers ───────────────────────────────────────────────────

async function registerWorkspaceFolder(workspaceId: string, workspaceName: string): Promise<void> {
  try {
    await fetch(`${API}/api/workspace/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_id: workspaceId, workspace_name: workspaceName }),
    })
  } catch {
    // Server may not be running yet on first open
  }
}

async function renameWorkspaceFolder(workspaceId: string, oldName: string, newName: string): Promise<void> {
  try {
    await fetch(`${API}/api/workspace/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_id: workspaceId, old_name: oldName, new_name: newName }),
    })
  } catch {
    // ignore
  }
}

async function deleteWorkspaceFolderIfEmpty(workspaceId: string, workspaceName: string): Promise<void> {
  try {
    await fetch(`${API}/api/workspace/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_id: workspaceId, workspace_name: workspaceName }),
    })
  } catch {
    // ignore
  }
}

async function fetchExistingWorkspaces(): Promise<string[]> {
  try {
    const res = await fetch(`${API}/api/workspace/list`)
    if (!res.ok) return []
    const data = await res.json()
    return data.workspaces ?? []
  } catch {
    return []
  }
}

// ── Main App ──────────────────────────────────────────────────────────────────

const App: React.FC = () => {
  const nextTabNumRef = useRef(1)
  const [tabs, setTabs] = useState<WorkspaceTab[]>([])
  const [activeTabId, setActiveTabId] = useState<string | null>(null)
  // Track per-tab workspace name for renaming (keeps names stable)
  const tabNamesRef = useRef<Record<string, string>>({})

  const activeTab = useMemo(
    () => tabs.find(tab => tab.id === activeTabId) ?? null,
    [activeTabId, tabs],
  )

  // On first load: discover existing workspace folders and seed nextTabNum
  useEffect(() => {
    fetchExistingWorkspaces().then(existing => {
      if (existing.length === 0) return
      // Determine the highest existing Workspace N number
      let max = 0
      for (const name of existing) {
        const m = name.match(/^Workspace\s+(\d+)$/i)
        if (m) max = Math.max(max, parseInt(m[1], 10))
      }
      if (max >= nextTabNumRef.current) {
        nextTabNumRef.current = max + 1
      }
    })
  }, [])

  const handleNewTab = useCallback(() => {
    const num = nextTabNumRef.current++
    const id = `ws-${num}`
    const name = `Workspace ${num}`
    const newTab: WorkspaceTab = { id, name, module: 'profile', modified: false }
    tabNamesRef.current[id] = name
    setTabs(prev => [...prev, newTab])
    setActiveTabId(id)
    registerWorkspaceFolder(id, name)
  }, [])

  const handleTabClose = useCallback((id: string) => {
    setTabs(prev => {
      const index = prev.findIndex(tab => tab.id === id)
      const remaining = prev.filter(tab => tab.id !== id)
      if (activeTabId === id) {
        const fallback = remaining[index] ?? remaining[index - 1] ?? null
        setActiveTabId(fallback?.id ?? null)
      }
      const name = tabNamesRef.current[id] ?? `Workspace ${id}`
      deleteWorkspaceFolderIfEmpty(id, name)
      delete tabNamesRef.current[id]
      return remaining
    })
  }, [activeTabId])

  const handleTabRename = useCallback((id: string, newName: string) => {
    const oldName = tabNamesRef.current[id] ?? ''
    tabNamesRef.current[id] = newName
    setTabs(prev => prev.map(tab => tab.id === id ? { ...tab, name: newName } : tab))
    if (oldName && oldName !== newName) {
      renameWorkspaceFolder(id, oldName, newName)
    }
  }, [])

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

  const activeModule = activeTab?.module ?? null

  const handleModuleChange = useCallback((module: AppModule) => {
    if (!activeTabId) return
    setTabs(prev => prev.map(tab => (tab.id === activeTabId ? { ...tab, module } : tab)))
  }, [activeTabId])

  const handleRefresh = useCallback(() => {
    if (!activeTabId || !activeModule) return
    const eventMap: Partial<Record<AppModule, string>> = {
      calibration: 'calibration-view-command',
      rtls: 'rtls-view-command',
    }
    const eventName = eventMap[activeModule]
    if (eventName) {
      window.dispatchEvent(new CustomEvent(eventName, { detail: { cmd: 'refresh', workspaceId: activeTabId } }))
    }
  }, [activeTabId, activeModule])

  const handleOpenFolder = useCallback(async () => {
    if (!activeTabId || !activeTab) return
    try {
      const wsName = encodeURIComponent(activeTab.name)
      const res = await fetch(`${API}/api/workspace/paths/${encodeURIComponent(activeTabId)}?workspace_name=${wsName}`)
      if (!res.ok) return
      const data = await res.json() as { tags?: string; rooms?: string; svg?: string; pdf?: string }
      const folderPath = activeModule === 'anchors' || activeModule === 'cad'
        ? data.svg
        : data.tags
      if (folderPath) await window.api?.openPath?.(folderPath)
    } catch { /* ignore */ }
  }, [activeTabId, activeTab, activeModule])

  const canCloseTab = tabs.length > 0 && activeTabId !== null

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
          onTabRename={handleTabRename}
          onNewTab={handleNewTab}
          onRefresh={handleRefresh}
          onOpenFolder={handleOpenFolder}
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
