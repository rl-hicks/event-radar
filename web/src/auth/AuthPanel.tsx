import { useState } from 'react'
import type { SupabaseClient } from '@supabase/supabase-js'
import { signIn, signOut, signUp } from './actions'
import { useSession } from './useSession'
import { getMe, type Me } from '../api/client'

function IdentityProbe({ client }: { client: SupabaseClient }) {
  const [me, setMe] = useState<Me | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  async function check() {
    setBusy(true); setMessage(''); setMe(null)
    try { setMe(await getMe(client)) }
    catch { setMessage('Authenticated API check failed. Check backend configuration and session.') }
    finally { setBusy(false) }
  }
  return <section aria-label="Backend identity proof">
    <button disabled={busy} onClick={check}>Check /api/me</button>
    {me && <p>Backend identity: {me.id}. Database roundtrip: {String(me.database_roundtrip)}.</p>}
    <p role="status">{message}</p>
  </section>
}

export default function AuthPanel({ client }: { client: SupabaseClient }) {
  const { session, loading, error } = useSession(client)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  async function authenticate(mode: 'in' | 'up') {
    setBusy(true); setMessage('')
    try {
      if (mode === 'in') { await signIn(client, email, password); setMessage('Signed in.') }
      else {
        const result = await signUp(client, email, password)
        setMessage(result.needsConfirmation ? 'Check your email to confirm your account before signing in.' : 'Account created and signed in.')
      }
    } catch { setMessage('Authentication failed. Check your credentials and email confirmation.') }
    finally { setPassword(''); setBusy(false) }
  }
  async function logout() {
    setBusy(true); setMessage('')
    try { await signOut(client); setMessage('This browser session is signed out.') }
    catch { setMessage('Sign-out failed. Please try again.') }
    finally { setBusy(false) }
  }
  if (loading) return <p>Loading browser session…</p>
  return <section aria-label="Authentication foundation">
    <h2>Authentication development check</h2>
    <p role="status">{error || message}</p>
    {session ? <>
      <p>Signed in as {session.user.email ?? session.user.id}</p>
      <button disabled={busy} onClick={logout}>Sign out of this browser</button>
      <IdentityProbe key={session.user.id} client={client} />
    </> : <form onSubmit={event => { event.preventDefault(); void authenticate('in') }}>
      <label>Email<input type="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)} /></label>
      <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} /></label>
      <button type="submit" disabled={busy}>Sign in</button>
      <button type="button" disabled={busy || !email || !password} onClick={() => authenticate('up')}>Sign up</button>
    </form>}
  </section>
}
