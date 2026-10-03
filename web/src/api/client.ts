import type { SupabaseClient } from '@supabase/supabase-js'

export type Me = { id: string; email: string | null; created_at: string; database_roundtrip: boolean }

async function requestMe(client: SupabaseClient, base = import.meta.env.VITE_API_URL || 'http://localhost:8000'): Promise<Me> {
  const { data, error } = await client.auth.getSession()
  if (error || !data.session?.access_token) throw new Error('Sign in before calling the API.')
  const url = new URL(base)
  const local = ['localhost', '127.0.0.1'].includes(url.hostname)
  if ((url.protocol !== 'https:' && !(local && url.protocol === 'http:')) || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('API configuration is invalid.')
  }
  let response: Response
  try {
    response = await fetch(new URL('/api/me', url), {
      method: 'GET', headers: { Authorization: `Bearer ${data.session.access_token}` },
      signal: AbortSignal.timeout(10000),
    })
  } catch { throw new Error('API request could not be completed.') }
  if (!response.ok) throw new Error(response.status === 401 ? 'Authentication expired or was rejected.' : 'API is unavailable.')
  try {
    const value = await response.json()
    if (typeof value.id !== 'string' || typeof value.created_at !== 'string' ||
        typeof value.database_roundtrip !== 'boolean' || (value.email !== null && typeof value.email !== 'string')) throw new Error()
    return { id: value.id, email: value.email, created_at: value.created_at, database_roundtrip: value.database_roundtrip }
  } catch { throw new Error('API response was invalid.') }
}

export async function getMe(client: SupabaseClient, base?: string): Promise<Me> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([
      requestMe(client, base),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error('API request could not be completed.')), 10000)
      }),
    ])
  } finally { clearTimeout(timer) }
}
