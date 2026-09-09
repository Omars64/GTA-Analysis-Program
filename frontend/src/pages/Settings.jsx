import { useEffect, useState } from 'react'
import api from '../api/client.js'

export default function Settings() {
  const [settings, setSettings] = useState(null)
  const [capabilities, setCapabilities] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setError('')
    Promise.all([api.get('/settings', { signal: controller.signal }), api.get('/capabilities', { signal: controller.signal })])
      .then(([s, c]) => { setSettings(s.data); setCapabilities(c.data) })
      .catch(e => { if (!controller.signal.aborted) setError(e.response?.data?.error || e.message) })
    return () => controller.abort()
  }, [retry])
  async function save(e) {
    e.preventDefault(); setSaving(true); setMessage(''); setError('')
    try { const { data } = await api.put('/settings', settings); setSettings(data); setMessage('Settings saved.') }
    catch (e) { setError(e.response?.data?.error || e.message) }
    finally { setSaving(false) }
  }
  async function browse() {
    try { const { data } = await api.post('/system/select-output-directory'); if (data.output_directory) setSettings(s => ({ ...s, output_directory: data.output_directory })) }
    catch (e) { setError(e.response?.data?.error || 'Folder picker unavailable; enter the path manually.') }
  }
  return <div className="dashboard-stack">
    <section className="page-title"><span className="eyebrow">SYSTEM</span><h2>Companion settings</h2><p>Export preferences and extraction resilience. Settings persist across sessions.</p></section>
    {error && <div className="error-banner" role="alert">{error}{!settings && <button onClick={() => setRetry(v => v + 1)}>Retry</button>}</div>}
    {!settings ? <div className="empty-state glass-panel">{error ? 'Settings unavailable.' : 'Loading settings…'}</div> :
      <form className="settings-card glass-panel" onSubmit={save}>
        {capabilities?.cloud ? <p className="notice-banner">Hosted mode: download reports from the dashboard or archive. Files are generated on demand from your saved database records.</p> : <>
          <label htmlFor="settings-output">Output directory</label><div className="input-action"><input id="settings-output" value={settings.output_directory} onChange={e => setSettings(s => ({ ...s, output_directory: e.target.value }))} />{capabilities?.native_folder_picker && <button type="button" onClick={browse}>Browse</button>}</div>
        </>}
        <div className="settings-two">
          <label>Source retry attempts<input type="number" required min="1" max="3" value={settings.source_retries} onChange={e => setSettings(s => ({ ...s, source_retries: Number(e.target.value) }))} /></label>
          <label>Request timeout (seconds)<input type="number" required min="5" max="60" value={settings.request_timeout} onChange={e => setSettings(s => ({ ...s, request_timeout: Number(e.target.value) }))} /></label>
          <label>Default history list size<input type="number" required min="1" max="200" value={settings.history_limit} onChange={e => setSettings(s => ({ ...s, history_limit: Number(e.target.value) }))} /></label>
        </div>
        <div className="toggle-row"><label className="check"><input type="checkbox" checked={settings.generate_pdf} onChange={e => setSettings(s => ({ ...s, generate_pdf: e.target.checked }))} /> Generate PDF by default</label><label className="check"><input type="checkbox" checked={settings.save_json} onChange={e => setSettings(s => ({ ...s, save_json: e.target.checked }))} /> Enable JSON export</label></div>
        <button className="primary-btn" disabled={saving}>{saving ? 'SAVING…' : 'SAVE SETTINGS'}</button>{message && <div className="notice-banner" role="status">{message}</div>}
      </form>}
  </div>
}
