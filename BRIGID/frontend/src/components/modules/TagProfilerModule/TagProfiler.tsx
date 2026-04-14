import React, { useCallback, useEffect, useRef, useState } from 'react'
import { TagProfile } from '../../../types'
import ProfileFormSection from './ProfileFormSection'
import './TagProfiler.css'

const API = 'http://localhost:8765'

interface TagProfilerProps {
  workspaceId: string
}

const createEmptyProfile = (): TagProfile => ({
  tag_id: '',
  identity: { profile_id: '', name: '', description: '' },
  device: {
    mac_address: '',
    device_type: 'Wrist Band',
    wrist_to_floor_ft: 0,
    arm_to_floor_ft: 0,
    hip_to_floor_ft: 0,
    breast_to_floor_ft: 0,
    description: '',
  },
  calibration: { equations: { A0: '', A1: '', A2: '', A3: '' }, last_calibration_date: '', equations_enabled: false },
  notes: '',
})

const TagProfiler: React.FC<TagProfilerProps> = ({ workspaceId }) => {
  const [profile, setProfile] = useState<TagProfile>(createEmptyProfile)
  const [savedProfiles, setSavedProfiles] = useState<string[]>([])
  const [dirty, setDirty] = useState(false)
  const [status, setStatus] = useState<string>('')
  const [statusKind, setStatusKind] = useState<'ok' | 'error' | ''>('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const showStatus = (msg: string, kind: 'ok' | 'error') => {
    setStatus(msg)
    setStatusKind(kind)
    window.setTimeout(() => {
      setStatus('')
      setStatusKind('')
    }, 4000)
  }

  const loadProfileList = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/profile/list?workspace_id=${encodeURIComponent(workspaceId)}`)
      const data = await res.json()
      if (data.success) setSavedProfiles(data.profiles)
    } catch {
      // Keep the workspace usable while backend boots.
    }
  }, [workspaceId])

  useEffect(() => { loadProfileList() }, [loadProfileList])

  const handleNew = useCallback(async () => {
    if (dirty && !window.confirm('Discard unsaved changes?')) return
    try {
      const res = await fetch(`${API}/api/profile/new`, { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        setProfile(data.profile)
        setDirty(false)
        return
      }
    } catch {
      // Fall back to a local empty draft if the backend is unavailable.
    }
    setProfile(createEmptyProfile())
    setDirty(false)
  }, [dirty])

  const handleSave = useCallback(async () => {
    if (!profile.tag_id.trim()) {
      showStatus('Tag ID is required before saving.', 'error')
      return
    }
    try {
      const res = await fetch(`${API}/api/profile/save?workspace_id=${encodeURIComponent(workspaceId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile }),
      })
      const data = await res.json()
      if (data.success) {
        showStatus(`Saved: ${data.tag_id}`, 'ok')
        setDirty(false)
        loadProfileList()
      } else {
        showStatus(data.error, 'error')
      }
    } catch {
      showStatus('Could not reach backend.', 'error')
    }
  }, [profile, loadProfileList])

  const handleLoadById = useCallback(async (tagId: string) => {
    if (dirty && !window.confirm('Discard unsaved changes?')) return
    try {
      const res = await fetch(`${API}/api/profile/${encodeURIComponent(tagId)}?workspace_id=${encodeURIComponent(workspaceId)}`)
      const data = await res.json()
      if (data.success) {
        setProfile(data.profile)
        setDirty(false)
      } else {
        showStatus(data.error, 'error')
      }
    } catch {
      showStatus('Could not reach backend.', 'error')
    }
  }, [dirty, workspaceId])

  const handleDelete = useCallback(async (tagId: string) => {
    if (!window.confirm(`Delete profile "${tagId}"?`)) return
    try {
      const res = await fetch(`${API}/api/profile/${encodeURIComponent(tagId)}?workspace_id=${encodeURIComponent(workspaceId)}`, { method: 'DELETE' })
      const data = await res.json()
      if (data.success) {
        showStatus('Profile deleted.', 'ok')
        loadProfileList()
        if (profile.tag_id === tagId) {
          setProfile(createEmptyProfile())
          setDirty(false)
        }
      } else {
        showStatus(data.error, 'error')
      }
    } catch {
      showStatus('Could not reach backend.', 'error')
    }
  }, [profile.tag_id, loadProfileList])

  const handleExport = useCallback(() => {
    const blob = new Blob([JSON.stringify(profile, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${profile.tag_id || 'profile'}.json`
    a.click()
    URL.revokeObjectURL(url)
  }, [profile])

  const handleImportFile = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = ev => {
      try {
        const data = JSON.parse(ev.target?.result as string) as TagProfile
        setProfile(data)
        setDirty(true)
        showStatus(`Loaded: ${data.tag_id || file.name}`, 'ok')
      } catch {
        showStatus('Invalid profile JSON.', 'error')
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }, [])

  const handleProfileChange = useCallback((updated: TagProfile) => {
    setProfile(updated)
    setDirty(true)
  }, [])

  return (
    <div className="tp-root">
      <div className="tp-header">
        <div className="tp-header-left">
          <div className="tp-header-title">Tag Profiler</div>
          <div className="tp-header-sub">
            {profile.tag_id ? profile.tag_id : 'No profile loaded'}
            {dirty && <span className="tp-dirty-badge">*</span>}
          </div>
        </div>
        <div className="tp-header-actions">
          <button className="tp-btn tp-btn--ghost" onClick={handleNew}>New</button>
          <button className="tp-btn tp-btn--ghost" onClick={() => fileInputRef.current?.click()}>Open</button>
          <button className="tp-btn tp-btn--secondary" onClick={handleSave}>Save</button>
          <button className="tp-btn tp-btn--ghost" onClick={handleExport}>Export</button>
          <input ref={fileInputRef} type="file" accept=".json" style={{ display: 'none' }} onChange={handleImportFile} />
        </div>
      </div>

      {status && (
        <div className={`tp-status tp-status--${statusKind}`}>{status}</div>
      )}

      <div className="tp-workspace">
        <div className="tp-profiles-sidebar">
          <div className="tp-sidebar-title">Saved Profiles</div>
          <div className="tp-sidebar-count">{savedProfiles.length} loaded</div>
          {savedProfiles.length === 0
            ? <div className="tp-sidebar-empty">No saved profiles</div>
            : savedProfiles.map(pid => (
              <div key={pid} className={`tp-profile-item${profile.tag_id === pid ? ' active' : ''}`}>
                <button className="tp-profile-name" onClick={() => handleLoadById(pid)}>{pid}</button>
                <button className="tp-profile-del" onClick={() => handleDelete(pid)} title="Delete">x</button>
              </div>
            ))
          }
        </div>

        <div className="tp-main">
          <div className="tp-scroll">
            <ProfileFormSection profile={profile} onChange={handleProfileChange} />
          </div>
        </div>
      </div>
    </div>
  )
}

export default TagProfiler
