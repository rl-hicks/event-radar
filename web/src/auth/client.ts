import { createClient, type SupabaseClient } from '@supabase/supabase-js'

export type BrowserConfig = { url?: string; publishableKey?: string }

export function createAuthClient(config: BrowserConfig): SupabaseClient | null {
  if (!config.url && !config.publishableKey) return null
  try {
    const url = new URL(config.url ?? '')
    const local = ['localhost', '127.0.0.1'].includes(url.hostname)
    if ((url.protocol !== 'https:' && !(local && url.protocol === 'http:')) ||
        url.username || url.password || url.search || url.hash || url.pathname !== '/' ||
        !config.publishableKey?.startsWith('sb_publishable_')) throw new Error()
    return createClient(url.origin, config.publishableKey, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    })
  } catch {
    throw new Error('Supabase browser configuration is invalid.')
  }
}

let cached: SupabaseClient | null | undefined
export function browserAuth(): SupabaseClient | null {
  if (cached === undefined) cached = createAuthClient({
    url: import.meta.env.VITE_SUPABASE_URL,
    publishableKey: import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY,
  })
  return cached
}
