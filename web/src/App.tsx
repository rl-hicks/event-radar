import { useState } from 'react'
import { browserAuth } from './auth/client'
import AuthPanel from './auth/AuthPanel'

export default function App() {
  const [auth] = useState(() => {
    try { return { client: browserAuth(), invalid: false } }
    catch { return { client: null, invalid: true } }
  })
  return <main>
    <p className="eyebrow">Development foundation</p>
    <h1>Event Radar</h1>
    <p>The product is under development. This page only verifies authentication and backend identity.</p>
    {auth.client ? <AuthPanel client={auth.client} /> : <p role="status">{auth.invalid ? 'Supabase browser configuration is invalid.' : 'Configure the public Supabase browser values to enable authentication.'}</p>}
  </main>
}
