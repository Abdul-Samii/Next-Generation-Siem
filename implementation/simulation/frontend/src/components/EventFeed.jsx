import { useEffect, useRef } from 'react'

const SEVERITY_COLOR = {
  CRITICAL: '#ef4444',
  HIGH:     '#f97316',
  MEDIUM:   '#eab308',
  LOW:      '#84cc16',
}

const SEVERITY_BG = {
  CRITICAL: 'rgba(239,68,68,0.08)',
  HIGH:     'rgba(249,115,22,0.08)',
  MEDIUM:   'rgba(234,179,8,0.08)',
  LOW:      'rgba(132,204,18,0.08)',
}

export default function EventFeed({ events }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    if (events.length > 0)
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  return (
    <div className="event-feed">
      <div className="feed-header">
        <span className="feed-title">Detection Feed</span>
        <span className="feed-count">{events.length} events</span>
      </div>
      <div className="feed-list">
        {events.length === 0 && (
          <div className="feed-empty">Waiting for detections...</div>
        )}
        {events.map((e, i) => (
          <div
            key={i}
            className="feed-item"
            style={{ background: SEVERITY_BG[e.severity] || 'transparent',
                     borderLeft: `3px solid ${SEVERITY_COLOR[e.severity] || '#64748b'}` }}
          >
            <div className="feed-item-top">
              <span className="feed-vehicle">{e.vehicle_id}</span>
              <span className="feed-severity" style={{ color: SEVERITY_COLOR[e.severity] }}>
                {e.severity}
              </span>
              <span className="feed-time">{e.ts}</span>
            </div>
            <div className="feed-item-bot">
              <span className="feed-type">{e.attack_type}</span>
              <span className="feed-conf">{(e.confidence * 100).toFixed(1)}%</span>
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
