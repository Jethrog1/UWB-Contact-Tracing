import React, { useMemo, useRef, useState } from 'react'
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

const WIDTH = 900
const HEIGHT = 210
const PAD = { left: 42, right: 14, top: 12, bottom: 30 }

const TICK_COUNT = 5

function niceTicks(max: number, count: number): number[] {
  if (max <= 0) return Array.from({ length: count + 1 }, (_, i) => i * 5)
  const rawStep = max / count
  const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)))
  const normalized = rawStep / magnitude
  const step = normalized <= 1 ? magnitude : normalized <= 2 ? 2 * magnitude : normalized <= 5 ? 5 * magnitude : 10 * magnitude
  const ticks: number[] = []
  for (let v = 0; v <= max + step * 0.01; v += step) ticks.push(parseFloat(v.toFixed(10)))
  return ticks
}

const CalibrationGraphPanel: React.FC<Props> = ({ tag, collapsed, onToggle }) => {
  const [zoom, setZoom] = useState(1.0)
  const svgRef = useRef<SVGSVGElement>(null)

  // ── Raw data bounds (always minX=0, minY=0) ──────────────────────
  const rawBounds = useMemo(() => {
    const xs: number[] = []
    const ys: number[] = []
    if (tag) {
      ANCHOR_IDS.forEach(anchorId => {
        const series = tag.graph[anchorId]
        series?.points.forEach(p => { xs.push(p.x); ys.push(p.y) })
        series?.fit_line.forEach(p => { xs.push(p.x); ys.push(p.y) })
        series?.capture.forEach(p => { xs.push(p.x); ys.push(p.y) })
        if (series?.live_raw) { xs.push(series.live_raw.x); ys.push(series.live_raw.y) }
        if (series?.live_cal) { xs.push(series.live_cal.x); ys.push(series.live_cal.y) }
      })
    }
    return {
      maxX: Math.max(30, ...xs, 1),
      maxY: Math.max(30, ...ys, 1),
    }
  }, [tag])

  // Apply zoom: zooming in reduces the visible range from origin
  const visibleMaxX = rawBounds.maxX / zoom
  const visibleMaxY = rawBounds.maxY / zoom

  const xTicks = useMemo(() => niceTicks(visibleMaxX, TICK_COUNT), [visibleMaxX])
  const yTicks = useMemo(() => niceTicks(visibleMaxY, TICK_COUNT), [visibleMaxY])

  const toSvgX = (x: number) =>
    PAD.left + (x / visibleMaxX) * (WIDTH - PAD.left - PAD.right)
  const toSvgY = (y: number) =>
    HEIGHT - PAD.bottom - (y / visibleMaxY) * (HEIGHT - PAD.top - PAD.bottom)

  const handleWheel = (e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault()
    const factor = e.deltaY < 0 ? 1.2 : 1 / 1.2
    setZoom(z => Math.max(0.5, Math.min(12, z * factor)))
  }

  const plotAreaLeft = PAD.left
  const plotAreaTop = PAD.top
  const plotAreaRight = WIDTH - PAD.right
  const plotAreaBottom = HEIGHT - PAD.bottom
  const plotWidth = plotAreaRight - plotAreaLeft
  const plotHeight = plotAreaBottom - plotAreaTop

  return (
    <div className={`ct-graph-panel${collapsed ? ' ct-graph-panel--collapsed' : ''}`}>
      <div className="ct-graph-header">
        <div className="ct-graph-title">Calibration Graph</div>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          {!collapsed && zoom !== 1 && (
            <button className="ct-mini-btn" onClick={() => setZoom(1)} title="Reset zoom" style={{ fontSize: 9 }}>
              Reset View
            </button>
          )}
          <button className="ct-mini-btn" onClick={onToggle}>{collapsed ? 'Show' : 'Hide'}</button>
        </div>
      </div>

      {!collapsed && (
        <div className="ct-graph-body">
          <svg
            ref={svgRef}
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            className="ct-graph-svg"
            role="img"
            aria-label="Calibration graph"
            onWheel={handleWheel}
          >
            {/* Background — transparent so panel blur shows through */}
            <rect x="0" y="0" width={WIDTH} height={HEIGHT} fill="transparent" />

            {/* Plot area clip */}
            <defs>
              <clipPath id="ct-plot-clip">
                <rect x={plotAreaLeft} y={plotAreaTop} width={plotWidth} height={plotHeight} />
              </clipPath>
            </defs>

            {/* Grid lines removed for clean look */}

            {/* Axes — same gray as graph bg border */}
            <line x1={plotAreaLeft} y1={plotAreaBottom} x2={plotAreaRight} y2={plotAreaBottom} stroke="rgba(255,255,255,0.08)" />
            <line x1={plotAreaLeft} y1={plotAreaTop} x2={plotAreaLeft} y2={plotAreaBottom} stroke="rgba(255,255,255,0.08)" />

            {/* X axis ticks + labels */}
            {xTicks.map(v => {
              const x = toSvgX(v)
              if (x < plotAreaLeft - 0.5 || x > plotAreaRight + 0.5) return null
              return (
                <g key={`xt-${v}`}>
                  <line x1={x} y1={plotAreaBottom} x2={x} y2={plotAreaBottom + 3} stroke="rgba(255,255,255,0.1)" />
                  <text x={x} y={plotAreaBottom + 13} fill="#5b6574" fontSize="8" textAnchor="middle" fontFamily="var(--font-primary)">
                    {v % 1 === 0 ? v : v.toFixed(1)}
                  </text>
                </g>
              )
            })}

            {/* Y axis ticks + labels */}
            {yTicks.map(v => {
              const y = toSvgY(v)
              if (y < plotAreaTop - 0.5 || y > plotAreaBottom + 0.5) return null
              return (
                <g key={`yt-${v}`}>
                  <line x1={plotAreaLeft - 3} y1={y} x2={plotAreaLeft} y2={y} stroke="rgba(255,255,255,0.1)" />
                  <text x={plotAreaLeft - 5} y={y + 3} fill="#5b6574" fontSize="8" textAnchor="end" fontFamily="var(--font-primary)">
                    {v % 1 === 0 ? v : v.toFixed(1)}
                  </text>
                </g>
              )
            })}

            {/* Axis labels */}
            <text x={(plotAreaLeft + plotAreaRight) / 2} y={HEIGHT - 4} fill="#5b6574" fontSize="9" textAnchor="middle" fontFamily="var(--font-primary)">
              Raw UWB (ft)
            </text>
            <text
              x={10}
              y={(plotAreaTop + plotAreaBottom) / 2}
              fill="#5b6574"
              fontSize="9"
              textAnchor="middle"
              fontFamily="var(--font-primary)"
              transform={`rotate(-90 10 ${(plotAreaTop + plotAreaBottom) / 2})`}
            >
              Reference (ft)
            </text>

            {/* Data series (clipped to plot area) */}
            <g clipPath="url(#ct-plot-clip)">
              {tag && ANCHOR_IDS.map(anchorId => {
                const series = tag.graph[anchorId]
                if (!series) return null
                const color = ANCHOR_COLORS[anchorId]
                const fitPath = series.fit_line
                  .filter(p => p.x >= 0 && p.x <= visibleMaxX && p.y >= 0 && p.y <= visibleMaxY)
                  .map((p, i) => `${i === 0 ? 'M' : 'L'} ${toSvgX(p.x)} ${toSvgY(p.y)}`)
                  .join(' ')

                return (
                  <g key={anchorId}>
                    {fitPath && <path d={fitPath} fill="none" stroke={color} strokeWidth="1.8" opacity="0.9" />}
                    {series.capture.map((p, i) => (
                      <circle key={`cap-${i}`} cx={toSvgX(p.x)} cy={toSvgY(p.y)} r="2" fill={color} opacity="0.3" />
                    ))}
                    {series.points.map((p, i) => (
                      <circle key={`pt-${i}`} cx={toSvgX(p.x)} cy={toSvgY(p.y)} r="3.5" fill={color} />
                    ))}
                    {series.live_raw && (
                      <rect
                        x={toSvgX(series.live_raw.x) - 4}
                        y={toSvgY(series.live_raw.y) - 4}
                        width="8" height="8"
                        transform={`rotate(45 ${toSvgX(series.live_raw.x)} ${toSvgY(series.live_raw.y)})`}
                        fill="rgba(255,255,255,0.1)"
                        stroke={color}
                        strokeWidth="1.2"
                      />
                    )}
                    {series.live_cal && (
                      <circle cx={toSvgX(series.live_cal.x)} cy={toSvgY(series.live_cal.y)} r="4.5" fill="none" stroke={color} strokeWidth="1.6" />
                    )}
                  </g>
                )
              })}
            </g>

            {/* Legend — anchored to very top-right of plot area */}
            <g transform={`translate(${plotAreaRight - 8}, ${plotAreaTop + 4})`}>
              {ANCHOR_IDS.map((anchorId, i) => (
                <g key={anchorId} transform={`translate(0, ${i * 14})`}>
                  <circle cx={-48} cy={4} r={3} fill={ANCHOR_COLORS[anchorId]} />
                  <text x={-40} y={7} fill="#8c96a5" fontSize="9" fontFamily="var(--font-primary)">{anchorId}</text>
                </g>
              ))}
            </g>
          </svg>
        </div>
      )}
    </div>
  )
}

export default CalibrationGraphPanel
