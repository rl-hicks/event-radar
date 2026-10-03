import { afterEach, expect, it, vi } from 'vitest'
import type { SupabaseClient } from '@supabase/supabase-js'
import { getMe } from './client'

const client = { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: { access_token: 'test-access', user: { id: 'browser-untrusted-id' } } }, error: null }) } } as unknown as SupabaseClient
afterEach(() => vi.unstubAllGlobals())
it('forwards only the active access token as identity proof', async () => {
  const me = { id: 'backend-id', email: null, created_at: '2026-10-03', database_roundtrip: true }
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => me })
  vi.stubGlobal('fetch', fetch)
  expect(await getMe(client, 'http://localhost:8000')).toEqual(me)
  const [url, options] = fetch.mock.calls[0]
  expect(String(url)).toBe('http://localhost:8000/api/me')
  expect(options.headers).toEqual({ Authorization: 'Bearer test-access' })
  expect(options.body).toBeUndefined()
  expect(JSON.stringify([String(url), options])).not.toContain('browser-untrusted-id')
})
it('fails without session and makes no API call', async () => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
  const absent = { auth: { getSession: async () => ({ data: { session: null }, error: null }) } } as unknown as SupabaseClient
  await expect(getMe(absent)).rejects.toThrow('Sign in before calling the API.')
  expect(fetch).not.toHaveBeenCalled()
})
it('does not surface provider bodies or tokens on errors', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401, text: async () => 'provider-secret' }))
  await expect(getMe(client)).rejects.toThrow('Authentication expired or was rejected.')
})
it('sanitizes network failures', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('provider-secret')))
  await expect(getMe(client)).rejects.toThrow('API request could not be completed.')
})
