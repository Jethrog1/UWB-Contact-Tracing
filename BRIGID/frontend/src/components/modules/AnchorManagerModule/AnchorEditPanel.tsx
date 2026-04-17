import React, { useEffect, useState } from 'react'
import { AnchorData, RoomData } from '../../../types'

interface Props {
  rooms: RoomData[]
  selectedRoomName: string | null
  selectedAnchorId: string | null
  hoverRoomName: string | null
  canUndo: boolean
  canRedo: boolean
  onRoomSelect: (roomName: string | null) => void
  onRoomHover: (roomName: string | null) => void
  onRoomDoubleClick: (roomName: string) => void
  onAnchorUpdate: (roomName: string, anchorId: string, patch: Partial<AnchorData>) => void
  onAnchorDelete: (roomName: string, anchorId: string) => void
  onAnchorSelect: (anchorId: string | null) => void
  onEdgesUpdate?: (roomName: string, nextEdges: [string, string][]) => void
  onReferenceAnchorChange: (roomName: string, referenceAnchorId: string | null) => void
  onUndo: () => void
  onRedo: () => void
  onEscapeCanvas: () => void
}

const AnchorEditPanel: React.FC<Props> = ({
  rooms,
  selectedRoomName,
  selectedAnchorId,
  hoverRoomName,
  canUndo,
  canRedo,
  onRoomSelect,
  onRoomHover,
  onRoomDoubleClick,
  onAnchorUpdate,
  onAnchorDelete,
  onAnchorSelect,
  onReferenceAnchorChange,
  onUndo,
  onRedo,
  onEscapeCanvas,
}) => {
  const [editFields, setEditFields] = useState<Partial<AnchorData>>({})
  const selectedRoom = rooms.find(room => room.room_name === selectedRoomName) ?? null
  const selectedAnchor = selectedRoom?.anchors.find(anchor => anchor.id === selectedAnchorId) ?? null

  useEffect(() => {
    if (!selectedAnchor) {
      setEditFields({})
      return
    }
    setEditFields({
      hw_id: selectedAnchor.hw_id,
      x_ft: selectedAnchor.x_ft,
      y_ft: selectedAnchor.y_ft,
      z_ft: selectedAnchor.z_ft,
    })
  }, [selectedAnchor])

  const handleApply = () => {
    if (!selectedRoom || !selectedAnchor) return
    onAnchorUpdate(selectedRoom.room_name, selectedAnchor.id, editFields)
  }

  return (
    <div className="am-floating-panel">
      <div className="am-floating-header">
        <div>
          <div className="am-floating-title">Room Manager</div>
        </div>
        <div className="am-floating-actions">
          <button className="am-mini-btn" onClick={onEscapeCanvas}>Esc</button>
          <button className="am-mini-btn" onClick={onUndo} disabled={!canUndo}>Undo</button>
          <button className="am-mini-btn" onClick={onRedo} disabled={!canRedo}>Redo</button>
        </div>
      </div>

      <div className="am-panel-section">
        <div className="am-section-label">Rooms</div>
        <div className="am-room-chip-list">
          {rooms.length === 0 && <div className="am-panel-empty">Load an SVG and create a room to begin.</div>}
          {rooms.map(room => (
            <button
              key={room.room_name}
              className={`am-room-chip${room.room_name === selectedRoomName ? ' active' : room.room_name === hoverRoomName ? ' hovered' : ''}`}
              onClick={() => {
                onRoomSelect(room.room_name === selectedRoomName ? null : room.room_name)
                onAnchorSelect(null)
              }}
              onMouseEnter={() => onRoomHover(room.room_name)}
              onMouseLeave={() => onRoomHover(null)}
              onDoubleClick={() => onRoomDoubleClick(room.room_name)}
            >
              {room.room_name} ({room.anchors.length} anchor{room.anchors.length !== 1 ? 's' : ''})
            </button>
          ))}
        </div>
      </div>

      {!selectedRoom && (
        <div className="am-panel-section">
          <div className="am-panel-empty">Select a room to edit anchors, reference coordinates, and history.</div>
        </div>
      )}

      {selectedRoom && (
        <>
          <div className="am-panel-section">
            <div className="am-panel-title">{selectedRoom.room_name}</div>
            <div className="am-panel-meta">
              {selectedRoom.room_bounds_ft.width.toFixed(1)} x {selectedRoom.room_bounds_ft.height.toFixed(1)} ft
            </div>
            <div className="am-panel-meta">Segments: {selectedRoom.segments_ft.length}</div>
            <div className="am-panel-meta">Anchors: {selectedRoom.anchors.length}</div>
          </div>

          <div className="am-panel-section">
            <div className="am-section-label">Reference Anchor</div>
            <select
              className="am-input"
              value={selectedRoom.reference_anchor_id ?? ''}
              onChange={event => onReferenceAnchorChange(selectedRoom.room_name, event.target.value || null)}
            >
              {selectedRoom.anchors.length === 0 && <option value="">No anchors yet</option>}
              {selectedRoom.anchors.map(anchor => (
                <option key={anchor.id} value={anchor.id}>
                  {anchor.hw_id || anchor.id}
                </option>
              ))}
            </select>
          </div>

          <div className="am-panel-section am-anchor-list-section">
            <div className="am-section-label">Anchors</div>
            {selectedRoom.anchors.length === 0 ? (
              <div className="am-panel-empty">Open room view and hold Ctrl+Click to place anchors.</div>
            ) : (
              <table className="am-anchor-table">
                <thead>
                  <tr><th>ID</th><th>HW</th><th>X</th><th>Y</th><th>Z</th><th /></tr>
                </thead>
                <tbody>
                  {selectedRoom.anchors.map(anchor => (
                    <tr
                      key={anchor.id}
                      className={anchor.id === selectedAnchorId ? 'am-anchor-row active' : 'am-anchor-row'}
                      onClick={() => onAnchorSelect(anchor.id === selectedAnchorId ? null : anchor.id)}
                    >
                      <td className="am-mono">{anchor.id}</td>
                      <td className="am-mono">{anchor.hw_id || '-'}</td>
                      <td>{anchor.x_ft.toFixed(2)}</td>
                      <td>{anchor.y_ft.toFixed(2)}</td>
                      <td>{anchor.z_ft.toFixed(2)}</td>
                      <td>
                        <button
                          className="am-del-btn"
                          onClick={event => {
                            event.stopPropagation()
                            onAnchorDelete(selectedRoom.room_name, anchor.id)
                          }}
                          title="Delete anchor"
                        >
                          x
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {selectedAnchor && (
            <div className="am-panel-section">
              <div className="am-section-label">Edit {selectedAnchor.hw_id || selectedAnchor.id}</div>

              <div className="am-edit-field">
                <label>HW ID</label>
                <input
                  className="am-input am-mono"
                  value={editFields.hw_id ?? ''}
                  onChange={event => setEditFields(prev => ({ ...prev, hw_id: event.target.value }))}
                  placeholder="A0, A1, ..."
                />
              </div>

              <div className="am-edit-grid">
                <div className="am-edit-field">
                  <label>Local X (ft)</label>
                  <input
                    className="am-input"
                    type="number"
                    step="0.01"
                    value={editFields.x_ft ?? 0}
                    onChange={event => setEditFields(prev => ({ ...prev, x_ft: parseFloat(event.target.value) || 0 }))}
                  />
                </div>
                <div className="am-edit-field">
                  <label>Local Y (ft)</label>
                  <input
                    className="am-input"
                    type="number"
                    step="0.01"
                    value={editFields.y_ft ?? 0}
                    onChange={event => setEditFields(prev => ({ ...prev, y_ft: parseFloat(event.target.value) || 0 }))}
                  />
                </div>
              </div>

              <div className="am-edit-field">
                <label>Height Z (ft)</label>
                <input
                  className="am-input"
                  type="number"
                  step="0.01"
                  min="0"
                  value={editFields.z_ft ?? 0}
                  onChange={event => setEditFields(prev => ({ ...prev, z_ft: parseFloat(event.target.value) || 0 }))}
                />
              </div>

              <button className="am-apply-btn" onClick={handleApply}>Apply Changes</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default AnchorEditPanel
