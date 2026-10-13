import type { SupabaseClient } from '@supabase/supabase-js'

export class PrivateApiError extends Error {
  constructor(public status: number) {
    super(status === 409 ? 'Your profile changed elsewhere. Reload before saving again.' : status === 422 ? 'Check your entries, including timezone, limits and time ranges.' : status === 401 ? 'Sign in again to continue.' : 'The request could not be completed. Please try again.')
  }
}
export async function privateRequest(client: SupabaseClient, account: string, path: string,
  options: { method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<unknown> {
  const signal = options.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(10000)]) : AbortSignal.timeout(10000)
  const { data, error } = await client.auth.getSession()
  if (error || !data.session?.access_token || data.session.user.id !== account || signal.aborted) throw new PrivateApiError(401)
  const base = new URL(import.meta.env.VITE_API_URL || 'http://localhost:8000')
  if ((base.protocol !== 'https:' && !(base.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(base.hostname))) || base.username || base.password || base.search || base.hash || base.pathname !== '/') throw new PrivateApiError(503)
  const response = await fetch(new URL(path, base), { method: options.method || 'GET', signal, cache: 'no-store',
    headers: { Authorization: `Bearer ${data.session.access_token}`, ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }) })
  if (!response.ok) throw new PrivateApiError(response.status)
  return response.status === 204 ? null : response.json()
}
export function privateError(error: unknown): string {
  return error instanceof PrivateApiError ? error.message : 'The request could not be completed. Please try again.'
}
