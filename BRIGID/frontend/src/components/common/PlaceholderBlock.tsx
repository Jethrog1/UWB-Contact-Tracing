import React from 'react'
import { Icon, IconName } from '@blueprintjs/core'
import './PlaceholderBlock.css'

type PlaceholderType = 'text' | 'image' | 'chart' | 'details' | 'observation' | 'action' | 'button' | 'data' | 'table'

interface PlaceholderBlockProps {
  type: PlaceholderType
  label?: string
  height?: string
  className?: string
}

const typeConfig: Record<PlaceholderType, { icon: IconName; defaultLabel: string }> = {
  text: { icon: 'align-left', defaultLabel: 'Text Content' },
  image: { icon: 'media', defaultLabel: 'Image' },
  chart: { icon: 'chart', defaultLabel: 'Chart / Visualization' },
  details: { icon: 'properties', defaultLabel: 'Details' },
  observation: { icon: 'eye-open', defaultLabel: 'Observation' },
  action: { icon: 'play', defaultLabel: 'Action' },
  button: { icon: 'widget-button', defaultLabel: 'Button' },
  data: { icon: 'database', defaultLabel: 'Data Feed' },
  table: { icon: 'th', defaultLabel: 'Table View' }
}

const PlaceholderBlock: React.FC<PlaceholderBlockProps> = ({
  type,
  label,
  height,
  className = ''
}) => {
  const config = typeConfig[type]

  return (
    <div
      className={`placeholder-block placeholder-block--${type} ${className}`}
      style={height ? { height } : undefined}
    >
      <div className="placeholder-block__inner">
        <Icon
          icon={config.icon}
          size={16}
          className="placeholder-block__icon"
        />
        <span className="placeholder-block__label">
          [{label || config.defaultLabel}]
        </span>
      </div>
    </div>
  )
}

export default PlaceholderBlock
