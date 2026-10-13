import { useEffect, useState } from 'react'
import type { SupabaseClient } from '@supabase/supabase-js'
import { privateRequest, privateError } from './api/private'
type Binding = { id: string; channel: string; status: string; revision: number }
export default function TelegramConnection({ client, account }: { client: SupabaseClient; account: string }) {
  const [bindings, setBindings] = useState<Binding[]>([]), [bot, setBot] = useState<string | null>(null), [token, setToken] = useState<string | null>(null), [expires, setExpires] = useState(0)
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [attempt, setAttempt] = useState(0), [loaded, setLoaded] = useState(false)
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    Promise.all([privateRequest(client, account, '/api/me/delivery/bindings', { signal: controller.signal }), privateRequest(client, account, '/api/me/delivery/telegram/config', { signal: controller.signal })]).then(([rows, config]) => {
      if (!Array.isArray(rows)) throw Error()
      if (active) { setBindings(rows as Binding[]); setBot((config as { bot_username: string | null }).bot_username); setLoaded(true) }
    }).catch(error => { if (active) setMessage(privateError(error)) })
    return () => { active = false; controller.abort() }
  }, [client, account, attempt])
  useEffect(() => { if (!token) return; const timer = setTimeout(() => { setToken(null); setMessage('Connection code expired. Request a new code if needed.') }, Math.max(0, expires - Date.now())); return () => clearTimeout(timer) }, [token, expires])
  async function connect() {
    setBusy(true); setMessage('')
    try { const value = await privateRequest(client, account, '/api/me/delivery/telegram/challenge', { method: 'POST' }) as { challenge: string; expires_in_seconds: number }
      setToken(value.challenge); setExpires(Date.now() + value.expires_in_seconds * 1000)
    } catch (error) { setMessage(privateError(error)) } finally { setBusy(false) }
  }
  async function revoke(id: string) {
    setBusy(true); setMessage('')
    try { await privateRequest(client, account, `/api/me/delivery/bindings/${encodeURIComponent(id)}/revoke`, { method: 'POST' }); setToken(null); setAttempt(a => a + 1) }
    catch (error) { setMessage(privateError(error)) } finally { setBusy(false) }
  }
  const connected = bindings.filter(b => b.channel === 'telegram' && b.status === 'active')
  return <section aria-label="Telegram connection"><h2>Telegram delivery</h2>
    <p>Optional. Connecting confirms consent to send your Weekend Packets to your private Telegram chat.</p>
    {message && <p role="status">{message}</p>}
    {!loaded && <p>Loading connection…</p>}
    {loaded && <p>{connected.length ? 'Telegram is connected.' : 'Telegram is not connected.'}</p>}
    {connected.map(b => <button key={b.id} disabled={busy} onClick={() => revoke(b.id)}>Revoke Telegram connection</button>)}
    <button disabled={busy || !bot} onClick={connect}>{connected.length ? 'Replace Telegram connection' : 'Connect Telegram'}</button>
    {!bot && <p>The Telegram bot is not configured for connections yet.</p>}
    {token && <><p>Open the verified Event Radar bot @{bot} in a private chat and send this exact command within ten minutes. Keep this code private.</p><code className="connection-code">/start {token}</code><p>Then select Refresh connection. This page does not contact Telegram.</p></>}
    <button disabled={busy} onClick={() => { setToken(null); setAttempt(a => a + 1) }}>Refresh connection</button>
  </section>
}
