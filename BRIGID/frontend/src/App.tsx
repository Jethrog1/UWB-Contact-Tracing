import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import logo4 from './assets/icons/logo4.png'
import { FocusStyleManager, Spinner } from '@blueprintjs/core'
import { motion, AnimatePresence } from 'motion/react'

import HotBar from './components/HotBar/HotBar'
import LeftRail from './components/LeftRail/LeftRail'
import TabStrip from './components/TabStrip/TabStrip'
import CADModule from './components/modules/CADModule/CADModule'
import TagProfiler from './components/modules/TagProfilerModule/TagProfiler'
import AnchorManager from './components/modules/AnchorManagerModule/AnchorManager'
import CalibrationTool from './components/modules/CalibrationToolModule/CalibrationTool'
import RTLSDashboard from './components/modules/RTLSDashboardModule/RTLSDashboard'
import { ConfirmHost, confirmAsync } from './components/common/ConfirmDialog'
import { AppModule, WorkspaceTab } from './types'
import './App.css'

FocusStyleManager.onlyShowFocusOnTabs()

const API = 'http://localhost:8765'

interface WorkspaceInfo {
  name: string
  modified: number
}

const EmptyWorkspacePanel: React.FC<{
  workspaces: WorkspaceInfo[]
  onOpen: (name: string) => void
  onNew: () => void
}> = ({ workspaces, onOpen, onNew }) => (
  <div className="app-empty-state">
    <div className="home-content">
      <img src={logo4} className="app-empty-logo" alt="BRIGID" />
      <div className="app-empty-title">Welcome to BRIGID</div>
      <div className="app-empty-acro">
        <span><strong>B</strong>ehavioral</span>{' '}
        <span><strong>R</strong>eal-time</span>{' '}
        <span><strong>I</strong>nteraction</span>{' '}
        <span><strong>G</strong>raphing</span>{' '}
        <span>for</span>{' '}
        <span><strong>I</strong>nfectious</span>{' '}
        <span><strong>D</strong>iseases</span>
      </div>

      <div className="workspace-explorer">
        <div className="workspace-explorer-header">
          <span>Recent Workspaces</span>
          <button className="workspace-create-btn" onClick={onNew}>
            Create New
          </button>
        </div>
      {workspaces.length > 0 ? (
        <div className="workspace-explorer-list">
          {workspaces.map(ws => (
            <button
              key={ws.name}
              className="workspace-explorer-item"
              onClick={() => onOpen(ws.name)}
            >
              <div className="workspace-item-name">{ws.name}</div>
              {ws.modified > 0 && (
                <div className="workspace-item-date">
                  {new Date(ws.modified * 1000).toLocaleString('en-US', {
                    minute: '2-digit',
                    hour: '2-digit',
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric'
                  })}
                </div>
              )}
            </button>
          ))}
        </div>
      ) : (
        <div className="workspace-explorer-empty">No recent workspaces</div>
      )}
      </div>
    </div>
  </div>
)

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
          <AnchorManager workspaceId={workspace.id} workspaceName={workspace.name} />
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

async function registerWorkspaceFolder(workspaceId: string, workspaceName: string): Promise<void> {
  try {
    await fetch(`${API}/api/workspace/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_id: workspaceId, workspace_name: workspaceName }),
    })
  } catch {
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
  }
}

async function fetchExistingWorkspaces(): Promise<WorkspaceInfo[]> {
  try {
    const res = await fetch(`${API}/api/workspace/list`)
    if (!res.ok) return []
    const data = await res.json()
    return data.workspaces ?? []
  } catch {
    return []
  }
}

const App: React.FC = () => {
  const nextTabNumRef = useRef(1)
  const [tabs, setTabs] = useState<WorkspaceTab[]>([])

  const [activeTabId, setActiveTabId] = useState<string | null>(null)
  const [isHome, setIsHome] = useState<boolean>(true)

  const [existingWorkspaces, setExistingWorkspaces] = useState<WorkspaceInfo[]>([])
  const [isLoading, setIsLoading] = useState(true)

  const [bleIdleEnabled, setBleIdleEnabled] = useState(false)
  const [bleIdleAvailable, setBleIdleAvailable] = useState(true)
  const [bleIdleTags, setBleIdleTags] = useState<Array<{ tag_id: string; mac_address: string; status: string }>>([])
  const [bleIdleDetail, setBleIdleDetail] = useState<string>('')

  const tabNamesRef = useRef<Record<string, string>>({})

  const activeTab = useMemo(
    () => tabs.find(tab => tab.id === activeTabId) ?? null,
    [activeTabId, tabs],
  )

  useEffect(() => {
    fetchExistingWorkspaces().then(existing => {
      setExistingWorkspaces(existing)
      if (existing.length > 0) {
        let max = 0
        for (const item of existing) {
          const m = item.name.match(/^Workspace\s+(\d+)$/i)
          if (m) max = Math.max(max, parseInt(m[1], 10))
        }
        if (max >= nextTabNumRef.current) {
          nextTabNumRef.current = max + 1
        }
      }
    }).finally(() => {
      setTimeout(() => setIsLoading(false), 900)
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
    setIsHome(false)
    registerWorkspaceFolder(id, name)
  }, [])

  const handleOpenWorkspace = useCallback((wsName: string) => {
    const existingObj = Object.entries(tabNamesRef.current).find(([, name]) => name === wsName)
    if (existingObj) {
      setActiveTabId(existingObj[0])
      setIsHome(false)
      return
    }

    const num = nextTabNumRef.current++
    const id = `ws-${num}`
    const newTab: WorkspaceTab = { id, name: wsName, module: 'profile', modified: false }
    tabNamesRef.current[id] = wsName
    setTabs(prev => [...prev, newTab])
    setActiveTabId(id)
    setIsHome(false)
    registerWorkspaceFolder(id, wsName)
  }, [])

  const handleOpenWorkspaceDialog = useCallback(async () => {
    if (window.api?.getPaths && window.api.openPath) {
      try {
        const paths = await window.api.getPaths()
        if (paths?.profile) {
          await window.api.openPath(paths.profile)
          return
        }
      } catch {
      }
    }
    if (window.api?.openFolder) {
      const { canceled, folderPath } = await window.api.openFolder()
      if (!canceled && folderPath) {
        const folderName = folderPath.split(/[/\\]/).pop() || 'Imported Workspace'
        handleOpenWorkspace(folderName)
      }
    } else {
      alert("Open Workspace requires the desktop app environment.")
    }
  }, [handleOpenWorkspace])

  const handleSave = useCallback(() => {
    if (!activeTabId) return
    const tab = tabs.find(t => t.id === activeTabId)
    window.dispatchEvent(new CustomEvent('workspace-save-command', {
      detail: { workspaceId: activeTabId, module: tab?.module ?? null },
    }))
  }, [activeTabId, tabs])

  const handleSaveAs = useCallback(() => {
    if (!activeTabId) return
    const tab = tabs.find(t => t.id === activeTabId)
    window.dispatchEvent(new CustomEvent('workspace-save-as-command', {
      detail: { workspaceId: activeTabId, module: tab?.module ?? null },
    }))
  }, [activeTabId, tabs])

  const handleTabClose = useCallback(async (id: string) => {
    const ok = await confirmAsync({
      title: 'Close Workspace',
      message: 'Are you sure you would like to close this workspace? Unsaved changes may be lost.',
      confirmLabel: 'Close',
      danger: true,
    })
    if (!ok) return

    setTabs(prev => {
      const index = prev.findIndex(tab => tab.id === id)
      const remaining = prev.filter(tab => tab.id !== id)
      if (activeTabId === id) {
        const fallback = remaining[index] ?? remaining[index - 1] ?? null
        setActiveTabId(fallback?.id ?? null)
        if (!fallback) setIsHome(true)
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
    if (isHome && activeTabId) {
       setIsHome(false)
       setTabs(prev => prev.map(tab => (tab.id === activeTabId ? { ...tab, module } : tab)))
    } else if (activeTabId) {
       setTabs(prev => prev.map(tab => (tab.id === activeTabId ? { ...tab, module } : tab)))
    }
  }, [activeTabId, isHome])

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

  const dispatchModuleCommand = useCallback((cmd: string) => {
    if (!activeTabId || !activeModule || isHome) return
    const eventMap: Partial<Record<AppModule, string>> = {
      cad: 'cad-view-command',
      anchors: 'anchor-view-command',
      calibration: 'calibration-view-command',
      rtls: 'rtls-view-command',
    }
    const eventName = eventMap[activeModule]
    if (eventName) {
      window.dispatchEvent(new CustomEvent(eventName, { detail: { cmd, workspaceId: activeTabId } }))
    }
  }, [activeTabId, activeModule, isHome])

  const handleViewCommand = useCallback((cmd: 'zoom_in' | 'zoom_out' | 'zoom_reset') => {
    dispatchModuleCommand(cmd)
  }, [dispatchModuleCommand])

  const handleEditCommand = useCallback((cmd: 'undo' | 'redo') => {
    dispatchModuleCommand(cmd)
  }, [dispatchModuleCommand])

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
    } catch {  }
  }, [activeTabId, activeTab, activeModule])

  const canCloseTab = tabs.length > 0 && activeTabId !== null
  const handleAnchorToolSelect = useCallback((tool: 'cursor' | 'select' | 'smartSelect') => {
    if (!activeTabId || activeModule !== 'anchors') return
    window.dispatchEvent(new CustomEvent('anchor-view-command', { detail: { cmd: 'set_tool', tool, workspaceId: activeTabId } }))
  }, [activeModule, activeTabId])

  const handleCadToolSelect = useCallback((tool: 'cursor' | 'line' | 'vertex' | 'dim' | 'rotate' | 'trim') => {
    if (!activeTabId || activeModule !== 'cad') return
    window.dispatchEvent(new CustomEvent('cad-view-command', {
      detail: { cmd: 'set_tool', tool, workspaceId: activeTabId },
    }))
  }, [activeModule, activeTabId])

  const handleRtlsQuickSetup = useCallback(() => {
    if (!activeTabId || activeModule !== 'rtls' || isHome) return
    window.dispatchEvent(new CustomEvent('rtls-quick-setup', {
      detail: { workspaceId: activeTabId },
    }))
  }, [activeModule, activeTabId, isHome])

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey)) return
      if (event.altKey || event.shiftKey) return
      if (event.key.toLowerCase() !== 'q') return
      if (activeModule !== 'rtls' || !activeTabId || isHome) return
      event.preventDefault()
      handleRtlsQuickSetup()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [activeModule, activeTabId, isHome, handleRtlsQuickSetup])

  useEffect(() => {
    let cancelled = false
    const poll = async () => {
      try {
        const res = await fetch(`${API}/api/ble_idle/status`)
        if (!res.ok) return
        const data = await res.json()
        if (cancelled) return
        setBleIdleEnabled(Boolean(data.enabled))
        setBleIdleAvailable(Boolean(data.available))
        setBleIdleTags(Array.isArray(data.tags) ? data.tags : [])
        setBleIdleDetail(typeof data.detail === 'string' ? data.detail : '')
      } catch {
      }
    }
    poll()
    const interval = window.setInterval(poll, 3000)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [])

  const handleBleIdleToggle = useCallback(async () => {
    if (bleIdleEnabled) {
      try {
        const res = await fetch(`${API}/api/ble_idle/disable`, { method: 'POST' })
        const data = await res.json().catch(() => ({}))
        setBleIdleEnabled(Boolean(data.enabled))
      } catch {
      }
      return
    }
    const workspaceName = activeTab?.name ?? tabNamesRef.current[activeTabId ?? ''] ?? null
    try {
      const res = await fetch(`${API}/api/ble_idle/enable`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: activeTabId,
          workspace_name: workspaceName,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (data?.success === false && data?.error) {
        alert(`Active BLE Idle: ${data.error}`)
      }
      setBleIdleEnabled(Boolean(data.enabled))
      if (typeof data.available === 'boolean') setBleIdleAvailable(data.available)
    } catch (exc) {
      alert(`Active BLE Idle could not start: ${String(exc)}`)
    }
  }, [activeTab, activeTabId, bleIdleEnabled])

  return (
    <div className="bp5-dark app-root">
      <ConfirmHost />
      <AnimatePresence>
        {isLoading && (
          <motion.div
            className="app-loader"
            initial={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.6 }}
          >
            <Spinner size={32} />
            <div style={{ marginTop: '16px', letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
              Booting System...
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {!isLoading && (
        <motion.div className="app-shell" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}>
          <HotBar
            activeModule={isHome ? null : activeModule}
            hasWorkspace={canCloseTab}
            onNewWorkspace={handleNewTab}
            onOpenWorkspace={handleOpenWorkspaceDialog}
            onSave={handleSave}
            onSaveAs={handleSaveAs}
            onCloseTab={() => activeTabId && handleTabClose(activeTabId)}
            onViewCommand={handleViewCommand}
            onEditCommand={handleEditCommand}
            onAnchorToolSelect={handleAnchorToolSelect}
            onCadToolSelect={handleCadToolSelect}
            bleIdleEnabled={bleIdleEnabled}
            bleIdleAvailable={bleIdleAvailable}
            bleIdleTags={bleIdleTags}
            bleIdleDetail={bleIdleDetail}
            onBleIdleToggle={handleBleIdleToggle}
            onRtlsQuickSetup={handleRtlsQuickSetup}
          />

          <TabStrip
            tabs={tabs}
            activeTabId={activeTabId}
            activeModule={isHome ? null : activeModule}
            onTabSelect={(id) => {
              setActiveTabId(id)
              setIsHome(false)
            }}
            onTabClose={handleTabClose}
            onTabReorder={handleTabReorder}
            onTabRename={handleTabRename}
            onNewTab={handleNewTab}
            onRefresh={handleRefresh}
            onOpenFolder={handleOpenFolder}
          />

          <LeftRail
            activeModule={isHome ? null : activeModule}
            onModuleChange={handleModuleChange}
            onHomeClick={() => setIsHome(true)}
            disabled={!activeTab && isHome === false}
          />

          {tabs.map(tab => (
            <WorkspaceHost key={tab.id} workspace={tab} isActive={tab.id === activeTabId && !isHome} />
          ))}

          {(!activeTab || isHome) && (
            <div className="app-workspace-host app-workspace-host--active">
               <EmptyWorkspacePanel workspaces={existingWorkspaces} onOpen={handleOpenWorkspace} onNew={handleNewTab} />
            </div>
          )}
        </motion.div>
      )}
    </div>
  )
}

export default App
