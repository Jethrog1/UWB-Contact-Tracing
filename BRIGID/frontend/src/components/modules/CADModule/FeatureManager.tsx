import React, { useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { CADFeatureNode, CADState } from './types'
import './FeatureManager.css'

interface Props {
  state: CADState | null
}

const FeatureNodeRow: React.FC<{
  node: CADFeatureNode
  depth: number
  activeDimKeys: Set<string>
}> = ({ node, depth, activeDimKeys }) => {
  const [open, setOpen] = useState(node.open)
  const hasChildren = node.children.length > 0
  const active = node.values.some(value => activeDimKeys.has(value))

  return (
    <div className="fm-node">
      <button
        className={`fm-node-row${active ? ' fm-node-row--active' : ''}`}
        style={{ paddingLeft: 12 + depth * 14 }}
        onClick={() => hasChildren && setOpen(v => !v)}
      >
        <span className="fm-node-chevron">
          {hasChildren ? (open ? '▾' : '▸') : null}
        </span>
        <span className="fm-node-text">{node.text}</span>
      </button>

      <AnimatePresence initial={false}>
        {hasChildren && open && (
          <motion.div
            className="fm-node-children"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            {node.children.map(child => (
              <FeatureNodeRow key={child.id} node={child} depth={depth + 1} activeDimKeys={activeDimKeys} />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

const FeatureManager: React.FC<Props> = ({ state }) => {
  const [collapsed, setCollapsed] = useState(false)
  const nodes = state?.feature_tree ?? []
  const activeDimKeys = new Set(state?.selected_dim_kinds ?? [])

  return (
    <motion.div
      className="feature-manager"
      initial={{ opacity: 0, x: -12, y: -8 }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
    >
      <div className="fm-header" onClick={() => setCollapsed(v => !v)}>
        <span className="fm-chevron" style={{ fontSize: 10, color: 'var(--text-muted)' }}>{collapsed ? '▸' : '▾'}</span>
        <span className="fm-title">Features</span>
        <span className="fm-summary">{nodes.length ? `${nodes.length}` : '—'}</span>
      </div>

      <AnimatePresence initial={false}>
        {!collapsed && (
          <motion.div
            className="fm-body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
          >
            {nodes.length === 0 ? (
              <div className="fm-empty">No geometry yet</div>
            ) : (
              nodes.map(node => (
                <FeatureNodeRow key={node.id} node={node} depth={0} activeDimKeys={activeDimKeys} />
              ))
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

export default FeatureManager

