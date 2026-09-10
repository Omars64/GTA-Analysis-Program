import { useEffect, useRef, useState } from 'react'
import api from '../api/client.js'

export default function VehicleCard({ vehicle, reportId, index, profileName }) {
  const [failed, setFailed] = useState([])
  const [profile, setProfile] = useState(null)
  const [requested, setRequested] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const dialog = useRef(null)
  const card = useRef(null)
  const [inView, setInView] = useState(false)
  const image = [...(profile?.image_urls || []), vehicle.image_url].find(url => url && !failed.includes(url))
  const needsProfile = requested || inView
  useEffect(() => {
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { setInView(true); observer.disconnect() }
    }, { rootMargin: '150px' })
    observer.observe(card.current)
    return () => observer.disconnect()
  }, [])
  useEffect(() => {
    if (!needsProfile || (!reportId && !profileName)) return
    const controller = new AbortController()
    setLoading(true); setError('')
    const request = reportId ? api.get(`/history/${encodeURIComponent(reportId)}/vehicles/${index}`, { signal: controller.signal, timeout: 35000 }) : api.get('/vehicles/profile', { params: { name: profileName || vehicle.name }, signal: controller.signal, timeout: 35000 })
    request
      .then(({ data }) => setProfile(data))
      .catch(e => { if (!controller.signal.aborted) setError(e.response?.data?.error || 'Vehicle details could not be loaded.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [needsProfile, reportId, index])
  function open() { setRequested(true); dialog.current.showModal() }
  const media = image ? <img src={image} alt={vehicle.name} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(previous => [...previous, image])} /> : <div className="vehicle-placeholder"><span>V</span><small>{loading ? 'FINDING VEHICLE IMAGE…' : 'IMAGE UNAVAILABLE FROM SOURCES'}</small></div>
  return <>
    <article className="vehicle-card" ref={card}>
      <button className="vehicle-open" onClick={open} aria-label={`View ${vehicle.name} specifications`}>
      <div className="vehicle-media">
        {media}
        <span className="vehicle-role">{vehicle.category || vehicle.vehicle_class || 'GTA V / Online'}</span>
      </div>
      <div className="vehicle-body">
        <div className="vehicle-title-row"><h3>{vehicle.name}</h3>{vehicle.confidence != null && <span className={vehicle.verified ? 'verified-chip' : 'confidence-chip'}>{Math.round((vehicle.confidence || 0) * 100)}%</span>}</div>
        <p>{vehicle.details || 'Detected in this week’s update.'}</p>
        <div className="vehicle-meta">
          <span>{vehicle.manufacturer || 'Unknown maker'}</span>
          <span>{vehicle.vehicle_class || `${vehicle.source_count || 1} source${vehicle.source_count === 1 ? '' : 's'}`}</span>
        </div>
        <small className="vehicle-details-hint">View performance & features ↗</small>
      </div>
      </button>
    </article>
    <dialog className="vehicle-dialog" ref={dialog} aria-label={`${vehicle.name} specifications`}>
      <div className="vehicle-dialog-heading"><h2>{vehicle.name}</h2><button autoFocus onClick={() => dialog.current.close()} aria-label="Close vehicle details">Close ✕</button></div>
      <div className="vehicle-media">{media}</div>
      {loading && <p role="status">Loading sourced specifications…</p>}
      {error && <p role="alert">{error}</p>}
      {profile && <>
        {!profile.available && <p>Specifications are not available from the vehicle database. No values have been estimated.</p>}
        <dl className="vehicle-specs">{Object.entries(profile.fields || {}).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
        <h3>Performance</h3>
        {Object.keys(profile.performance || {}).length ? Object.entries(profile.performance).map(([name, score]) => <label className="vehicle-stat" key={name}>{name}<span>{score.toFixed(2)} / 100</span><meter min="0" max="100" value={score}>{score}</meter></label>) : <p>Performance ratings unavailable.</p>}
        <h3>Durability</h3><p>{profile.durability_conditions || 'No tested durability conditions available.'}</p>
        {profile.durability?.length > 0 && <dl className="vehicle-specs">{profile.durability.map(row => <div key={row.weapon}><dt>{row.weapon}</dt><dd>{row.hits} hit(s) to destroy</dd></div>)}</dl>}
        {profile.source_url && <a href={profile.source_url} target="_blank" rel="noreferrer">Vehicle specifications & image source: GTABase ↗</a>}
      </>}
    </dialog>
  </>
}
