import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { AuthChangeEvent, Session, SupabaseClient } from '@supabase/supabase-js'
import { signIn, signOut, signUp } from './actions'
import { useSession } from './useSession'

const session = { access_token: 'test-access', user: { id: 'user-a', email: 'a@example.test' } } as Session
function fixture() {
  let listener: (event: AuthChangeEvent, next: Session | null) => void = () => {}
  const unsubscribe = vi.fn()
  const auth = {
    signInWithPassword: vi.fn().mockResolvedValue({ data: { session }, error: null }),
    signUp: vi.fn().mockResolvedValue({ data: { session: null }, error: null }),
    signOut: vi.fn().mockResolvedValue({ error: null }),
    getSession: vi.fn().mockResolvedValue({ data: { session: null }, error: null }),
    onAuthStateChange: vi.fn(callback => { listener = callback; return { data: { subscription: { unsubscribe } } } }),
  }
  return { client: { auth } as unknown as SupabaseClient, auth, unsubscribe, emit: (next: Session | null) => listener(next ? 'SIGNED_IN' : 'SIGNED_OUT', next) }
}

describe('Supabase auth actions', () => {
  it('signs in using email and password', async () => {
    const { client, auth } = fixture()
    expect(await signIn(client, 'a@example.test', 'test-password')).toBe(session)
    expect(auth.signInWithPassword).toHaveBeenCalledWith({ email: 'a@example.test', password: 'test-password' })
  })
  it('reports signup confirmation instead of pretending a session exists', async () => {
    const { client, auth } = fixture()
    expect(await signUp(client, 'a@example.test', 'test-password')).toEqual({ session: null, needsConfirmation: true })
    expect(auth.signUp).toHaveBeenCalledWith({ email: 'a@example.test', password: 'test-password' })
    auth.signUp.mockResolvedValue({ data: { session }, error: null })
    expect((await signUp(client, 'a@example.test', 'test-password')).needsConfirmation).toBe(false)
  })
  it('signs out only the local session', async () => {
    const { client, auth } = fixture()
    await signOut(client)
    expect(auth.signOut).toHaveBeenCalledWith({ scope: 'local' })
  })
  it('sanitizes provider errors', async () => {
    const { client, auth } = fixture()
    auth.signInWithPassword.mockResolvedValue({ data: { session: null }, error: { message: 'provider-secret' } })
    await expect(signIn(client, 'a', 'b')).rejects.toThrow('Sign-in failed.')
    auth.signUp.mockResolvedValue({ data: {}, error: { message: 'provider-secret' } })
    await expect(signUp(client, 'a', 'b')).rejects.toThrow('Sign-up could not be completed.')
    auth.signOut.mockResolvedValue({ error: { message: 'provider-secret' } })
    await expect(signOut(client)).rejects.toThrow('Sign-out could not be completed.')
  })
})

it('loads session, tracks auth changes and unsubscribes', async () => {
  const { client, emit, unsubscribe } = fixture()
  const hook = renderHook(() => useSession(client))
  await waitFor(() => expect(hook.result.current.loading).toBe(false))
  act(() => emit(session))
  expect(hook.result.current.session).toBe(session)
  act(() => emit(null))
  expect(hook.result.current.session).toBeNull()
  hook.unmount()
  expect(unsubscribe).toHaveBeenCalledOnce()
})

it('recovers from a session-load error on a later valid auth event', async () => {
  const { client, auth, emit } = fixture()
  auth.getSession.mockResolvedValue({ data: { session: null }, error: { message: 'provider-secret' } })
  const hook = renderHook(() => useSession(client))
  await waitFor(() => expect(hook.result.current.error).toBe('Session could not be loaded.'))
  act(() => emit(session))
  expect(hook.result.current.error).toBe('')
  expect(hook.result.current.session).toBe(session)
})

it('clears an expired session if Supabase has not refreshed it', async () => {
  vi.useFakeTimers()
  try {
    const { client, emit } = fixture()
    const hook = renderHook(() => useSession(client))
    act(() => emit({ ...session, expires_at: Math.floor(Date.now() / 1000) + 2 }))
    act(() => vi.advanceTimersByTime(2000))
    expect(hook.result.current.session).toBeNull()
    hook.unmount()
  } finally { vi.useRealTimers() }
})

it('does not admit an already expired SDK session', async () => {
  const { client, emit } = fixture()
  const hook = renderHook(() => useSession(client))
  act(() => emit({ ...session, expires_at: Math.floor(Date.now() / 1000) - 1 }))
  expect(hook.result.current.session).toBeNull()
  hook.unmount()
})
it('does not time out a successfully restored session', async () => {
  vi.useFakeTimers()
  try {
    const { client, auth } = fixture()
    auth.getSession.mockResolvedValue({ data: { session }, error: null })
    const hook = renderHook(() => useSession(client))
    await act(async () => {})
    act(() => vi.advanceTimersByTime(10000))
    expect(hook.result.current.session).toBe(session)
    expect(hook.result.current.error).toBe('')
    hook.unmount()
  } finally { vi.useRealTimers() }
})
