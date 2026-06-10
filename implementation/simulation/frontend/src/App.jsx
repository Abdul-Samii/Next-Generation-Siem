import { useState, useEffect, useRef, useCallback } from 'react'
import CityMap from './components/CityMap.jsx'
import StatsBar from './components/StatsBar.jsx'
import EventFeed from './components/EventFeed.jsx'
import AttackPanel from './components/AttackPanel.jsx'

const MAX_EVENTS = 120
const WS_URL = `ws://${window.location.hostname}:8000/ws`

const ALL_ATTACKS = [
  'DoS','DoSRandom','DoSDisruptive','Disruptive','DoSRandomSybil',
  'DoSDisruptiveSybil','DataReplaySybil','GridSybil',
  'ConstPos','ConstPosOffset','RandomPos','RandomPosOffset',
  'ConstSpeed','ConstSpeedOffset','RandomSpeed','RandomSpeedOffset',
  'DataReplay','DelayedMessages','EventualStop',
]

const GROUP_OF = {
  DoS:'DoSFamily', DoSRandom:'DoSFamily', DoSDisruptive:'DoSFamily',
  Disruptive:'DoSFamily', DoSRandomSybil:'DoSFamily',
  DoSDisruptiveSybil:'DoSFamily', DataReplaySybil:'DoSFamily', GridSybil:'DoSFamily',
  ConstPos:'PositionAttack', ConstPosOffset:'PositionAttack',
  RandomPos:'PositionAttack', RandomPosOffset:'PositionAttack',
  ConstSpeed:'SpeedManip', ConstSpeedOffset:'SpeedManip',
  RandomSpeed:'SpeedManip', RandomSpeedOffset:'SpeedManip',
  DataReplay:'ReplayAttack', DelayedMessages:'DelayedMessages', EventualStop:'EventualStop',
}

const GROUP_COLOR = {
  DoSFamily:'#ef4444', PositionAttack:'#f59e0b', SpeedManip:'#a855f7',
  ReplayAttack:'#06b6d4', DelayedMessages:'#3b82f6', EventualStop:'#84cc16',
}

export default function App() {
  const [vehicles, setVehicles]         = useState([])
  const [events, setEvents]             = useState([])
  const [stats, setStats]               = useState({ total:0, attacks:0, benign:0, by_type:{} })
  const [running, setRunning]           = useState(false)
  const [connected, setConnected]       = useState(false)
  const [activeAttack, setActiveAttack] = useState(null)
  const [alert, setAlert]               = useState(null)

  // pre-simulation mode selector
  const [mode, setMode]                 = useState('normal')   // 'normal' | 'attack' | 'mixed'
  const [chosenAttack, setChosenAttack] = useState('RandomPos')

  const wsRef      = useRef(null)
  const alertTimer = useRef(null)

  const showAlert = useCallback((msg, severity) => {
    setAlert({ msg, severity })
    clearTimeout(alertTimer.current)
    alertTimer.current = setTimeout(() => setAlert(null), 4000)
  }, [])

  const send = useCallback((obj) => {
    if (wsRef.current?.readyState === WebSocket.OPEN)
      wsRef.current.send(JSON.stringify(obj))
  }, [])

  useEffect(() => {
    function connect() {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws
      ws.onopen  = () => setConnected(true)
      ws.onclose = () => { setConnected(false); setTimeout(connect, 2000) }
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data)
        if (msg.type === 'init')  { setVehicles(msg.vehicles); setRunning(msg.running); setStats(msg.stats) }
        if (msg.type === 'batch') {
          setVehicles(prev => {
            const map = Object.fromEntries(prev.map(v => [v.id, v]))
            msg.vehicles.forEach(v => { map[v.id] = v })
            return Object.values(map)
          })
          if (msg.detections?.length) {
            setEvents(prev => [...prev, ...msg.detections].slice(-MAX_EVENTS))
            const crit = msg.detections.find(d => d.severity === 'CRITICAL')
            if (crit) showAlert(`CRITICAL: ${crit.attack_type} on ${crit.vehicle_id}`, 'CRITICAL')
          }
          if (msg.stats) setStats(msg.stats)
        }
        if (msg.type === 'status')   { setRunning(msg.running); if (msg.stats) { setStats(msg.stats); setEvents([]) } }
        if (msg.type === 'injected') { setActiveAttack(msg.attack_type); showAlert(`Attack injected: ${msg.attack_type}`, 'HIGH') }
        if (msg.type === 'cleared')  { setActiveAttack(null); setEvents([]) }
      }
    }
    connect()
    return () => wsRef.current?.close()
  }, [showAlert])

  const handleStart = () => {
    send({ action: 'start', mode, attack_type: mode === 'attack' ? chosenAttack : null })
    if (mode === 'attack') setActiveAttack(chosenAttack)
  }
  const handleStop   = () => send({ action: 'stop' })
  const handleInject = (type) => send({ action: 'inject', attack_type: type })
  const handleClear  = () => { send({ action: 'clear' }); setActiveAttack(null) }

  const ALERT_COLOR = { CRITICAL:'#ef4444', HIGH:'#f97316', MEDIUM:'#eab308' }

  return (
    <div className="app">
      {alert && (
        <div className="alert-banner" style={{ background: ALERT_COLOR[alert.severity] || '#f97316' }}>
          ⚠ {alert.msg}
        </div>
      )}

      {/* ── header ── */}
      <header className="app-header">
        <div className="header-left">
          <div className="logo">V2X</div>
          <div>
            <div className="app-title">Anomaly Detection System</div>
            <div className="app-sub">Real-time ML-powered V2X Intrusion Detection</div>
          </div>
        </div>
        <div className="header-right">
          <div className={`conn-dot ${connected ? 'connected' : 'disconnected'}`} />
          <span className="conn-label">{connected ? 'Connected' : 'Disconnected'}</span>
          <button
            className={`ctrl-btn ${running ? 'btn-stop' : 'btn-start'}`}
            onClick={running ? handleStop : handleStart}
            disabled={!connected}
          >
            {running ? '⏹ Stop' : '▶ Start'} Simulation
          </button>
        </div>
      </header>

      {/* ── mode selector (only when stopped) ── */}
      {!running && (
        <div className="mode-bar">
          <span className="mode-label">Simulation Mode:</span>

          {['normal','attack','mixed'].map(m => (
            <button
              key={m}
              className={`mode-btn ${mode === m ? 'mode-active' : ''}`}
              onClick={() => setMode(m)}
            >
              {m === 'normal' && '🟢 Normal Traffic'}
              {m === 'attack' && '🔴 Attack Only'}
              {m === 'mixed'  && '🟡 Mixed'}
            </button>
          ))}

          {mode === 'attack' && (
            <select
              className="attack-select"
              value={chosenAttack}
              onChange={e => setChosenAttack(e.target.value)}
            >
              {ALL_ATTACKS.map(a => (
                <option key={a} value={a}>
                  {a}  ({GROUP_OF[a]})
                </option>
              ))}
            </select>
          )}

          {mode === 'attack' && (
            <span className="mode-hint" style={{ color: GROUP_COLOR[GROUP_OF[chosenAttack]] }}>
              → will classify as {GROUP_OF[chosenAttack]}
            </span>
          )}
          {mode === 'normal' && <span className="mode-hint">Only benign BSMs — no attacks injected</span>}
          {mode === 'mixed'  && <span className="mode-hint">Benign traffic + manual injection from attack panel</span>}
        </div>
      )}

      <StatsBar stats={stats} />

      <div className="main-content">
        <div className="map-wrap">
          <CityMap vehicles={vehicles} />
          {!running && (
            <div className="map-overlay">
              <div className="overlay-card">
                <div className="overlay-mode">
                  {mode === 'normal' && '🟢 Normal Traffic'}
                  {mode === 'attack' && `🔴 ${chosenAttack}`}
                  {mode === 'mixed'  && '🟡 Mixed Mode'}
                </div>
                <button className="big-start-btn" onClick={handleStart} disabled={!connected}>
                  ▶ Start Simulation
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="sidebar">
          {mode !== 'normal' && (
            <AttackPanel onInject={handleInject} onClear={handleClear} activeAttack={activeAttack} />
          )}
          <EventFeed events={events} />
        </div>
      </div>

      <footer className="app-footer">
        <span>XGBoost Binary · LightGBM Multiclass · VeReMi Dataset · 68.85% Attack Classification Accuracy</span>
      </footer>
    </div>
  )
}
