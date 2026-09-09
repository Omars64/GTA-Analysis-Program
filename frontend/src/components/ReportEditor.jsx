import { useState } from 'react'
import api, { exportUrl } from '../api/client.js'

export default function ReportEditor({ report, onSave, emailConfigured }) {
  const [editing, setEditing] = useState(false)
  const [rows, setRows] = useState([])
  const [note, setNote] = useState('')
  const [recipient, setRecipient] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [delivery, setDelivery] = useState(null)
  async function save() {
    setBusy(true); setMessage('')
    try {
      const edits = rows.map((r, index) => ({ index, category: r.category, item: r.item, details: r.details || '' })).filter((r, i) => ['category', 'item', 'details'].some(k => r[k] !== (report.items[i][k] || '')))
      const { data } = await api.put(`/history/${report.id}`, { revision: report.revision || 0, edits, note })
      onSave(data); setEditing(false); setMessage('Corrections saved. Downloads and email use this revision.')
    } catch (e) { setMessage(e.response?.data?.error || e.message) }
    finally { setBusy(false) }
  }
  async function send() {
    setBusy(true); setMessage('')
    const requestId = delivery || crypto.randomUUID(); setDelivery(requestId)
    try {
      const { data } = await api.post(`/history/${report.id}/email`, { recipients: recipient.split(',').map(v => v.trim()).filter(Boolean), requestId })
      setMessage(data.status === 'sent' ? 'Email accepted by the mail server.' : 'Delivery is still pending.');
    } catch (e) { setMessage(e.response?.data?.error || 'Delivery could not be confirmed. Retry checks the same delivery.') }
    finally { setBusy(false) }
  }
  return <section className="glass-panel control-panel">
    <h3>Report document · revision {report.revision || 0}</h3>
    <p>Review the fetched data below. Edit individual items and describe your changes before saving. Human corrections retain the original evidence and are not marked source-verified.</p>
    <div className="export-actions">
      <button onClick={() => { setRows(report.items.map(r => ({ ...r }))); setEditing(!editing) }} disabled={busy}>{editing ? 'Cancel editing' : 'Edit report'}</button>
      {!editing && <>{(report.exports?.pdf ?? report.pdf_path) && <a href={exportUrl(report.id, 'pdf')}>Download PDF</a>}{(report.exports?.json ?? report.json_path) && <a href={exportUrl(report.id, 'json')}>Download JSON</a>}</>}
    </div>
    {editing && <>
      {rows.map((row, i) => <fieldset key={i}><legend>Item {i + 1}</legend>{['category', 'item', 'details'].map(key => <label key={key}>{key}<textarea rows={key === 'details' ? 2 : 1} maxLength={2000} value={row[key] || ''} onChange={e => setRows(current => current.map((r, j) => j === i ? { ...r, [key]: e.target.value } : r))} /></label>)}</fieldset>)}
      <label>Describe your changes<textarea maxLength={2000} value={note} onChange={e => setNote(e.target.value)} /></label>
      <button className="primary-btn" onClick={save} disabled={busy}>Save corrections</button>
    </>}
    <label>Email this saved report<input aria-label="Report email recipients" placeholder="Recipient email, or comma-separated recipients" value={recipient} onChange={e => { setRecipient(e.target.value); setDelivery(null) }} /></label>
    <button onClick={send} disabled={busy || editing || !emailConfigured || !recipient.trim()}>Email PDF</button>
    {!emailConfigured && <p>Email server configuration is required.</p>}
    {message && <p role="status">{message}</p>}
  </section>
}
