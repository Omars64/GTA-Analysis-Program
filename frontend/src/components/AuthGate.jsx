import { useCallback, useEffect, useState } from 'react'
import api from '../api/client.js'

export default function AuthGate({ children }) {
  const [session, setSession] = useState(null)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const check = useCallback(async () => {
    setError('')
    try { setSession((await api.get('/session')).data) }
    catch (e) { setError(e.response?.data?.error || 'Cannot reach the service. Check the connection and retry.') }
  }, [])
  useEffect(() => {
    check()
    const expired = () => { setSession({ authenticated: false, required: true }); setPassword('') }
    window.addEventListener('session-expired', expired)
    return () => window.removeEventListener('session-expired', expired)
  }, [check])
  async function signIn(event) {
    event.preventDefault(); setBusy(true); setError('')
    try { setSession((await api.post('/session', { password })).data); setPassword('') }
    catch (e) { setError(e.response?.data?.error || 'Unable to sign in.') }
    finally { setBusy(false) }
  }
  async function signOut() {
    try { await api.delete('/session'); setSession({ authenticated: false, required: true }) }
    catch { setError('Unable to sign out. Please retry.') }
  }
  if (session?.authenticated) return <>{session.required && <div className="session-bar"><span>PRIVATE COMPANION</span><button onClick={signOut}>Sign out</button>{error && <span role="alert">{error}</span>}</div>}{children}</>
  return <main className="auth-shell app-shell"><section className="auth-card glass-panel">
    <span className="eyebrow">LOS SANTOS NETWORK // PRIVATE ACCESS</span>
    <h1>GTA Weekly Intelligence</h1>
    {session ? <form onSubmit={signIn}>
      <p>Sign in with your companion password to run scans and access your reports.</p>
      <label htmlFor="app-password">Companion password</label>
      <input id="app-password" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required />
      <button className="primary-btn" disabled={busy}>{busy ? 'SIGNING IN…' : 'SIGN IN'}</button>
    </form> : <p role="status">{error ? 'Service unavailable.' : 'Connecting to your companion…'}</p>}
    {error && <div className="error-banner" role="alert">{error}</div>}
    {!session && error && <button className="primary-btn" onClick={check}>RETRY CONNECTION</button>}
  </section></main>
}
