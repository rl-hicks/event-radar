import { useEffect, useRef, useState, type FormEvent } from 'react'
import type { SupabaseClient } from '@supabase/supabase-js'
import { privateRequest, privateError, PrivateApiError } from './api/private'

type Availability = { weekday: string; start: string; end: string; disposition: string; note: string | null }
type Context = { base_location: { locality: string; timezone: string; latitude?: number | null; longitude?: number | null }; travel?: Record<string, unknown> | null; cost?: Record<string, unknown> | null; recurring_availability?: Availability[] | null; [key: string]: unknown }
type Revision = { revision_id: string; context: Context }
const listFields = [['interests', 'Interests'], ['desired_experiences', 'Desired experiences'], ['objectives', 'Objectives'], ['activity_preferences', 'Activity preferences'], ['exclusions', 'Things to avoid'], ['social_preferences', 'Social preferences'], ['participation_preferences', 'Participation preferences'], ['solo_considerations', 'Solo considerations'], ['accessibility_constraints', 'Access needs']] as const
function lines(value: unknown) { return Array.isArray(value) ? value.join('\n') : '' }
function nullable(value: string) { return value.trim() || null }
function items(value: string) { const result = value.split('\n').map(v => v.trim()).filter(Boolean); return result.length ? result : null }
function draftFor(context?: Context): Record<string, string> {
  const c = context
  return { locality: c?.base_location.locality || '', timezone: c?.base_location.timezone || '',
    ...Object.fromEntries(listFields.map(([key]) => [key, lines(c?.[key])])),
    minutes: String(c?.travel?.maximum_one_way_minutes ?? ''), modes: lines(c?.travel?.modes), travelNotes: String(c?.travel?.exceptional_experience_tradeoffs ?? ''),
    amount: String(c?.cost?.maximum_per_activity ?? ''), currency: String(c?.cost?.currency ?? ''), costNotes: String(c?.cost?.tradeoffs ?? '') }
}
export default function ProfileEditor({ client, account, onSaved }: { client: SupabaseClient; account: string; onSaved: () => void }) {
  const [revision, setRevision] = useState<Revision | null>(null)
  const [draft, setDraft] = useState(draftFor())
  const [availability, setAvailability] = useState<Availability[]>([])
  const [dirty, setDirty] = useState<Set<string>>(new Set())
  const [loaded, setLoaded] = useState(false), [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [failed, setFailed] = useState(false), [attempt, setAttempt] = useState(0), [conflict, setConflict] = useState(false)
  const mounted = useRef(false)
  useEffect(() => {
    mounted.current = true
    let active = true
    const controller = new AbortController()
    privateRequest(client, account, '/api/me/context', { signal: controller.signal }).then(value => {
      const next = value as Revision
      if (!next?.revision_id || !next.context?.base_location) throw new Error()
      if (active) { setRevision(next); setDraft(draftFor(next.context)); setAvailability(next.context.recurring_availability || []); setDirty(new Set()); setLoaded(true); setConflict(false); setMessage('') }
    }).catch(error => {
      if (!active) return
      if (error instanceof PrivateApiError && error.status === 404) { setLoaded(true); setRevision(null) }
      else { setMessage(privateError(error)); setFailed(true) }
    })
    return () => { active = false; mounted.current = false; controller.abort() }
  }, [client, account, attempt])
  function change(key: string, value: string) { setDraft(d => ({ ...d, [key]: value })); setDirty(d => new Set([...d, key])) }
  function editAvailability(rows: Availability[]) { setAvailability(rows); setDirty(d => new Set([...d, 'availability'])) }
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage(''); setFailed(false)
    const context: Context = { ...(revision?.context || {}), base_location: { ...revision?.context.base_location, locality: draft.locality.trim(), timezone: draft.timezone.trim() } }
    if (dirty.has('locality')) { context.base_location.latitude = null; context.base_location.longitude = null }
    for (const [key] of listFields) if (!revision || dirty.has(key)) context[key] = items(draft[key])
    if (!revision || ['minutes', 'modes', 'travelNotes'].some(k => dirty.has(k))) context.travel = { ...context.travel,
      maximum_one_way_minutes: draft.minutes === '' ? null : Number(draft.minutes), modes: items(draft.modes), exceptional_experience_tradeoffs: nullable(draft.travelNotes) }
    if (!revision || ['amount', 'currency', 'costNotes'].some(k => dirty.has(k))) context.cost = { ...context.cost,
      maximum_per_activity: nullable(draft.amount), currency: nullable(draft.currency), tradeoffs: nullable(draft.costNotes) }
    if (dirty.has('availability')) context.recurring_availability = availability.length ? availability : null
    try {
      const next = await privateRequest(client, account, '/api/me/context', { method: revision ? 'PUT' : 'POST', body: revision ? { expected_revision_id: revision.revision_id, context } : context }) as Revision
      if (mounted.current) { setRevision(next); setDirty(new Set()); setMessage('Profile saved. Existing packets keep the preferences used to create them.'); onSaved() }
    } catch (error) { if (mounted.current) { setFailed(true); setMessage(privateError(error)); setConflict(error instanceof PrivateApiError && error.status === 409) } }
    finally { if (mounted.current) setBusy(false) }
  }
  const field = (key: string, label: string, type = 'text') => <label>{label}<input type={type} value={draft[key]} onChange={e => change(key, e.target.value)} required={['locality', 'timezone'].includes(key)} maxLength={400} {...(type === 'number' ? { min: 0, max: key === 'minutes' ? 1440 : 100000, step: key === 'amount' ? '.01' : '1' } : {})} /></label>
  const preference = ([key, label]: typeof listFields[number]) => <label key={key}>{label}<textarea value={draft[key]} onChange={e => change(key, e.target.value)} rows={2} placeholder="Optional · one item per line" /></label>
  return <section aria-label="Your profile"><h2>Your profile</h2><p>Start with your location and a few interests. Blank preferences stay unknown. Up to 20 items per preference, 400 characters each.</p>
    {!loaded && !message && <p role="status">Loading profile…</p>}
    {message && <p role={failed ? 'alert' : 'status'}>{message}</p>}
    {(!loaded || conflict) && message && <button onClick={() => { setLoaded(false); setAttempt(a => a + 1) }}>Reload profile</button>}
    {loaded && <form onSubmit={save}><fieldset disabled={busy || conflict}>
      {field('locality', 'Base locality')}{field('timezone', 'Timezone (IANA, e.g. America/Los_Angeles)')}
      {listFields.slice(0, 2).map(preference)}
      <details><summary>More preferences and practical limits</summary>
        {listFields.slice(2).map(preference)}
        {field('minutes', 'Maximum one-way travel (minutes)', 'number')}
        <label>Travel modes<textarea value={draft.modes} onChange={e => change('modes', e.target.value)} /></label>
        {field('travelNotes', 'Travel tradeoffs')}{field('amount', 'Maximum cost per activity', 'number')}{field('currency', 'Currency (e.g. USD)')}{field('costNotes', 'Cost tradeoffs')}
        <h3>Recurring availability</h3><p>Optional same-day time windows in your base timezone.</p>
        {availability.map((row, i) => <div key={i} className="availability-row">
          <label>Day {i + 1}<select value={row.weekday} onChange={e => editAvailability(availability.map((r, n) => n === i ? { ...r, weekday: e.target.value } : r))}>{['monday','tuesday','wednesday','thursday','friday','saturday','sunday'].map(day => <option key={day}>{day}</option>)}</select></label>
          {(['start','end'] as const).map(key => <label key={key}>{key} {i + 1}<input type="time" required value={row[key].slice(0,5)} onChange={e => editAvailability(availability.map((r,n) => n === i ? { ...r, [key]: e.target.value } : r))} /></label>)}
          <label>Preference {i + 1}<select value={row.disposition} onChange={e => editAvailability(availability.map((r,n) => n === i ? { ...r, disposition: e.target.value } : r))}>{['available','unavailable','prefer'].map(v => <option key={v}>{v}</option>)}</select></label>
          <button type="button" onClick={() => editAvailability(availability.filter((_,n) => n !== i))}>Remove window {i + 1}</button>
        </div>)}
        <button type="button" disabled={availability.length >= 21} onClick={() => editAvailability([...availability, { weekday: 'saturday', start: '', end: '', disposition: 'available', note: null }])}>Add time window</button>
      </details>
      <button>{busy ? 'Saving…' : 'Save profile'}</button>
    </fieldset></form>}
  </section>
}
