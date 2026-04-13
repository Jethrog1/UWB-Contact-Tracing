import React from 'react'
import { Icon } from '@blueprintjs/core'
import { motion } from 'motion/react'
import PlaceholderBlock from '../common/PlaceholderBlock'
import './FloatingPanel.css'

const FloatingPanel: React.FC = () => {
  return (
    <motion.div
      className="floating-panel"
      initial={{ opacity: 0, y: 24, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.5, delay: 0.4, ease: [0.4, 0, 0.2, 1] }}
    >
      {/* ---- Header ---- */}
      <div className="floating-panel__header">
        <div className="floating-panel__title-row">
          <h3 className="floating-panel__title">Satellite Observation</h3>
          <button className="floating-panel__close" aria-label="Close">
            <Icon icon="cross" size={14} />
          </button>
        </div>
        <div className="floating-panel__meta">
          <span className="floating-panel__meta-label">COLLECTION AREA: SECTOR 7-G</span>
          <span className="floating-panel__meta-separator">•</span>
          <span className="floating-panel__meta-label">TIME: 06/08 12:51GT</span>
        </div>
      </div>

      {/* ---- Description ---- */}
      <div className="floating-panel__description">
        <PlaceholderBlock type="text" label="Analysis summary — detection model output narrative will appear here" />
      </div>

      {/* ---- Model Source Row ---- */}
      <div className="floating-panel__model-row">
        <div className="floating-panel__model-info">
          <div className="floating-panel__model-icon">
            <Icon icon="predictive-analysis" size={14} />
          </div>
          <div className="floating-panel__model-text">
            <span className="floating-panel__model-name">Density Model</span>
            <span className="floating-panel__model-source">• BRIGID Analytics</span>
          </div>
        </div>
        <div className="floating-panel__model-actions">
          <button className="floating-panel__mini-btn" title="Pin">
            <Icon icon="pin" size={12} />
          </button>
          <button className="floating-panel__mini-btn" title="Feedback">
            <Icon icon="thumbs-up" size={12} />
          </button>
          <button className="floating-panel__mini-btn floating-panel__mini-btn--accent" title="Details">
            Details
          </button>
        </div>
      </div>

      {/* ---- Image Comparison ---- */}
      <div className="floating-panel__images">
        <div className="floating-panel__image-card">
          <PlaceholderBlock type="image" label="Before" height="130px" />
          <span className="floating-panel__image-date">06/06</span>
        </div>
        <div className="floating-panel__image-card">
          <PlaceholderBlock type="image" label="After" height="130px" />
          <span className="floating-panel__image-date">06/08</span>
        </div>
      </div>

      {/* ---- Footer Actions ---- */}
      <div className="floating-panel__footer">
        <span className="floating-panel__footer-label">ACTIONS</span>
        <div className="floating-panel__footer-actions">
          <button className="floating-panel__action-btn">
            <Icon icon="history" size={12} />
            <span>View historic activity</span>
          </button>
          <button className="floating-panel__action-btn">
            <Icon icon="document" size={12} />
            <span>Create report</span>
          </button>
          <button className="floating-panel__action-btn">
            <Icon icon="map-create" size={12} />
            <span>Create plan</span>
          </button>
        </div>
      </div>
    </motion.div>
  )
}

export default FloatingPanel
