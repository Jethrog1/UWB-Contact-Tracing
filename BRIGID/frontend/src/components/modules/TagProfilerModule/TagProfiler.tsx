import React, { useCallback, useEffect, useRef, useState } from 'react'
import { TagProfile } from '../../../types'
import ProfileFormSection from './ProfileFormSection'
import { motion, AnimatePresence } from 'motion/react'
import './TagProfiler.css'

const API = 'http://localhost:8765'

const PALETTE = [
  '#4b729f', '#2b8279', '#c2823a', '#a63939', '#348550',
  '#6b46c1', '#b83280', '#c05621', '#5c8a14', '#2b6cb0'
]

const getTagColor = (str: string) => {
  if (!str) return 'var(--text-primary)'
  let hash = 0
  for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash)
  return PALETTE[Math.abs(hash) % PALETTE.length]
}

interface TagProfilerProps {
  workspaceId: string
}

interface Toast {
  id: number
  message: string
  kind: 'ok' | 'error'
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

const normalizeLoadedProfile = (raw: Partial<TagProfile> | null | undefined): TagProfile => {
  const fallback = createEmptyProfile()
  const device = raw?.device ?? {}
  const calibration = raw?.calibration ?? {}
  const equations = calibration.equations ?? {}

  const parseHeight = (value: unknown): number => {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : 0
  }

  return {
    ...fallback,
    ...raw,
    identity: {
      ...fallback.identity,
      ...(raw?.identity ?? {}),
    },
    device: {
      ...fallback.device,
      ...device,
      wrist_to_floor_ft: parseHeight(device.wrist_to_floor_ft),
      arm_to_floor_ft: parseHeight(device.arm_to_floor_ft),
      hip_to_floor_ft: parseHeight(device.hip_to_floor_ft),
      breast_to_floor_ft: parseHeight(device.breast_to_floor_ft),
    },
    calibration: {
      ...fallback.calibration,
      ...calibration,
      equations: {
        ...fallback.calibration.equations,
        ...equations,
      },
    },
    notes: raw?.notes ?? fallback.notes,
  }
}

const TagProfiler: React.FC<TagProfilerProps> = ({ workspaceId }) => {
  const [profile, setProfile] = useState<TagProfile>(createEmptyProfile)
  const [savedProfiles, setSavedProfiles] = useState<string[]>([])
  const [dirty, setDirty] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])
  const toastCounter = useRef(0)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Stable toast dispatch — lives in a ref so callbacks never go stale
  const pushToastRef = useRef((message: string, kind: 'ok' | 'error') => {})
  pushToastRef.current = (message: string, kind: 'ok' | 'error') => {
    const id = toastCounter.current++
    setToasts(prev => [...prev, { id, message, kind }])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 3000)
  }
  const pushToast = useCallback((message: string, kind: 'ok' | 'error') => {
    pushToastRef.current(message, kind)
  }, [])

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
      pushToast('Tag ID is required before saving.', 'error')
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
        pushToast(`Saved: ${data.tag_id}`, 'ok')
        setDirty(false)
        loadProfileList()
      } else {
        pushToast(data.error, 'error')
      }
    } catch {
      pushToast('Could not reach backend.', 'error')
    }
  }, [profile, loadProfileList, workspaceId])

  const handleLoadById = useCallback(async (tagId: string) => {
    if (dirty && !window.confirm('Discard unsaved changes?')) return
    try {
      const res = await fetch(`${API}/api/profile/${encodeURIComponent(tagId)}?workspace_id=${encodeURIComponent(workspaceId)}`)
      const data = await res.json()
      if (data.success) {
        setProfile(normalizeLoadedProfile(data.profile))
        setDirty(false)
      } else {
        pushToast(data.error, 'error')
      }
    } catch {
      pushToast('Could not reach backend.', 'error')
    }
  }, [dirty, workspaceId])

  const handleDelete = useCallback(async (tagId: string) => {
    if (!window.confirm(`Delete profile "${tagId}"?`)) return
    try {
      const res = await fetch(`${API}/api/profile/${encodeURIComponent(tagId)}?workspace_id=${encodeURIComponent(workspaceId)}`, { method: 'DELETE' })
      const data = await res.json()
      if (data.success) {
        pushToast('Profile deleted.', 'error')
        // Always reset to blank form so fields are unlocked
        setProfile(createEmptyProfile())
        setDirty(false)
        loadProfileList()
      } else {
        pushToast(data.error, 'error')
      }
    } catch {
      pushToast('Could not reach backend.', 'error')
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadProfileList, workspaceId])

  const handleImportFile = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = ev => {
      try {
        const data = JSON.parse(ev.target?.result as string) as TagProfile
        setProfile(normalizeLoadedProfile(data))
        setDirty(true)
        pushToast(`Loaded: ${data.tag_id || file.name}`, 'ok')
      } catch {
        pushToast('Invalid profile JSON.', 'error')
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
      {/* Floating toast notifications */}
      <div className="tp-toast-container">
        <AnimatePresence>
          {toasts.map(toast => (
            <motion.div
              key={toast.id}
              className={`tp-toast tp-toast--${toast.kind}`}
              initial={{ x: 80, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 80, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 380, damping: 32 }}
            >
              <span className="tp-toast-dot" />
              {toast.message}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      <div className="tp-header">
        <div className="tp-header-left">
          <div className="tp-header-title">Profile Manager</div>
          {dirty && <span className="tp-dirty-badge"> *</span>}
        </div>
        <div className="tp-header-actions">
          <button className="tp-btn tp-btn--outline" onClick={handleNew}>New</button>
          <button className="tp-btn tp-btn--outline" onClick={() => fileInputRef.current?.click()}>Open</button>
          <button className="tp-btn tp-btn--primary" onClick={handleSave}>Save</button>
          <input ref={fileInputRef} type="file" accept=".json" style={{ display: 'none' }} onChange={handleImportFile} />
        </div>
      </div>

      <div className="tp-workspace">
        <div className="tp-profiles-sidebar">
          <div className="tp-sidebar-title">Profiles</div>
          {savedProfiles.length === 0
            ? <div className="tp-sidebar-empty">None</div>
            : savedProfiles.map(pid => (
              <div key={pid} className={`tp-profile-item${profile.tag_id === pid ? ' active' : ''}`}>
                <button
                  className="tp-profile-name"
                  onClick={() => handleLoadById(pid)}
                  style={{ color: getTagColor(pid), fontWeight: profile.tag_id === pid ? 700 : 400 }}
                >
                  {pid}
                </button>
                <button className="tp-profile-del" onClick={() => handleDelete(pid)} title="Delete">×</button>
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
