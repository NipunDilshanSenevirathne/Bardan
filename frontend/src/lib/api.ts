/* API client, sandbox session, simulated offline mode and the offline outbox (finalsystem.md §20). */
import { useSyncExternalStore } from 'react'

export type Role = 'worker' | 'supervisor' | 'hse' | 'clinician' | 'nurse' | 'auditor'
export type Persona = { key: string; actor: string; role: Role; name: string; lang: string; title: string }
export type Session = {
  sandboxId: string
  persona: string
  tokens: Record<string, string>
  personas: Record<string, Persona>
  permissions: Record<string, string[]>
}

type State = { session: Session | null; offline: boolean; netDown: boolean; outbox: OutboxEvent[]; lastSync: string | null; seq: number; acks: Record<string, any>; drillLive: boolean }
export type OutboxEvent = { event_id: string; sequence: number; event_type: string; payload: any; observed_at: string; persona?: string }

const KEY = 'bardan.session.v1'
const OUTBOX = 'bardan.outbox.v1'
function load<T>(k: string, d: T): T {
  try { const v = localStorage.getItem(k); return v ? (JSON.parse(v) as T) : d } catch { return d }
}
function save(k: string, v: unknown) { try { localStorage.setItem(k, JSON.stringify(v)) } catch { /* ignore */ } }

let state: State = { session: load<Session | null>(KEY, null), offline: false, outbox: load<OutboxEvent[]>(OUTBOX, []),
  lastSync: null, seq: 0, acks: {}, drillLive: false, netDown: false }
const listeners = new Set<() => void>()
function set(p: Partial<State>) {
  state = { ...state, ...p }
  if ('session' in p) save(KEY, state.session)
  if ('outbox' in p) save(OUTBOX, state.outbox)
  listeners.forEach((l) => l())
}
export const store = {
  get: () => state,
  subscribe: (l: () => void) => { listeners.add(l); return () => listeners.delete(l) },
  set,
}
export function useStore<T>(sel: (s: State) => T): T {
  return useSyncExternalStore(store.subscribe, () => sel(state), () => sel(state))
}

export class OfflineError extends Error { constructor() { super('offline') } }
export class ApiError extends Error {
  status: number; detail: string; code?: string
  constructor(status: number, detail: string, code?: string) { super(detail); this.status = status; this.detail = detail; this.code = code }
}

function lang() { try { return localStorage.getItem('bardan.lang') === 'ar' ? 'ar' : 'en' } catch { return 'en' } }

/* The sandbox runs on a scenario clock (19 Aug 2025). Device-side events are stamped on that clock so the
   server's clock-quality checks (test T55) see a consistent timeline. */
let sandboxClock: string | null = null
export function noteSandboxClock(c?: string | null) { if (c) sandboxClock = c }
export function deviceNow(): string { return sandboxClock ?? new Date().toISOString() }

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; auth?: boolean; idem?: string; as?: string } = {}): Promise<T> {
  if (state.offline) throw new OfflineError()
  const headers: Record<string, string> = { 'X-Bardan-Lang': lang() }
  const s = state.session
  // `as`: send with another persona's token from this session (queued events go out as the person who made them).
  const who = opts.as && s?.tokens[opts.as] ? opts.as : s?.persona
  if (opts.auth !== false && s && who) headers.Authorization = `Bearer ${s.tokens[who]}`
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  if (opts.idem) headers['Idempotency-Key'] = opts.idem
  let res: Response
  try {
    res = await fetch(`/v1${path}`, { method: opts.method ?? (opts.body !== undefined ? 'POST' : 'GET'), headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined })
  } catch {
    // A real loss of network (airplane mode, no signal): shown in the shell, and queued events wait on the phone.
    if (!state.netDown) set({ netDown: true })
    throw new ApiError(0, 'Network unavailable')
  }
  if (state.netDown) set({ netDown: false })
  if (res.status === 401 && s && opts.auth !== false && who === s.persona) {
    // Token expired or the server restarted: get a fresh capability for the same persona.
    await switchPersona(s.persona, true)
    return api<T>(path, opts)
  }
  const ct = res.headers.get('content-type') || ''
  if (!res.ok) {
    const j = ct.includes('json') ? await res.json().catch(() => ({})) : {}
    throw new ApiError(res.status, j.detail || res.statusText, j.code)
  }
  if (ct.includes('json')) {
    const j = await res.json()
    if (path.startsWith('/sandbox')) noteSandboxClock(j?.clock ?? j?.state?.clock)
    return j as T
  }
  return (await res.blob()) as unknown as T
}

export async function startSession(persona: string, sandboxId?: string) {
  const r = await api<any>('/sandbox/session', { body: { persona, ...(sandboxId ? { sandbox_id: sandboxId } : {}) }, auth: false })
  const prev = state.session
  const personas = prev?.personas ?? {}
  personas[persona] = r.persona
  const session: Session = {
    sandboxId: r.sandbox_id,
    persona,
    tokens: { ...(prev && prev.sandboxId === r.sandbox_id ? prev.tokens : {}), [persona]: r.token },
    personas,
    permissions: { ...(prev?.permissions ?? {}), [persona]: r.permissions },
  }
  set({ session })
  return r
}

export async function switchPersona(persona: string, force = false) {
  const s = state.session
  if (!s) return startSession(persona)
  if (!force && s.tokens[persona]) { set({ session: { ...s, persona } }); return null }
  const prevOffline = state.offline
  state.offline = false
  try { return await startSession(persona, s.sandboxId) } finally { state.offline = prevOffline }
}

export function resetLocalSession() { set({ session: null, outbox: [] }) }

export function setOffline(v: boolean) {
  set({ offline: v })
  if (!v) void flushOutbox()
}

function uid() {
  const a = new Uint8Array(8); crypto.getRandomValues(a)
  return Array.from(a, (b) => b.toString(16).padStart(2, '0')).join('')
}

/* One Idempotency-Key per intended action. If the outcome is unknown (the connection dropped), the same key is
   reused when the person taps again, so the server does the action at most once. */
const pendingKeys = new Map<string, string>()
export async function actOnce<T = any>(intent: string, path: string, body: unknown): Promise<T> {
  const key = pendingKeys.get(intent) ?? uid()
  pendingKeys.set(intent, key)
  try {
    const r = await api<T>(path, { body, idem: key })
    pendingKeys.delete(intent)
    return r
  } catch (e) {
    if (!(e instanceof ApiError && e.status === 0) && !(e instanceof OfflineError)) pendingKeys.delete(intent)
    throw e
  }
}

/** Store an event locally first (atomic with the outbox), then sync when a connection exists (§20.3). */
export function enqueue(event_type: string, payload: any): OutboxEvent {
  const ev: OutboxEvent = { event_id: uid(), sequence: state.outbox.length + 1 + state.seq, event_type, payload,
    observed_at: deviceNow(), persona: state.session?.persona }
  set({ outbox: [...state.outbox, ev], seq: state.seq + 1 })
  if (!state.offline) void flushOutbox()
  return ev
}

let flushing = false
export async function flushOutbox() {
  if (state.offline || !state.outbox.length || !state.session || flushing) return
  flushing = true
  try { await flushOnce() } finally { flushing = false }
}

async function flushOnce() {
  const current = state.session?.persona
  if (!current) return
  // Each event goes out as the persona that made it, even if someone switched persona while offline.
  const groups = new Map<string, OutboxEvent[]>()
  for (const e of state.outbox) {
    const who = e.persona && state.session?.tokens[e.persona] ? e.persona : current
    groups.set(who, [...(groups.get(who) ?? []), e])
  }
  for (const [persona, batch] of groups) {
    try {
      const r = await api<any>('/sync', { body: { device_id: `browser-${persona}`, events: batch }, as: persona })
      const ok = r.acks.filter((a: any) => a.status !== 'rejected')
      const done = new Set(ok.map((a: any) => a.event_id))
      // The server's receipt for each event is kept: "received by the server" is shown only from a real receipt.
      const acks = { ...state.acks }
      for (const a of ok) acks[a.event_id] = a
      set({ outbox: state.outbox.filter((e) => !done.has(e.event_id)), lastSync: r.server_time, acks })
    } catch { /* keep queued; pending is shown honestly */ }
  }
}

/* Events saved on the phone are sent when the network comes back (the browser's online event), on every page
   load (the outbox survives a reload), and by a gentle retry every 10 seconds while anything is waiting. */
if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('online', () => { void flushOutbox() })
  setTimeout(() => { void flushOutbox() }, 1500)
  setInterval(() => { if (state.outbox.length) void flushOutbox() }, 10000)
}

export function currentRole(): Role | null {
  const s = state.session
  return s ? s.personas[s.persona]?.role ?? null : null
}
