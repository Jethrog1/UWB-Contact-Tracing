import React from 'react'
import { Tooltip } from '@blueprintjs/core'

interface FieldInputProps {
  label: string
  value: string | number
  onChange: (value: string) => void
  help?: string
  type?: 'text' | 'number' | 'textarea' | 'select'
  options?: string[]
  placeholder?: string
  readOnly?: boolean
  monospace?: boolean
  className?: string
}

const FieldInput: React.FC<FieldInputProps> = ({
  label,
  value,
  onChange,
  help,
  type = 'text',
  options = [],
  placeholder = '',
  readOnly = false,
  monospace = false,
  className = '',
}) => (
  <div className={`tp-field${className ? ' ' + className : ''}`}>
    <div className="tp-field-label-row">
      <label className="tp-field-label">{label}</label>
      {help && (
        <Tooltip
          content={<span style={{ fontSize: 10, letterSpacing: '0.04em' }}>{help}</span>}
          placement="right"
          minimal
          hoverOpenDelay={150}
        >
          <span className="tp-field-help">?</span>
        </Tooltip>
      )}
    </div>
    {type === 'select' ? (
      <select
        className="tp-field-select"
        value={String(value)}
        onChange={e => onChange(e.target.value)}
        disabled={readOnly}
      >
        {options.map(opt => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
    ) : type === 'textarea' ? (
      <textarea
        className={`tp-field-textarea${monospace ? ' tp-field-mono' : ''}`}
        value={String(value)}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        readOnly={readOnly}
        rows={3}
      />
    ) : (
      <input
        className={`tp-field-input${monospace ? ' tp-field-mono' : ''}`}
        type={type}
        value={String(value)}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        readOnly={readOnly}
        step={type === 'number' ? '0.01' : undefined}
        min={type === 'number' ? '0' : undefined}
      />
    )}
  </div>
)

export default FieldInput
