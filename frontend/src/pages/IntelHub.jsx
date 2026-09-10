import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api/client.js'

const split = value => value.split(',').map(item => item.trim()).filter(Boolean)
const join = value => (value || []).join(', ')

export default function IntelHub() {
  const [profile, setProfile] = useState(null)
  const [plan, setPlan] = useState(null)
  const [news, setNews] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [sending, setSending] = useState(false)
  const [sendingCrew, setSendingCrew] = useState(false)
  useEffect(() => {
    Promise.all([api.get('/workspace'), api.get('/plan'), api.get('/news')]).then(([p, planResponse, newsResponse]) => { setProfile(p.data); setPlan(planResponse.data); setNews(newsResponse.data) }).catch(e => setError(e.response?.data?.error || e.message))
  }, [])
  function patch(key, value) { setProfile(current => ({ ...current, [key]: value })) }
  async function save(e) {
    e.preventDefault(); setSaving(true); setMessage(''); setError('')
    try { const { data } = await api.put('/workspace', profile); setProfile(data); setPlan((await api.get('/plan')).data); setMessage('Private profile saved.') }
    catch (e) { setError(e.response?.data?.error || e.message) }
    finally { setSaving(false) }
  }
  async function sendDigest() {
    setSending(true); setMessage(''); setError('')
    try { const { data } = await api.post('/notifications/send'); setMessage(data.message) }
    catch (e) { setError(e.response?.data?.error || e.message) }
    finally { setSending(false) }
  }
  async function sendCrew() {
    setSendingCrew(true); setMessage(''); setError('')
    try { await api.post('/crew/send'); setMessage('Crew plan posted to Discord.') }
    catch (e) { setError(e.response?.data?.error || e.message) }
    finally { setSendingCrew(false) }
  }
  if (!profile) return <div className="empty-state glass-panel">Loading your private GTA hub…</div>
  const notifications = profile.notifications || {}
  const crew = profile.crew || {}
  return <div className="dashboard-stack">
    <section className="page-title"><span className="eyebrow">LOS SANTOS NETWORK // YOUR PROFILE</span><h2>Intel hub</h2><p>Save your garage, wishlist, businesses and play preferences to turn each weekly scan into a practical checklist. This profile stays behind the current app login.</p></section>
    {error && <div className="error-banner" role="alert">{error}</div>}
    <form onSubmit={save} className="hub-grid">
      <section className="glass-panel hub-card"><div className="panel-heading"><div><span className="eyebrow">PERSONAL PROFILE</span><h3>Garage & wishlist</h3></div></div><label>Owned vehicles<input value={join(profile.garage)} onChange={e => patch('garage', split(e.target.value))} placeholder="Zentorno, Oppressor Mk II" /></label><label>Wishlist<input value={join(profile.wishlist)} onChange={e => patch('wishlist', split(e.target.value))} placeholder="Turismo Omaggio, Toreador" /></label><label>Businesses and properties<input value={join(profile.businesses)} onChange={e => patch('businesses', split(e.target.value))} placeholder="Agency, Nightclub, Acid Lab" /></label><div className="settings-two"><label>Platform<select value={profile.platform} onChange={e => patch('platform', e.target.value)}><option>PC</option><option>PlayStation</option><option>Xbox</option></select></label><label>Style<select value={profile.play_style} onChange={e => patch('play_style', e.target.value)}><option>Solo</option><option>Crew</option></select></label></div><label>Hours available this week<input type="number" min="1" max="24" value={profile.available_hours} onChange={e => patch('available_hours', Number(e.target.value))} /></label></section>
      <section className="glass-panel hub-card"><div className="panel-heading"><div><span className="eyebrow">WEEKLY CHECKLIST</span><h3>What should I do this week?</h3></div></div>{plan?.tasks?.map((task, index) => <div className="plan-task" key={`${task.title}-${index}`}><span className="check-dot">✓</span><div><strong>{task.title}</strong><p>{task.details}</p><small>{task.source} · expires at the next weekly reset</small></div></div>)}<p className="muted-note">{plan?.note}</p><label>Add checklist items<input value={join(profile.checklist)} onChange={e => patch('checklist', split(e.target.value))} placeholder="Buy supplies, claim prize ride" /></label></section>
      <section className="glass-panel hub-card"><div className="panel-heading"><div><span className="eyebrow">CREW SESSION</span><h3>Plan a crew night</h3></div></div><label>Session name<input value={crew.name} onChange={e => patch('crew', { ...crew, name: e.target.value })} placeholder="Thursday heist prep" /></label><label>Date and time<input type="datetime-local" value={crew.date} onChange={e => patch('crew', { ...crew, date: e.target.value })} /></label><label>Notes<textarea rows="3" value={crew.notes} onChange={e => patch('crew', { ...crew, notes: e.target.value })} placeholder="Activities, roles, time limit" /></label><label>Discord invite URL<input type="url" value={crew.discord_url} onChange={e => patch('crew', { ...crew, discord_url: e.target.value })} placeholder="https://discord.gg/your-server" /></label><button className="secondary-btn" type="button" onClick={sendCrew} disabled={sendingCrew}>{sendingCrew ? 'POSTING…' : 'POST CREW PLAN TO DISCORD'}</button></section>
      <section className="glass-panel hub-card"><div className="panel-heading"><div><span className="eyebrow">OPT-IN DELIVERY</span><h3>Email & Discord digest</h3></div></div><label className="checkbox-line"><input type="checkbox" checked={Boolean(notifications.email_enabled)} onChange={e => patch('notifications', { ...notifications, email_enabled: e.target.checked })} /> Email my weekly PDF digest</label><label>Recipients<input value={join(notifications.email_recipients)} onChange={e => patch('notifications', { ...notifications, email_recipients: split(e.target.value) })} placeholder="you@example.com" /></label><label className="checkbox-line"><input type="checkbox" checked={Boolean(notifications.discord_enabled)} onChange={e => patch('notifications', { ...notifications, discord_enabled: e.target.checked })} /> Post the weekly link to Discord</label><label>Discord webhook URL<input type="url" value={notifications.discord_webhook || ''} onChange={e => patch('notifications', { ...notifications, discord_webhook: e.target.value })} placeholder={notifications.discord_webhook_configured ? 'Configured — enter a new URL to replace it' : 'https://discord.com/api/webhooks/…'} /></label><div className="hub-actions"><button className="primary-btn" type="submit" disabled={saving}>{saving ? 'SAVING…' : 'SAVE PROFILE'}</button><button className="secondary-btn" type="button" onClick={sendDigest} disabled={sending}>{sending ? 'SENDING…' : 'SEND DIGEST NOW'}</button></div>{message && <p className="notice-banner" role="status">{message}</p>}</section>
    </form>
    <section className="glass-panel hub-card"><div className="panel-heading"><div><span className="eyebrow">ROCKSTAR NEWSWIRE</span><h3>Official GTA news</h3></div><a className="secondary-btn" href="https://www.rockstargames.com/newswire" target="_blank" rel="noreferrer">OPEN NEWSWIRE ↗</a></div>{news?.items?.length ? <div className="news-list">{news.items.map(item => <a key={item.url} href={item.url} target="_blank" rel="noreferrer"><strong>{item.title}</strong><small>{item.date || 'Rockstar Newswire'} ↗</small></a>)}</div> : <p className="muted-note">Newswire items are unavailable right now; the official link remains available above.</p>}{news?.stale && <p className="muted-note">Showing the last cached Newswire index.</p>}</section>
    <section className="hub-links"><Link to="/vehicles" className="glass-panel feature-link"><span className="eyebrow">DATABASE</span><strong>Browse and compare vehicles →</strong></Link><Link to="/history" className="glass-panel feature-link"><span className="eyebrow">HISTORY</span><strong>Review discount history and saved scans →</strong></Link><a href="https://www.rockstargames.com/account/connections" target="_blank" rel="noreferrer" className="glass-panel feature-link"><span className="eyebrow">ACCOUNT</span><strong>Manage official Rockstar account connections ↗</strong></a></section>
  </div>
}
