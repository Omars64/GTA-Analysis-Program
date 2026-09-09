import { NavLink } from 'react-router-dom'
import { useContext, useEffect, useState } from 'react'
import { AuthContext } from './AuthGate.jsx'
import api from '../api/client.js'

export default function Layout({ children }) {
  const auth = useContext(AuthContext)
  const [number, setNumber] = useState(5)
  useEffect(() => {
    const refresh = () => api.get('/settings').then(r => setNumber(Math.min(6, Math.max(1, r.data.game_number || 5)))).catch(() => {})
    refresh(); window.addEventListener('settings-updated', refresh)
    return () => window.removeEventListener('settings-updated', refresh)
  }, [])
  const roman = 'X'.repeat(Math.floor(number / 10)) + ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX'][number % 10]
  return (
    <div className="app-shell">
      <div className="sky-glow" />
      <div className="grid-horizon" />
      <div className="scanlines" />
      <header className="topbar glass-panel">
        <div className="brand-lockup">
          <div className="brand-mark" aria-label={`GTA ${number}`}><span>{roman}</span></div>
          <div>
            <div className="eyebrow">LOS SANTOS NETWORK // ONLINE</div>
            <h1>GTA Intelligence</h1>
          </div>
        </div>
        <nav className="nav-tabs">
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/history">History</NavLink>
          <NavLink to="/settings">Settings</NavLink>
          <button className="nav-signout" onClick={auth?.signOut} disabled={auth?.busy}>{auth?.busy ? 'Signing out…' : 'Sign out'}</button>
        </nav>
      </header>
      <main className="page-wrap">{auth?.error && <p className="error-banner" role="alert">{auth.error}</p>}{children}</main>
      <footer className="footer">GTA Intelligence · source-backed analysis · unofficial fan project</footer>
    </div>
  )
}
