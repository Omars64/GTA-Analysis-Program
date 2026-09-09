import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api, { exportUrl } from '../api/client.js'

export default function History() {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    api.get('/history?limit=200', { signal: controller.signal })
      .then(r => setHistory(r.data.history || []))
      .catch(e => { if (!controller.signal.aborted) setError(e.response?.data?.error || e.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [retry])
  return <div className="dashboard-stack">
    <section className="page-title"><span className="eyebrow">ARCHIVE</span><h2>Weekly intelligence history</h2><p>Open a saved report, explore its sources, or download its exports. Showing the latest 200 runs.</p></section>
    {error && <div className="error-banner" role="alert">{error} <button onClick={() => setRetry(v => v + 1)}>Retry</button></div>}
    <div className="history-grid">
      {history.map(item => <article className="history-card glass-panel" key={item.id}>
        <div className="history-date"><strong>{item.week_start}</strong><span>→</span><strong>{item.week_end}</strong></div>
        <div className="history-stats"><span>{item.row_count} items</span><span>{item.vehicle_count} vehicles</span><span>{Math.round((item.confidence || 0) * 100)}% confidence</span></div>
        <small>{item.created_at ? new Date(item.created_at).toLocaleString() : ''}</small>
        <div className="export-actions">
          <Link to={'/?snapshot=' + encodeURIComponent(item.id)}>VIEW REPORT</Link>
          {(item.result?.exports?.pdf ?? item.result?.pdf_path) && <a href={exportUrl(item.id, 'pdf')}>PDF</a>}
          {(item.result?.exports?.json ?? item.result?.json_path) && <a href={exportUrl(item.id, 'json')}>JSON</a>}
        </div>
      </article>)}
      {loading && <div className="empty-state glass-panel" role="status">Loading archived reports…</div>}
      {!loading && !error && !history.length && <div className="empty-state glass-panel">No archived runs yet. Run your first scan from the dashboard.</div>}
    </div>
  </div>
}
