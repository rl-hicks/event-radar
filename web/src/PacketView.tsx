import { useEffect, useState } from 'react'
import type { Session, SupabaseClient } from '@supabase/supabase-js'
import { getCurrentPacket, safeSource, type PacketViewData } from './api/packets'

export default function PacketView({ client, session }: { client: SupabaseClient; session: Session }) {
  const [result, setResult] = useState<{ account: string; token: string; value?: PacketViewData; error?: string } | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    const timer = setTimeout(() => { controller.abort(); if (active) setResult({ account: session.user.id, token: session.access_token, error: 'Your packet could not be loaded. Please try again.' }); active = false }, 10000)
    getCurrentPacket(client, session.user.id, controller.signal).then(value => {
      if (active) setResult({ account: session.user.id, token: session.access_token, value })
    }).catch(error => {
      if (active) setResult({ account: session.user.id, token: session.access_token, error: error.message })
    }).finally(() => clearTimeout(timer))
    return () => { active = false; controller.abort(); clearTimeout(timer) }
  }, [client, session.user.id, session.access_token, attempt])
  const current = result?.account === session.user.id && result.token === session.access_token ? result : null
  const value = current?.value
  return <section aria-label="Current Weekend Packet"><h2>Your Weekend Packet</h2>
    {!current && <p role="status">Loading your packet…</p>}
    {current?.error && <><p role="alert">{current.error}</p><button onClick={() => { setResult(null); setAttempt(a => a + 1) }}>Retry packet</button></>}
    {value && <><p>Weekend beginning Friday {value.weekend} · Sonoma County</p>
      {value.state === 'not_generated' && <p role="status">Your packet has not been generated yet.</p>}
      {value.state === 'unavailable' && <p role="alert">Your packet is unavailable.</p>}
      {value.state === 'older_context' && <p role="status">This packet uses earlier preferences. It does not reflect your latest context.</p>}
      {value.degraded && <p role="status">This packet has partial or degraded research or curation.</p>}
      {value.stale && <p>The research is older than its freshness window. Verify current details.</p>}
      {value.superseded && <p>Newer regional research exists; this packet retains the research used to create it.</p>}
      {value.packet && <><p>Research as of {value.packet.asOf}. Research: {value.packet.research}; curation: {value.packet.curation}.</p>
        <p>Recommendations do not confirm booking or attendance availability. Check source terms before making plans.</p>
        {value.packet.recommendations.length === 0 && <p>No recommendations in this packet.</p>}
        <ol className="packet-list">{value.packet.recommendations.map((r, i) => <li key={i}><article>
          <h3>{r.title}</h3><p>{r.location}</p><p>{r.rationale}</p>
          {r.times.length ? r.times.map((t, i) => <p key={i}>{t}</p>) : <p>No scheduled time established. Verify opening times and access.</p>}
          {r.route && <p>{r.route}</p>}<p>Access: {r.access}</p>
          <p>Tradeoffs: {r.tradeoffs}. Friction: {r.friction}.</p>
          {r.semantics.map((s, i) => <p key={i}>{s}</p>)}
          <h4>Important unknowns</h4><ul>{r.unknowns.map((u, i) => <li key={i}>{u}</li>)}</ul>
          <h4>Sources</h4><ul>{r.sources.map((source, i) => { const safe = safeSource(source); return <li key={i}>{safe ? <a href={safe} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">{source}</a> : 'Source link unavailable'}</li> })}</ul>
        </article></li>)}</ol>
      </>}
    </>}
  </section>
}
