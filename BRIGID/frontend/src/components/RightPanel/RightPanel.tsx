import React, { useState } from 'react'
import { Icon, Collapse } from '@blueprintjs/core'
import { motion } from 'motion/react'
import { AppModule } from '../TopBar/TopBar'
import PlaceholderBlock from '../common/PlaceholderBlock'
import './RightPanel.css'

interface RightPanelProps {
  activeModule: AppModule
}

/* ─────────────── RTLS Panel ─────────────── */
const RTLSPanel: React.FC = () => {
  const [alertOpen, setAlertOpen] = useState(true)
  const [eventLogOpen, setEventLogOpen] = useState(true)

  return (
    <>
      {/* Entity Card */}
      <div className="right-panel__entity">
        <div className="right-panel__entity-icon">
          <Icon icon="locate" size={22} />
        </div>
        <div className="right-panel__entity-info">
          <h3 className="right-panel__entity-title">Live Tracking Status</h3>
          <span className="right-panel__entity-type">RTLS Dashboard Module</span>
        </div>
      </div>

      <PlaceholderBlock type="data" label="[POSITION MAP — LIVE TAG OVERLAY]" />

      {/* Details Grid */}
      <div className="right-panel__detail-grid">
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Active Tags</span>
          <span className="right-panel__detail-val">[0]</span>
        </div>
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Active Anchors</span>
          <span className="right-panel__detail-val">[0]</span>
        </div>
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Serial Port</span>
          <span className="right-panel__detail-val">[none]</span>
        </div>
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Update Rate</span>
          <span className="right-panel__detail-val">[— Hz]</span>
        </div>
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Tracked Distances</span>
          <span className="right-panel__detail-val">[—]</span>
        </div>
      </div>

      {/* Alert Banner */}
      <div className="right-panel__collapsible">
        <button className="right-panel__collapse-header" onClick={() => setAlertOpen(!alertOpen)}>
          <Icon icon={alertOpen ? 'chevron-down' : 'chevron-right'} size={14} />
          <span className="right-panel__collapse-title">SYSTEM ALERTS</span>
        </button>
        <Collapse isOpen={alertOpen}>
          <div className="right-panel__collapse-body">
            <div className="right-panel__alert-banner right-panel__alert-banner--info">
              <Icon icon="info-sign" size={14} />
              <span>No active connections — connect a serial module to begin tracking</span>
            </div>
          </div>
        </Collapse>
      </div>

      {/* Event Log */}
      <div className="right-panel__collapsible">
        <button className="right-panel__collapse-header" onClick={() => setEventLogOpen(!eventLogOpen)}>
          <Icon icon={eventLogOpen ? 'chevron-down' : 'chevron-right'} size={14} />
          <span className="right-panel__collapse-title">EVENT TIMELINE</span>
        </button>
        <Collapse isOpen={eventLogOpen}>
          <div className="right-panel__collapse-body">
            <PlaceholderBlock type="chart" label="[EVENT TIMELINE — CONTACT / PROXIMITY LOG]" />
          </div>
        </Collapse>
      </div>
    </>
  )
}

/* ─────────────── CAD Panel ─────────────── */
const CADPanel: React.FC = () => {
  const [layersOpen, setLayersOpen] = useState(true)

  return (
    <>
      <div className="right-panel__entity">
        <div className="right-panel__entity-icon">
          <Icon icon="draw" size={22} />
        </div>
        <div className="right-panel__entity-info">
          <h3 className="right-panel__entity-title">Floor Plan Editor</h3>
          <span className="right-panel__entity-type">CAD Modeling Module</span>
        </div>
      </div>

      <PlaceholderBlock type="image" label="[ACTIVE FLOOR PLAN — SVG PREVIEW]" />

      <div className="right-panel__detail-grid">
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Drawing Status</span>
          <span className="right-panel__detail-val">[no file loaded]</span>
        </div>
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Scale</span>
          <span className="right-panel__detail-val">[1:1]</span>
        </div>
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Geometry Objects</span>
          <span className="right-panel__detail-val">[0]</span>
        </div>
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Selected Element</span>
          <span className="right-panel__detail-val">[none]</span>
        </div>
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Rooms Defined</span>
          <span className="right-panel__detail-val">[0]</span>
        </div>
      </div>

      <div className="right-panel__collapsible">
        <button className="right-panel__collapse-header" onClick={() => setLayersOpen(!layersOpen)}>
          <Icon icon={layersOpen ? 'chevron-down' : 'chevron-right'} size={14} />
          <span className="right-panel__collapse-title">LAYERS</span>
        </button>
        <Collapse isOpen={layersOpen}>
          <div className="right-panel__collapse-body">
            <PlaceholderBlock type="table" label="[LAYER LIST — WALLS, ROOMS, GEOMETRY]" />
          </div>
        </Collapse>
      </div>
    </>
  )
}

/* ─────────────── Anchor Placement Panel ─────────────── */
const AnchorPanel: React.FC = () => {
  const [listOpen, setListOpen] = useState(true)
  const [validityOpen, setValidityOpen] = useState(true)

  return (
    <>
      <div className="right-panel__entity">
        <div className="right-panel__entity-icon">
          <Icon icon="cell-tower" size={22} />
        </div>
        <div className="right-panel__entity-info">
          <h3 className="right-panel__entity-title">Anchor Configuration</h3>
          <span className="right-panel__entity-type">Anchor Placement Module</span>
        </div>
      </div>

      <PlaceholderBlock type="image" label="[ANCHOR LAYOUT MAP — PLACEMENT PREVIEW]" />

      <div className="right-panel__detail-grid">
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Total Anchors</span>
          <span className="right-panel__detail-val">[0]</span>
        </div>
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Selected Anchor</span>
          <span className="right-panel__detail-val">[none]</span>
        </div>
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Position (X, Y)</span>
          <span className="right-panel__detail-val">[—, —]</span>
        </div>
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Elevation (ft)</span>
          <span className="right-panel__detail-val">[—]</span>
        </div>
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Coverage Estimate</span>
          <span className="right-panel__detail-val">[—]</span>
        </div>
      </div>

      <div className="right-panel__collapsible">
        <button className="right-panel__collapse-header" onClick={() => setListOpen(!listOpen)}>
          <Icon icon={listOpen ? 'chevron-down' : 'chevron-right'} size={14} />
          <span className="right-panel__collapse-title">ANCHOR LIST</span>
        </button>
        <Collapse isOpen={listOpen}>
          <div className="right-panel__collapse-body">
            <PlaceholderBlock type="table" label="[ANCHOR TABLE — ID, NAME, X, Y, STATUS]" />
          </div>
        </Collapse>
      </div>

      <div className="right-panel__collapsible">
        <button className="right-panel__collapse-header" onClick={() => setValidityOpen(!validityOpen)}>
          <Icon icon={validityOpen ? 'chevron-down' : 'chevron-right'} size={14} />
          <span className="right-panel__collapse-title">PLACEMENT VALIDITY</span>
        </button>
        <Collapse isOpen={validityOpen}>
          <div className="right-panel__collapse-body">
            <div className="right-panel__alert-banner right-panel__alert-banner--info">
              <Icon icon="info-sign" size={14} />
              <span>Place at least 3 anchors to enable trilateration</span>
            </div>
          </div>
        </Collapse>
      </div>
    </>
  )
}

/* ─────────────── Profiling Panel ─────────────── */
const ProfilingPanel: React.FC = () => {
  const [calOpen, setCalOpen] = useState(true)
  const [sessionOpen, setSessionOpen] = useState(true)

  return (
    <>
      <div className="right-panel__entity">
        <div className="right-panel__entity-icon">
          <Icon icon="regression-chart" size={22} />
        </div>
        <div className="right-panel__entity-info">
          <h3 className="right-panel__entity-title">Tag Profiling</h3>
          <span className="right-panel__entity-type">Calibration & Profiling Module</span>
        </div>
      </div>

      <PlaceholderBlock type="chart" label="[RAW vs CORRECTED DISTANCE CHART]" />

      <div className="right-panel__detail-grid">
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Selected Tag</span>
          <span className="right-panel__detail-val">[none]</span>
        </div>
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Device Profile</span>
          <span className="right-panel__detail-val">[—]</span>
        </div>
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Correction Model</span>
          <span className="right-panel__detail-val">[—]</span>
        </div>
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Fit Equation</span>
          <span className="right-panel__detail-val">[—]</span>
        </div>
        <div className="right-panel__detail-row">
          <span className="right-panel__detail-key">Last Calibration</span>
          <span className="right-panel__detail-val">[—]</span>
        </div>
      </div>

      <div className="right-panel__collapsible">
        <button className="right-panel__collapse-header" onClick={() => calOpen ? setCalOpen(false) : setCalOpen(true)}>
          <Icon icon={calOpen ? 'chevron-down' : 'chevron-right'} size={14} />
          <span className="right-panel__collapse-title">CALIBRATION EQUATIONS</span>
        </button>
        <Collapse isOpen={calOpen}>
          <div className="right-panel__collapse-body">
            <PlaceholderBlock type="table" label="[EQUATION TABLE — A0, A1, A2, A3 PER-ANCHOR CORRECTIONS]" />
          </div>
        </Collapse>
      </div>

      <div className="right-panel__collapsible">
        <button className="right-panel__collapse-header" onClick={() => setSessionOpen(!sessionOpen)}>
          <Icon icon={sessionOpen ? 'chevron-down' : 'chevron-right'} size={14} />
          <span className="right-panel__collapse-title">TEST RUN SUMMARY</span>
        </button>
        <Collapse isOpen={sessionOpen}>
          <div className="right-panel__collapse-body">
            <PlaceholderBlock type="data" label="[CAPTURE SESSION LOG — SAMPLES, ACCURACY, RESIDUALS]" />
          </div>
        </Collapse>
      </div>
    </>
  )
}

/* ─────────────── Right Panel Container ─────────────── */
const RightPanel: React.FC<RightPanelProps> = ({ activeModule }) => {
  return (
    <motion.aside
      className="right-panel"
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.5, delay: 0.3, ease: [0.4, 0, 0.2, 1] }}
    >
      <div className="right-panel__scroll">
        <motion.div
          key={activeModule}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="right-panel__content"
        >
          {activeModule === 'rtls' && <RTLSPanel />}
          {activeModule === 'cad' && <CADPanel />}
          {activeModule === 'anchors' && <AnchorPanel />}
          {activeModule === 'profiling' && <ProfilingPanel />}
        </motion.div>
      </div>

      {/* ---- Footer ---- */}
      <div className="right-panel__footer">
        BRIGID RTLS Platform • v1.0.0
      </div>
    </motion.aside>
  )
}

export default RightPanel
