import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { SupabaseClient, Session } from '@supabase/supabase-js'
import { MemoryRouter } from 'react-router'
import ProfileEditor from './ProfileEditor'
import TelegramConnection from './TelegramConnection'
import Foundation from './Foundation'

const client = { auth: { getSession: vi.fn(async () => ({ data: { session: { access_token: 'test-A', user: { id: 'A' } } }, error: null })) } } as unknown as SupabaseClient
const context = { schema_version: 'user-context-v1', base_location: { locality: 'Petaluma', timezone: 'America/Los_Angeles' }, interests: ['Art'], output: { maximum_recommendations: 3 }, novelty_preferences: 'Try new things', travel: null, cost: null, recurring_availability: null }
const revision = { revision_id: 'revision-1', context }
const response = (value: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => value })
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })
it('creates a normal profile without inventing optional preferences', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(response({}, 404)).mockResolvedValueOnce(response(revision, 201))
  vi.stubGlobal('fetch', fetch)
  const saved = vi.fn()
  render(<ProfileEditor client={client} account="A" onSaved={saved} />)
  await screen.findByRole('button', { name: 'Save profile' })
  fireEvent.change(screen.getByLabelText('Base locality'), { target: { value: 'Petaluma' } })
  fireEvent.change(screen.getByLabelText(/Timezone/), { target: { value: 'America/Los_Angeles' } })
  fireEvent.change(screen.getByLabelText('Interests'), { target: { value: 'Art\nLive music' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save profile' }))
  await screen.findByText(/Profile saved/)
  const options = fetch.mock.calls[1][1], body = JSON.parse(options.body)
  expect(options.method).toBe('POST')
  expect(body.interests).toEqual(['Art', 'Live music'])
  expect(body.objectives).toBeNull()
  expect(body.solo_considerations).toBeNull()
  expect(options.headers.Authorization).toBe('Bearer test-A')
  expect(saved).toHaveBeenCalledOnce()
})
it('updates with expected revision and preserves fields outside the editor', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(response(revision)).mockResolvedValueOnce(response({ ...revision, revision_id: 'revision-2' }))
  vi.stubGlobal('fetch', fetch)
  render(<ProfileEditor client={client} account="A" onSaved={() => {}} />)
  await screen.findByDisplayValue('Petaluma')
  fireEvent.change(screen.getByLabelText('Interests'), { target: { value: 'Gardens' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save profile' }))
  await screen.findByText(/Profile saved/)
  const options = fetch.mock.calls[1][1], body = JSON.parse(options.body)
  expect(options.method).toBe('PUT')
  expect(body.expected_revision_id).toBe('revision-1')
  expect(body.context.output).toEqual(context.output)
  expect(body.context.novelty_preferences).toBe(context.novelty_preferences)
  expect(body.context.travel).toBeNull()
})
it('blocks a stale save until the profile is reloaded', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response(revision)).mockResolvedValueOnce(response({}, 409)).mockResolvedValueOnce(response({ ...revision, revision_id: 'revision-2' })))
  render(<ProfileEditor client={client} account="A" onSaved={() => {}} />)
  await screen.findByDisplayValue('Petaluma')
  fireEvent.click(screen.getByRole('button', { name: 'Save profile' }))
  await screen.findByRole('alert')
  expect(screen.getByRole('button', { name: 'Save profile' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Reload profile' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save profile' })).toBeEnabled())
})
it('surfaces backend validation without echoing private raw errors', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response(revision)).mockResolvedValueOnce(response({ private: 'RAW_SECRET' }, 422)))
  render(<ProfileEditor client={client} account="A" onSaved={() => {}} />)
  await screen.findByDisplayValue('Petaluma')
  fireEvent.click(screen.getByRole('button', { name: 'Save profile' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Check your entries')
  expect(screen.queryByText('RAW_SECRET')).not.toBeInTheDocument()
})
it('connects with a challenge command and revokes through account routes only', async () => {
  let connected = false
  const fetch = vi.fn(async (url, options) => {
    const path = new URL(url).pathname
    if (path.endsWith('/config')) return response({ bot_username: 'EventRadarTestBot' })
    if (path.endsWith('/challenge')) { connected = true; return response({ challenge: 'synthetic-code', expires_in_seconds: 600 }) }
    if (path.endsWith('/revoke')) { connected = false; return response(null, 204) }
    expect(options.body).toBeUndefined()
    return response(connected ? [{ id: 'binding-A', channel: 'telegram', status: 'active', revision: 1 }] : [])
  })
  vi.stubGlobal('fetch', fetch)
  render(<TelegramConnection client={client} account="A" />)
  await screen.findByText('Telegram is not connected.')
  fireEvent.click(screen.getByRole('button', { name: 'Connect Telegram' }))
  await screen.findByText('/start synthetic-code')
  expect(screen.getByText(/Keep this code private/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Refresh connection' }))
  await screen.findByText('Telegram is connected.')
  expect(screen.queryByText('/start synthetic-code')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Revoke Telegram connection' }))
  await screen.findByText('Telegram is not connected.')
  expect(fetch.mock.calls.every(([url]) => String(url).startsWith('http://localhost:8000/api/me/'))).toBe(true)
  expect(fetch.mock.calls.some(([, options]) => String(options.body).includes('chat_id'))).toBe(false)
})
it('disables connection when the public bot handle is unconfigured', async () => {
  vi.stubGlobal('fetch', vi.fn(async url => response(String(url).endsWith('/config') ? { bot_username: null } : [])))
  render(<TelegramConnection client={client} account="A" />)
  await screen.findByText('Telegram is not connected.')
  expect(screen.getByRole('button', { name: 'Connect Telegram' })).toBeDisabled()
})
it('clears profile and challenge on account switch and ignores delayed profile results', async () => {
  const session = (id: string) => ({ access_token: `token-${id}`, user: { id } }) as Session
  let current: Session | null = session('A'), listener: (event: string, next: Session | null) => void = () => {}
  let release: (value: unknown) => void = () => {}
  const auth = { getSession: vi.fn(async () => ({ data: { session: current }, error: null })), onAuthStateChange: vi.fn(cb => { listener = cb; return { data: { subscription: { unsubscribe: vi.fn() } } } }) }
  vi.stubGlobal('fetch', vi.fn(async (url, options) => {
    const path = new URL(url).pathname, id = options.headers.Authorization.endsWith('-A') ? 'A' : 'B'
    if (path === '/api/me') return response({ id, email: null, created_at: '2026-10-12', database_roundtrip: true })
    if (path.endsWith('/context')) return id === 'A' ? new Promise(resolve => { release = resolve }) : response({ ...revision, context: { ...context, base_location: { ...context.base_location, locality: 'B town' } } })
    if (path.endsWith('/config')) return response({ bot_username: 'EventRadarTestBot' })
    if (path.endsWith('/challenge')) return response({ challenge: 'private-A-code', expires_in_seconds: 600 })
    if (path.endsWith('/bindings')) return response([])
    return response({ state: 'not_generated', weekend_friday: '2026-10-16', degraded: false, research_stale: false, snapshot_superseded: false, packet: null })
  }))
  render(<MemoryRouter initialEntries={['/app']}><Foundation client={{ auth } as unknown as SupabaseClient} /></MemoryRouter>)
  await screen.findByText('Telegram is not connected.')
  fireEvent.click(screen.getByText('Connect Telegram', { selector: 'summary' }))
  fireEvent.click(screen.getByRole('button', { name: 'Connect Telegram' }))
  await screen.findByText('/start private-A-code')
  act(() => { current = session('B'); listener('SIGNED_IN', current) })
  await screen.findByDisplayValue('B town')
  await act(async () => release(response(revision)))
  expect(screen.queryByDisplayValue('Petaluma')).not.toBeInTheDocument()
  expect(screen.queryByText('/start private-A-code')).not.toBeInTheDocument()
  act(() => { current = null; listener('SIGNED_OUT', null) })
  await screen.findByRole('heading', { name: 'Sign in' })
  expect(screen.queryByDisplayValue('B town')).not.toBeInTheDocument()
})
