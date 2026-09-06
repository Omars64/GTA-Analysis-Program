import { useEffect, useState } from 'react'
import api from '../api/client.js'

export default function Settings() {
  const [settings, setSettings] = useState(null)
  const [message, setMessage] = useState('')
  useEffect(() => { api.get('/settings').then(r => setSettings(r.data)).catch(e => setMessage(e.message)) }, [])
  if (!settings) return <div className="empty-state glass-panel">Loading settings…</div>
  async function save() {
    try { const { data } = await api.put('/settings', settings); setSettings(data); setMessage('Settings saved.') }
    catch (e) { setMessage(e.response?.data?.error || e.message) }
  }
  async function browse() {
    try { const { data } = await api.post('/system/select-output-directory'); if (data.output_directory) setSettings(s => ({...s, output_directory:data.output_directory})) }
    catch (e) { setMessage(e.response?.data?.error || 'Folder picker unavailable; enter the path manually.') }
  }
  return <div className="dashboard-stack">
    <section className="page-title"><span className="eyebrow">SYSTEM</span><h2>Companion settings</h2><p>Local export, extraction resilience and persistence configuration.</p></section>
    <section className="settings-card glass-panel">
      <label>Output directory</label><div className="input-action"><input value={settings.output_directory} onChange={e => setSettings(s => ({...s, output_directory:e.target.value}))}/><button onClick={browse}>Browse</button></div>
      <div className="settings-two">
        <label>Source retry attempts<input type="number" min="1" max="5" value={settings.source_retries} onChange={e => setSettings(s => ({...s, source_retries:Number(e.target.value)}))}/></label>
        <label>Request timeout (seconds)<input type="number" min="5" max="120" value={settings.request_timeout} onChange={e => setSettings(s => ({...s, request_timeout:Number(e.target.value)}))}/></label>
      </div>
      <div className="toggle-row"><label className="check"><input type="checkbox" checked={settings.generate_pdf} onChange={e => setSettings(s => ({...s, generate_pdf:e.target.checked}))}/> Generate PDF by default</label><label className="check"><input type="checkbox" checked={settings.save_json} onChange={e => setSettings(s => ({...s, save_json:e.target.checked}))}/> Save structured JSON</label></div>
      <button className="primary-btn" onClick={save}>SAVE SETTINGS</button>{message && <div className="notice-banner">{message}</div>}
    </section>
  </div>
}
