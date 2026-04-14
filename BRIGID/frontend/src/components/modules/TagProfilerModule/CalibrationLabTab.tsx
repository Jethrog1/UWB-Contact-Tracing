import React, { useCallback, useState } from 'react'
import { CalibrationPoint, TagProfile } from '../../../types'

const API = 'http://localhost:8765'
const ANCHOR_IDS = ['A0', 'A1', 'A2', 'A3']
const FIT_MODES = ['Linear', 'Polynomial', 'Logarithmic', 'Power Series', 'Exponential', 'Moving Average']

interface Props {
  profile: TagProfile
  onChange: (updated: TagProfile) => void
}

interface AnchorCalState {
  points: CalibrationPoint[]
  equation: string
  generating: boolean
  error: string
}

const emptyAnchorState = (): AnchorCalState => ({
  points: [],
  equation: '',
  generating: false,
  error: '',
})

const CalibrationLabTab: React.FC<Props> = ({ profile, onChange }) => {
  const [selectedAnchor, setSelectedAnchor] = useState<string>('A0')
  const [fitMode, setFitMode] = useState<string>('Linear')
  const [polyDeg, setPolyDeg] = useState<number>(4)
  const [anchorStates, setAnchorStates] = useState<Record<string, AnchorCalState>>(
    Object.fromEntries(ANCHOR_IDS.map(id => [id, emptyAnchorState()]))
  )
  const [rawInput, setRawInput] = useState<string>('')

  const updateAnchor = (aid: string, patch: Partial<AnchorCalState>) => {
    setAnchorStates(prev => ({ ...prev, [aid]: { ...prev[aid], ...patch } }))
  }

  const parsePoints = (text: string): CalibrationPoint[] => {
    return text.trim().split('\n').flatMap(line => {
      const parts = line.trim().split(/[\s,\t]+/)
      if (parts.length >= 2) {
        const m = parseFloat(parts[0])
        const t = parseFloat(parts[1])
        if (!isNaN(m) && !isNaN(t)) return [{ measured: m, true_dist: t }]
      }
      return []
    })
  }

  const handleGenerateEquation = useCallback(async () => {
    const state = anchorStates[selectedAnchor]
    const pts = state.points.length > 0 ? state.points : parsePoints(rawInput)
    if (pts.length < 2) {
      updateAnchor(selectedAnchor, { error: 'Enter at least 2 data points.' })
      return
    }
    updateAnchor(selectedAnchor, { generating: true, error: '' })
    try {
      const res = await fetch(`${API}/api/profile/calibration/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          points: pts.map(p => [p.measured, p.true_dist]),
          fit_mode: fitMode,
          poly_deg: polyDeg,
        }),
      })
      const data = await res.json()
      if (data.success) {
        updateAnchor(selectedAnchor, { equation: data.equation, points: pts, generating: false })
      } else {
        updateAnchor(selectedAnchor, { error: data.error, generating: false })
      }
    } catch (e) {
      updateAnchor(selectedAnchor, { error: 'Server unreachable.', generating: false })
    }
  }, [selectedAnchor, anchorStates, rawInput, fitMode, polyDeg])

  const handleApplyEquation = () => {
    const eq = anchorStates[selectedAnchor].equation
    if (!eq) return
    const next = JSON.parse(JSON.stringify(profile)) as TagProfile
    next.calibration.equations[selectedAnchor] = eq
    next.calibration.last_calibration_date = new Date().toISOString().split('T')[0]
    onChange(next)
  }

  const handleAddPoint = () => {
    const pts = parsePoints(rawInput)
    if (pts.length === 0) return
    updateAnchor(selectedAnchor, { points: [...anchorStates[selectedAnchor].points, ...pts] })
    setRawInput('')
  }

  const handleClearPoints = () => {
    updateAnchor(selectedAnchor, { points: [], equation: '', error: '' })
    setRawInput('')
  }

  const curState = anchorStates[selectedAnchor]

  return (
    <div className="tp-callib">
      {/* Anchor selector */}
      <div className="tp-callib-anchors">
        {ANCHOR_IDS.map(aid => (
          <button
            key={aid}
            className={`tp-callib-anchor-btn${selectedAnchor === aid ? ' active' : ''}`}
            onClick={() => setSelectedAnchor(aid)}
          >
            {aid}
            {profile.calibration.equations[aid] && <span className="tp-callib-dot" />}
          </button>
        ))}
      </div>

      <div className="tp-callib-body">
        {/* Left: point entry */}
        <div className="tp-callib-entry">
          <div className="tp-callib-section-title">Data Points — {selectedAnchor}</div>
          <div className="tp-callib-hint">
            Enter "measured true" pairs, one per line.<br />
            Example: <code>3.2 3.0</code>
          </div>
          <textarea
            className="tp-callib-textarea"
            rows={6}
            value={rawInput}
            onChange={e => setRawInput(e.target.value)}
            placeholder={"measured true\n3.2 3.0\n5.1 4.8\n..."}
          />
          <div className="tp-callib-actions">
            <button className="tp-btn tp-btn--secondary" onClick={handleAddPoint}>Add Points</button>
            <button className="tp-btn tp-btn--ghost" onClick={handleClearPoints}>Clear</button>
          </div>

          {/* Point table */}
          {curState.points.length > 0 && (
            <div className="tp-callib-table-wrap">
              <table className="tp-callib-table">
                <thead>
                  <tr><th>#</th><th>Measured</th><th>True</th></tr>
                </thead>
                <tbody>
                  {curState.points.map((pt, i) => (
                    <tr key={i}>
                      <td>{i + 1}</td>
                      <td>{pt.measured.toFixed(3)}</td>
                      <td>{pt.true_dist.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Right: fit mode + generate */}
        <div className="tp-callib-generate">
          <div className="tp-callib-section-title">Fit Mode</div>
          <select className="tp-field-select" value={fitMode} onChange={e => setFitMode(e.target.value)}>
            {FIT_MODES.map(m => <option key={m} value={m}>{m}</option>)}
          </select>

          {fitMode === 'Polynomial' && (
            <div className="tp-field" style={{ marginTop: 8 }}>
              <label className="tp-field-label">Polynomial Degree</label>
              <input className="tp-field-input" type="number" min={1} max={8}
                value={polyDeg} onChange={e => setPolyDeg(parseInt(e.target.value) || 4)} />
            </div>
          )}

          <button
            className="tp-btn tp-btn--primary tp-callib-generate-btn"
            onClick={handleGenerateEquation}
            disabled={curState.generating}
          >
            {curState.generating ? 'Generating...' : 'Generate Equation'}
          </button>

          {curState.error && (
            <div className="tp-callib-error">{curState.error}</div>
          )}

          {curState.equation && (
            <div className="tp-callib-result">
              <div className="tp-callib-result-label">Generated Equation:</div>
              <div className="tp-callib-result-eq">{curState.equation}</div>
              <button className="tp-btn tp-btn--accent" onClick={handleApplyEquation}>
                Apply to {selectedAnchor}
              </button>
            </div>
          )}

          {/* Current equation in profile */}
          <div className="tp-callib-current">
            <div className="tp-callib-result-label">Current equation in profile:</div>
            <div className="tp-callib-result-eq tp-callib-result-eq--current">
              {profile.calibration.equations[selectedAnchor] || <span className="tp-muted">None (raw distance)</span>}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default CalibrationLabTab
