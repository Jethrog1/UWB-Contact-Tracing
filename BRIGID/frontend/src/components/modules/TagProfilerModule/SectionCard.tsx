import React from 'react'

interface SectionCardProps {
  title: string
  subtitle?: string
  children: React.ReactNode
  className?: string
}

const SectionCard: React.FC<SectionCardProps> = ({ title, subtitle, children, className = '' }) => (
  <div className={`tp-card ${className}`}>
    <div className="tp-card-header">
      <div className="tp-card-title">{title}</div>
      {subtitle && <div className="tp-card-subtitle">{subtitle}</div>}
    </div>
    <div className="tp-card-body">{children}</div>
  </div>
)

export default SectionCard
