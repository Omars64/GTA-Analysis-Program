import { useEffect, useMemo, useState } from 'react'
import api from '../api/client.js'
import VehicleCard from '../components/VehicleCard.jsx'

function CompareRow({ label, profiles }) {
  return <div className="compare-row"><strong>{label}</strong>{profiles.map(profile => <span key={profile.name}>{profile.fields?.[label] || profile.performance?.[label] || '—'}</span>)}</div>
}

export default function VehicleBrowser() {
  const [query, setQuery] = useState('')
  const [manufacturer, setManufacturer] = useState('')
  const [data, setData] = useState({ items: [], manufacturers: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState([])
  const [profiles, setProfiles] = useState([])
  const [compareBusy, setCompareBusy] = useState(false)

  async function load(refresh = false) {
    refresh ? setRefreshing(true) : setLoading(true); setError('')
    try {
      const { data: response } = await api.get('/vehicles', { params: { q: query, manufacturer, refresh: refresh ? 1 : 0 }, timeout: 40000 })
      setData(response)
    } catch (e) { setError(e.response?.data?.error || e.message) }
    finally { setLoading(false); setRefreshing(false) }
  }
  useEffect(() => { const timer = setTimeout(() => load(), 250); return () => clearTimeout(timer) }, [query, manufacturer])

  const selectedItems = useMemo(() => data.items.filter(item => selected.includes(item.id)), [data.items, selected])
  function toggle(item) {
    setSelected(current => current.includes(item.id) ? current.filter(id => id !== item.id) : current.length < 3 ? [...current, item.id] : current)
  }
  async function compare() {
    setCompareBusy(true); setError('')
    try {
      const values = await Promise.all(selectedItems.map(item => api.get('/vehicles/profile', { params: { name: item.name }, timeout: 35000 }).then(r => r.data)))
      setProfiles(values)
    } catch (e) { setError(e.response?.data?.error || 'Comparison details could not be loaded.') }
    finally { setCompareBusy(false) }
  }
  return <div className="dashboard-stack">
    <section className="page-title"><span className="eyebrow">GTA V // ONLINE DATABASE</span><h2>Vehicle browser</h2><p>Search every vehicle in the live directory by manufacturer or model. Open a card for sourced performance, price, features and durability details.</p></section>
    <section className="glass-panel browser-controls">
      <label>Search vehicle or manufacturer<input aria-label="Search vehicles" value={query} onChange={e => setQuery(e.target.value)} placeholder="Try Ocelot, Zentorno or Sentinel" /></label>
      <label>Manufacturer<select aria-label="Filter by manufacturer" value={manufacturer} onChange={e => setManufacturer(e.target.value)}><option value="">All manufacturers</option>{data.manufacturers.map(name => <option key={name} value={name}>{name}</option>)}</select></label>
      <button className="primary-btn" onClick={() => load(true)} disabled={refreshing}>{refreshing ? 'REFRESHING…' : 'REFRESH DIRECTORY'}</button>
      <div className="browser-meta"><strong>{loading ? 'Loading directory…' : `${data.total || 0} vehicle${data.total === 1 ? '' : 's'}`}</strong><span>{data.stale ? 'Showing cached data; refresh will retry the source.' : 'Source-linked catalogue'}</span></div>
    </section>
    {error && <div className="error-banner" role="alert">{error}</div>}
    {selected.length > 0 && <section className="glass-panel compare-toolbar"><div><span className="eyebrow">COMPARISON</span><strong>{selected.length} selected</strong><small>Choose up to three vehicles for a side-by-side view.</small></div><button className="primary-btn" onClick={compare} disabled={compareBusy}>{compareBusy ? 'LOADING…' : 'COMPARE SELECTED'}</button><button className="secondary-btn" onClick={() => { setSelected([]); setProfiles([]) }}>CLEAR</button></section>}
    {profiles.length > 0 && <section className="glass-panel comparison"><div className="panel-heading"><div><span className="eyebrow">VEHICLE INTELLIGENCE</span><h3>Side-by-side comparison</h3></div><button className="secondary-btn" onClick={() => setProfiles([])}>Close</button></div><div className="compare-grid"><div className="compare-heading"><strong>SPECIFICATION</strong>{profiles.map(profile => <strong key={profile.name}>{profile.name}</strong>)}</div><CompareRow label="Manufacturer" profiles={profiles} /><CompareRow label="Vehicle Class" profiles={profiles} /><CompareRow label="GTA Online Price" profiles={profiles} /><CompareRow label="Top Speed" profiles={profiles} /><CompareRow label="Lap Time" profiles={profiles} /><CompareRow label="Speed" profiles={profiles} /><CompareRow label="Handling" profiles={profiles} /></div></section>}
    {loading ? <div className="empty-state glass-panel">Loading the vehicle directory…</div> : data.items.length ? <div className="vehicle-grid browser-grid">{data.items.map(item => <div className="browser-card-wrap" key={item.id}><VehicleCard vehicle={{ ...item, category: item.vehicle_class || 'GTA V / Online', details: item.price ? `Listed price: ${item.price}` : 'Open for sourced specifications.', verified: false }} profileName={item.name} /><label className="compare-check"><input type="checkbox" checked={selected.includes(item.id)} onChange={() => toggle(item)} /> Compare</label></div>)}</div> : <div className="empty-state glass-panel">No matching vehicles. Try a model name, a manufacturer, or clear the filters.</div>}
    <p className="source-caption">Directory and specifications: <a href={data.source_url || 'https://www.gtabase.com/grand-theft-auto-v/vehicles/'} target="_blank" rel="noreferrer">GTABase GTA V vehicles ↗</a>. GTA Intelligence links to the source and does not claim Rockstar affiliation.</p>
  </div>
}
