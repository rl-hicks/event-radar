import { useState } from 'react'
import { BrowserRouter } from 'react-router'
import { browserAuth } from './auth/client'
import Foundation from './Foundation'

export default function App() {
  const [auth] = useState(() => {
    try { return { client: browserAuth(), invalid: false } }
    catch { return { client: null, invalid: true } }
  })
  return <BrowserRouter><Foundation client={auth.client} invalid={auth.invalid} /></BrowserRouter>
}
