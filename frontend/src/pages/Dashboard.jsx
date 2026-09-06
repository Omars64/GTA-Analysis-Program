import { useEffect, useRef, useState } from 'react'
import api, { API_BASE, API_ORIGIN } from '../api/client.js'
import ProgressPipeline from '../components/ProgressPipeline.jsx'
import LogPanel from '../components/LogPanel.jsx'
import VehicleCard from '../components/VehicleCard.jsx'
import ResultSections from '../components/ResultSections.jsx'

const defaultEmail = { smtpServer: 'smtp.gmail.com', smtpPort: 587, username: '', password: '', fromAddress: '', recipients: '', useTls: true }

export default function Dashboard() {
  const [manualUrl, setManualUrl] = useState('')
  const [settings, setSettings] = useState({ output_directory: '', generate_pdf: true, save_json: true })
  const [sendEmail, setSendEmail] = useState(false)
  const [email, setEmail] = useState(defaultEmail)
  const [job, setJob] = useState(null)
  const [logs, setLogs] = useState([])
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [answer, setAnswer] = useState(null)
  const eventsRef = useRef(null)

  useEffect(() => {
    api.get('/settings').then(r => setSettings(r.data)).catch(() => {})
    api.get('/latest').then(r => { if (r.data?.week_start) setResult(r.data) }).catch(() => {})
    return () => eventsRef.current?.close()
  }, [])

  const running = job && ['queued', 'running'].includes(job.status)

  async function startRun() {
    setError(''); setLogs([]); setAnswer(null)
    try {
      const payload = {
        manualUrl: manualUrl || null,
        outputDirectory: settings.output_directory,
        generatePdf: settings.generate_pdf,
        saveJson: settings.save_json,
        sendEmail,
        emailConfig: sendEmail ? { ...email, recipients: email.recipients.split(',').map(x => x.trim()).filter(Boolean) } : undefined,
      }
      const { data } = await api.post('/runs', payload)
      setJob(data)
      eventsRef.current?.close()
      const es = new EventSource(`${API_BASE}/runs/${data.id}/events`)
      eventsRef.current = es
      es.addEventListener('progress', evt => {
        const event = JSON.parse(evt.data)
        setLogs(prev => [...prev, event])
        setJob(prev => ({ ...(prev || {}), ...event }))
      })
      es.addEventListener('done', async evt => {
        const snapshot = JSON.parse(evt.data)
        setJob(snapshot)
        es.close()
        if (snapshot.status === 'completed') {
          const final = await api.get(`/runs/${data.id}`)
          setResult(final.data.result)
        } else if (snapshot.error) setError(snapshot.error)
      })
      es.onerror = () => {
        if (es.readyState === EventSource.CLOSED) return
      }
    } catch (e) {
      setError(e.response?.data?.error || e.message)
    }
  }

  async function cancelRun() {
    if (!job?.id) return
    await api.post(`/runs/${job.id}/cancel`).catch(() => {})
  }

  async function browseFolder() {
    try {
      const { data } = await api.post('/system/select-output-directory')
      if (data.output_directory) setSettings(s => ({ ...s, output_directory: data.output_directory }))
    } catch (e) {
      setError(e.response?.data?.error || 'Native folder picker is unavailable. Enter the path manually.')
    }
  }

  async function askWeekly(e) {
    e.preventDefault()
    if (!query.trim()) return
    try { setAnswer((await api.post('/knowledge/query', { query })).data) }
    catch (e) { setAnswer({ answer: e.response?.data?.error || e.message, matches: [] }) }
  }

  const stats = result?.stats || {}
  const pdfUrl = job?.id && result?.pdf_path ? `${API_ORIGIN}/api/runs/${job.id}/pdf` : null
  const jsonUrl = job?.id && result?.json_path ? `${API_ORIGIN}/api/runs/${job.id}/json` : null

  return <div className="dashboard-stack">
    <section className="hero glass-panel">
      <div className="hero-copy">
        <div className="eyebrow">GTA ONLINE // WEEKLY COMPANION</div>
        <h2>Weekly Intelligence,<br/><span>not just a PDF.</span></h2>
        <p>Discover, cross-check, extract, enrich and explore the current GTA Online week from one structured dataset.</p>
        <div className="hero-actions">
          <button className="primary-btn" onClick={startRun} disabled={running}>{running ? 'INTELLIGENCE RUN ACTIVE' : 'RUN WEEKLY INTELLIGENCE'}</button>
          {running && <button className="danger-btn" onClick={cancelRun}>CANCEL RUN</button>}
        </div>
      </div>
      <div className="hero-week">
        <span>CURRENT DATASET</span>
        <strong>{result?.week_start || 'NO SCAN'}</strong>
        <i>→</i>
        <strong>{result?.week_end || 'RUN TO LOAD'}</strong>
        {result && <div className="confidence-orb">{Math.round((result.overall_confidence || 0) * 100)}<small>% CONF</small></div>}
      </div>
    </section>

    <div className="control-grid">
      <section className="glass-panel control-panel">
        <div className="panel-heading"><div><span className="eyebrow">SCAN CONTROL</span><h3>Run configuration</h3></div><span className="status-led">{running ? 'ACTIVE' : 'READY'}</span></div>
        <label>Manual article URL <small>optional</small></label>
        <input value={manualUrl} onChange={e => setManualUrl(e.target.value)} placeholder="Leave blank for multi-source discovery" />
        <label>Output directory</label>
        <div className="input-action"><input value={settings.output_directory || ''} onChange={e => setSettings(s => ({ ...s, output_directory: e.target.value }))} /><button onClick={browseFolder}>Browse</button></div>
        <div className="toggle-row">
          <label className="check"><input type="checkbox" checked={settings.generate_pdf ?? true} onChange={e => setSettings(s => ({ ...s, generate_pdf: e.target.checked }))} /> PDF export</label>
          <label className="check"><input type="checkbox" checked={settings.save_json ?? true} onChange={e => setSettings(s => ({ ...s, save_json: e.target.checked }))} /> JSON export</label>
          <label className="check"><input type="checkbox" checked={sendEmail} onChange={e => setSendEmail(e.target.checked)} /> Email PDF</label>
        </div>
        {sendEmail && <div className="email-grid">
          <input placeholder="SMTP server" value={email.smtpServer} onChange={e => setEmail(v => ({...v, smtpServer:e.target.value}))}/>
          <input placeholder="Port" type="number" value={email.smtpPort} onChange={e => setEmail(v => ({...v, smtpPort:e.target.value}))}/>
          <input placeholder="Username" value={email.username} onChange={e => setEmail(v => ({...v, username:e.target.value}))}/>
          <input placeholder="App password (never persisted)" type="password" value={email.password} onChange={e => setEmail(v => ({...v, password:e.target.value}))}/>
          <input placeholder="From address" value={email.fromAddress} onChange={e => setEmail(v => ({...v, fromAddress:e.target.value}))}/>
          <input placeholder="Recipients, comma separated" value={email.recipients} onChange={e => setEmail(v => ({...v, recipients:e.target.value}))}/>
        </div>}
        {error && <div className="error-banner">{error}</div>}
      </section>

      <section className="glass-panel telemetry-panel">
        <div className="panel-heading"><div><span className="eyebrow">TELEMETRY</span><h3>Extraction pipeline</h3></div></div>
        <ProgressPipeline progress={job?.progress || 0} stage={job?.stage || 'queued'} message={job?.message || 'Ready for scan'} />
        <LogPanel logs={logs} />
      </section>
    </div>

    {result && <>
      <section className="stats-strip">
        {[
          ['SOURCES', stats.sources ?? result.sources?.length ?? 0], ['ITEMS', stats.items ?? result.row_count ?? 0],
          ['VERIFIED', stats.verified ?? result.verified_count ?? 0], ['VEHICLES', stats.vehicles ?? result.vehicles?.length ?? 0],
          ['DISCOUNTS', stats.discounts ?? 0], ['BONUSES', stats.bonuses ?? 0],
        ].map(([label,value]) => <div className="stat-card" key={label}><span>{label}</span><strong>{value}</strong></div>)}
      </section>

      <section className="glass-panel intelligence-query">
        <div><span className="eyebrow">RETRIEVAL INTELLIGENCE</span><h3>Ask this week</h3><p>Queries are answered from the latest structured weekly dataset, not general model memory.</p></div>
        <form onSubmit={askWeekly}><input value={query} onChange={e => setQuery(e.target.value)} placeholder="e.g. What is the podium vehicle? Show me this week's cars"/><button className="primary-btn">ASK WEEKLY</button></form>
        {answer && <div className="answer-box"><strong>{answer.answer}</strong>{answer.matches?.length > 0 && <small>{answer.matches.length} retrieved match(es)</small>}</div>}
      </section>

      <section className="content-heading"><div><span className="eyebrow">VEHICLE INTELLIGENCE</span><h2>Weekly garage</h2></div><div className="export-actions">{pdfUrl && <a href={pdfUrl} target="_blank">OPEN PDF</a>}{jsonUrl && <a href={jsonUrl} target="_blank">OPEN JSON</a>}</div></section>
      {result.vehicles?.length ? <div className="vehicle-grid">{result.vehicles.map((v,i) => <VehicleCard vehicle={v} key={`${v.name}-${i}`}/>)}</div> : <div className="empty-state glass-panel">No vehicle entities were confidently resolved in this dataset.</div>}

      <section className="content-heading"><div><span className="eyebrow">FULL DATASET</span><h2>Everything active this week</h2></div></section>
      <ResultSections sections={result.sections} />
    </>}
  </div>
}
