/*
 * Device-side deterministic policy engine (TypeScript). Same rules as backend/app/core/policy.py, driven by the
 * same signed policy JSON and held to the same conformance suite (shared/conformance.json). The Decision Replay
 * Pack compares the two engines' meanings, not their formatting (finalsystem.md §29.2).
 */
import heatPack from '../../../shared/packs/AE-AD-HEAT.json'
import middayPack from '../../../shared/packs/AE-FED-MIDDAY.json'
import manifest from '../../../shared/packs/manifest.json'

export type Obs = { kind?: string; value?: number | null; observed_at?: string | null; provenance?: string } | null
export type Input = {
  now: string
  zone?: { outdoor?: boolean; direct_sun?: boolean }
  task?: { workload?: string; outdoor?: boolean; ppe?: string }
  worker?: { acclimatization?: string; day?: number; restriction?: string | { label?: string } | null } | null
  observation?: Obs
  observations?: Obs[]
  resources?: { water_available?: boolean }
  symptoms?: string[]
  exemption?: { authorised?: boolean } | null
}
export type Decision = { state: string; band: string | null; actions: string[]; reasons: string[]; exposure_percent: number }

const RANK: Record<string, number> = { routine: 0, enhanced: 1, unavailable: 2, stop: 3, emergency: 4 }
const BAND_RANK: Record<string, number> = { unrestricted: 0, acclimatization: 1, buffer: 2, withdrawal: 3 }
const KNOWN_WORKLOADS = ['light', 'moderate', 'heavy']
type Rule = { band: string; min_inclusive?: number | null; min_exclusive?: number | null; max_inclusive?: number | null; max_exclusive?: number | null }

function inRange(v: number, r: Rule): boolean {
  if (r.min_inclusive != null && v < r.min_inclusive) return false
  if (r.min_exclusive != null && v <= r.min_exclusive) return false
  if (r.max_inclusive != null && v > r.max_inclusive) return false
  if (r.max_exclusive != null && v >= r.max_exclusive) return false
  return true
}
export function bandFromTwl(v: number) {
  const r = (heatPack.twl_zones as Rule[]).find((z) => inRange(v, z))
  if (!r) throw new Error(`TWL ${v} outside all bands`)
  return r.band
}
export function bandFromWbgt(v: number) {
  const r = (heatPack.wbgt_planning_bands_demo as Rule[]).find((z) => inRange(v, z))
  if (!r) throw new Error(`WBGT ${v} outside all bands`)
  return r.band
}

/** Parse an ISO time with an explicit offset into epoch ms (no device time zone involved, test T18). */
export function parseTime(s: string): number {
  if (!/[zZ]|[+-]\d\d:\d\d$/.test(s)) throw new Error('timestamps must include a UTC offset')
  return Date.parse(s)
}

function dubaiParts(ms: number) {
  // Asia/Dubai is UTC+4 all year (no daylight saving); computed explicitly so the device zone never matters.
  const d = new Date(ms + 4 * 3600 * 1000)
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mi = String(d.getUTCMinutes()).padStart(2, '0')
  return { md: `${mm}-${dd}`, hm: `${hh}:${mi}`, day: `${d.getUTCFullYear()}-${mm}-${dd}` }
}

/** Packs past their review date are not used (test T21); the emergency path never depends on a pack. */
export function overduePacks(ms: number): string[] {
  const day = dubaiParts(ms).day
  const packs = (manifest as { packs: Record<string, { review_by?: string }> }).packs
  return ['AE-AD-HEAT', 'AE-FED-MIDDAY'].filter((n) => (packs[n]?.review_by ?? '9999-12-31') < day)
}
export function inMiddayWindow(ms: number) {
  const { md, hm } = dubaiParts(ms)
  if (!(middayPack.season.from <= md && md <= middayPack.season.to)) return false
  return middayPack.window.start <= hm && hm < middayPack.window.end
}

function freshnessKey(o: NonNullable<Obs>): string | null {
  if (o.provenance === 'measured' && (o.kind === 'twl' || o.kind === 'wbgt')) return `${o.kind}_measured`
  if (o.provenance === 'official_external') return 'official_external'
  if (o.provenance === 'derived') return 'derived'
  return null // forecasts never count as a live observation
}
export function isFresh(o: Obs | undefined, nowMs: number) {
  if (!o || o.value == null || !o.observed_at) return false
  const key = freshnessKey(o)
  if (!key) return false
  const age = (nowMs - parseTime(o.observed_at)) / 60000
  if (age < -5) return false
  return age <= (heatPack.freshness_minutes as Record<string, number>)[key]
}
export function acclimatizationPercent(w: Input['worker']) {
  if (!w) return 100
  const stage = w.acclimatization ?? 'acclimatized'
  const day = Number(w.day ?? 99)
  let sched: number[]
  if (stage === 'new') sched = heatPack.acclimatization.new_percent_by_day
  else if (stage === 'returning') sched = heatPack.acclimatization.experienced_percent_by_day
  else return 100
  if (day < 1) return sched[0]
  if (day > sched.length) return 100
  return sched[day - 1]
}
const unacclimatized = (w: Input['worker']) => !!w && acclimatizationPercent(w) < 100

export function evaluate(inp: Input): Decision {
  const now = parseTime(inp.now)
  const zone = inp.zone ?? {}
  const task = inp.task ?? {}
  const worker = inp.worker ?? null
  const symptoms = inp.symptoms ?? []
  const exemption = inp.exemption ?? {}
  const reasons: string[] = []
  const actions = new Set<string>()
  let state = 'routine'
  let band: string | null = null
  let exposure = acclimatizationPercent(worker)
  const raise = (s: string) => { if (RANK[s] > RANK[state]) state = s }

  if (symptoms.some((s) => heatPack.urgent_symptoms.includes(s))) {
    return { state: 'emergency', band: null, actions: ['BUDDY_STAY', 'CALL_998', 'EMERGENCY_CARD', 'START_COOLING'],
      reasons: ['emergency:urgent_symptom'], exposure_percent: 0 }
  }
  if (overduePacks(now).length) {
    return { state: 'unavailable', band: null, actions: ['FOLLOW_FALLBACK_PLAN'], reasons: ['policy:pack_review_overdue'], exposure_percent: 0 }
  }
  const concerning = symptoms.filter((s) => heatPack.concerning_symptoms.includes(s))
  if (concerning.length) {
    raise('stop'); ['STOP_ACTIVITY', 'MOVE_TO_SHADE', 'FIRST_AIDER_CHECK'].forEach((a) => actions.add(a))
    reasons.push('triage:concerning_symptom')
    if (concerning.includes('muscle_pain_dark_urine')) { actions.add('URGENT_CLINICAL_ASSESSMENT'); reasons.push('triage:possible_muscle_breakdown') }
    exposure = 0
  }
  const heatTask = !!(task.outdoor || zone.direct_sun)
  if (inMiddayWindow(now) && task.outdoor && zone.direct_sun && !(exemption && exemption.authorised)) {
    raise('stop'); actions.add('STOP_OUTDOOR_WORK'); actions.add('MOVE_TO_SHADE'); reasons.push('AE-FED-MIDDAY:window'); exposure = 0
  }
  // Unknown workload or clothing/PPE: approved conservative plan, treated as heavy (T12).
  let workload = task.workload
  if (Object.keys(task).length > 0 && (!KNOWN_WORKLOADS.includes(String(workload)) || task.ppe === 'unknown')) {
    raise('enhanced'); actions.add('FOLLOW_FALLBACK_PLAN'); reasons.push('unknown:workload_or_ppe'); workload = 'heavy'
  }
  const restriction = typeof worker?.restriction === 'object' && worker?.restriction ? worker.restriction.label : worker?.restriction
  if ((restriction === 'shaded_light_duty' && (workload === 'heavy' || zone.direct_sun)) || (restriction === 'no_heat_work' && heatTask)) {
    raise('stop'); actions.add('REASSIGN_SHADED_LIGHT'); reasons.push('clinical:restriction'); exposure = 0
  }
  // Two or more credible sources: the most protective band governs, all controls apply, a person resolves (T15).
  const candidates: Obs[] = [...(inp.observation ? [inp.observation] : []), ...(inp.observations ?? [])]
  const fresh = candidates.filter((o) => isFresh(o, now) && (o!.kind === 'twl' || o!.kind === 'wbgt'))
  if (!fresh.length) {
    raise('unavailable'); actions.add('FOLLOW_FALLBACK_PLAN'); reasons.push('freshness:missing_or_stale')
  } else {
    const graded = fresh.map((o) => { const b = o!.kind === 'twl' ? bandFromTwl(Number(o!.value)) : bandFromWbgt(Number(o!.value)); return { r: BAND_RANK[b], b, o: o! } })
    const top = graded.reduce((a, x) => (x.r > a.r ? x : a))
    band = top.b
    reasons.push(`AE-AD-HEAT:${top.o.kind === 'twl' ? 'twl' : 'wbgt_demo'}:${band}`)
    for (const g of graded) ((heatPack.controls_by_band as Record<string, string[]>)[g.b] ?? []).forEach((a) => actions.add(a))
    if (new Set(graded.map((g) => g.b)).size > 1) { actions.add('RESOLVE_SOURCE_CONFLICT'); reasons.push('conflict:sources_disagree') }
    if (band) {
      raise((heatPack.state_by_band as Record<string, string>)[band])
      if ((band === 'buffer' || band === 'withdrawal') && unacclimatized(worker) && heatTask) {
        raise('stop'); actions.add('UNACCLIMATIZED_STOP_HEAT_WORK'); reasons.push('AE-AD-HEAT:unacclimatized'); exposure = 0
      } else if (band === 'acclimatization' && unacclimatized(worker)) actions.add('NO_LONE_WORK')
    }
  }
  if (inp.resources?.water_available === false && heatTask) {
    raise('stop'); actions.add('RESTORE_WATER'); actions.add('STOP_AFFECTED_WORK'); reasons.push('resources:water_unavailable'); exposure = 0
  }
  if (exposure < 100 && state !== 'stop' && state !== 'emergency' && worker) actions.add('LIMIT_EXPOSURE')
  return { state, band, actions: [...actions].sort(), reasons, exposure_percent: exposure }
}

export const ENGINE_INFO = { language: 'TypeScript (browser)', packs: [`${heatPack.policy_id}@${heatPack.version}`,
  `${middayPack.policy_id}@${(middayPack as any).version ?? 'demo'}`] }

/* Emergency triage that works with no network and no model (finalsystem.md §12.3, invariant 7). */
export const URGENT = heatPack.urgent_symptoms as string[]
export const CONCERNING = heatPack.concerning_symptoms as string[]
