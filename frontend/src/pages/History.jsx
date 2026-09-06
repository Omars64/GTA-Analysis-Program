import { useEffect, useState } from 'react'
import api from '../api/client.js'

export default function History() {
  const [history, setHistory] = useState([])
  useEffect(() => { api.get('/history?limit=50').then(r => setHistory(r.data.history || [])).catch(() => {}) }, [])
  return <div className="dashboard-stack">
    <section className="page-title"><span className="eyebrow">ARCHIVE</span><h2>Weekly intelligence history</h2><p>Every completed run is retained as a structured snapshot for comparison and retrieval.</p></section>
    <div className="history-grid">
      {history.map(item => <article className="history-card glass-panel" key={item.id}>
        <div className="history-date"><strong>{item.week_start}</strong><span>→</span><strong>{item.week_end}</strong></div>
        <div className="history-stats"><span>{item.row_count} items</span><span>{item.vehicle_count} vehicles</span><span>{Math.round((item.confidence || 0)*100)}% confidence</span></div>
        <small>{item.created_at ? new Date(item.created_at).toLocaleString() : ''}</small>
      </article>)}
      {!history.length && <div className="empty-state glass-panel">No archived runs yet.</div>}
    </div>
  </div>
}
