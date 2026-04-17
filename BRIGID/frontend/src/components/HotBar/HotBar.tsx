import React, { useEffect, useRef, useState } from 'react'
import { AppModule } from '../../types'
import './HotBar.css'

type MenuAction =
  | 'new-workspace'
  | 'open-workspace'
  | 'save'
  | 'save-as'
  | 'close-tab'
  | 'anchor-tool-cursor'
  | 'anchor-tool-select'
  | 'anchor-tool-smart-select'
  | null

interface MenuItem {
  label: string
  shortcut?: string
  separator?: boolean
  disabled?: boolean
  action?: MenuAction
}

interface MenuEntry {
  label: string
  items: MenuItem[]
}

interface HotBarProps {
  activeModule: AppModule | null
  hasWorkspace: boolean
  onNewWorkspace: () => void
  onOpenWorkspace: () => void
  onSave: () => void
  onSaveAs: () => void
  onCloseTab: () => void
  onAnchorToolSelect?: (tool: 'cursor' | 'select' | 'smartSelect') => void
}

const buildMenus = (hasWorkspace: boolean, activeModule: AppModule | null): MenuEntry[] => [
  {
    label: 'File',
    items: [
      { label: 'New Workspace', shortcut: 'Ctrl+N', action: 'new-workspace' },
      { label: 'Open Workspace...', shortcut: 'Ctrl+O', action: 'open-workspace' },
      { separator: true, label: '' },
      { label: 'Save', shortcut: 'Ctrl+S', action: 'save', disabled: !hasWorkspace },
      { label: 'Save As...', shortcut: 'Ctrl+Shift+S', action: 'save-as', disabled: !hasWorkspace },
      { separator: true, label: '' },
      { label: 'Import SVG Floor Plan...', disabled: true },
      { separator: true, label: '' },
      { label: 'Close Workspace', shortcut: 'Ctrl+W', action: 'close-tab', disabled: !hasWorkspace },
    ],
  },
  {
    label: 'Edit',
    items: [
      { label: 'Undo', shortcut: 'Ctrl+Z', disabled: true },
      { label: 'Redo', shortcut: 'Ctrl+Y', disabled: true },
      { separator: true, label: '' },
      { label: 'Cut', shortcut: 'Ctrl+X', disabled: true },
      { label: 'Copy', shortcut: 'Ctrl+C', disabled: true },
      { label: 'Paste', shortcut: 'Ctrl+V', disabled: true },
      { separator: true, label: '' },
      { label: 'Select All', shortcut: 'Ctrl+A', disabled: true },
      { label: 'Delete Selected', shortcut: 'Del', disabled: true },
    ],
  },
  {
    label: 'View',
    items: [
      { label: 'Zoom In', shortcut: 'Ctrl+=', disabled: true },
      { label: 'Zoom Out', shortcut: 'Ctrl+-', disabled: true },
      { label: 'Zoom Reset', shortcut: 'Ctrl+0', disabled: true },
    ],
  },
  {
    label: 'Tools',
    items: activeModule === 'anchors'
      ? [
          { label: 'Cursor', shortcut: 'C', action: 'anchor-tool-cursor', disabled: !hasWorkspace },
          { label: 'Select', shortcut: 'Hold Shift+Click', action: 'anchor-tool-select', disabled: !hasWorkspace },
          { label: 'Smart Select', shortcut: 'Hold Ctrl+Shift+Click', action: 'anchor-tool-smart-select', disabled: !hasWorkspace },
        ]
      : [
          { label: 'Cursor Tool', shortcut: 'V', disabled: true },
          { label: 'Line Tool', shortcut: 'L', disabled: true },
          { label: 'Dimension Tool', shortcut: 'D', disabled: true },
          { label: 'Vertex Manipulate', shortcut: 'N', disabled: true },
          { separator: true, label: '' },
          { label: 'Rotate Selection', disabled: true },
          { label: 'Trim Line', disabled: true },
        ],
  },
  {
    label: 'Window',
    items: [
      { label: 'Minimize', shortcut: 'Win+Down', disabled: true },
      { label: 'Maximize / Restore', disabled: true },
      { separator: true, label: '' },
      { label: 'BRIGID Dashboard', disabled: true },
    ],
  },
  {
    label: 'Help',
    items: [
      { label: 'BRIGID Documentation', disabled: true },
      { label: 'Keyboard Shortcuts', disabled: true },
      { separator: true, label: '' },
      { label: 'About BRIGID', disabled: true },
    ],
  },
]

const HotBar: React.FC<HotBarProps> = ({
  activeModule,
  hasWorkspace,
  onNewWorkspace,
  onOpenWorkspace,
  onSave,
  onSaveAs,
  onCloseTab,
  onAnchorToolSelect,
}) => {
  const [openMenu, setOpenMenu] = useState<string | null>(null)
  const barRef = useRef<HTMLDivElement>(null)
  const menus = buildMenus(hasWorkspace, activeModule)

  useEffect(() => {
    const handleClick = (event: MouseEvent) => {
      if (barRef.current && !barRef.current.contains(event.target as Node)) {
        setOpenMenu(null)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const toggleMenu = (label: string) => {
    setOpenMenu(current => (current === label ? null : label))
  }

  const runAction = (action: MenuAction) => {
    if (action === 'new-workspace') onNewWorkspace()
    if (action === 'open-workspace') onOpenWorkspace()
    if (action === 'save') onSave()
    if (action === 'save-as') onSaveAs()
    if (action === 'close-tab') onCloseTab()
    if (action === 'anchor-tool-cursor') onAnchorToolSelect?.('cursor')
    if (action === 'anchor-tool-select') onAnchorToolSelect?.('select')
    if (action === 'anchor-tool-smart-select') onAnchorToolSelect?.('smartSelect')
    setOpenMenu(null)
  }

  return (
    <div className="hot-bar electron-drag" ref={barRef}>
      <div className="hot-bar__brand electron-no-drag">
        <span className="hot-bar__brand-name">BRIGID</span>
      </div>

      <nav className="hot-bar__menus electron-no-drag">
        {menus.map(menu => (
          <div key={menu.label} className="hot-bar__menu-root">
            <button
              type="button"
              className={`hot-bar__menu-btn ${openMenu === menu.label ? 'hot-bar__menu-btn--open' : ''}`}
              onClick={() => toggleMenu(menu.label)}
              onMouseEnter={() => openMenu !== null && setOpenMenu(menu.label)}
            >
              {menu.label}
            </button>
            {openMenu === menu.label && (
              <div className="hot-bar__dropdown electron-no-drag" role="menu">
                {menu.items.map((item, index) =>
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
                      <span className="hot-bar__dropdown-label">{item.label}</span>
                      {item.shortcut && <span className="hot-bar__dropdown-shortcut">{item.shortcut}</span>}
                    </button>
                  )
                )}
              </div>
            )}
          </div>
        ))}
      </nav>

      <div className="hot-bar__spacer" />
    </div>
  )
}

export default HotBar
