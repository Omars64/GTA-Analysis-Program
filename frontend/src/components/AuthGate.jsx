import { createContext, useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client.js'

export const AuthContext = createContext(null)
function resetScanSession() {
  try { sessionStorage.removeItem('gta.session-run'); localStorage.removeItem('gta.last-run.v1') } catch { /* Storage can be disabled. */ }
}

export default function AuthGate({ children }) {
  const [session, setSession] = useState(null)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [visible, setVisible] = useState(false)
  const navigate = useNavigate()
  const check = useCallback(async () => {
    setError('')
    try { setSession((await api.get('/session')).data) }
    catch (e) { setError(e.response?.data?.error || 'Cannot reach the service. Check the connection and retry.') }
  }, [])
  useEffect(() => {
    check()
    const expired = () => { resetScanSession(); setSession({ authenticated: false, required: true }); setPassword(''); setVisible(false) }
    window.addEventListener('session-expired', expired)
    return () => window.removeEventListener('session-expired', expired)
  }, [check])
  async function signIn(event) {
    event.preventDefault(); setBusy(true); setError('')
    try { const { data } = await api.post('/session', { password }); resetScanSession(); navigate('/', { replace: true }); setSession(data); setPassword(''); setVisible(false) }
    catch (e) { setError(e.response?.data?.error || 'Unable to sign in.') }
    finally { setBusy(false) }
  }
  async function signOut() {
    setBusy(true); setError('')
    try { await api.delete('/session'); resetScanSession(); navigate('/', { replace: true }); setSession({ authenticated: false, required: true }); setVisible(false) }
    catch { setError('Unable to sign out. Please retry.') }
    finally { setBusy(false) }
  }
  if (session?.authenticated) return <AuthContext.Provider value={{ signOut, busy, error }}>{children}</AuthContext.Provider>
  return <main className="auth-shell app-shell"><section className="auth-card glass-panel">
    <span className="eyebrow">LOS SANTOS NETWORK // PRIVATE ACCESS</span>
    <h1>GTA Intelligence</h1>
    {session ? <form onSubmit={signIn}>
      <p>Sign in to run scans and access your reports.</p>
      <label htmlFor="app-password">Password</label>
      <div className="password-field"><input id="app-password" type={visible ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /><button type="button" aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible} onClick={() => setVisible(v => !v)}>{visible ? 'Hide' : 'Show'}</button></div>
      <button className="primary-btn" disabled={busy}>{busy ? 'SIGNING IN…' : 'SIGN IN'}</button>
    </form> : <p role="status">{error ? 'Service unavailable.' : 'Connecting to GTA Intelligence…'}</p>}
    {error && <div className="error-banner" role="alert">{error}</div>}
    {!session && error && <button className="primary-btn" onClick={check}>RETRY CONNECTION</button>}
  </section></main>
}
