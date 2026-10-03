import { useEffect, useState } from 'react'
import type { Session, SupabaseClient } from '@supabase/supabase-js'

function unexpired(session: Session | null): Session | null {
  return session?.expires_at && session.expires_at * 1000 <= Date.now() ? null : session
}

export function useSession(client: SupabaseClient) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    let changed = false
    const timer = setTimeout(() => {
      if (active && !changed) {
        changed = true
        setError('Session could not be loaded. Reload to try again.')
        setLoading(false)
      }
    }, 10000)
    const { data } = client.auth.onAuthStateChange((_event, next) => {
      changed = true
      if (active) { setSession(unexpired(next)); setError(''); setLoading(false) }
    })
    client.auth.getSession().then(({ data, error }) => {
      if (!active || changed) return
      clearTimeout(timer)
      setSession(error ? null : unexpired(data.session))
      setError(error ? 'Session could not be loaded.' : '')
      setLoading(false)
    }).catch(() => {
      clearTimeout(timer)
      if (active && !changed) { setError('Session could not be loaded.'); setLoading(false) }
    })
    return () => { active = false; clearTimeout(timer); data.subscription.unsubscribe() }
  }, [client])
  useEffect(() => {
    if (!session?.expires_at) return
    // Supabase refresh events replace this timer; an unrefreshed expired session
    // must not retain protected UI indefinitely.
    const timer = setTimeout(() => setSession(null), Math.max(0, session.expires_at * 1000 - Date.now()))
    return () => clearTimeout(timer)
  }, [session])
  return { session, loading, error }
}
