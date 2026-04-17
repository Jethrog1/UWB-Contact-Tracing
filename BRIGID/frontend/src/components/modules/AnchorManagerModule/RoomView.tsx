import React, { useEffect, useRef } from 'react'
import { AnchorData, RoomData } from '../../../types'
import RoomViewCanvas, { RoomViewCanvasHandle } from './RoomViewCanvas'

interface RoomViewProps {
  room: RoomData
  workspaceId: string
  selectedAnchorId: string | null
  onBack?: () => void
  onAnchorSelect: (anchorId: string | null) => void
  onAnchorPlace: (localX: number, localY: number) => void
  onAnchorUpdate: (anchorId: string, patch: Partial<AnchorData>) => void
  onAnchorDelete: (anchorId: string) => void
  onAnchorMoveStart: (anchorId: string) => void
  onAnchorMove: (anchorId: string, localX: number, localY: number) => void
  onAnchorMoveEnd: () => void
}

const RoomView: React.FC<RoomViewProps> = ({
  room,
  selectedAnchorId,
  onBack,
  onAnchorSelect,
  onAnchorPlace,
  onAnchorUpdate,
  onAnchorDelete,
  onAnchorMoveStart,
  onAnchorMove,
  onAnchorMoveEnd,
}) => {
  const canvasRef = useRef<RoomViewCanvasHandle>(null)
  const hwIdInputRef = useRef<HTMLInputElement>(null)
  const [editFields, setEditFields] = React.useState<Partial<AnchorData>>({})
  const selectedAnchor = room.anchors.find(a => a.id === selectedAnchorId) ?? null

  useEffect(() => {
    if (!selectedAnchor) { setEditFields({}); return }
    setEditFields({ hw_id: selectedAnchor.hw_id, x_ft: selectedAnchor.x_ft, y_ft: selectedAnchor.y_ft, z_ft: selectedAnchor.z_ft })
  }, [selectedAnchor])

  // Focus the HW ID input when an anchor is freshly selected (double-click equivalent)
  useEffect(() => {
    if (selectedAnchor) {
      const t = window.setTimeout(() => hwIdInputRef.current?.focus(), 50)
      return () => window.clearTimeout(t)
    }
  }, [selectedAnchor?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="am-room-view">
      <div className="am-room-view-header">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {onBack && (
              <button className="am-mini-btn" onClick={onBack} title="Back to floor plan">← Floor Plan</button>
            )}
            <div className="am-room-view-title">{room.room_name}</div>
          </div>
          <button className="am-mini-btn" onClick={() => canvasRef.current?.fitView()} title="Fit view (F)">Fit</button>
        </div>
        <div className="am-room-view-meta">
          {room.room_bounds_ft.width.toFixed(1)} × {room.room_bounds_ft.height.toFixed(1)} ft
          &nbsp;·&nbsp;{room.anchors.length} anchor{room.anchors.length !== 1 ? 's' : ''}
          &nbsp;·&nbsp;Ref: {room.reference_anchor_id ?? '—'}
        </div>
        <div className="am-room-view-hint">
          Hold Ctrl and click to place anchor · Click anchor to select · Drag to move · Scroll to zoom
        </div>
      </div>

      <div className="am-room-view-canvas-wrap">
        <RoomViewCanvas
          ref={canvasRef}
          room={room}
          selectedAnchorId={selectedAnchorId}
          onAnchorSelect={onAnchorSelect}
          onAnchorPlace={onAnchorPlace}
          onAnchorMoveStart={onAnchorMoveStart}
          onAnchorMove={onAnchorMove}
          onAnchorMoveEnd={onAnchorMoveEnd}
        />
      </div>

      {room.anchors.length > 0 && (
        <table className="am-anchor-table am-room-view-table">
          <thead>
            <tr><th>ID</th><th>HW ID</th><th>X (ft)</th><th>Y (ft)</th><th>Z (ft)</th><th /></tr>
          </thead>
          <tbody>
            {room.anchors.map(anchor => (
              <tr
                key={anchor.id}
                className={`am-anchor-row${anchor.id === selectedAnchorId ? ' active' : ''}`}
                onClick={() => onAnchorSelect(anchor.id === selectedAnchorId ? null : anchor.id)}
              >
                <td className="am-mono">{anchor.id}</td>
                <td className="am-mono">{anchor.hw_id || '—'}</td>
                <td>{anchor.x_ft.toFixed(3)}</td>
                <td>{anchor.y_ft.toFixed(3)}</td>
                <td>{anchor.z_ft.toFixed(3)}</td>
                <td>
                  <button
                    className="am-del-btn"
                    title="Delete anchor"
                    onClick={e => { e.stopPropagation(); onAnchorDelete(anchor.id) }}
                  >×</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {room.anchors.length === 0 && (
        <div className="am-panel-empty" style={{ padding: '12px 0' }}>
          Click anywhere inside the room outline to place an anchor.
        </div>
      )}

      {selectedAnchor && (
        <div className="am-room-view-edit">
          <div className="am-section-label" style={{ marginBottom: 8 }}>
            Edit {selectedAnchor.hw_id || selectedAnchor.id}
          </div>
          <div className="am-edit-field">
            <label>HW ID</label>
            <input
              ref={hwIdInputRef}
              className="am-input am-mono"
              value={editFields.hw_id ?? ''}
              onChange={e => setEditFields(prev => ({ ...prev, hw_id: e.target.value }))}
              placeholder="A0, A1, ..."
            />
          </div>
          <div className="am-edit-grid">
            <div className="am-edit-field">
              <label>Local X (ft)</label>
              <input className="am-input" type="number" step="0.01"
                value={editFields.x_ft ?? 0}
                onChange={e => setEditFields(prev => ({ ...prev, x_ft: parseFloat(e.target.value) || 0 }))} />
            </div>
            <div className="am-edit-field">
              <label>Local Y (ft)</label>
              <input className="am-input" type="number" step="0.01"
                value={editFields.y_ft ?? 0}
                onChange={e => setEditFields(prev => ({ ...prev, y_ft: parseFloat(e.target.value) || 0 }))} />
            </div>
          </div>
          <div className="am-edit-field">
            <label>Height Z (ft)</label>
            <input className="am-input" type="number" step="0.01" min="0"
              value={editFields.z_ft ?? 0}
              onChange={e => setEditFields(prev => ({ ...prev, z_ft: parseFloat(e.target.value) || 0 }))} />
          </div>
          <button className="am-apply-btn" onClick={() => onAnchorUpdate(selectedAnchor.id, editFields)}>
            Apply Changes
          </button>
        </div>
      )}
    </div>
  )
}

export default RoomView
