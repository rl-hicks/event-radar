import type { SupabaseClient } from '@supabase/supabase-js'

export async function signIn(client: SupabaseClient, email: string, password: string) {
  const { data, error } = await client.auth.signInWithPassword({ email, password })
  if (error || !data.session) throw new Error('Sign-in failed. Check your credentials and confirmation status.')
  return data.session
}

export async function signUp(client: SupabaseClient, email: string, password: string) {
  const { data, error } = await client.auth.signUp({ email, password })
  if (error) throw new Error('Sign-up could not be completed.')
  return { session: data.session, needsConfirmation: !data.session }
}

export async function signOut(client: SupabaseClient) {
  const { error } = await client.auth.signOut({ scope: 'local' })
  if (error) throw new Error('Sign-out could not be completed.')
}
