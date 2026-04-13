// ── Feature Manager — floating geometry tree overlay ─────────────
import React, { useState } from 'react'
import { Icon } from '@blueprintjs/core'
import { motion, AnimatePresence } from 'motion/react'
import { CADState } from './types'
import './FeatureManager.css'

interface Props {
  state: CADState | null
}

const FeatureManager: React.FC<Props> = ({ state }) => {
  const [collapsed, setCollapsed] = useState(false)

  const lineCount     = state?.lines.length ?? 0
  const fixedCount    = state ? Object.keys(state.fixed_lengths).length : 0
  const angleCount    = state?.angle_constraints.length ?? 0
  const distCount     = state?.distance_constraints.length ?? 0

  return (
    <motion.div
      className="feature-manager"
      initial={{ opacity: 0, x: -12, y: -8 }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
    >
      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="fm-header" onClick={() => setCollapsed(c => !c)}>
        <Icon icon="diagram-tree" size={12} color="#38bdf8" />
        <span className="fm-title">Feature Manager</span>
        <Icon
          icon={collapsed ? 'chevron-right' : 'chevron-down'}
          size={11}
          color="#3d4d60"
          className="fm-chevron"
        />
      </div>

      {/* ── Body ─────────────────────────────────────────────────── */}
      <AnimatePresence>
        {!collapsed && (
          <motion.div
            className="fm-body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <FMSection
              icon="minus"
              label="Lines"
              count={lineCount}
              items={state?.lines.map(l => ({
                id: l.id,
                label: `Line ${l.id.slice(0, 6)}`,
                sub: `(${l.x1.toFixed(1)}, ${l.y1.toFixed(1)}) → (${l.x2.toFixed(1)}, ${l.y2.toFixed(1)})`,
                active: l.id === state?.selected_id || state?.multi_selected_ids.includes(l.id),
              })) ?? []}
            />

            <FMSection
              icon="tag"
              label="Fixed Lengths"
              count={fixedCount}
              items={state ? Object.entries(state.fixed_lengths).map(([id, m]) => ({
                id,
                label: `Len ${id.slice(0, 6)}`,
                sub: `= ${m.len.toFixed(2)}`,
                active: false,
              })) : []}
            />

            <FMSection
              icon="arrows-horizontal"
              label="Distance Dims"
              count={distCount}
              items={state?.distance_constraints.map((dc, i) => ({
                id: String(i),
                label: `Dist ${i + 1}`,
                sub: `${dc.dist.toFixed(2)}`,
                active: false,
              })) ?? []}
            />

            <FMSection
              icon="curved-range-chart"
              label="Angle Dims"
              count={angleCount}
              items={state?.angle_constraints.map((ac, i) => ({
                id: String(i),
                label: `Angle ${i + 1}`,
                sub: `${ac.deg.toFixed(1)}°`,
                active: false,
              })) ?? []}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

// ── Section sub-component ─────────────────────────────────────────
interface FMItem { id: string; label: string; sub: string; active: boolean }

const FMSection: React.FC<{
  icon: string
  label: string
  count: number
  items: FMItem[]
}> = ({ icon, label, count, items }) => {
  const [open, setOpen] = useState(true)

  return (
    <div className="fm-section">
      <div className="fm-section-header" onClick={() => setOpen(o => !o)}>
        <Icon icon={open ? 'chevron-down' : 'chevron-right'} size={10} color="#3d4d60" />
        <Icon icon={icon as any} size={11} color="#4a5a74" style={{ marginLeft: 2 }} />
        <span className="fm-section-label">{label}</span>
        <span className="fm-section-count">{count}</span>
      </div>

      <AnimatePresence>
        {open && items.length > 0 && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: 'auto' }}
            exit={{ height: 0 }}
            transition={{ duration: 0.15 }}
            style={{ overflow: 'hidden' }}
          >
            {items.map(item => (
              <div key={item.id} className={`fm-item${item.active ? ' fm-item--active' : ''}`}>
                <span className="fm-item-label">{item.label}</span>
                <span className="fm-item-sub">{item.sub}</span>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {open && items.length === 0 && (
        <div className="fm-empty">—</div>
      )}
    </div>
  )
}

export default FeatureManager
