import React, { useEffect, useMemo, useRef, useState } from 'react'
import { AnchorData, RoomData } from '../../../types'
import RoomViewCanvas, { RoomViewCanvasHandle } from './RoomViewCanvas'

export type AnchorPanelPage = 'rooms' | 'room-detail'

interface Props {
  rooms: RoomData[]
  selectedRoomName: string | null
  selectedAnchorId: string | null
  hoverRoomName: string | null
  panelPage: AnchorPanelPage
  serialPorts: string[]
  autoDetectPort: string
  serialPortsLoading: boolean
  externalPreview: { roomName: string; localX: number; localY: number } | null
  onPageChange: (page: AnchorPanelPage) => void
  onRoomSelect: (roomName: string | null) => void
  onRoomHover: (roomName: string | null) => void
  onRoomDoubleClick: (roomName: string) => void
  onAnchorUpdate: (roomName: string, anchorId: string, patch: Partial<AnchorData>) => void
  onAnchorDelete: (roomName: string, anchorId: string) => void
  onAnchorSelect: (anchorId: string | null) => void
  onAnchorPlace: (roomName: string, localX: number, localY: number) => void
  onAnchorMoveStart: (roomName: string, anchorId: string) => void
  onAnchorMove: (roomName: string, anchorId: string, localX: number, localY: number) => void
  onAnchorMoveEnd: () => void
  onEdgesUpdate?: (roomName: string, nextEdges: [string, string][]) => void
  onReferenceAnchorChange: (roomName: string, referenceAnchorId: string | null) => void
  onRefreshSerialPorts: () => void
  onRoomSettingsUpdate: (roomName: string, patch: Partial<RoomData['rtls_settings']>) => void
  onSetAllAnchorZ: (roomName: string, zValue: number) => void
}

const AnchorEditPanelImpl: React.FC<Props> = ({
  rooms,
  selectedRoomName,
  selectedAnchorId,
  hoverRoomName,
  panelPage,
  serialPorts,
  autoDetectPort,
  serialPortsLoading,
  externalPreview,
  onPageChange,
  onRoomSelect,
  onRoomHover,
  onRoomDoubleClick,
  onAnchorUpdate,
  onAnchorDelete,
  onAnchorSelect,
  onAnchorPlace,
  onAnchorMoveStart,
  onAnchorMove,
  onAnchorMoveEnd,
  onReferenceAnchorChange,
  onRefreshSerialPorts,
  onRoomSettingsUpdate,
  onSetAllAnchorZ,
}) => {
  const [editFields, setEditFields] = useState<Partial<AnchorData>>({})
  const [universalZByRoom, setUniversalZByRoom] = useState<Record<string, { active: boolean; value: string }>>({})
  const roomCanvasRef = useRef<RoomViewCanvasHandle>(null)
  const hwIdInputRef = useRef<HTMLInputElement>(null)

  const selectedRoom = rooms.find(room => room.room_name === selectedRoomName) ?? null
  const selectedAnchor = selectedRoom?.anchors.find(anchor => anchor.id === selectedAnchorId) ?? null
  const universalZ = selectedRoom ? universalZByRoom[selectedRoom.room_name] ?? { active: false, value: '' } : { active: false, value: '' }
  const zLocked = universalZ.active

  const canGoBack = panelPage === 'room-detail'
  const canGoForward = panelPage === 'rooms' && selectedRoom !== null

  const applyUniversalZ = (roomName: string, rawValue: string) => {
    setUniversalZByRoom(prev => ({ ...prev, [roomName]: { active: true, value: rawValue } }))
    const parsed = parseFloat(rawValue)
    if (!Number.isNaN(parsed)) {
      onSetAllAnchorZ(roomName, parsed)
    }
  }

  const toggleUniversalZ = (roomName: string) => {
    setUniversalZByRoom(prev => {
      const current = prev[roomName] ?? { active: false, value: '' }
      const next = { ...current, active: !current.active }
      if (next.active && next.value.trim() !== '') {
        const parsed = parseFloat(next.value)
        if (!Number.isNaN(parsed)) onSetAllAnchorZ(roomName, parsed)
      }
      return { ...prev, [roomName]: next }
    })
  }

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

  useEffect(() => {
    if (panelPage === 'room-detail' && selectedAnchor) {
      const t = window.setTimeout(() => hwIdInputRef.current?.focus({ preventScroll: true }), 60)
      return () => window.clearTimeout(t)
    }
  }, [panelPage, selectedAnchor?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const savedPort = selectedRoom?.rtls_settings?.ble_module_port ?? ''
  const portOptions = useMemo(() => {
    const values = new Set<string>(serialPorts.filter(Boolean))
    if (autoDetectPort) values.add(autoDetectPort)
    if (savedPort) values.add(savedPort)
    return Array.from(values)
  }, [autoDetectPort, savedPort, serialPorts])

  const handleApply = () => {
    if (!selectedRoom || !selectedAnchor) return
    onAnchorUpdate(selectedRoom.room_name, selectedAnchor.id, editFields)
  }

  const handleBack = () => {
    if (canGoBack) onPageChange('rooms')
  }

  const handleForward = () => {
    if (canGoForward) onPageChange('room-detail')
  }

  const title = panelPage === 'room-detail' && selectedRoom
    ? selectedRoom.room_name
    : 'Room Manager'

  return (
    <div className="am-floating-panel">
      <div className="am-floating-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <button
            className="am-nav-btn"
            onClick={handleBack}
            disabled={!canGoBack}
            title="Back to Room Manager"
            aria-label="Back"
          >
            {'\u2190'}
          </button>
          <button
            className="am-nav-btn"
            onClick={handleForward}
            disabled={!canGoForward}
            title={selectedRoom ? `Open ${selectedRoom.room_name}` : 'Select a room to open its detail view'}
            aria-label="Forward"
          >
            {'\u2192'}
          </button>
          <div className="am-floating-title" style={{ marginLeft: 4 }}>{title}</div>
        </div>
      </div>

      {panelPage === 'rooms' && (
        <>
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
                <div className="am-panel-meta">COM Port: {selectedRoom.rtls_settings?.ble_module_port || '—'}</div>
                <button
                  className="am-btn am-btn--secondary"
                  style={{ marginTop: 8, width: '100%' }}
                  onClick={() => onPageChange('room-detail')}
                >
                  Open Room Detail →
                </button>
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
                      {anchor.id}{anchor.hw_id ? ` (HW ${anchor.hw_id})` : ''}
                    </option>
                  ))}
                </select>
              </div>

              <div className="am-panel-section am-anchor-list-section">
                <div className="am-section-label">Anchors</div>
                {selectedRoom.anchors.length === 0 ? (
                  <div className="am-panel-empty">Open Room Detail and Ctrl+Click to place anchors.</div>
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
                  <div className="am-section-label">Edit {selectedAnchor.id}</div>

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
        </>
      )}

      {panelPage === 'room-detail' && !selectedRoom && (
        <div className="am-panel-section">
          <div className="am-panel-empty">No room selected. Go back to pick one.</div>
        </div>
      )}

      {panelPage === 'room-detail' && selectedRoom && (
        <>
          <div className="am-panel-section">
            <div className="am-panel-meta">
              {selectedRoom.room_bounds_ft.width.toFixed(1)} × {selectedRoom.room_bounds_ft.height.toFixed(1)} ft
              &nbsp;·&nbsp;{selectedRoom.anchors.length} anchor{selectedRoom.anchors.length !== 1 ? 's' : ''}
              &nbsp;·&nbsp;Ref: {selectedRoom.reference_anchor_id ?? '—'}
            </div>
            <div className="am-panel-hint" style={{ marginTop: 6 }}>
              Hold Ctrl and click to place an anchor · Click an anchor to select · Drag to move · Scroll to zoom
            </div>
            <div className="am-panel-room-canvas">
              <RoomViewCanvas
                ref={roomCanvasRef}
                room={selectedRoom}
                selectedAnchorId={selectedAnchorId}
                externalPreview={externalPreview && externalPreview.roomName === selectedRoom.room_name
                  ? { localX: externalPreview.localX, localY: externalPreview.localY }
                  : null}
                onAnchorSelect={onAnchorSelect}
                onAnchorPlace={(localX, localY) => onAnchorPlace(selectedRoom.room_name, localX, localY)}
                onAnchorMoveStart={anchorId => onAnchorMoveStart(selectedRoom.room_name, anchorId)}
                onAnchorMove={(anchorId, localX, localY) => onAnchorMove(selectedRoom.room_name, anchorId, localX, localY)}
                onAnchorMoveEnd={onAnchorMoveEnd}
              />
            </div>
            <button
              className="am-mini-btn"
              style={{ width: '100%' }}
              onClick={() => roomCanvasRef.current?.fitView()}
              title="Fit view (F)"
            >
              Fit View
            </button>
          </div>

          <div className="am-panel-section">
            <div className="am-section-label">COM Port</div>
            <div style={{ display: 'flex', gap: 6 }}>
              <select
                className="am-input"
                style={{ flex: 1 }}
                value={savedPort}
                onChange={event => onRoomSettingsUpdate(selectedRoom.room_name, { ble_module_port: event.target.value })}
              >
                <option value="">No saved COM port</option>
                {portOptions.map(port => (
                  <option key={port} value={port}>{port}</option>
                ))}
              </select>
              <button
                className="am-mini-btn"
                onClick={onRefreshSerialPorts}
                disabled={serialPortsLoading}
              >
                {serialPortsLoading ? '…' : 'Refresh'}
              </button>
            </div>
            <div className="am-panel-hint" style={{ marginTop: 6 }}>
              {autoDetectPort
                ? `Auto-detect available: ${autoDetectPort}`
                : 'No auto-detected serial module found right now.'}
            </div>
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
                  {anchor.id}{anchor.hw_id ? ` (HW ${anchor.hw_id})` : ''}
                </option>
              ))}
            </select>
          </div>

          <div className="am-panel-section am-anchor-list-section">
            <div className="am-section-label">Anchors</div>
            {selectedRoom.anchors.length === 0 ? (
              <div className="am-panel-empty">Ctrl+Click inside the room outline to place an anchor.</div>
            ) : (
              <table className="am-anchor-table">
                <thead>
                  <tr><th>ID</th><th>HW ID</th><th>X (ft)</th><th>Y (ft)</th><th>Z (ft)</th><th /></tr>
                </thead>
                <tbody>
                  {selectedRoom.anchors.map(anchor => (
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
                          onClick={e => {
                            e.stopPropagation()
                            onAnchorDelete(selectedRoom.room_name, anchor.id)
                          }}
                        >×</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <div className="am-universal-z">
              <div className="am-universal-z-row">
                <span className="am-universal-z-label">Universal z (ft) Height</span>
                <label className="am-toggle" title={universalZ.active ? 'Universal z is active' : 'Enable to apply one z value to all anchors'}>
                  <input
                    type="checkbox"
                    checked={universalZ.active}
                    onChange={() => toggleUniversalZ(selectedRoom.room_name)}
                  />
                  <span className="am-toggle-slider" />
                </label>
                <input
                  className="am-input am-universal-z-input"
                  type="number"
                  step="0.01"
                  placeholder="ft"
                  value={universalZ.value}
                  disabled={!universalZ.active}
                  onChange={event => applyUniversalZ(selectedRoom.room_name, event.target.value)}
                />
              </div>
            </div>
          </div>

          {selectedAnchor && (
            <div className="am-panel-section">
              <div className="am-section-label">Edit {selectedAnchor.id}</div>
              <div className="am-edit-field">
                <label>HW ID</label>
                <input
                  ref={hwIdInputRef}
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
                <label>Height Z (ft){zLocked ? ' · locked by Universal z' : ''}</label>
                <input
                  className="am-input"
                  type="number"
                  step="0.01"
                  min="0"
                  value={editFields.z_ft ?? 0}
                  disabled={zLocked}
                  title={zLocked ? 'Universal z Height is active — deactivate to edit per-anchor z' : undefined}
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

const AnchorEditPanel = React.memo(AnchorEditPanelImpl)
export default AnchorEditPanel
