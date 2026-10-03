import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { AuthChangeEvent, Session, SupabaseClient } from '@supabase/supabase-js'
import { signIn, signOut, signUp } from './actions'
import { useSession } from './useSession'
import AuthPanel from './AuthPanel'

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

it('renders reusable signup/signin controls and confirmation messaging', async () => {
  const { client, auth, emit } = fixture()
  render(<AuthPanel client={client} />)
  await screen.findByRole('button', { name: 'Sign in' })
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@example.test' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign up' }))
  await screen.findByText(/Check your email to confirm/)
  expect(screen.getByLabelText('Password')).toHaveValue('')
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  await waitFor(() => expect(auth.signInWithPassword).toHaveBeenCalledOnce())
  act(() => emit(session))
  expect(screen.getByText(/Signed in as/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Sign out of this browser' }))
  await waitFor(() => expect(auth.signOut).toHaveBeenCalledWith({ scope: 'local' }))
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
