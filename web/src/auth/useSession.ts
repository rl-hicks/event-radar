import { useEffect, useState } from 'react'
import type { Session, SupabaseClient } from '@supabase/supabase-js'

export function useSession(client: SupabaseClient) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    let changed = false
    const { data } = client.auth.onAuthStateChange((_event, next) => {
      changed = true
      if (active) { setSession(next); setError(''); setLoading(false) }
    })
    client.auth.getSession().then(({ data, error }) => {
      if (!active || changed) return
      setSession(error ? null : data.session)
      setError(error ? 'Session could not be loaded.' : '')
      setLoading(false)
    }).catch(() => {
      if (active && !changed) { setError('Session could not be loaded.'); setLoading(false) }
    })
    return () => { active = false; data.subscription.unsubscribe() }
  }, [client])
  return { session, loading, error }
}
