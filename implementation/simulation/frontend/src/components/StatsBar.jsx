const GROUP_COLOR = {
  DoSFamily:       '#ef4444',
  PositionAttack:  '#f59e0b',
  SpeedManip:      '#a855f7',
  ReplayAttack:    '#06b6d4',
  DelayedMessages: '#3b82f6',
  EventualStop:    '#84cc16',
}

function StatCard({ label, value, sub, color }) {
  return (
    <div className="stat-card">
      <div className="stat-value" style={{ color }}>{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

export default function StatsBar({ stats }) {
  const { total = 0, attacks = 0, benign = 0, by_type = {} } = stats
  const rate = total > 0 ? ((attacks / total) * 100).toFixed(1) : '0.0'

  return (
    <div className="stats-bar">
      <div className="stats-left">
        <StatCard label="Total Messages" value={total.toLocaleString()} color="#94a3b8" />
        <StatCard label="Attacks Detected" value={attacks.toLocaleString()} color="#ef4444" sub={`${rate}% attack rate`} />
        <StatCard label="Benign" value={benign.toLocaleString()} color="#22c55e" />
      </div>

      <div className="stats-types">
        {Object.entries(GROUP_COLOR).map(([group, color]) => {
          const count = by_type[group] || 0
          const pct   = attacks > 0 ? (count / attacks) * 100 : 0
          return (
            <div key={group} className="type-pill">
              <div className="type-bar-wrap">
                <div className="type-bar" style={{ width: `${pct}%`, background: color }} />
              </div>
              <span className="type-name" style={{ color }}>{group.replace('Attack','').replace('Family','')}</span>
              <span className="type-count">{count}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
