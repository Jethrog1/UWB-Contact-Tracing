import React from 'react'
import { TagProfile } from '../../../types'
import SectionCard from './SectionCard'
import FieldInput from './FieldInput'

const ANCHOR_IDS = ['A0', 'A1', 'A2', 'A3']
const DEVICE_TYPES = ['Wrist Band', 'Arm Band', 'Belt Clip-on', 'Breast Pocket']
const HEIGHT_FIELDS: Record<string, string> = {
  'Wrist Band': 'wrist_to_floor_ft',
  'Arm Band': 'arm_to_floor_ft',
  'Belt Clip-on': 'hip_to_floor_ft',
  'Breast Pocket': 'breast_to_floor_ft',
}

interface Props {
  profile: TagProfile
  onChange: (updated: TagProfile) => void
}

const ProfileFormSection: React.FC<Props> = ({ profile, onChange }) => {
  const set = (path: string[], val: string | number) => {
    const next = JSON.parse(JSON.stringify(profile)) as TagProfile
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let obj: any = next
    for (let i = 0; i < path.length - 1; i++) obj = obj[path[i]]
    obj[path[path.length - 1]] = val
    onChange(next)
  }

  const activeHeightField = HEIGHT_FIELDS[profile.device.device_type] ?? 'wrist_to_floor_ft'

  return (
    <div className="tp-form-grid">
      {/* Left column */}
      <div className="tp-form-col">
        {/* Identity */}
        <SectionCard title="Identity" subtitle="Profile identification">
          <FieldInput label="Tag ID *" value={profile.tag_id}
            onChange={v => set(['tag_id'], v)}
            help="Hardware ID. Required." />
          <FieldInput label="Profile ID" value={profile.identity.profile_id}
            onChange={v => set(['identity', 'profile_id'], v)}
            placeholder="e.g. TAG-001"
            help="Used as profile name when saving." />
          <FieldInput label="Name" value={profile.identity.name}
            onChange={v => set(['identity', 'name'], v)}
            help="Person's name associated with this tag." />
          <FieldInput label="Description" value={profile.identity.description}
            onChange={v => set(['identity', 'description'], v)}
            type="textarea" help="Optional notes about the tag or wearer." />
        </SectionCard>

        {/* Calibration equations */}
        <SectionCard title="Calibration Equations" subtitle="Distance correction per anchor">
          {/* Enable / Disable toggle */}
          <div className="tp-cal-toggle-row">
            <span className="tp-field-label">Enable editing</span>
            <button
              className={`tp-toggle${profile.calibration.equations_enabled ? ' tp-toggle--on' : ''}`}
              onClick={() => {
                const next = JSON.parse(JSON.stringify(profile)) as TagProfile
                next.calibration.equations_enabled = !next.calibration.equations_enabled
                onChange(next)
              }}
              title={profile.calibration.equations_enabled ? 'Disable equation editing' : 'Enable equation editing'}
            >
              <span className="tp-toggle-knob" />
            </button>
          </div>
          {ANCHOR_IDS.map(aid => (
            <FieldInput key={aid} label={aid}
              value={profile.calibration.equations[aid] ?? ''}
              onChange={v => {
                const next = JSON.parse(JSON.stringify(profile)) as TagProfile
                next.calibration.equations[aid] = v
                onChange(next)
              }}
              placeholder={profile.calibration.equations_enabled ? 'e.g. (0.95*Raw)+0.5 or leave blank' : '—'}
              monospace
              readOnly={!profile.calibration.equations_enabled}
              help={`Calibration correction equation for anchor ${aid}. Leave blank for raw distance.`} />
          ))}
          <FieldInput label="Last Calibration Date"
            value={profile.calibration.last_calibration_date}
            onChange={v => set(['calibration', 'last_calibration_date'], v)}
            placeholder="ISO date e.g. 2026-04-13"
            readOnly />
        </SectionCard>
      </div>

      {/* Right column */}
      <div className="tp-form-col">
        {/* Device */}
        <SectionCard title="Device" subtitle="Physical device configuration">
          <FieldInput label="MAC Address" value={profile.device.mac_address}
            onChange={v => set(['device', 'mac_address'], v)}
            placeholder="AA:BB:CC:DD:EE:FF"
            help="BLE MAC address of the physical device." />
          <FieldInput label="Device Type" value={profile.device.device_type}
            onChange={v => set(['device', 'device_type'], v)}
            type="select" options={DEVICE_TYPES}
            help="Form factor of the wearable. Determines which height field is active." />

          {/* Only the active height field is shown prominently */}
          <div className="tp-height-fields">
            {(['wrist_to_floor_ft', 'arm_to_floor_ft', 'hip_to_floor_ft', 'breast_to_floor_ft'] as const).map(hf => (
              <FieldInput key={hf}
                label={hf.replace(/_ft$/, ' (ft)').replace(/_/g, ' ')}
                value={profile.device[hf]}
                onChange={v => set(['device', hf], parseFloat(v) || 0)}
                type="number"
                className={hf !== activeHeightField ? 'tp-field--inactive' : ''}
                help={`Distance in feet. Active for ${Object.entries(HEIGHT_FIELDS).find(([, f]) => f === hf)?.[0]}.`} />
            ))}
          </div>

          <FieldInput label="Device Description" value={profile.device.description}
            onChange={v => set(['device', 'description'], v)}
            type="textarea" />
        </SectionCard>

        {/* Notes */}
        <SectionCard title="Notes" subtitle="Operational notes">
          <FieldInput label="Notes" value={profile.notes}
            onChange={v => set(['notes'], v)}
            type="textarea"
            placeholder="Deployment notes, observations, maintenance history..."
            help="Free-form operational notes." />
        </SectionCard>
      </div>
    </div>
  )
}

export default ProfileFormSection
