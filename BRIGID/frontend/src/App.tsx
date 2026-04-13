import React, { useState, useCallback } from 'react'
import { FocusStyleManager } from '@blueprintjs/core'
import { motion } from 'motion/react'

import HotBar from './components/HotBar/HotBar'
import TabStrip from './components/TabStrip/TabStrip'
import LeftRail from './components/LeftRail/LeftRail'
import CADModule from './components/modules/CADModule/CADModule'
import { AppModule, WorkspaceTab } from './types'
import './App.css'

FocusStyleManager.onlyShowFocusOnTabs()

// ── Default empty state ────────────────────────────────────────────
const DEFAULT_TABS: WorkspaceTab[] = [
  { id: 'ws-1', name: 'Workspace 1', module: 'cad', modified: false },
]

let nextTabId = 2

// ── Placeholder panels for non-CAD modules ─────────────────────────
const EmptyModulePanel: React.FC<{ module: AppModule }> = ({ module }) => {
  const labels: Record<AppModule, { title: string; sub: string; icon: string }> = {
    profile:     { title: 'Profile Manager',    sub: 'User profiles and device assignments', icon: '◉' },
    calibration: { title: 'Calibration Tool',   sub: 'Tag distance correction and fitting',  icon: '◈' },
    cad:         { title: '2D CAD Modeling',     sub: 'Floor plan geometry editor',           icon: '⬡' },
    anchors:     { title: 'Anchor Manager',     sub: 'UWB anchor configuration and layout',  icon: '⊕' },
    rtls:        { title: 'RTLS Dashboard',     sub: 'Real-time location tracking monitor',  icon: '⊗' },
  }
  const info = labels[module]
  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      background: '#0a0e17',
      color: '#2d3d50',
      gap: 12,
      userSelect: 'none',
    }}>
      <div style={{ fontSize: 48, lineHeight: 1 }}>{info.icon}</div>
      <div style={{ fontSize: 18, fontWeight: 600, color: '#3d4d60', letterSpacing: '0.04em' }}>{info.title}</div>
      <div style={{ fontSize: 13, color: '#1e2d42' }}>{info.sub}</div>
      <div style={{ marginTop: 16, fontSize: 12, color: '#182030', border: '1px solid #182030', padding: '6px 14px', borderRadius: 4 }}>
        Module coming soon
      </div>
    </div>
  )
}

// ── Right panel stub for non-CAD modules ──────────────────────────
const StubRightPanel: React.FC<{ module: AppModule }> = ({ module }) => (
  <motion.aside
    initial={{ opacity: 0, x: 16 }}
    animate={{ opacity: 1, x: 0 }}
    transition={{ duration: 0.4, delay: 0.2 }}
    style={{
      gridArea: 'right',
      width: 300,
      background: '#0c1220',
      borderLeft: '1px solid rgba(56,68,94,0.35)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      color: '#1e2d42',
      fontSize: 12,
      gap: 8,
    }}
  >
    <span style={{ fontSize: 22, opacity: 0.3 }}>◫</span>
    <span style={{ opacity: 0.5 }}>No panel for {module}</span>
  </motion.aside>
)

// ── App ──────────────────────────────────────────────────────────
const App: React.FC = () => {
  const [tabs, setTabs] = useState<WorkspaceTab[]>(DEFAULT_TABS)
  const [activeTabId, setActiveTabId] = useState<string>('ws-1')
  const [activeModule, setActiveModule] = useState<AppModule>('cad')

  const activeTab = tabs.find(t => t.id === activeTabId) ?? tabs[0]

  const handleNewTab = useCallback(() => {
    const id = `ws-${nextTabId++}`
    const newTab: WorkspaceTab = { id, name: `Workspace ${nextTabId - 1}`, module: activeModule, modified: false }
    setTabs(prev => [...prev, newTab])
    setActiveTabId(id)
  }, [activeModule])

  const handleTabClose = useCallback((id: string) => {
    setTabs(prev => {
      const remaining = prev.filter(t => t.id !== id)
      if (remaining.length === 0) {
        // Always keep at least one tab
        const fallback: WorkspaceTab = { id: `ws-${nextTabId++}`, name: `Workspace ${nextTabId - 1}`, module: 'cad', modified: false }
        setActiveTabId(fallback.id)
        return [fallback]
      }
      if (activeTabId === id) {
        setActiveTabId(remaining[remaining.length - 1].id)
      }
      return remaining
    })
  }, [activeTabId])

  const handleModuleChange = useCallback((module: AppModule) => {
    setActiveModule(module)
  }, [])

  const isCAD = activeModule === 'cad'

  return (
    <div className="bp5-dark app-root">
      <motion.div
        className="app-shell"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4 }}
      >
        {/* ── Row 1: Application menu bar ── */}
        <HotBar />

        {/* ── Row 2: Project workspace tabs ── */}
        <TabStrip
          tabs={tabs}
          activeTabId={activeTabId}
          onTabSelect={setActiveTabId}
          onTabClose={handleTabClose}
          onNewTab={handleNewTab}
        />

        {/* ── Row 3: Left rail + main content + right panel ── */}
        <LeftRail activeModule={activeModule} onModuleChange={handleModuleChange} />

        {/* ── Center + Right — module-specific ── */}
        {isCAD ? (
          // CAD has its own integrated layout (canvas + feature manager + right panel)
          <CADModule />
        ) : (
          <>
            <EmptyModulePanel module={activeModule} />
            <StubRightPanel module={activeModule} />
          </>
        )}
      </motion.div>
    </div>
  )
}

export default App
