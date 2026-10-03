import { beforeEach, expect, it, vi } from 'vitest'
const createClient = vi.hoisted(() => vi.fn(() => ({ auth: {} })))
vi.mock('@supabase/supabase-js', () => ({ createClient }))
import { createAuthClient } from './client'

beforeEach(() => createClient.mockClear())
it('allows an unconfigured development shell without creating a client', () => {
  expect(createAuthClient({})).toBeNull()
  expect(createClient).not.toHaveBeenCalled()
})
it('uses publishable configuration and normal persisted refreshable sessions', () => {
  createAuthClient({ url: 'https://project.example.test', publishableKey: 'sb_publishable_fixture' })
  expect(createClient).toHaveBeenCalledWith('https://project.example.test', 'sb_publishable_fixture', {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  })
})
it.each(['sb_secret_forbidden', 'legacy-service-role-jwt', ''])('rejects non-publishable keys', key => {
  expect(() => createAuthClient({ url: 'https://project.example.test', publishableKey: key })).toThrow('configuration is invalid')
  expect(createClient).not.toHaveBeenCalled()
})
