import { NavLink } from 'react-router-dom'

export default function Layout({ children }) {
  return (
    <div className="app-shell">
      <div className="sky-glow" />
      <div className="grid-horizon" />
      <div className="scanlines" />
      <header className="topbar glass-panel">
        <div className="brand-lockup">
          <div className="brand-mark"><span>VI</span></div>
          <div>
            <div className="eyebrow">LOS SANTOS NETWORK // ONLINE</div>
            <h1>GTA Weekly Intelligence</h1>
          </div>
        </div>
        <nav className="nav-tabs">
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/history">History</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
      </header>
      <main className="page-wrap">{children}</main>
      <footer className="footer">GTA Online Weekly Companion · local-first intelligence dashboard</footer>
    </div>
  )
}
