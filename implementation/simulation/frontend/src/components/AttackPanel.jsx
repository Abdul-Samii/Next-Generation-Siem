import { useState } from 'react'

const GROUPS = {
  DoSFamily: {
    color: '#ef4444',
    types: ['DoS','DoSRandom','DoSDisruptive','Disruptive','DoSRandomSybil','DoSDisruptiveSybil','DataReplaySybil','GridSybil'],
  },
  PositionAttack: {
    color: '#f59e0b',
    types: ['ConstPos','ConstPosOffset','RandomPos','RandomPosOffset'],
  },
  SpeedManip: {
    color: '#a855f7',
    types: ['ConstSpeed','ConstSpeedOffset','RandomSpeed','RandomSpeedOffset'],
  },
  ReplayAttack: {
    color: '#06b6d4',
    types: ['DataReplay'],
  },
  DelayedMessages: {
    color: '#3b82f6',
    types: ['DelayedMessages'],
  },
  EventualStop: {
    color: '#84cc16',
    types: ['EventualStop'],
  },
}

export default function AttackPanel({ onInject, onClear, activeAttack }) {
  const [selected, setSelected] = useState('RandomPos')

  return (
    <div className="attack-panel">
      <div className="panel-header">
        <span className="panel-title">Attack Injection</span>
        {activeAttack && (
          <span className="active-badge">● ACTIVE</span>
        )}
      </div>

      <div className="group-list">
        {Object.entries(GROUPS).map(([group, { color, types }]) => (
          <div key={group} className="attack-group">
            <div className="group-label" style={{ color }}>{group}</div>
            <div className="type-list">
              {types.map(t => (
                <button
                  key={t}
                  className={`type-btn ${selected === t ? 'selected' : ''}`}
                  style={selected === t ? { borderColor: color, background: `${color}18`, color } : {}}
                  onClick={() => setSelected(t)}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="panel-actions">
        <button
          className="inject-btn"
          onClick={() => onInject(selected)}
        >
          ⚡ INJECT ATTACK
        </button>
        <button className="clear-btn" onClick={onClear}>
          ✕ Clear
        </button>
      </div>
    </div>
  )
}
