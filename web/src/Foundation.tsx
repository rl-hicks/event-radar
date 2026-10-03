import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, Route, Routes } from 'react-router'
import type { Session, SupabaseClient } from '@supabase/supabase-js'
import { signIn, signOut, signUp } from './auth/actions'
import { useSession } from './auth/useSession'
import { getMe, type Me } from './api/client'

type Props = { client: SupabaseClient | null; invalid?: boolean }
export default function Foundation({ client, invalid = false }: Props) {
  return <main><p className="eyebrow">Event Radar · E0 foundation</p>
    {client ? <Connected client={client} /> : <Pages client={null} session={null} loading={false} error={invalid ? 'Supabase browser configuration is invalid.' : 'Configure the public Supabase browser values to enable authentication.'} />}
  </main>
}
function Connected({ client }: { client: SupabaseClient }) {
  const state = useSession(client)
  return <Pages client={client} {...state} />
}
type State = { client: SupabaseClient | null; session: Session | null; loading: boolean; error: string }
function Pages({ client, session, loading, error }: State) {
  const gate = (protectedPage: boolean) => {
    if (loading) return <p role="status">Restoring session…</p>
    if (error) return <p role="alert">{error}</p>
    if (!client) return <p role="alert">Authentication is unavailable.</p>
    if (protectedPage) return session ? <Identity key={session.user.id} client={client} session={session} /> : <Navigate to="/login" replace />
    return session ? <Navigate to="/app" replace /> : null
  }
  return <Routes>
    <Route path="/" element={<><h1>Event Radar</h1><p>Your weekend, researched for you.</p><p>The product is under development. This is the authentication and database foundation only.</p><nav aria-label="Account"><Link to="/login">Sign in</Link> · <Link to="/signup">Create account</Link></nav></>} />
    <Route path="/login" element={gate(false) ?? <AuthForm key="login" client={client!} mode="login" />} />
    <Route path="/signup" element={gate(false) ?? <AuthForm key="signup" client={client!} mode="signup" />} />
    <Route path="/app" element={gate(true)} />
    <Route path="*" element={<><h1>Page not found</h1><Link to="/">Return home</Link></>} />
  </Routes>
}
function AuthForm({ client, mode }: { client: SupabaseClient; mode: 'login' | 'signup' }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [failed, setFailed] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage(''); setFailed(false)
    try {
      if (mode === 'login') await signIn(client, email, password)
      else {
        const result = await signUp(client, email, password)
        if (result.needsConfirmation) setMessage('Check your email to confirm your account, then sign in. You are not signed in yet.')
      }
      setPassword('')
    } catch { setFailed(true); setMessage(mode === 'login' ? 'Sign-in failed. Check your credentials and confirmation status.' : 'Sign-up could not be completed. Please try again.') }
    finally { setBusy(false) }
  }
  return <><h1>{mode === 'login' ? 'Sign in' : 'Create account'}</h1>
    <form onSubmit={submit} aria-busy={busy}>
      <label htmlFor="email">Email</label><input id="email" type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} disabled={busy} />
      <label htmlFor="password">Password</label><input id="password" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required value={password} onChange={e => setPassword(e.target.value)} disabled={busy} />
      <button disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
    </form>
    {message && <p role={failed ? 'alert' : 'status'}>{message}</p>}
    <p><Link to={mode === 'login' ? '/signup' : '/login'}>{mode === 'login' ? 'Create account' : 'Sign in'}</Link> · <Link to="/">Home</Link></p>
  </>
}
function Identity({ client, session }: { client: SupabaseClient; session: Session }) {
  const [result, setResult] = useState<{ token: string; me?: Me; error?: string } | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [busy, setBusy] = useState(false)
  const [logoutError, setLogoutError] = useState('')
  useEffect(() => {
    let active = true
    getMe(client).then(me => { if (active) setResult({ token: session.access_token, me }) }).catch(error => {
      if (active) setResult({ token: session.access_token, error: error instanceof Error && ['Authentication expired or was rejected.', 'API is unavailable.', 'API response was invalid.'].includes(error.message) ? error.message : 'API request could not be completed.' })
    })
    return () => { active = false }
  }, [client, session.access_token, attempt])
  async function logout() {
    setBusy(true); setLogoutError('')
    try { await signOut(client) }
    catch { setLogoutError('Sign-out could not be completed. Please try again.'); setBusy(false) }
  }
  const current = result?.token === session.access_token ? result : null
  return <><h1>E0 authenticated foundation</h1><p>Signed in as {session.user.email || 'authenticated user'}.</p>
    <p>This verifies authentication and persistence only. Product features are not available.</p>
    {!current && <p role="status">Checking API connectivity…</p>}
    {current?.error && <p role="alert">{current.error} You can retry or sign out and sign in again.</p>}
    {current?.me && <section aria-label="Backend identity"><h2>Backend connection</h2><p>API connectivity: confirmed</p><p>Backend identity: {current.me.id}</p><p>Database roundtrip: {current.me.database_roundtrip ? 'confirmed' : 'not confirmed'}</p></section>}
    {current?.error && <button onClick={() => { setResult(null); setAttempt(value => value + 1) }}>Retry API</button>}
    <button disabled={busy} onClick={logout}>{busy ? 'Signing out…' : 'Sign out'}</button>
    {logoutError && <p role="alert">{logoutError}</p>}
  </>
}
