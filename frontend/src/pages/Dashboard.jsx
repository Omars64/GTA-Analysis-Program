import { useEffect, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import api from '../api/client.js'
import useScan from '../hooks/useScan.js'
import ProgressPipeline from '../components/ProgressPipeline.jsx'
import LogPanel from '../components/LogPanel.jsx'
import VehicleCard from '../components/VehicleCard.jsx'
import ResultSections from '../components/ResultSections.jsx'
import ReportEditor from '../components/ReportEditor.jsx'

export default function Dashboard() {
  const [searchParams, setSearchParams] = useSearchParams()
  const snapshotId = searchParams.get('snapshot')
  const [manualUrl, setManualUrl] = useState('')
  const [settings, setSettings] = useState({ output_directory: '', generate_pdf: true, save_json: true })
  const [capabilities, setCapabilities] = useState(null)
  const [result, setResult] = useState(null)
  const [query, setQuery] = useState('')
  const [answer, setAnswer] = useState(null)
  const [asking, setAsking] = useState(false)
  const { job, logs, running, starting, recovering, reconnecting, start, cancel, error, setError } = useScan()

  useEffect(() => {
    const controller = new AbortController()
    const config = { signal: controller.signal }
    Promise.all([api.get('/settings', config), api.get('/capabilities', config)])
      .then(([settingsResponse, capabilitiesResponse]) => {
        setSettings(settingsResponse.data); setCapabilities(capabilitiesResponse.data)
      }).catch(e => { if (!controller.signal.aborted) setError(e.response?.data?.error || e.message) })
    return () => controller.abort()
  }, [setError])

  useEffect(() => {
    const controller = new AbortController()
    setAnswer(null)
    if (!snapshotId) { setResult(null); return () => controller.abort() }
    api.get(`/history/${encodeURIComponent(snapshotId)}`, { signal: controller.signal })
      .then(r => setResult(r.data?.week_start ? r.data : null))
      .catch(e => { if (!controller.signal.aborted) { setResult(null); setError(e.response?.data?.error || e.message) } })
    return () => controller.abort()
  }, [snapshotId, setError])

  useEffect(() => {
    if (job?.status === 'completed' && job.result && !snapshotId) setResult(job.result)
  }, [job?.status, job?.result, snapshotId])

  async function startRun() {
    setAnswer(null); setResult(null); setSearchParams({})
    await start({
      manualUrl: manualUrl.trim() || null,
      outputDirectory: settings.output_directory,
      generatePdf: true, saveJson: true, sendEmail: false,
    })
  }

  async function browseFolder() {
    try {
      const { data } = await api.post('/system/select-output-directory')
      if (data.output_directory) setSettings(s => ({ ...s, output_directory: data.output_directory }))
    } catch (e) { setError(e.response?.data?.error || 'Native folder picker is unavailable. Enter the path manually.') }
  }

  async function askWeekly(e) {
    e.preventDefault()
    if (!query.trim()) return
    setAsking(true)
    try { setAnswer((await api.post('/knowledge/query', { query, snapshotId: result?.id })).data) }
    catch (e) { setAnswer({ answer: e.response?.data?.error || e.message, matches: [] }) }
    finally { setAsking(false) }
  }

  const stats = result?.stats || {}

  return <div className="dashboard-stack">
    <section className="hero glass-panel">
      <div className="hero-copy">
        <div className="eyebrow">GTA ONLINE // WEEKLY ANALYSIS</div>
        <h2>Weekly Analysis<br/><span>and Intelligence</span></h2>
        <p>Discover, cross-check, extract, enrich and explore the current GTA Online week from one structured dataset.</p>
        <div className="hero-actions">
          <button className="primary-btn" onClick={startRun} disabled={running || starting || recovering || !capabilities}>{starting ? 'STARTING…' : recovering ? 'RESTORING SESSION…' : running ? 'INTELLIGENCE RUN ACTIVE' : 'RUN WEEKLY INTELLIGENCE'}</button>
          {running && <button className="danger-btn" onClick={cancel} disabled={job.cancel_requested}>{job.cancel_requested ? 'CANCELLING…' : 'CANCEL RUN'}</button>}
        </div>
      </div>
      <div className="hero-week">
        <span>{snapshotId ? 'ARCHIVED DATASET' : result?.is_current ? 'CURRENT DATASET' : 'LATEST AVAILABLE DATASET'}</span>
        <strong>{result?.week_start || 'NO SCAN'}</strong>
        <i>→</i>
        <strong>{result?.week_end || 'RUN TO LOAD'}</strong>
        {result && <div className="confidence-orb">{Math.round((result.overall_confidence || 0) * 100)}<small>% CONF</small></div>}
      </div>
    </section>

    <div className="control-grid">
      <section className="glass-panel control-panel">
        <div className="panel-heading"><div><span className="eyebrow">SCAN CONTROL</span><h3>Run configuration</h3></div><span className="status-led">{running ? 'ACTIVE' : 'READY'}</span></div>
        <p className="muted-note">These sources will be scanned when you press Run. Add or change them in Settings.</p>
        <div className="source-list">{settings.source_urls?.map(url => <a key={url} href={url} target="_blank" rel="noreferrer">{url}</a>)}</div>
        <label htmlFor="manual-url">Additional article URL <small>optional</small></label>
        <input id="manual-url" type="url" value={manualUrl} onChange={e => setManualUrl(e.target.value)} placeholder="Leave blank for multi-source discovery" />
        {capabilities?.cloud ? <p className="muted-note">Reports are stored securely and downloaded through your browser. No local folder is needed.</p> : <>
          <label htmlFor="output-directory">Output directory</label>
          <div className="input-action"><input id="output-directory" value={settings.output_directory || ''} onChange={e => setSettings(s => ({ ...s, output_directory: e.target.value }))} />{capabilities?.native_folder_picker && <button onClick={browseFolder}>Browse</button>}</div>
        </>}
        {error && <div className="error-banner" role="alert">{error}</div>}
      </section>

      <section className="glass-panel telemetry-panel">
        <div className="panel-heading"><div><span className="eyebrow">TELEMETRY</span><h3>Extraction pipeline</h3></div></div>
        <ProgressPipeline progress={job?.progress || 0} stage={job?.stage || 'queued'} message={job?.message || 'Ready for scan'} />
        <LogPanel logs={logs} />
        {reconnecting && running && <p className="muted-note" role="status">Reconnecting live updates. Status is also checked every five seconds.</p>}
      </section>
    </div>

    {snapshotId && <div className="notice-banner">Viewing an archived report. <Link to="/">Return to dashboard →</Link></div>}
    {result && <>
      <ReportEditor key={`${result.id}-${result.revision || 0}`} report={result} onSave={setResult} emailConfigured={capabilities?.email_configured} />
      {(result.warnings?.length > 0 || result.email_error || result.email_sent) && <section className="notice-banner" aria-label="Report notices">
        {result.warnings?.map((warning, index) => <p key={index}>{warning}</p>)}
        {result.email_error && <p role="alert">{result.email_error}</p>}
        {result.email_sent && <p>Email delivery accepted by the mail server.</p>}
      </section>}
      <section className="stats-strip">
        {[
          ['SOURCES', stats.sources ?? result.sources?.length ?? 0], ['ITEMS', stats.items ?? result.row_count ?? 0],
          ['VERIFIED', stats.verified ?? result.verified_count ?? 0], ['VEHICLES', stats.vehicles ?? result.vehicles?.length ?? 0],
          ['DISCOUNTS', stats.discounts ?? 0], ['BONUSES', stats.bonuses ?? 0],
        ].map(([label,value]) => <div className="stat-card" key={label}><span>{label}</span><strong>{value}</strong></div>)}
      </section>

      <section className="glass-panel intelligence-query">
        <div><span className="eyebrow">RETRIEVAL INTELLIGENCE</span><h3>Find specifics</h3><p>Answers are retrieved from this report’s structured data and linked sources.</p></div>
        <form onSubmit={askWeekly}><input aria-label="Question about this report" maxLength={1000} value={query} onChange={e => setQuery(e.target.value)} placeholder="e.g. What is the podium vehicle? Show me this week's cars"/><button className="primary-btn" disabled={asking || !query.trim()}>{asking ? 'SEARCHING…' : 'SEARCH'}</button></form>
        {answer && <div className="answer-box"><strong>{answer.answer}</strong>{answer.corrected_query && <small>Searching for: {answer.corrected_query}</small>}{answer.matches?.length > 0 && <ul>{answer.matches.map((match, i) => <li key={i}>{match.item || match.name}{match.details ? ` — ${match.details}` : ""}</li>)}</ul>}</div>}
      </section>

      <section className="content-heading"><div><span className="eyebrow">VEHICLE INTELLIGENCE</span><h2>Weekly garage</h2></div></section>
      {result.vehicles?.length ? <div className="vehicle-grid">{result.vehicles.map((v,i) => <VehicleCard vehicle={v} reportId={result.id} index={i} key={`${result.id}-${v.name}-${i}`}/>)}</div> : <div className="empty-state glass-panel">No vehicle entities were confidently resolved in this dataset.</div>}

      <section className="content-heading"><div><span className="eyebrow">FULL DATASET</span><h2>Everything active this week</h2></div></section>
      <ResultSections sections={result.sections} />
      <section className="glass-panel control-panel source-list"><h3>Report sources</h3>{result.sources?.map(source => <a key={source.url} href={source.url} target="_blank" rel="noopener noreferrer">{source.provider}: {source.label || source.url} ↗</a>)}</section>
    </>}
  </div>
}
