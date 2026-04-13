import React, { useState, useRef, useEffect } from 'react'
import { Icon } from '@blueprintjs/core'
import './HotBar.css'

interface MenuEntry {
  label: string
  items: { label: string; shortcut?: string; separator?: boolean; disabled?: boolean }[]
}

const MENUS: MenuEntry[] = [
  {
    label: 'File',
    items: [
      { label: 'New Workspace', shortcut: 'Ctrl+N' },
      { label: 'Open Project...', shortcut: 'Ctrl+O' },
      { separator: true, label: '' },
      { label: 'Save', shortcut: 'Ctrl+S' },
      { label: 'Save As...', shortcut: 'Ctrl+Shift+S' },
      { separator: true, label: '' },
      { label: 'Import SVG Floor Plan...' },
      { label: 'Export as PNG...' },
      { label: 'Export as SVG...' },
      { separator: true, label: '' },
      { label: 'Close Tab', shortcut: 'Ctrl+W' },
      { label: 'Close Project' },
    ],
  },
  {
    label: 'Edit',
    items: [
      { label: 'Undo', shortcut: 'Ctrl+Z' },
      { label: 'Redo', shortcut: 'Ctrl+Y' },
      { separator: true, label: '' },
      { label: 'Cut', shortcut: 'Ctrl+X' },
      { label: 'Copy', shortcut: 'Ctrl+C' },
      { label: 'Paste', shortcut: 'Ctrl+V' },
      { separator: true, label: '' },
      { label: 'Select All', shortcut: 'Ctrl+A' },
      { label: 'Delete Selected', shortcut: 'Del' },
    ],
  },
  {
    label: 'View',
    items: [
      { label: 'Zoom In', shortcut: 'Ctrl+=' },
      { label: 'Zoom Out', shortcut: 'Ctrl+-' },
      { label: 'Zoom Reset', shortcut: 'Ctrl+0' },
      { separator: true, label: '' },
      { label: 'Toggle Feature Manager' },
      { label: 'Toggle Right Panel' },
      { separator: true, label: '' },
      { label: 'Snap Axis', shortcut: '' },
      { label: 'Line Match', shortcut: '' },
    ],
  },
  {
    label: 'Tools',
    items: [
      { label: 'Cursor Tool', shortcut: 'Esc' },
      { label: 'Line Tool', shortcut: 'L' },
      { label: 'Dimension Tool', shortcut: 'D' },
      { label: 'Vertex Manipulate', shortcut: 'V' },
      { separator: true, label: '' },
      { label: 'Rotate Selection' },
      { label: 'Trim Line' },
    ],
  },
  {
    label: 'Window',
    items: [
      { label: 'Minimize', shortcut: 'Win+Down' },
      { label: 'Maximize / Restore' },
      { separator: true, label: '' },
      { label: 'BRIGID Dashboard' },
    ],
  },
  {
    label: 'Help',
    items: [
      { label: 'BRIGID Documentation' },
      { label: 'Keyboard Shortcuts' },
      { separator: true, label: '' },
      { label: 'About BRIGID' },
    ],
  },
]

const HotBar: React.FC = () => {
  const [openMenu, setOpenMenu] = useState<string | null>(null)
  const barRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (barRef.current && !barRef.current.contains(e.target as Node)) {
        setOpenMenu(null)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const toggleMenu = (label: string) => {
    setOpenMenu(prev => (prev === label ? null : label))
  }

  return (
    <div className="hot-bar electron-drag" ref={barRef}>
      {/* Brand */}
      <div className="hot-bar__brand electron-no-drag">
        <Icon icon="locate" size={13} color="#38bdf8" />
        <span className="hot-bar__brand-name">BRIGID</span>
      </div>

      {/* App Menus */}
      <nav className="hot-bar__menus electron-no-drag">
        {MENUS.map((menu) => (
          <div key={menu.label} className="hot-bar__menu-root">
            <button
              className={`hot-bar__menu-btn ${openMenu === menu.label ? 'hot-bar__menu-btn--open' : ''}`}
              onClick={() => toggleMenu(menu.label)}
              onMouseEnter={() => openMenu !== null && setOpenMenu(menu.label)}
            >
              {menu.label}
            </button>
            {openMenu === menu.label && (
              <div className="hot-bar__dropdown">
                {menu.items.map((item, idx) =>
                  item.separator ? (
                    <div key={idx} className="hot-bar__dropdown-sep" />
                  ) : (
                    <button
                      key={idx}
                      className={`hot-bar__dropdown-item ${item.disabled ? 'hot-bar__dropdown-item--disabled' : ''}`}
                      onClick={() => setOpenMenu(null)}
                    >
                      <span className="hot-bar__dropdown-label">{item.label}</span>
                      {item.shortcut && (
                        <span className="hot-bar__dropdown-shortcut">{item.shortcut}</span>
                      )}
                    </button>
                  )
                )}
              </div>
            )}
          </div>
        ))}
      </nav>

      {/* Spacer — the rest is taken by Electron's native titlebar overlay (Win controls) */}
      <div className="hot-bar__spacer" />
    </div>
  )
}

export default HotBar
