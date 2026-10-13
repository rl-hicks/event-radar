import type { SupabaseClient } from '@supabase/supabase-js'

type Row = Record<string, unknown>
function row(v: unknown): Row { if (!v || typeof v !== 'object' || Array.isArray(v)) throw Error(); return v as Row }
function text(v: unknown): string { if (typeof v !== 'string') throw Error(); return v }
function list(v: unknown): unknown[] { if (!Array.isArray(v)) throw Error(); return v }
function optional(v: unknown): string { return v === null ? 'Unknown' : text(v) }
function bool(v: unknown): boolean { if (typeof v !== 'boolean') throw Error(); return v }
function observation(v: unknown): string { const o = row(v); return `${text(o.state)}${typeof o.value === 'boolean' ? (o.value ? ' — reported yes' : ' — reported no') : ''}` }
function location(v: unknown): string { const r = row(v); return [optional(r.venue), optional(r.city), text(r.county)].join(', ') }
function amount(v: unknown): string { return typeof v === 'number' ? String(v) : optional(v) }
export function safeSource(value: string): string | null {
  try { const u = new URL(value); return u.protocol === 'https:' && !u.username && !u.password ? u.href : null } catch { return null }
}
export type PacketViewData = {
  state: 'current' | 'older_context' | 'not_generated' | 'unavailable'; weekend: string;
  degraded: boolean; stale: boolean; superseded: boolean;
  packet: null | { asOf: string; research: string; curation: string; recommendations: {
    title: string; location: string; rationale: string; tradeoffs: string; friction: string;
    access: string; times: string[]; unknowns: string[]; sources: string[]; semantics: string[]; route: string | null;
  }[] }
}
export function parseCurrent(value: unknown, account: string): PacketViewData {
  const v = row(value), state = text(v.state)
  if (!['current', 'older_context', 'not_generated', 'unavailable'].includes(state)) throw Error()
  const result: PacketViewData = { state: state as PacketViewData['state'], weekend: text(v.weekend_friday),
    degraded: bool(v.degraded), stale: bool(v.research_stale), superseded: bool(v.snapshot_superseded), packet: null }
  if (v.packet === null) { if (state === 'current' || state === 'older_context') throw Error(); return result }
  const p = row(v.packet)
  if (p.user_id !== account || !['current', 'older_context'].includes(state)) throw Error()
  result.packet = { asOf: text(p.research_as_of), research: text(p.research_quality), curation: text(p.curation_status),
    recommendations: list(p.recommendations).map(value => {
      const r = row(value), f = row(r.facts), j = row(r.judgment)
      return { title: text(f.title), location: location(f.location), rationale: text(r.rationale),
        tradeoffs: list(j.tradeoffs).map(text).join(', ') || 'None specified', friction: text(j.friction).replaceAll('_', ' '),
        access: observation(f.access_open), unknowns: list(r.important_unknowns).map(text),
        sources: list(f.evidence).map(e => text(row(e).url)),
        semantics: f.semantics === null ? [] : list(f.semantics).map(e => { const s = row(e); return `${text(s.kind)}: ${text(s.description)} (${text(s.confidence)} confidence)` }),
        route: f.route === null ? null : (() => { const route = row(f.route); return `${amount(route.distance_miles)} miles; ${amount(route.elevation_gain_ft)} ft elevation gain. ${optional(route.route_description)}` })(),
        times: list(f.occurrences).map(value => { const o = row(value), price = row(o.price)
          const quotes = list(price.quotes).map(value => { const q = row(value); return `${optional(q.currency)} ${amount(q.minimum)}–${amount(q.maximum)}; ${optional(q.details)}` }).join('; ')
          return `${text(o.start)} to ${optional(o.end)} · ${location(o.location)} · Price ${text(price.state)}${quotes ? ': ' + quotes : ''} · Attendance ${observation(o.available)}`
        }),
      }
    }) }
  return result
}
export async function getCurrentPacket(client: SupabaseClient, account: string, signal: AbortSignal): Promise<PacketViewData> {
  try {
    const { data, error } = await client.auth.getSession()
    if (error || !data.session?.access_token || data.session.user.id !== account) throw Error()
    const url = new URL(import.meta.env.VITE_API_URL || 'http://localhost:8000')
    const local = ['localhost', '127.0.0.1'].includes(url.hostname)
    if ((url.protocol !== 'https:' && !(local && url.protocol === 'http:')) || url.username || url.password || url.search || url.hash || url.pathname !== '/') throw Error()
    const response = await fetch(new URL('/api/me/packets/current', url), { headers: { Authorization: `Bearer ${data.session.access_token}` }, cache: 'no-store', signal })
    if (response.status === 401) throw new Error('Sign in again to read your packet.')
    if (!response.ok) throw Error()
    return parseCurrent(await response.json(), account)
  } catch (error) {
    if (error instanceof Error && error.message === 'Sign in again to read your packet.') throw error
    throw new Error('Your packet could not be loaded. Please try again.', { cause: error })
  }
}
