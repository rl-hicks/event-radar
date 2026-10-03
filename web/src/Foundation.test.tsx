import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router'
import type { Session, SupabaseClient } from '@supabase/supabase-js'
import Foundation from './Foundation'

const session = { access_token: 'test-token', user: { id: 'browser-user', email: 'user@example.test' } } as Session
function setup(path: string, initial: Session | null = null, pending = false) {
  let current = initial
  let listener: (event: string, next: Session | null) => void = () => {}
  const emit = (next: Session | null) => { current = next; listener(next ? 'SIGNED_IN' : 'SIGNED_OUT', next) }
  const auth = {
    getSession: vi.fn(() => pending ? new Promise<never>(() => {}) : Promise.resolve({ data: { session: current }, error: null })),
    onAuthStateChange: vi.fn(callback => { listener = callback; return { data: { subscription: { unsubscribe: vi.fn() } } } }),
    signInWithPassword: vi.fn(async () => { emit(session); return { data: { session }, error: null } }),
    signUp: vi.fn(async () => ({ data: { session: null as Session | null }, error: null })),
    signOut: vi.fn(async () => { emit(null); return { error: null } }),
  }
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: 'backend-user', email: null, created_at: '2026-10-03', database_roundtrip: true }) })
  vi.stubGlobal('fetch', fetch)
  render(<MemoryRouter initialEntries={[path]}><Foundation client={{ auth } as unknown as SupabaseClient} /></MemoryRouter>)
  return { auth, fetch, emit }
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })
it.each([['/', 'Event Radar'], ['/login', 'Sign in'], ['/signup', 'Create account'], ['/missing', 'Page not found']])('renders %s', async (path, heading) => {
  const { fetch } = setup(path)
  expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
})
it('protects app while resolving and after missing session', async () => {
  const { emit, fetch } = setup('/app', null, true)
  expect(screen.getByRole('status')).toHaveTextContent('Restoring session')
  expect(screen.queryByText('E0 authenticated foundation')).not.toBeInTheDocument()
  act(() => emit(null))
  expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
})
it('bounds session restoration without exposing protected content', () => {
  vi.useFakeTimers(); setup('/app', null, true)
  act(() => vi.advanceTimersByTime(10000))
  expect(screen.getByRole('alert')).toHaveTextContent('Session could not be loaded')
  expect(screen.queryByText('E0 authenticated foundation')).not.toBeInTheDocument()
})
it.each(['/app?user_id=other-user&email=other@example.test', '/login'])('uses authenticated API identity at %s', async path => {
  const { fetch } = setup(path, session)
  expect(await screen.findByText('Backend identity: backend-user')).toBeInTheDocument()
  expect(screen.getByText('Database roundtrip: confirmed')).toBeInTheDocument()
  const [url, options] = fetch.mock.calls[0]
  expect(String(url)).toBe('http://localhost:8000/api/me')
  expect(options.headers).toEqual({ Authorization: 'Bearer test-token' })
  expect(options.body).toBeUndefined()
  expect(JSON.stringify([String(url), options])).not.toContain('other-user')
})
async function fill(label: string) {
  await screen.findByRole('button', { name: label })
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'user@example.test' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test-password' } })
  fireEvent.click(screen.getByRole('button', { name: label }))
}
it('login enters app and local signout clears protected identity', async () => {
  const { auth } = setup('/login')
  await fill('Sign in')
  await screen.findByText('Backend identity: backend-user')
  fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
  await screen.findByRole('heading', { name: 'Sign in' })
  expect(auth.signOut).toHaveBeenCalledWith({ scope: 'local' })
  expect(screen.queryByText('Backend identity: backend-user')).not.toBeInTheDocument()
})
it('session removal clears protected content including pending API results', async () => {
  const { emit, fetch } = setup('/app', session)
  let resolve: (value: unknown) => void = () => {}
  fetch.mockImplementation(() => new Promise(done => { resolve = done }))
  await screen.findByRole('heading', { name: 'E0 authenticated foundation' })
  act(() => emit(null))
  await act(async () => resolve({ ok: true, json: async () => ({ id: 'stale', email: null, created_at: '', database_roundtrip: true }) }))
  expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  expect(screen.queryByText(/Backend identity/)).not.toBeInTheDocument()
})
it('signup requiring confirmation stays unauthenticated', async () => {
  setup('/signup'); await fill('Create account')
  expect(await screen.findByRole('status')).toHaveTextContent('You are not signed in yet')
  expect(screen.queryByText('E0 authenticated foundation')).not.toBeInTheDocument()
})
it('signup with immediate session enters app', async () => {
  const { auth, emit } = setup('/signup')
  auth.signUp.mockImplementation(async () => { emit(session); return { data: { session }, error: null } })
  await fill('Create account')
  await screen.findByText('Backend identity: backend-user')
})
it('sanitizes login errors and releases busy state', async () => {
  const { auth } = setup('/login')
  auth.signInWithPassword.mockRejectedValue(new Error('provider-secret'))
  await fill('Sign in')
  expect(await screen.findByRole('alert')).toHaveTextContent('Sign-in failed')
  expect(screen.queryByText(/provider-secret/)).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled()
})
it.each(['401', 'unavailable', 'network', 'malformed', 'timeout'])('bounds API %s failure', async kind => {
  const { fetch } = setup('/app', session)
  if (kind === 'network' || kind === 'timeout') fetch.mockRejectedValue(new Error('provider-secret'))
  else fetch.mockResolvedValue({ ok: kind === 'malformed', status: kind === '401' ? 401 : 503, json: async () => ({ secret: 'provider-secret' }) })
  await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
  expect(screen.getByRole('alert')).not.toHaveTextContent('provider-secret')
  expect(screen.queryByText('Database roundtrip: confirmed')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Retry API' })).toBeEnabled()
})
it('clearly handles missing configuration on protected route', () => {
  render(<MemoryRouter initialEntries={['/app']}><Foundation client={null} /></MemoryRouter>)
  expect(screen.getByRole('alert')).toHaveTextContent('Configure the public Supabase')
})
