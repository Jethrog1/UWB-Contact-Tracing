import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AppModule } from '../../types'
import './HotBar.css'

const GITHUB_URL = 'https://github.com/Jethrog1/UWB-Contact-Tracing'

const BLE_TAG_PALETTE = [
  '#4b729f', '#2b8279', '#c2823a', '#a63939', '#348550',
  '#6b46c1', '#b83280', '#c05621', '#5c8a14', '#2b6cb0',
]

const getTagColor = (str: string): string => {
  if (!str) return 'var(--text-primary)'
  let hash = 0
  for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash)
  return BLE_TAG_PALETTE[Math.abs(hash) % BLE_TAG_PALETTE.length]
}

const bleStatusColor = (status: string): string => {
  const s = (status || '').toLowerCase()
  if (s.includes('connected') && !s.includes('disconnect')) return '#42d17e'
  if (s.includes('connecting')) return '#ffb11f'
  return '#ff5b4d'
}

interface BleIdleTag {
  tag_id: string
  mac_address: string
  status: string
}

type MenuAction =
  | 'new-workspace'
  | 'open-workspace'
  | 'save'
  | 'save-as'
  | 'close-tab'
  | 'edit-undo'
  | 'edit-redo'
  | 'view-zoom-in'
  | 'view-zoom-out'
  | 'view-zoom-reset'
  | 'anchor-tool-cursor'
  | 'anchor-tool-select'
  | 'anchor-tool-smart-select'
  | 'cad-tool-cursor'
  | 'cad-tool-line'
  | 'cad-tool-vertex'
  | 'cad-tool-dim'
  | 'cad-tool-rotate'
  | 'cad-tool-trim'
  | 'ble-idle-toggle'
  | 'rtls-quick-setup'
  | null

interface MenuItem {
  label: string
  shortcut?: string
  separator?: boolean
  disabled?: boolean
  action?: MenuAction
  checked?: boolean
}

interface MenuEntry {
  label: string
  items?: MenuItem[]
  href?: string
}

interface HotBarProps {
  activeModule: AppModule | null
  hasWorkspace: boolean
  onNewWorkspace: () => void
  onOpenWorkspace: () => void
  onSave: () => void
  onSaveAs: () => void
  onCloseTab: () => void
  onViewCommand?: (cmd: 'zoom_in' | 'zoom_out' | 'zoom_reset') => void
  onEditCommand?: (cmd: 'undo' | 'redo') => void
  onAnchorToolSelect?: (tool: 'cursor' | 'select' | 'smartSelect') => void
  onCadToolSelect?: (tool: 'cursor' | 'line' | 'vertex' | 'dim' | 'rotate' | 'trim') => void
  bleIdleEnabled?: boolean
  bleIdleAvailable?: boolean
  bleIdleTags?: BleIdleTag[]
  bleIdleDetail?: string
  onBleIdleToggle?: () => void
  onRtlsQuickSetup?: () => void
}

const buildMenus = (
  hasWorkspace: boolean,
  activeModule: AppModule | null,
): MenuEntry[] => {
  const editEnabledModules: AppModule[] = ['cad', 'anchors']
  const viewEnabledModules: AppModule[] = ['calibration', 'cad', 'anchors', 'rtls']
  const editEnabled = hasWorkspace && activeModule !== null && editEnabledModules.includes(activeModule)
  const viewEnabled = hasWorkspace && activeModule !== null && viewEnabledModules.includes(activeModule)

  let toolsItems: MenuItem[]
  if (activeModule === 'cad') {
    toolsItems = [
      { label: 'Cursor Tool', shortcut: 'V', action: 'cad-tool-cursor', disabled: !hasWorkspace },
      { label: 'Line Tool', shortcut: 'L', action: 'cad-tool-line', disabled: !hasWorkspace },
      { label: 'Vertex Manipulate', shortcut: 'N', action: 'cad-tool-vertex', disabled: !hasWorkspace },
      { label: 'Dimension Tool', shortcut: 'D', action: 'cad-tool-dim', disabled: !hasWorkspace },
      { separator: true, label: '' },
      { label: 'Rotate Selection', action: 'cad-tool-rotate', disabled: !hasWorkspace },
      { label: 'Trim Line', action: 'cad-tool-trim', disabled: !hasWorkspace },
    ]
  } else if (activeModule === 'anchors') {
    toolsItems = [
      { label: 'Cursor', shortcut: 'C', action: 'anchor-tool-cursor', disabled: !hasWorkspace },
      { label: 'Select', shortcut: 'Shift+Click', action: 'anchor-tool-select', disabled: !hasWorkspace },
      { label: 'Smart Select', shortcut: 'Ctrl+Shift+Click', action: 'anchor-tool-smart-select', disabled: !hasWorkspace },
    ]
  } else if (activeModule === 'rtls') {
    toolsItems = [
      { label: 'Quick Setup', shortcut: 'Ctrl+Q', action: 'rtls-quick-setup', disabled: !hasWorkspace },
    ]
  } else {
    toolsItems = [
      { label: 'No tools available', disabled: true },
    ]
  }

  return [
    {
      label: 'File',
      items: [
        { label: 'New Workspace', shortcut: 'Ctrl+N', action: 'new-workspace' },
        { label: 'Open Workspace...', shortcut: 'Ctrl+O', action: 'open-workspace' },
        { separator: true, label: '' },
        { label: 'Save', shortcut: 'Ctrl+S', action: 'save', disabled: !hasWorkspace },
        { label: 'Save As...', shortcut: 'Ctrl+Shift+S', action: 'save-as', disabled: !hasWorkspace },
        { separator: true, label: '' },
        { label: 'Close Workspace', shortcut: 'Ctrl+W', action: 'close-tab', disabled: !hasWorkspace },
      ],
    },
    {
      label: 'Edit',
      items: [
        { label: 'Undo', shortcut: 'Ctrl+Z', action: 'edit-undo', disabled: !editEnabled },
        { label: 'Redo', shortcut: 'Ctrl+Y', action: 'edit-redo', disabled: !editEnabled },
      ],
    },
    {
      label: 'View',
      items: [
        { label: 'Zoom In', shortcut: 'Ctrl+=', action: 'view-zoom-in', disabled: !viewEnabled },
        { label: 'Zoom Out', shortcut: 'Ctrl+-', action: 'view-zoom-out', disabled: !viewEnabled },
        { label: 'Reset View', shortcut: 'Ctrl+0', action: 'view-zoom-reset', disabled: !viewEnabled },
      ],
    },
    {
      label: 'Tools',
      items: toolsItems,
    },
    {
      label: 'BLE',
      items: [],
    },
    {
      label: 'Help',
      href: GITHUB_URL,
    },
  ]
}

const HotBar: React.FC<HotBarProps> = ({
  activeModule,
  hasWorkspace,
  onNewWorkspace,
  onOpenWorkspace,
  onSave,
  onSaveAs,
  onCloseTab,
  onViewCommand,
  onEditCommand,
  onAnchorToolSelect,
  onCadToolSelect,
  bleIdleEnabled = false,
  bleIdleAvailable = true,
  bleIdleTags = [],
  bleIdleDetail = '',
  onBleIdleToggle,
  onRtlsQuickSetup,
}) => {
  const [openMenu, setOpenMenu] = useState<string | null>(null)
  const [dropdownPos, setDropdownPos] = useState<{ left: number; top: number } | null>(null)
  const barRef = useRef<HTMLDivElement>(null)
  const buttonRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const dropdownRef = useRef<HTMLDivElement>(null)
  const menus = buildMenus(hasWorkspace, activeModule)

  const positionDropdown = useCallback((label: string) => {
    const btn = buttonRefs.current[label]
    if (!btn) {
      setDropdownPos(null)
      return
    }
    const rect = btn.getBoundingClientRect()
    setDropdownPos({ left: rect.left, top: rect.bottom + 2 })
  }, [])

  useLayoutEffect(() => {
    if (openMenu) positionDropdown(openMenu)
  }, [openMenu, positionDropdown])

  useEffect(() => {
    if (!openMenu) return
    const handleReposition = () => positionDropdown(openMenu)
    window.addEventListener('resize', handleReposition)
    window.addEventListener('scroll', handleReposition, true)
    return () => {
      window.removeEventListener('resize', handleReposition)
      window.removeEventListener('scroll', handleReposition, true)
    }
  }, [openMenu, positionDropdown])

  useEffect(() => {
    const handleClick = (event: MouseEvent) => {
      const target = event.target as Node
      if (barRef.current?.contains(target)) return
      if (dropdownRef.current?.contains(target)) return
      setOpenMenu(null)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const toggleMenu = (label: string) => {
    setOpenMenu(current => (current === label ? null : label))
  }

  const openHelpLink = () => {
    setOpenMenu(null)
    window.open(GITHUB_URL, '_blank', 'noopener,noreferrer')
  }

  const runAction = (action: MenuAction) => {
    if (action === 'new-workspace') onNewWorkspace()
    else if (action === 'open-workspace') onOpenWorkspace()
    else if (action === 'save') onSave()
    else if (action === 'save-as') onSaveAs()
    else if (action === 'close-tab') onCloseTab()
    else if (action === 'edit-undo') onEditCommand?.('undo')
    else if (action === 'edit-redo') onEditCommand?.('redo')
    else if (action === 'view-zoom-in') onViewCommand?.('zoom_in')
    else if (action === 'view-zoom-out') onViewCommand?.('zoom_out')
    else if (action === 'view-zoom-reset') onViewCommand?.('zoom_reset')
    else if (action === 'anchor-tool-cursor') onAnchorToolSelect?.('cursor')
    else if (action === 'anchor-tool-select') onAnchorToolSelect?.('select')
    else if (action === 'anchor-tool-smart-select') onAnchorToolSelect?.('smartSelect')
    else if (action === 'cad-tool-cursor') onCadToolSelect?.('cursor')
    else if (action === 'cad-tool-line') onCadToolSelect?.('line')
    else if (action === 'cad-tool-vertex') onCadToolSelect?.('vertex')
    else if (action === 'cad-tool-dim') onCadToolSelect?.('dim')
    else if (action === 'cad-tool-rotate') onCadToolSelect?.('rotate')
    else if (action === 'cad-tool-trim') onCadToolSelect?.('trim')
    else if (action === 'ble-idle-toggle') onBleIdleToggle?.()
    else if (action === 'rtls-quick-setup') onRtlsQuickSetup?.()
    setOpenMenu(null)
  }

  const activeMenu = openMenu ? menus.find(m => m.label === openMenu) : null
  const activeItems = activeMenu?.items ?? []

  return (
    <div className="hot-bar electron-drag" ref={barRef}>
      <div className="hot-bar__brand electron-no-drag">
        <span className="hot-bar__brand-name">BRIGID</span>
      </div>

      <nav className="hot-bar__menus electron-no-drag">
        {menus.map(menu => {
          if (menu.href) {
            return (
              <div key={menu.label} className="hot-bar__menu-root">
                <button
                  type="button"
                  ref={el => { buttonRefs.current[menu.label] = el }}
                  className="hot-bar__menu-btn"
                  onMouseEnter={() => setOpenMenu(null)}
                  onClick={openHelpLink}
                  title={`Open ${menu.href}`}
                >
                  {menu.label}
                </button>
              </div>
            )
          }

          return (
            <div key={menu.label} className="hot-bar__menu-root">
              <button
                type="button"
                ref={el => { buttonRefs.current[menu.label] = el }}
                className={`hot-bar__menu-btn ${openMenu === menu.label ? 'hot-bar__menu-btn--open' : ''}`}
                onClick={() => toggleMenu(menu.label)}
                onMouseEnter={() => setOpenMenu(menu.label)}
              >
                {menu.label}
              </button>
            </div>
          )
        })}
      </nav>

      <div className="hot-bar__spacer" />

      {activeMenu && dropdownPos && createPortal(
        <div
          ref={dropdownRef}
          className={`hot-bar__dropdown electron-no-drag ${openMenu === 'BLE' ? 'hot-bar__dropdown--ble' : ''}`}
          role="menu"
          style={{ position: 'fixed', left: dropdownPos.left, top: dropdownPos.top }}
        >
          {openMenu === 'BLE' ? (
            <div className="hot-bar__ble-panel">
              <div className="hot-bar__ble-header-row">
                <span className="hot-bar__ble-toggle-label">Active BLE Idle</span>
              </div>
              {bleIdleDetail && (
                <div className="hot-bar__ble-note">{bleIdleDetail}</div>
              )}
              {bleIdleTags.length > 0 ? (
                <div className="hot-bar__ble-rows">
                  {bleIdleTags.map(tag => (
                    <div key={tag.tag_id} className="hot-bar__ble-row">
                      <span className="hot-bar__ble-row-name">
                        <span
                          className="hot-bar__ble-dot"
                          style={{ background: getTagColor(tag.tag_id) }}
                        />
                        {tag.tag_id}
                      </span>
                      <span
                        className="hot-bar__ble-row-status"
                        style={{ color: bleStatusColor(tag.status) }}
                      >
                        {tag.status}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="hot-bar__ble-empty">
                  {bleIdleEnabled ? 'Waiting for tags…' : 'No tags configured.'}
                </div>
              )}
              <button
                type="button"
                className={`hot-bar__ble-btn ${bleIdleEnabled ? 'hot-bar__ble-btn--ghost' : 'hot-bar__ble-btn--primary'}`}
                disabled={!bleIdleAvailable}
                onClick={() => {
                  if (bleIdleAvailable) onBleIdleToggle?.()
                }}
              >
                {bleIdleEnabled ? 'Disconnect' : 'Connect'}
              </button>
            </div>
          ) : (
            activeItems.map((item, index) =>
              item.separator ? (
                <div key={index} className="hot-bar__dropdown-sep" />
              ) : (
                <button
                  type="button"
                  key={index}
                  className={`hot-bar__dropdown-item electron-no-drag ${item.disabled ? 'hot-bar__dropdown-item--disabled' : ''}`}
                  role="menuitem"
                  onMouseDown={event => {
                    event.preventDefault()
                    if (!item.disabled) runAction(item.action ?? null)
                  }}
                  onKeyDown={event => {
                    if ((event.key === 'Enter' || event.key === ' ') && !item.disabled) {
                      event.preventDefault()
                      runAction(item.action ?? null)
                    }
                  }}
                >
                  <span className="hot-bar__dropdown-label">
                    {item.checked !== undefined && (
                      <span className="hot-bar__dropdown-check" aria-hidden="true">
                        {item.checked ? '\u2713' : '\u00A0'}
                      </span>
                    )}
                    {item.label}
                  </span>
                  {item.shortcut && <span className="hot-bar__dropdown-shortcut">{item.shortcut}</span>}
                </button>
              )
            )
          )}
        </div>,
        document.body
      )}
    </div>
  )
}

export default HotBar
