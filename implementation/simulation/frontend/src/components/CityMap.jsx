import { useEffect, useRef } from 'react'

const W = 940
const H = 620
const H_ROADS = [120, 310, 500]
const V_ROADS = [160, 400, 700]
const ROAD_W  = 36
const LANE_W  = 2

const SEVERITY_COLOR = {
  CRITICAL: '#ef4444',
  HIGH:     '#f97316',
  MEDIUM:   '#eab308',
  LOW:      '#84cc16',
  NONE:     '#22c55e',
}

function rRect(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.lineTo(x + w - r, y)
  ctx.arcTo(x + w, y, x + w, y + r, r)
  ctx.lineTo(x + w, y + h - r)
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r)
  ctx.lineTo(x + r, y + h)
  ctx.arcTo(x, y + h, x, y + h - r, r)
  ctx.lineTo(x, y + r)
  ctx.arcTo(x, y, x + r, y, r)
  ctx.closePath()
}

// pre-seeded windows so they don't flicker each frame
const WINDOWS = []
;(function seedWindows() {
  const xs = [0, ...V_ROADS, W]
  const ys = [0, ...H_ROADS, H]
  for (let i = 0; i < xs.length - 1; i++) {
    for (let j = 0; j < ys.length - 1; j++) {
      const bx = xs[i] + (i === 0 ? 0 : ROAD_W / 2)
      const by = ys[j] + (j === 0 ? 0 : ROAD_W / 2)
      const bw = xs[i+1] - xs[i] - ROAD_W / 2 - (i === xs.length-2 ? 0 : ROAD_W/2)
      const bh = ys[j+1] - ys[j] - ROAD_W / 2 - (j === ys.length-2 ? 0 : ROAD_W/2)
      if (bw < 10 || bh < 10) continue
      const wins = []
      for (let wx = bx+12; wx+8 < bx+bw-12; wx += 22) {
        for (let wy = by+10; wy+6 < by+bh-10; wy += 18) {
          wins.push({ x: wx, y: wy, lit: Math.random() > 0.35, warm: Math.random() > 0.6 })
        }
      }
      WINDOWS.push({ bx, by, bw, bh, wins })
    }
  }
})()

function drawGrid(ctx) {
  ctx.fillStyle = '#0f172a'
  ctx.fillRect(0, 0, W, H)

  // buildings
  WINDOWS.forEach(({ bx, by, bw, bh, wins }) => {
    ctx.fillStyle = '#1e293b'
    ctx.fillRect(bx, by, bw, bh)
    wins.forEach(w => {
      if (!w.lit) return
      ctx.fillStyle = w.warm ? 'rgba(254,240,138,0.25)' : 'rgba(148,163,184,0.15)'
      ctx.fillRect(w.x, w.y, 8, 6)
    })
  })

  // road surfaces
  ctx.fillStyle = '#1f2937'
  H_ROADS.forEach(y => ctx.fillRect(0, y - ROAD_W/2, W, ROAD_W))
  V_ROADS.forEach(x => ctx.fillRect(x - ROAD_W/2, 0, ROAD_W, H))

  // centre dashes
  ctx.setLineDash([18, 12])
  ctx.lineWidth = LANE_W
  ctx.strokeStyle = '#374151'
  H_ROADS.forEach(y => { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(W,y); ctx.stroke() })
  V_ROADS.forEach(x => { ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,H); ctx.stroke() })
  ctx.setLineDash([])

  // intersections
  ctx.fillStyle = '#273244'
  H_ROADS.forEach(y => V_ROADS.forEach(x =>
    ctx.fillRect(x - ROAD_W/2, y - ROAD_W/2, ROAD_W, ROAD_W)
  ))
}

function drawVehicle(ctx, v, tick) {
  const { x, y, angle, is_attack, severity, pulse, wave } = v

  // radio wave ripple
  const waveAlpha = 1 - wave
  const waveR     = 18 + wave * 40
  ctx.beginPath()
  ctx.arc(x, y, waveR, 0, Math.PI * 2)
  ctx.strokeStyle = is_attack
    ? `rgba(239,68,68,${waveAlpha * 0.5})`
    : `rgba(34,197,94,${waveAlpha * 0.3})`
  ctx.lineWidth = 1.5
  ctx.stroke()

  // pulse ring for attacks
  if (pulse > 0) {
    const pulseR = 14 + pulse * 10
    ctx.beginPath()
    ctx.arc(x, y, pulseR, 0, Math.PI * 2)
    ctx.strokeStyle = `rgba(239,68,68,${pulse * 0.8})`
    ctx.lineWidth = 2.5
    ctx.stroke()
  }

  // vehicle body
  ctx.save()
  ctx.translate(x, y)
  ctx.rotate((angle * Math.PI) / 180)

  const color = is_attack ? (SEVERITY_COLOR[severity] || '#ef4444') : '#22c55e'

  // glow
  ctx.shadowColor  = color
  ctx.shadowBlur   = is_attack ? 16 : 8

  // car body
  ctx.fillStyle = color
  ctx.beginPath()
  ctx.roundRect(-10, -6, 20, 12, 3)
  ctx.fill()

  // windshield
  ctx.fillStyle = '#0f172a'
  ctx.beginPath()
  ctx.roundRect(2, -4, 6, 8, 2)
  ctx.fill()

  // headlights
  ctx.fillStyle = '#fef9c3'
  ctx.fillRect(8, -5, 3, 3)
  ctx.fillRect(8, 2, 3, 3)

  ctx.shadowBlur = 0
  ctx.restore()

  // vehicle ID label
  ctx.font = '9px JetBrains Mono, monospace'
  ctx.fillStyle = '#94a3b8'
  ctx.textAlign = 'center'
  ctx.fillText(v.id, x, y - 16)

  // attack type badge
  if (is_attack && v.attack_type && v.attack_type !== 'Benign') {
    const label = v.attack_type.replace('Attack', '').replace('Family', '')
    const tw = ctx.measureText(label).width + 10
    ctx.fillStyle = SEVERITY_COLOR[severity] || '#ef4444'
    ctx.beginPath()
    ctx.roundRect(x - tw / 2, y - 32, tw, 14, 3)
    ctx.fill()
    ctx.fillStyle = '#0f172a'
    ctx.font = 'bold 8px Inter, sans-serif'
    ctx.fillText(label, x, y - 22)
  }
}

export default function CityMap({ vehicles }) {
  const canvasRef = useRef(null)
  const tickRef   = useRef(0)
  const vRef      = useRef(vehicles)

  useEffect(() => { vRef.current = vehicles }, [vehicles])

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx    = canvas.getContext('2d')
    let raf

    // pre-draw static city layer onto offscreen canvas
    const offscreen = document.createElement('canvas')
    offscreen.width  = W
    offscreen.height = H
    const octx = offscreen.getContext('2d')
    drawGrid(octx)

    function frame() {
      tickRef.current++
      ctx.drawImage(offscreen, 0, 0)
      vRef.current.forEach(v => drawVehicle(ctx, v, tickRef.current))
      raf = requestAnimationFrame(frame)
    }

    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [])

  return (
    <canvas
      ref={canvasRef}
      width={W}
      height={H}
      style={{ width: '100%', height: 'auto', display: 'block', borderRadius: '12px' }}
    />
  )
}
