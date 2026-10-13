import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { Session, SupabaseClient } from '@supabase/supabase-js'
import PacketView from './PacketView'
import { parseCurrent, safeSource } from './api/packets'
import Foundation from './Foundation'
import { MemoryRouter } from 'react-router'

const session = (id: string) => ({ access_token: `token-${id}`, user: { id } }) as Session
const location = { venue: 'Test hall', city: 'Petaluma', county: 'Sonoma County' }
function payload(id = 'A') { return { state: 'older_context', weekend_friday: '2026-10-16', degraded: true, research_stale: false, snapshot_superseded: false,
  packet: { user_id: id, research_as_of: '2026-10-15T10:00:00-07:00', research_quality: 'partial', curation_status: 'success', recommendations: [
    { rationale: 'A reason <script>unsafe</script>', important_unknowns: ['Attendance availability is unknown.'], judgment: { tradeoffs: ['travel'], friction: 'needs_assessment' }, facts: {
      title: `${id} workshop`, location, access_open: { state: 'unknown', value: null }, semantics: null, route: null,
      occurrences: [{ start: '2026-10-17T12:00:00-07:00', end: null, location, available: { state: 'unknown', value: null }, price: { state: 'unknown', quotes: [] } }],
      evidence: [{ url: 'javascript:alert(1)' }, { url: 'https://example.org/event' }],
    } },
  ] } } }
const response = (value: unknown) => ({ ok: true, json: async () => value })
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })
function client(id = 'A') { return { auth: { getSession: vi.fn(async () => ({ data: { session: session(id) }, error: null })) } } as unknown as SupabaseClient }
it('renders persisted facts, uncertainty, context warning and safe sources in order', async () => {
  const fetch = vi.fn().mockResolvedValue(response(payload()))
  vi.stubGlobal('fetch', fetch)
  render(<PacketView client={client()} session={session('A')} />)
  expect(await screen.findByText('A workshop')).toBeInTheDocument()
  expect(screen.getByText(/earlier preferences/)).toBeInTheDocument()
  expect(screen.getByText(/partial or degraded/)).toBeInTheDocument()
  expect(screen.getByText(/Price unknown/)).toBeInTheDocument()
  expect(screen.getByText('Attendance availability is unknown.')).toBeInTheDocument()
  expect(screen.getByText('A reason <script>unsafe</script>')).toBeInTheDocument()
  expect(document.querySelector('script')).toBeNull()
  expect(screen.getAllByRole('link')).toHaveLength(1)
  expect(screen.getByRole('link')).toHaveAttribute('rel', 'noopener noreferrer')
  expect(fetch.mock.calls[0][1].cache).toBe('no-store')
  expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer token-A')
})
it('discards delayed responses after account switch even if transport ignores abort', async () => {
  let finish: (value: unknown) => void = () => {}
  vi.stubGlobal('fetch', vi.fn().mockImplementationOnce(() => new Promise(resolve => { finish = resolve })).mockResolvedValue(response(payload('B'))))
  const view = render(<PacketView client={client()} session={session('A')} />)
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
  view.rerender(<PacketView client={client('B')} session={session('B')} />)
  expect(screen.queryByText('A workshop')).not.toBeInTheDocument()
  await screen.findByText('B workshop')
  await act(async () => finish(response(payload())))
  expect(screen.queryByText('A workshop')).not.toBeInTheDocument()
  expect(screen.getByText('B workshop')).toBeInTheDocument()
})
it('rejects a session that changed before token acquisition', async () => {
  vi.stubGlobal('fetch', vi.fn())
  render(<PacketView client={client('B')} session={session('A')} />)
  await screen.findByRole('alert')
  expect(fetch).not.toHaveBeenCalled()
})
it('rejects foreign packet payloads', () => { expect(() => parseCurrent(payload('B'), 'A')).toThrow() })
it.each(['not_generated', 'unavailable'])('handles %s without inventing recommendations', async state => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ ...payload(), state, packet: null })))
  render(<PacketView client={client()} session={session('A')} />)
  await screen.findByText(state === 'not_generated' ? 'Your packet has not been generated yet.' : 'Your packet is unavailable.')
  expect(screen.queryByText('A workshop')).not.toBeInTheDocument()
})
it.each([401, 503])('handles API %s with retry', async status => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status }))
  render(<PacketView client={client()} session={session('A')} />)
  await screen.findByRole('alert')
  expect(screen.getByRole('button', { name: 'Retry packet' })).toBeEnabled()
})
it('clears private packet on normal authenticated signout', async () => {
  let current: Session | null = session('A')
  let listener: (event: string, next: Session | null) => void = () => {}
  const auth = { getSession: vi.fn(async () => ({ data: { session: current }, error: null })),
    onAuthStateChange: vi.fn(cb => { listener = cb; return { data: { subscription: { unsubscribe: vi.fn() } } } }),
    signOut: vi.fn(async () => { current = null; listener('SIGNED_OUT', null); return { error: null } }),
  }
  vi.stubGlobal('fetch', vi.fn(async url => String(url).endsWith('/current') ? response(payload()) : response({ id: 'A', email: null, created_at: '2026-10-12', database_roundtrip: true })))
  render(<MemoryRouter initialEntries={['/app']}><Foundation client={{ auth } as unknown as SupabaseClient} /></MemoryRouter>)
  await screen.findByText('A workshop')
  fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
  await screen.findByRole('heading', { name: 'Sign in' })
  expect(screen.queryByText('A workshop')).not.toBeInTheDocument()
})
it.each(['javascript:alert(1)', 'data:text/html,a', 'https://user:password@example.org', 'http://example.org'])('rejects unsafe source %s', url => { expect(safeSource(url)).toBeNull() })
