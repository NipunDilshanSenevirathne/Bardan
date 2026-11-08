import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { api, store, useStore, type Role } from './api'
import { useI18n } from './i18n'

export function useSession() {
  return useStore((s) => s.session)
}
export function useRole(): Role | null {
  const s = useSession()
  return s ? (s.personas[s.persona]?.role ?? null) : null
}
export function usePersona() {
  const s = useSession()
  return s ? s.personas[s.persona] : null
}

/** Capability check for the current persona (mirrors the server; the server still decides). */
export function useCan() {
  const s = useSession()
  const perms = s ? s.permissions[s.persona] ?? [] : []
  return (cap: string) => perms.includes(cap)
}

/** Staff and worker names for audit and history rows (actor ids are never shown bare when a name is known). */
/** Persona names are proper names and stay as written, except role-like labels that need translating. */
const AR_NAMES: Record<string, string> = { 'Guest reviewer': 'مُقيِّم ضيف' }
export function displayName(name: string | null | undefined, lang: string): string {
  if (!name) return ''
  return lang === 'ar' ? AR_NAMES[name] ?? name : name
}

export function useActorNames() {
  const p = usePublicApi<any[]>('/personas')
  const { lang } = useI18n()
  const map: Record<string, string> = {}
  for (const x of p.data ?? []) map[x.actor] = displayName(x.name, lang)
  return (id?: string | null) => {
    if (!id) return '–'
    const base = id.split(' ')[0]
    const name = map[base]
    if (!name) return id
    return id.includes('(') ? `${name} ${id.slice(id.indexOf('('))}` : name
  }
}

/** GET with React Query, keyed by sandbox, persona and language. */
export function useApi<T = any>(path: string | null, opts: { refetch?: number; key?: QueryKey } = {}) {
  const s = useSession()
  const { lang } = useI18n()
  // During an observed drill the sandbox runs in real time, so screens that refresh do so every few seconds.
  const live = useStore((x) => x.drillLive)
  return useQuery<T>({
    queryKey: ['api', s?.sandboxId, s?.persona, lang, path, ...(opts.key ?? [])],
    queryFn: () => api<T>(path as string),
    enabled: !!path && !!s,
    refetchInterval: opts.refetch && live ? Math.min(opts.refetch, 4000) : opts.refetch,
    retry: (n, e: any) => n < 1 && e?.message !== 'offline' && e?.status !== 403,
  })
}

export function usePublicApi<T = any>(path: string) {
  return useQuery<T>({ queryKey: ['public', path], queryFn: () => api<T>(path, { auth: false }), staleTime: 60_000 })
}

/** POST helper that refreshes every query afterwards (the sandbox world changed). */
export function useAction<TBody = any, TOut = any>(path: string | ((b: TBody) => string), method = 'POST') {
  const qc = useQueryClient()
  return useMutation<TOut, any, TBody>({
    mutationFn: (body: TBody) => api<TOut>(typeof path === 'function' ? path(body) : path, { method, body: body ?? {} }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['api'] }) },
  })
}

export function minutesBetween(a?: string | null, b?: string | null) {
  if (!a || !b) return null
  return Math.round((Date.parse(b) - Date.parse(a)) / 60000)
}

export function fmtTime(iso?: string | null) {
  if (!iso) return '–'
  return iso.slice(11, 16)
}
export function fmtDate(iso?: string | null, lang = 'en') {
  if (!iso) return '–'
  const d = new Date(iso)
  return d.toLocaleDateString(lang === 'ar' ? 'ar-AE' : 'en-GB', { day: 'numeric', month: 'short', timeZone: 'Asia/Dubai' })
}
export function fmtNum(n: number | null | undefined, digits = 0) {
  if (n == null || Number.isNaN(n)) return '–'
  return n.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

export const offlineNow = () => store.get().offline
