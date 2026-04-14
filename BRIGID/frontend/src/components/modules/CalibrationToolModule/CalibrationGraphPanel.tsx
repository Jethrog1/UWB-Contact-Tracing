import React, { useMemo } from 'react'
import { ANCHOR_IDS, CalibrationTagRuntime } from './types'

interface Props {
  tag: CalibrationTagRuntime | null
  collapsed: boolean
  onToggle: () => void
}

const ANCHOR_COLORS: Record<string, string> = {
  A0: '#ff5b4d',
  A1: '#42d17e',
  A2: '#ae62ff',
  A3: '#ffb11f',
}

const WIDTH = 980
const HEIGHT = 240
const PADDING = { left: 52, right: 20, top: 16, bottom: 34 }

const CalibrationGraphPanel: React.FC<Props> = ({ tag, collapsed, onToggle }) => {
  const bounds = useMemo(() => {
    const xs: number[] = []
    const ys: number[] = []
    if (tag) {
      ANCHOR_IDS.forEach(anchorId => {
        const series = tag.graph[anchorId]
        series?.points.forEach(point => { xs.push(point.x); ys.push(point.y) })
        series?.fit_line.forEach(point => { xs.push(point.x); ys.push(point.y) })
        series?.capture.forEach(point => { xs.push(point.x); ys.push(point.y) })
        if (series?.live_raw) { xs.push(series.live_raw.x); ys.push(series.live_raw.y) }
        if (series?.live_cal) { xs.push(series.live_cal.x); ys.push(series.live_cal.y) }
      })
    }

    const minX = 0
    const minY = 0
    const maxX = Math.max(30, ...xs, 1)
    const maxY = Math.max(30, ...ys, 1)
    return { minX, minY, maxX, maxY }
  }, [tag])

  const toSvgX = (x: number) => PADDING.left + ((x - bounds.minX) / Math.max(bounds.maxX - bounds.minX, 1)) * (WIDTH - PADDING.left - PADDING.right)
  const toSvgY = (y: number) => HEIGHT - PADDING.bottom - ((y - bounds.minY) / Math.max(bounds.maxY - bounds.minY, 1)) * (HEIGHT - PADDING.top - PADDING.bottom)

  return (
    <div className={`ct-graph-panel${collapsed ? ' ct-graph-panel--collapsed' : ''}`}>
      <div className="ct-graph-header">
        <div className="ct-graph-title">Calibration Graph</div>
        <button className="ct-mini-btn" onClick={onToggle}>{collapsed ? 'Show' : 'Hide'}</button>
      </div>

      {!collapsed && (
        <div className="ct-graph-body">
          <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="ct-graph-svg" role="img" aria-label="Calibration graph">
            <rect x="0" y="0" width={WIDTH} height={HEIGHT} fill="#151515" />
            {[0, 0.25, 0.5, 0.75, 1].map(step => {
              const x = PADDING.left + step * (WIDTH - PADDING.left - PADDING.right)
              const y = PADDING.top + step * (HEIGHT - PADDING.top - PADDING.bottom)
              return (
                <g key={step}>
                  <line x1={x} y1={PADDING.top} x2={x} y2={HEIGHT - PADDING.bottom} stroke="rgba(255,255,255,0.1)" />
                  <line x1={PADDING.left} y1={y} x2={WIDTH - PADDING.right} y2={y} stroke="rgba(255,255,255,0.1)" />
                </g>
              )
            })}

            <line x1={PADDING.left} y1={HEIGHT - PADDING.bottom} x2={WIDTH - PADDING.right} y2={HEIGHT - PADDING.bottom} stroke="#4b5563" />
            <line x1={PADDING.left} y1={PADDING.top} x2={PADDING.left} y2={HEIGHT - PADDING.bottom} stroke="#4b5563" />

            {tag && ANCHOR_IDS.map(anchorId => {
              const series = tag.graph[anchorId]
              if (!series) return null
              const color = ANCHOR_COLORS[anchorId]
              const fitPath = series.fit_line
                .map((point, index) => `${index === 0 ? 'M' : 'L'} ${toSvgX(point.x)} ${toSvgY(point.y)}`)
                .join(' ')

              return (
                <g key={anchorId}>
                  {fitPath && <path d={fitPath} fill="none" stroke={color} strokeWidth="2" opacity="0.85" />}
                  {series.capture.map((point, index) => (
                    <circle key={`capture-${index}`} cx={toSvgX(point.x)} cy={toSvgY(point.y)} r="2.4" fill={color} opacity="0.35" />
                  ))}
                  {series.points.map((point, index) => (
                    <circle key={`point-${index}`} cx={toSvgX(point.x)} cy={toSvgY(point.y)} r="4" fill={color} />
                  ))}
                  {series.live_raw && (
                    <rect
                      x={toSvgX(series.live_raw.x) - 4}
                      y={toSvgY(series.live_raw.y) - 4}
                      width="8"
                      height="8"
                      transform={`rotate(45 ${toSvgX(series.live_raw.x)} ${toSvgY(series.live_raw.y)})`}
                      fill="rgba(255,255,255,0.12)"
                      stroke={color}
                    />
                  )}
                  {series.live_cal && (
                    <circle cx={toSvgX(series.live_cal.x)} cy={toSvgY(series.live_cal.y)} r="5" fill="none" stroke={color} strokeWidth="1.8" />
                  )}
                </g>
              )
            })}

            <text x={WIDTH / 2} y={HEIGHT - 8} fill="#8ea4c8" fontSize="12" textAnchor="middle">Raw UWB (ft)</text>
            <text x="14" y={HEIGHT / 2} fill="#8ea4c8" fontSize="12" textAnchor="middle" transform={`rotate(-90 14 ${HEIGHT / 2})`}>
              Reference (ft)
            </text>
          </svg>

          <div className="ct-graph-legend">
            {ANCHOR_IDS.map(anchorId => (
              <div key={anchorId} className="ct-graph-legend-item">
                <span className="ct-graph-dot" style={{ background: ANCHOR_COLORS[anchorId] }} />
                <span>{anchorId} pts</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default CalibrationGraphPanel
