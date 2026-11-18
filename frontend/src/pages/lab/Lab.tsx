/* Scenario Lab and shift simulator (programme feedback, November 2026).
   The reviewer edits sample workers, weather and tasks; the server's planner re-plans (CP-SAT, break planner,
   independent re-check) and returns every named worker's phone view. "Play the shift" moves the clock in
   30-minute steps; conditions changed mid-shift are re-planned from that moment with the past frozen.
   Simulated wearables run here, on the "phone": only the words "needs a break" reach the planner, and only
   for workers who chose to share. Nothing entered is stored. */
import {
  Activity, AlertTriangle, BadgeCheck, CalendarClock, ChevronDown, ChevronUp, CloudSun, Droplets, FlaskConical,
  HeartPulse, Info, ListRestart, Pause, Play, Plus, RotateCcw, ShieldCheck, Smartphone, StepForward, Thermometer,
  Trash2, Users, Watch, Wind, Wrench,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { PlanTimeline } from '../../components/PlanTimeline'
import { Badge, Button, Card, CardHeader, ErrorNote, PageHeader, Skeleton, Stat, cx } from '../../components/ui'
import { assess, simulateHeartRate, type Level, type Minute, type Sample } from '../../engine/strain'
import { api } from '../../lib/api'
import { useApi } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'
import { STRINGS, type Lang } from '../../lib/strings'
import { slotLabel, useVizColors, WBGT_BANDS } from '../../lib/viz'

type Scenario = any
type Ev = { type: string; at: string; target?: string | null }
type LogItem = { at: string; kind: 'start' | 'replan' | 'harder' | 'noplan'; title: string; lines: string[] }
type WearInfo = { level: Level; hr: number | null; shared: boolean }

const WATTS: Record<string, number> = { light: 180, moderate: 300, heavy: 415 }
const CAF: Record<string, number> = { work_clothes: 0, coveralls: 1, double_layer: 3 }
const TIMES = Array.from({ length: 29 }, (_, i) => slotLabel(i))
const slotOf = (hhmm: string) => (parseInt(hhmm.slice(0, 2)) * 60 + parseInt(hhmm.slice(3, 5)) - 300) / 30
const qLabel = (q: number) => { const m = 300 + 15 * q; return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}` }

/** Translate into a given language (a phone shows its owner's language, whatever the reviewer's interface). */
function tl(lang: Lang, k: string, v?: Record<string, string | number>) {
  let s = STRINGS[lang][k] ?? STRINGS.en[k] ?? k
  if (v) for (const [key, val] of Object.entries(v)) s = s.split(`{${key}}`).join(String(val))
  return s
}

function hashSeed(s: string) { let h = 7; for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return h }

/* ------------------------------------------------------------------ simulated wearable (on the phone) */
function minutesFor(res: any, w: any, upToSlot: number, events: Ev[]): Minute[] {
  const plan = res.plan
  const t = plan.tasks.find((x: any) => x.crew === w.crew)
  const zone = res.world.zones.find((z: any) => z.id === t.zone)
  const a = plan.assignments?.[w.id]
  const heat = new Set<number>(a ? a.heat_slots : t.slots)
  const restQ = new Set<number>()
  for (const b of plan.breaks) if (b.crew === w.crew) for (let q = b.start_q; q < b.start_q + b.quarters; q++) restQ.add(q)
  const personal = new Set<number>()
  for (const e of events) if (e.type === 'wearable' && e.target === w.id) personal.add(slotOf(e.at))
  const out: Minute[] = []
  for (let m = 0; m < upToSlot * 30; m++) {
    const s = Math.floor(m / 30)
    const q = Math.floor(m / 15)
    const working = heat.has(s) && !restQ.has(q) && !personal.has(s)
    if (working) out.push({ mW: WATTS[t.workload], wbgt: res.grid.zones[t.zone][s].wbgt_point + (CAF[t.clothing] ?? 0), working: true })
    else if (heat.has(s) || personal.has(s)) out.push({ mW: 115, wbgt: res.grid.rest_wbgt[zone.rest_area][s], working: false })
    else out.push({ mW: 150, wbgt: res.grid.shade[s], working: false })
  }
  return out
}

function wearableAt(res: any, w: any, toSlot: number, fromSlot: number, events: Ev[], harder: boolean): { level: Level; hr: number | null; hrs: number[] } {
  if (!res?.plan || toSlot <= 0) return { level: 'no_reading', hr: null, hrs: [] }
  const mins = minutesFor(res, w, toSlot, events)
  const sim = simulateHeartRate(mins, { seed: hashSeed(w.id), harderDay: harder, acclimatized: w.status === 'acclimatized' })
  const samples: Sample[] = sim.hr.map((hr, i) => ({ hr, working: mins[i].working }))
  // A phone checks every minute; between two 30-minute steps the worst level counts.
  const rank: Record<Level, number> = { no_reading: 0, steady: 1, rising: 2, high: 3 }
  let worst: Level = 'steady'
  for (let m = Math.max(1, fromSlot * 30); m <= toSlot * 30; m++) {
    const l = assess(samples.slice(0, m), { age: w.age, acclimatized: w.status === 'acclimatized' }).level
    if (rank[l] > rank[worst]) worst = l
  }
  return { level: worst, hr: sim.hr[sim.hr.length - 1] ?? null, hrs: sim.hr.slice(-90) }
}

/* ------------------------------------------------------------------ page */
export default function Lab() {
  const { t, lang } = useI18n()
  const pre = useApi<any>('/lab/presets')
  const [presetId, setPresetId] = useState<string>('summer_site')
  const [sc, setSc] = useState<Scenario | null>(null)
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<unknown>(null)
  const [now, setNow] = useState<string | null>(null)
  const [events, setEvents] = useState<Ev[]>([])
  const [log, setLog] = useState<LogItem[]>([])
  const [playing, setPlaying] = useState(false)
  const [harder, setHarder] = useState<Record<string, boolean>>({})
  const [wear, setWear] = useState<Record<string, WearInfo>>({})
  const [noplan, setNoplan] = useState<any>(null)
  const reqId = useRef(0)
  const tRef = useRef(t)
  tRef.current = t
  const state = useRef({ sc, res, now, events, harder, busy })
  state.current = { sc, res, now, events, harder, busy }
  const skipNextReplan = useRef(false)

  useEffect(() => {
    const p = pre.data?.presets?.find((x: any) => x.id === presetId)
    if (p && !sc) setSc(structuredClone(p))
  }, [pre.data, presetId, sc])

  const call = useCallback(async (body: any) => {
    const id = ++reqId.current
    setBusy(true); setErr(null)
    try {
      const r = await api('/lab/plan', { body })
      return id === reqId.current ? r : null
    } catch (e) { if (id === reqId.current) setErr(e); return null } finally { if (id === reqId.current) setBusy(false) }
  }, [])

  // Any edit to the scenario re-plans the whole day (debounced) and restarts the simulation.
  useEffect(() => {
    if (!sc) return
    if (skipNextReplan.current) { skipNextReplan.current = false; return }
    const h = setTimeout(async () => {
      const r = await call({ scenario: sc })
      if (!r) return
      setPlaying(false); setNow(null); setEvents([]); setWear({})
      setRes(r)
      // No protected plan for the whole day: say so and offer only the permitted options, never a blank result.
      const start = tRef.current('lab.log.start')
      setNoplan(r.plan ? null : { ...r, at: '05:00', evs: [], title: start, initial: true })
      setLog([r.plan ? { at: '05:00', kind: 'start', title: start, lines: [] }
        : { at: '05:00', kind: 'noplan', title: `${start} · ${tRef.current('lab.noplan')}`, lines: [] }])
    }, 450)
    return () => clearTimeout(h)
  }, [sc, call])

  const named: any[] = res?.named_workers ?? []

  /** Move the clock to `to`, adding `added` events; wearables are checked first, on the "phone". */
  const advance = useCallback(async (to: string, added: Ev[], title: string) => {
    const cur = state.current
    if (!cur.sc || !cur.res?.plan) return
    let evs = [...cur.events, ...added]
    const toSlot = slotOf(to)
    const fromSlot = cur.now ? slotOf(cur.now) : 0
    const lines: string[] = []
    const nextWear: Record<string, WearInfo> = {}
    for (const w of cur.res.named_workers.filter((x: any) => x.wearable)) {
      const rw = cur.res.workers.find((x: any) => x.id === w.id)
      const st = wearableAt(cur.res, { ...w, status: w.acclimatization, age: w.age ?? rw?.age, crew: w.crew }, toSlot, fromSlot, evs, !!cur.harder[w.id])
      const recent = evs.some((e) => e.type === 'wearable' && e.target === w.id && toSlot - slotOf(e.at) < 2)
      let shared = false
      if (st.level === 'high' && !recent) {
        if (w.share_status) {
          evs = [...evs, { type: 'wearable', at: to, target: w.id }]
          shared = true
          lines.push(t('lab.log.wear_shared', { name: w.name }))
        } else lines.push(t('lab.log.wear_private', { name: w.name }))
      }
      nextWear[w.id] = { level: st.level, hr: st.hr, shared: shared || recent }
    }
    const r = await call({ scenario: cur.sc, now: to, previous: cur.res.plan, events: evs })
    if (!r) { setPlaying(false); return }
    if (!r.plan) {
      // Conditions really changed, so they are kept; the day waits for a permitted decision before moving on.
      setPlaying(false); setNoplan({ ...r, at: to, evs, title }); setEvents(evs); setNow(to)
      setLog((l) => [...l, { at: to, kind: 'noplan', title: `${title} · ${t('lab.noplan')}`, lines }])
      return
    }
    setNoplan(null)
    setRes(r); setNow(to); setEvents(evs); setWear(nextWear)
    const changed = (r.changes ?? []).map((c: any) => t('lab.log.changed', { task: c.name, after: c.work_after.join(', ') || '–', rest: c.rest_after_min }))
    setLog((l) => [...l, { at: to, kind: 'replan', title, lines: [...lines, ...(changed.length ? changed : added.length ? [t('lab.log.nochange')] : [])] }])
  }, [call, t])

  const step = useCallback(async () => {
    const cur = state.current
    const next = cur.now ? slotOf(cur.now) + 1 : 1
    if (next > 28) { setPlaying(false); return }
    await advance(slotLabel(next), [], t('lab.log.replan', { t: slotLabel(next) }))
  }, [advance, t])

  useEffect(() => {
    if (!playing || busy) return
    if (now && slotOf(now) >= 28) { setPlaying(false); return }
    const h = setTimeout(() => { void step() }, 1700)
    return () => clearTimeout(h)
  }, [playing, busy, now, step])

  function addEvent(type: string, target?: string) {
    const at = now ?? '05:00'
    void advance(at, [{ type, at, target: target ?? null }], `${t(`lab.ev.${type}`)}${target ? ` · ${targetName(target)}` : ''}`)
  }
  function targetName(id: string) {
    return res?.world?.rest_areas?.find((r: any) => r.id === id)?.name ?? res?.world?.crews?.find((c: any) => c.id === id)?.name ??
      named.find((w) => w.id === id)?.name ?? id
  }
  function restart() {
    setPlaying(false)
    setSc((s: Scenario) => (s ? { ...s } : s))
  }
  function applyRemedy(key: string) {
    if (!sc || !noplan) return
    const nsc = structuredClone(sc)
    if (key === 'deferral') nsc.tasks.forEach((x: any) => { x.can_wait = true })
    if (key === 'rest_capacity') nsc.rest_areas.forEach((r: any) => { r.seats = Math.min(60, r.seats + 6) })
    if (key === 'shaded_capacity') nsc.shaded_places = Math.min(20, (nsc.shaded_places ?? 0) + 3)
    skipNextReplan.current = true
    setSc(nsc)
    state.current = { ...state.current, sc: nsc }
    const pending = noplan
    setNoplan(null)
    void (async () => {
      // Before the shift there is no plan to re-plan from: the whole day is planned again with the remedy.
      const r = pending.initial
        ? await call({ scenario: nsc })
        : await call({ scenario: nsc, now: pending.at, previous: state.current.res.plan, events: pending.evs })
      if (r?.plan) {
        setRes(r)
        if (!pending.initial) { setNow(pending.at); setEvents(pending.evs) }
        setLog((l) => [...l, { at: pending.at, kind: 'replan', title: `${t('lab.apply')}: ${pending.diagnosis.permitted_remedies.find((x: any) => x.remedy === key)?.[lang === 'ar' ? 'text_ar' : 'text']}`, lines: (r.changes ?? []).map((c: any) => t('lab.log.changed', { task: c.name, after: c.work_after.join(', ') || '–', rest: c.rest_after_min })) }])
      } else if (r) setNoplan({ ...r, at: pending.at, evs: pending.evs, title: pending.title, initial: pending.initial })
    })()
  }
  function chooseHarder(id: string) {
    setHarder((h) => ({ ...h, [id]: true }))
    const w = named.find((x) => x.id === id)
    setLog((l) => [...l, { at: now ?? '05:00', kind: 'harder', title: t('lab.log.harder', { name: w?.name ?? id }), lines: [] }])
  }

  if (pre.isLoading || (!sc && !pre.error)) return <Skeleton className="h-[40rem]" />
  if (pre.error) return <ErrorNote error={pre.error} onRetry={() => pre.refetch()} />
  const nowSlot = now ? slotOf(now) : null

  return (
    <div className="space-y-6">
      <PageHeader title={t('lab.title')} icon={<FlaskConical className="size-6" />}
        sub={<>{t('lab.sub')} <Badge tone="sun" className="ms-1">{t('common.simulation')}</Badge></>}
        actions={<>
          <label className="flex items-center gap-2 text-sm font-semibold">{t('lab.preset')}
            <select value={presetId} onChange={(e) => { setPresetId(e.target.value); setSc(structuredClone(pre.data.presets.find((x: any) => x.id === e.target.value))) }}
              className="h-11 rounded-xl border border-line bg-surface px-3 text-sm font-semibold">
              {pre.data.presets.map((p: any) => <option key={p.id} value={p.id}>{lang === 'ar' ? p.title_ar : p.title}</option>)}
            </select>
          </label>
          <Button variant="outline" onClick={() => setSc(structuredClone(pre.data.presets.find((x: any) => x.id === presetId)))} icon={<RotateCcw className="size-4" />}>{t('lab.reset')}</Button>
        </>} />
      <div className="flex items-start gap-3 rounded-2xl border border-warn/30 bg-warn-soft/60 p-3 text-sm font-semibold text-warn"><Info className="mt-0.5 size-4 shrink-0" />{t('lab.notice')}</div>
      {err ? <ErrorNote error={err} /> : null}

      <div className="grid grid-cols-1 gap-6 2xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] xl:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]">
        {/* ------------------------------------------------ inputs */}
        <div className="space-y-5">
          <WeatherCard sc={sc} set={setSc} res={res} nowSlot={nowSlot} />
          <TasksCard sc={sc} set={setSc} />
          <PeopleCard sc={sc} set={setSc} />
          <RestCard sc={sc} set={setSc} />
        </div>

        {/* ------------------------------------------------ results */}
        <div className="min-w-0 space-y-5">
          <SimBar now={now} playing={playing} busy={busy || !!noplan} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onStep={() => void step()}
            onRestart={restart} res={res} onEvent={addEvent} onHarder={chooseHarder} harder={harder} />
          {noplan && <NoPlan r={noplan} onApply={applyRemedy} />}
          {res && <Summary res={res} busy={busy} />}
          {res?.plan && (
            <Card>
              <CardHeader title={t('lab.result')} icon={<CalendarClock className="size-5" />}
                sub={<span className="inline-flex flex-wrap items-center gap-2">{res.revalidation.result === 'valid'
                  ? <Badge tone="ok" icon={<BadgeCheck className="size-3.5" />}>{t('lab.valid', { n: res.revalidation.checks })}</Badge>
                  : <Badge tone="stop" icon={<AlertTriangle className="size-3.5" />}>{t('lab.invalid', { n: res.revalidation.violations.length })}</Badge>}
                  <span className="text-xs text-muted">{busy ? t('lab.planning') : t('lab.replanned', { s: res.runtime_s })}</span></span>} />
              <div className="p-4 sm:p-5">
                <NeedsBreak events={events} named={named} />
                <PlanTimeline plan={res.plan} grid={res.grid} crewSize={Object.fromEntries(res.world.crews.map((c: any) => [c.id, c.size]))}
                  restAreas={res.world.rest_areas} workers={Object.fromEntries(named.map((w: any) => [w.id, w]))} nowSlot={nowSlot}
                  taskSub={(tk) => <>{t(`lab.exp.${res.world.zones.find((z: any) => z.id === tk.zone)?.exposure}`)} · {t(`wl.${tk.workload}`)} · {res.world.crews.find((c: any) => c.id === tk.crew)?.size} {t('common.workers')}</>} />
              </div>
            </Card>
          )}
          {res?.plan && <Phones res={res} now={now} wear={wear} events={events} />}
          <div className="grid grid-cols-1 gap-5 2xl:grid-cols-2">
            {res?.plan && <Why res={res} />}
            <Log log={log} />
          </div>
          <Method res={res} />
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ inputs */
function Field({ label, children, className }: { label: ReactNode; children: ReactNode; className?: string }) {
  return <label className={cx('block text-xs font-semibold text-muted', className)}>{label}<div className="mt-1 text-sm text-ink">{children}</div></label>
}
const inputCls = 'h-10 w-full rounded-xl border border-line bg-surface px-2.5 text-sm font-semibold'

function Seg<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { id: T; label: ReactNode }[] }) {
  return (
    <div role="radiogroup" className="inline-flex w-full flex-wrap gap-1 rounded-xl bg-surface-2 p-1">
      {items.map((it) => (
        <button key={it.id} role="radio" aria-checked={value === it.id} onClick={() => onChange(it.id)}
          className={cx('min-h-9 flex-1 rounded-lg px-2.5 text-xs font-bold transition-colors', value === it.id ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-ink')}>{it.label}</button>
      ))}
    </div>
  )
}

function Slider({ label, value, min, max, step, unit, onChange, icon }: { label: string; value: number; min: number; max: number; step: number; unit: string; onChange: (v: number) => void; icon: ReactNode }) {
  return (
    <div>
      <div className="flex items-center justify-between text-xs font-semibold text-muted"><span className="inline-flex items-center gap-1.5">{icon}{label}</span><span className="num text-sm font-bold text-ink" dir="ltr">{value} {unit}</span></div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} aria-label={label}
        className="mt-1.5 w-full accent-[var(--brand)]" />
    </div>
  )
}

function WeatherCard({ sc, set, res, nowSlot }: { sc: Scenario; set: (f: (s: Scenario) => Scenario) => void; res: any; nowSlot: number | null }) {
  const { t } = useI18n()
  const wx = sc.weather
  const upd = (p: any) => set((s) => ({ ...s, weather: { ...s.weather, ...p } }))
  return (
    <Card>
      <CardHeader title={t('lab.weather')} icon={<CloudSun className="size-5" />} />
      <div className="space-y-4 p-5">
        <Field label={t('lab.season')}>
          <Seg value={sc.season} onChange={(v) => set((s) => ({ ...s, season: v }))} items={[{ id: 'summer', label: t('lab.season.summer') }, { id: 'autumn', label: t('lab.season.autumn') }]} />
          <p className="mt-1 text-xs text-muted">{t(`lab.season.${sc.season}.b`)}</p>
        </Field>
        <Slider label={t('lab.peak')} value={wx.peak_c} min={25} max={50} step={1} unit="°C" onChange={(v) => upd({ peak_c: v })} icon={<Thermometer className="size-3.5" />} />
        <Slider label={t('lab.humidity')} value={wx.humidity_pct} min={10} max={90} step={1} unit="%" onChange={(v) => upd({ humidity_pct: v })} icon={<Droplets className="size-3.5" />} />
        <Slider label={t('lab.wind')} value={wx.wind_ms} min={0.5} max={10} step={0.5} unit="m/s" onChange={(v) => upd({ wind_ms: v })} icon={<Wind className="size-3.5" />} />
        <Field label={t('lab.sky')}>
          <Seg value={wx.sky} onChange={(v) => upd({ sky: v })} items={(['clear', 'haze', 'cloud'] as const).map((k) => ({ id: k, label: t(`lab.sky.${k}`) }))} />
        </Field>
        {res?.grid && <HeatChart res={res} nowSlot={nowSlot} />}
      </div>
    </Card>
  )
}

function HeatChart({ res, nowSlot }: { res: any; nowSlot: number | null }) {
  const { t } = useI18n()
  const c = useVizColors()
  const rows = res.grid.sun.map((v: number, i: number) => ({ i, time: slotLabel(i), sun: v, shade: res.grid.shade[i] }))
  return (
    <div>
      <div className="text-xs font-semibold text-muted">{t('lab.heat_chart')}</div>
      <div className="mt-1 h-40" dir="ltr">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
            {WBGT_BANDS.map((b) => <ReferenceArea key={b.band} y1={b.from} y2={b.to} fill={c.bands[b.band]} fillOpacity={0.09} stroke="none" ifOverflow="hidden" />)}
            <CartesianGrid stroke={c.grid} vertical={false} />
            <XAxis dataKey="i" tickFormatter={(i) => slotLabel(i)} ticks={[0, 6, 12, 18, 24]} tick={{ fontSize: 10, fill: c.muted }} stroke={c.line} />
            <YAxis domain={[18, 40]} ticks={[20, 25, 28, 31, 33, 38]} tick={{ fontSize: 10, fill: c.muted }} stroke={c.line} />
            <Tooltip formatter={(v: any, n: any) => [`${Number(v).toFixed(1)} °C`, n === 'sun' ? t('lab.sun') : t('lab.shade')]} labelFormatter={(i: any) => slotLabel(Number(i))}
              contentStyle={{ background: c.surface, border: `1px solid ${c.line}`, borderRadius: 12, fontSize: 12 }} />
            {nowSlot != null && <ReferenceLine x={nowSlot} stroke="var(--sun-bright)" strokeWidth={2} />}
            <Line type="monotone" dataKey="sun" stroke={c.s2} strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="shade" stroke={c.s1} strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-3 text-[11px] text-ink-2">
        <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-5 rounded" style={{ background: c.s2 }} />{t('lab.sun')}</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-5 rounded" style={{ background: c.s1 }} />{t('lab.shade')}</span>
        <span className="text-muted">{t('lab.cooled_room')}: <span className="num" dir="ltr">{Number(res.grid.cooled).toFixed(1)} °C</span></span>
      </div>
      <p className="mt-1 text-[11px] text-muted">{t('lab.heat_chart.b', { m: res.grid.planning_margin_c })}</p>
    </div>
  )
}

function TasksCard({ sc, set }: { sc: Scenario; set: (f: (s: Scenario) => Scenario) => void }) {
  const { t } = useI18n()
  const [open, setOpen] = useState<string | null>(null)
  const upd = (id: string, p: any) => set((s) => ({ ...s, tasks: s.tasks.map((x: any) => (x.id === id ? { ...x, ...p } : x)) }))
  function add() {
    set((s) => {
      const n = [1, 2, 3, 4, 5, 6, 7].find((k) => !s.tasks.some((x: any) => x.id === `T${k}`)) ?? 9
      return { ...s, tasks: [...s.tasks, { id: `T${n}`, name: `Task ${n}`, exposure: 'sun', workload: 'moderate', clothing: 'work_clothes', hours: 3, start: '05:00', end: '19:00', crew_size: 4, rest_area: s.rest_areas[0].id, walk_min: 3, one_piece: false, can_wait: true }] }
    })
  }
  return (
    <Card>
      <CardHeader title={t('lab.tasks')} icon={<Wrench className="size-5" />}
        action={<Button size="sm" variant="soft" onClick={add} disabled={sc.tasks.length >= 6} icon={<Plus className="size-4" />}>{t('lab.add_task')}</Button>} />
      <div className="space-y-3 p-4">
        {sc.tasks.map((x: any) => (
          <div key={x.id} className="rounded-2xl border border-line p-3">
            <div className="flex items-center gap-2">
              <input value={x.name} maxLength={40} onChange={(e) => upd(x.id, { name: e.target.value || x.id })} aria-label={t('lab.task_name')} className={cx(inputCls, 'flex-1')} />
              <button onClick={() => set((s) => ({ ...s, tasks: s.tasks.filter((y: any) => y.id !== x.id), workers: s.workers.filter((w: any) => w.task !== x.id) }))}
                disabled={sc.tasks.length <= 1} aria-label={t('lab.remove')} className="grid size-10 place-items-center rounded-xl text-muted hover:bg-surface-2 disabled:opacity-30"><Trash2 className="size-4" /></button>
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <Field label={t('lab.exposure')}><select value={x.exposure} onChange={(e) => upd(x.id, { exposure: e.target.value })} className={inputCls}>
                {['sun', 'partial', 'shade', 'indoor'].map((k) => <option key={k} value={k}>{t(`lab.exp.${k}`)}</option>)}</select></Field>
              <Field label={t('lab.workload')}><select value={x.workload} onChange={(e) => upd(x.id, { workload: e.target.value })} className={inputCls}>
                {['light', 'moderate', 'heavy'].map((k) => <option key={k} value={k}>{t(`wl.${k}`)}</option>)}</select></Field>
              <Field label={t('lab.hours')}><input type="number" min={0.5} max={10} step={0.5} value={x.hours} onChange={(e) => upd(x.id, { hours: Math.max(0.5, Math.min(10, Number(e.target.value) || 0.5)) })} className={inputCls} /></Field>
              <Field label={t('lab.crew')}><input type="number" min={1} max={30} value={x.crew_size} onChange={(e) => upd(x.id, { crew_size: Math.max(1, Math.min(30, Math.round(Number(e.target.value) || 1))) })} className={inputCls} /></Field>
              <Field label={t('lab.rest_area')} className="col-span-2"><select value={x.rest_area} onChange={(e) => upd(x.id, { rest_area: e.target.value })} className={inputCls}>
                {sc.rest_areas.map((r: any) => <option key={r.id} value={r.id}>{r.name} · {t(`lab.ra.${r.type}`)}</option>)}</select></Field>
            </div>
            <button onClick={() => setOpen(open === x.id ? null : x.id)} className="mt-2 inline-flex items-center gap-1 text-xs font-bold text-brand">
              {open === x.id ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}{open === x.id ? t('lab.less') : t('lab.more')}</button>
            {open === x.id && (
              <div className="mt-2 grid grid-cols-2 gap-2">
                <Field label={t('lab.clothing')} className="col-span-2"><select value={x.clothing} onChange={(e) => upd(x.id, { clothing: e.target.value })} className={inputCls}>
                  {['work_clothes', 'coveralls', 'double_layer'].map((k) => <option key={k} value={k}>{t(`lab.cl.${k}`)}</option>)}</select></Field>
                <Field label={t('lab.window')}><select value={x.start} onChange={(e) => upd(x.id, { start: e.target.value })} className={inputCls} dir="ltr">
                  {TIMES.slice(0, 28).map((h) => <option key={h} value={h}>{h}</option>)}</select></Field>
                <Field label="–"><select value={x.end} onChange={(e) => upd(x.id, { end: e.target.value })} className={inputCls} dir="ltr">
                  {TIMES.slice(1).map((h) => <option key={h} value={h}>{h}</option>)}</select></Field>
                <Field label={t('lab.walk')}><input type="number" min={0} max={10} value={x.walk_min} onChange={(e) => upd(x.id, { walk_min: Math.max(0, Math.min(10, Number(e.target.value) || 0)) })} className={inputCls} /></Field>
                <div className="col-span-2 space-y-1.5 pt-1 text-sm">
                  <label className="flex items-center gap-2"><input type="checkbox" checked={!!x.one_piece} onChange={(e) => upd(x.id, { one_piece: e.target.checked })} className="size-4 accent-[var(--brand)]" />{t('lab.one_piece')}</label>
                  <label className="flex items-center gap-2"><input type="checkbox" checked={!!x.can_wait} onChange={(e) => upd(x.id, { can_wait: e.target.checked })} className="size-4 accent-[var(--brand)]" />{t('lab.can_wait')}</label>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  )
}

function PeopleCard({ sc, set }: { sc: Scenario; set: (f: (s: Scenario) => Scenario) => void }) {
  const { t } = useI18n()
  const upd = (id: string, p: any) => set((s) => ({ ...s, workers: s.workers.map((x: any) => (x.id === id ? { ...x, ...p } : x)) }))
  function add() {
    set((s) => {
      const n = Array.from({ length: 13 }, (_, i) => i + 1).find((k) => !s.workers.some((x: any) => x.id === `P${k}`)) ?? 99
      const task = s.tasks.find((tk: any) => s.workers.filter((w: any) => w.task === tk.id).length < tk.crew_size) ?? s.tasks[0]
      return { ...s, workers: [...s.workers, { id: `P${n}`, name: `Worker ${n}`, lang: 'en', task: task.id, status: 'acclimatized', day: 1 }] }
    })
  }
  return (
    <Card>
      <CardHeader title={t('lab.people')} sub={t('lab.people.b')} icon={<Users className="size-5" />}
        action={<Button data-tour="lab-add-person" size="sm" variant="soft" onClick={add} disabled={sc.workers.length >= 12} icon={<Plus className="size-4" />}>{t('lab.add_person')}</Button>} />
      <div className="space-y-3 p-4">
        {sc.workers.map((w: any) => (
          <div key={w.id} className="rounded-2xl border border-line p-3">
            <div className="flex items-center gap-2">
              <input value={w.name} maxLength={30} onChange={(e) => upd(w.id, { name: e.target.value || w.id })} aria-label={t('lab.name')} className={cx(inputCls, 'flex-1')} />
              <div className="w-24"><Seg value={w.lang} onChange={(v) => upd(w.id, { lang: v })} items={[{ id: 'en', label: 'EN' }, { id: 'ar', label: 'ع' }]} /></div>
              <button onClick={() => set((s) => ({ ...s, workers: s.workers.filter((y: any) => y.id !== w.id) }))} aria-label={t('lab.remove')} className="grid size-10 place-items-center rounded-xl text-muted hover:bg-surface-2"><Trash2 className="size-4" /></button>
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <Field label={t('lab.task_name')} className="col-span-2"><select value={w.task} onChange={(e) => upd(w.id, { task: e.target.value })} className={inputCls}>
                {sc.tasks.map((tk: any) => <option key={tk.id} value={tk.id}>{tk.name}</option>)}</select></Field>
              <Field label={t('lab.status')}><select value={w.status} onChange={(e) => upd(w.id, { status: e.target.value, day: e.target.value === 'acclimatized' ? 365 : Math.min(w.day ?? 1, 5) })} className={inputCls}>
                {['new', 'returning', 'acclimatized'].map((k) => <option key={k} value={k}>{t(`lab.st.${k}`)}</option>)}</select></Field>
              {w.status !== 'acclimatized'
                ? <Field label={t('lab.day')}><select value={w.day} onChange={(e) => upd(w.id, { day: Number(e.target.value) })} className={inputCls}>{[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>{d}</option>)}</select></Field>
                : <Field label={t('lab.restriction')}><select value={w.restriction ?? ''} onChange={(e) => upd(w.id, { restriction: e.target.value || null })} className={inputCls}>
                  {['', 'shaded_light_duty', 'no_heat_work'].map((k) => <option key={k} value={k}>{t(`lab.rs.${k || 'none'}`)}</option>)}</select></Field>}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
              <label className="inline-flex items-center gap-2 font-semibold"><input type="checkbox" checked={!!w.wearable} onChange={(e) => upd(w.id, { wearable: e.target.checked, share_status: e.target.checked ? w.share_status : false })} className="size-4 accent-[var(--brand)]" /><Watch className="size-4 text-brand" />{t('lab.wearable')}</label>
              {w.wearable && <label className="inline-flex items-center gap-2"><input type="checkbox" checked={!!w.share_status} onChange={(e) => upd(w.id, { share_status: e.target.checked })} className="size-4 accent-[var(--brand)]" />{t('lab.share')}</label>}
              {w.wearable && <label className="inline-flex items-center gap-2 text-xs text-muted">{t('lab.age')}<input type="number" min={16} max={75} value={w.age ?? ''} onChange={(e) => upd(w.id, { age: e.target.value ? Math.max(16, Math.min(75, Number(e.target.value))) : null })} className="h-9 w-16 rounded-lg border border-line bg-surface px-2 text-sm font-semibold text-ink" /></label>}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

function RestCard({ sc, set }: { sc: Scenario; set: (f: (s: Scenario) => Scenario) => void }) {
  const { t } = useI18n()
  const upd = (id: string, p: any) => set((s) => ({ ...s, rest_areas: s.rest_areas.map((x: any) => (x.id === id ? { ...x, ...p } : x)) }))
  return (
    <Card>
      <CardHeader title={t('lab.rest_areas')} icon={<ShieldCheck className="size-5" />} />
      <div className="space-y-3 p-4">
        {sc.rest_areas.map((r: any) => (
          <div key={r.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-2 rounded-2xl border border-line p-3">
            <input value={r.name} maxLength={40} onChange={(e) => upd(r.id, { name: e.target.value || r.id })} aria-label={t('lab.name')} className={cx(inputCls, 'col-span-2')} />
            <Seg value={r.type} onChange={(v) => upd(r.id, { type: v })} items={[{ id: 'cooled', label: t('lab.ra.cooled') }, { id: 'shade', label: t('lab.ra.shade') }]} />
            <Field label={t('lab.seats')}><input type="number" min={0} max={60} value={r.seats} onChange={(e) => upd(r.id, { seats: Math.max(0, Math.min(60, Math.round(Number(e.target.value) || 0))) })} className={cx(inputCls, 'w-20')} /></Field>
          </div>
        ))}
        <Field label={t('lab.shaded_places')}>
          <input type="number" min={0} max={20} value={sc.shaded_places} onChange={(e) => set((s) => ({ ...s, shaded_places: Math.max(0, Math.min(20, Math.round(Number(e.target.value) || 0))) }))} className={cx(inputCls, 'w-24')} />
          <p className="mt-1 text-xs font-normal text-muted">{t('lab.shaded_places.b')}</p>
        </Field>
      </div>
    </Card>
  )
}

/* ------------------------------------------------------------------ simulator controls */
function SimBar({ now, playing, busy, onPlay, onPause, onStep, onRestart, res, onEvent, onHarder, harder }: {
  now: string | null; playing: boolean; busy: boolean; onPlay: () => void; onPause: () => void; onStep: () => void; onRestart: () => void
  res: any; onEvent: (type: string, target?: string) => void; onHarder: (id: string) => void; harder: Record<string, boolean>
}) {
  const { t } = useI18n()
  const over = now != null && slotOf(now) >= 28
  const tasks: any[] = res?.world?.crews ?? []
  const rests: any[] = res?.world?.rest_areas?.filter((r: any) => r.cooled) ?? []
  const people: any[] = res?.named_workers ?? []
  const wearers = people.filter((w) => w.wearable)
  const disabled = busy || !res?.plan || over
  return (
    <Card className="border-sun/40">
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-4">
        <div className="grid size-9 place-items-center rounded-xl bg-sun-soft text-sun"><Activity className="size-5" /></div>
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold leading-tight">{t('lab.sim')}</h3>
          <p className="mt-0.5 text-sm text-muted">{t('lab.sim.b')}</p>
        </div>
        <div className="flex items-center gap-2 rounded-2xl bg-surface-2 px-3 py-1.5">
          <span className="text-[11px] font-semibold text-muted">{t('lab.sim.now')}</span>
          <span className="num text-xl font-extrabold" dir="ltr">{now ?? '05:00'}</span>
          {!now && <Badge tone="neutral">{t('lab.sim.before')}</Badge>}
          {over && <Badge tone="neutral">{t('lab.sim.end')}</Badge>}
        </div>
      </div>
      <div className="space-y-3 p-4 sm:p-5">
        <div className="flex flex-wrap gap-2">
          {playing
            ? <Button variant="sun" onClick={onPause} icon={<Pause className="size-4" />}>{t('lab.sim.pause')}</Button>
            : <Button variant="sun" onClick={onPlay} disabled={disabled} icon={<Play className="size-4" />}>{t('lab.sim.play')}</Button>}
          <Button data-tour="lab-step" variant="outline" onClick={onStep} disabled={disabled || playing} loading={busy && !playing} icon={<StepForward className="flip-rtl size-4" />}>{t('lab.sim.step')}</Button>
          <Button variant="ghost" onClick={onRestart} icon={<ListRestart className="size-4" />}>{t('lab.sim.restart')}</Button>
        </div>
        <div>
          <div className="mb-1.5 text-xs font-bold uppercase tracking-wide text-muted">{t('lab.ev')}</div>
          <div className="flex flex-wrap gap-2">
            {['hotter', 'humid', 'calm', 'cloud'].map((k) => <Button key={k} size="sm" variant="soft" disabled={disabled} onClick={() => onEvent(k)}>{t(`lab.ev.${k}`)}</Button>)}
            <Picker label={t('lab.ev.water_out')} items={tasks.map((c) => ({ id: c.id, label: c.name }))} disabled={disabled} onPick={(id) => onEvent('water_out', id)} />
            {rests.length > 0 && <Picker label={t('lab.ev.ac_fails')} items={rests.map((r) => ({ id: r.id, label: r.name }))} disabled={disabled} onPick={(id) => onEvent('ac_fails', id)} />}
            {people.length > 0 && <Picker label={t('lab.ev.symptom')} items={people.map((w) => ({ id: w.id, label: w.name }))} disabled={disabled} onPick={(id) => onEvent('symptom', id)} />}
            {wearers.length > 0 && <Picker label={t('lab.ev.harder')} items={wearers.filter((w) => !harder[w.id]).map((w) => ({ id: w.id, label: w.name }))} disabled={busy || !res?.plan} onPick={onHarder} icon={<HeartPulse className="size-3.5" />} />}
          </div>
        </div>
      </div>
    </Card>
  )
}

function Picker({ label, items, onPick, disabled, icon }: { label: string; items: { id: string; label: string }[]; onPick: (id: string) => void; disabled?: boolean; icon?: ReactNode }) {
  const { t } = useI18n()
  return (
    <label className={cx('inline-flex h-9 items-center gap-1.5 rounded-xl bg-surface-2 ps-3 text-sm font-semibold', (disabled || !items.length) && 'opacity-50')}>
      {icon}{label}
      <select value="" disabled={disabled || !items.length} onChange={(e) => { if (e.target.value) onPick(e.target.value) }}
        className="h-9 rounded-xl border-0 bg-transparent pe-2 text-sm font-semibold text-brand focus:outline-none">
        <option value="">{t('lab.ev.choose')}</option>
        {items.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
      </select>
    </label>
  )
}

/* ------------------------------------------------------------------ results */
function Summary({ res, busy }: { res: any; busy: boolean }) {
  const { t } = useI18n()
  const m = res.metrics
  const u = res.usual
  return (
    <div className={cx('space-y-3 transition-opacity', busy && 'opacity-60')}>
      {m && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label={t('lab.kpi.productive')} value={m.productive_worker_hours} sub={`${t('lab.kpi.unit')} · ${t('lab.kpi.productive.sub', { n: m.required_worker_hours })}`} tone="brand" />
          <Stat label={t('lab.kpi.rest')} value={m.rest_worker_hours} sub={`${t('lab.kpi.unit')} · ${t('lab.kpi.rest.sub', { p: m.rest_share_pct })}`} />
          <Stat label={t('lab.kpi.wait')} value={m.deferred_worker_hours} sub={t('lab.kpi.unit')} tone={m.deferred_worker_hours > 0 ? 'sun' : 'ink'} />
          <Stat label={t('lab.kpi.water')} value={t('lab.kpi.l', { n: m.water_litres })} sub={t('lab.kpi.water.sub')} />
        </div>
      )}
      <div className={cx('rounded-2xl border p-4 text-sm', u.valid ? 'border-line bg-surface' : 'border-stop/30 bg-stop-soft/50')}>
        <div className="font-bold">{t('lab.usual')}</div>
        <p className="mt-1 text-muted">{t('lab.usual.b')}</p>
        {u.valid ? <p className="mt-2 font-semibold text-ok">{t('lab.usual.ok')}</p> : (
          <ul className="mt-2 flex flex-wrap gap-2">
            {u.crew_hours_over_limit > 0 && <li><Badge tone="stop">{t('lab.usual.over', { n: u.crew_hours_over_limit })}</Badge></li>}
            {u.new_worker_hours_over_limit > 0 && <li><Badge tone="stop">{t('lab.usual.new', { n: u.new_worker_hours_over_limit })}</Badge></li>}
            {u.midday_worker_hours > 0 && <li><Badge tone="stop">{t('lab.usual.midday', { n: u.midday_worker_hours })}</Badge></li>}
            {u.withdrawal_worker_hours > 0 && <li><Badge tone="stop">{t('lab.usual.withdrawal', { n: u.withdrawal_worker_hours })}</Badge></li>}
          </ul>
        )}
      </div>
    </div>
  )
}

function NoPlan({ r, onApply }: { r: any; onApply: (key: string) => void }) {
  const { t, lang } = useI18n()
  return (
    <Card className="border-stop/40 p-5" role="alert" data-testid="lab-noplan">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 size-5 shrink-0 text-stop" />
        <div className="min-w-0 flex-1">
          <div className="font-bold text-stop">{t('lab.noplan')} · <span dir="ltr">{r.at}</span></div>
          <p className="mt-1 text-sm">{t('lab.noplan.b')}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {r.diagnosis.permitted_remedies.map((x: any) => (
              x.remedy === 'reschedule'
                ? <Badge key={x.remedy} tone="neutral" className="whitespace-normal!">{lang === 'ar' ? x.text_ar : x.text}</Badge>
                : <Button key={x.remedy} size="sm" variant="outline" onClick={() => onApply(x.remedy)}>{t('lab.apply')}: {lang === 'ar' ? x.text_ar : x.text}</Button>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted">{t('lab.never')}</p>
        </div>
      </div>
    </Card>
  )
}

function NeedsBreak({ events, named }: { events: Ev[]; named: any[] }) {
  const { t } = useI18n()
  const items = events.filter((e) => e.type === 'wearable')
  if (!items.length) return null
  return (
    <div className="mb-3 flex flex-wrap gap-2">
      {items.map((e, i) => (
        <span key={i} className="inline-flex items-center gap-2 rounded-xl border border-warn/30 bg-warn-soft px-3 py-1.5 text-sm font-semibold text-warn">
          <Watch className="size-4" /><span dir="ltr" className="num">{e.at}</span> {t('lab.sup.needs_break', { name: named.find((w) => w.id === e.target)?.name ?? e.target ?? '' })}
        </span>
      ))}
    </div>
  )
}

function Why({ res }: { res: any }) {
  const { t } = useI18n()
  const [all, setAll] = useState(false)
  const names = Object.fromEntries(res.world.crews.map((c: any) => [c.id, c.name]))
  const rows: any[] = res.why
  const shown = all ? rows : rows.filter((r) => r.rest_min > 0).slice(0, 8)
  return (
    <Card data-tour="lab-why">
      <CardHeader title={t('lab.why')} sub={t('lab.why.b')} icon={<Info className="size-5" />}
        action={rows.length > 8 ? <Button size="sm" variant="ghost" onClick={() => setAll((v) => !v)}>{all ? t('lab.less') : t('common.show_all')}</Button> : undefined} />
      <ul className="divide-y divide-line text-sm">
        {shown.map((r, i) => (
          <li key={i} className="px-5 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold">{names[r.task]} · <span dir="ltr" className="num">{r.hour}</span></span>
              <Badge tone={r.rest_min >= 30 ? 'warn' : r.rest_min > 0 ? 'cyan' : 'neutral'}>{t('lab.why.planned', { m: r.rest_min })}</Badge>
            </div>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
              <span>{t('lab.why.work')} <b className="num text-ink" dir="ltr">{r.wbgt_work} °C</b></span>
              <span>{t('lab.why.rest')} <b className="num text-ink" dir="ltr">{r.wbgt_rest} °C</b></span>
              <span>{t('lab.why.iso', { m: r.iso_rest_min })}</span>
              {r.floor_min > 0 && <span>{t('lab.why.floor', { m: r.floor_min })}</span>}
              {r.new_worker_rest_min > r.iso_rest_min && <span>{t('lab.why.new', { m: r.new_worker_rest_min })}</span>}
              {r.ac_failed && <Badge tone="stop">{t('lab.why.ac')}</Badge>}
            </div>
            <div className="mt-0.5 text-[11px] text-muted">{t('lab.why.limit', { w: r.wbgt_avg, l: r.limit, m: r.m_avg })}</div>
          </li>
        ))}
      </ul>
    </Card>
  )
}

function Log({ log }: { log: LogItem[] }) {
  const { t } = useI18n()
  return (
    <Card>
      <CardHeader title={t('lab.log')} icon={<ListRestart className="size-5" />} />
      {log.length <= 1 && <p className="px-5 py-4 text-sm text-muted">{t('lab.log.empty')}</p>}
      <ol className="divide-y divide-line text-sm">
        {log.slice().reverse().map((x, i) => (
          <li key={i} className="px-5 py-3">
            <div className="flex items-center gap-2 font-semibold"><span className="num rounded-lg bg-surface-2 px-2 py-0.5 text-xs" dir="ltr">{x.at}</span>
              <span className={cx(x.kind === 'noplan' && 'text-stop')}>{x.title}</span></div>
            {x.lines.length > 0 && <ul className="mt-1 space-y-0.5 ps-1 text-xs text-ink-2">{x.lines.map((l, j) => <li key={j}>• {l}</li>)}</ul>}
          </li>
        ))}
      </ol>
    </Card>
  )
}

function Method({ res }: { res: any }) {
  const { t } = useI18n()
  return (
    <details className="rounded-2xl border border-line bg-surface p-4 text-sm">
      <summary className="cursor-pointer font-semibold">{t('lab.method')}</summary>
      <p className="mt-2 text-muted">{t('lab.method.b')}</p>
      {res?.method && <ul className="mt-2 list-disc space-y-0.5 ps-5 text-xs text-muted">{res.method.sources.map((s: any) => <li key={s.id}>{s.text}</li>)}</ul>}
    </details>
  )
}

/* ------------------------------------------------------------------ phones */
function Phones({ res, now, wear, events }: { res: any; now: string | null; wear: Record<string, WearInfo>; events: Ev[] }) {
  const { t } = useI18n()
  const workers: any[] = res.workers ?? []
  if (!workers.length) return null
  return (
    <Card data-tour="lab-phones">
      <CardHeader title={t('lab.phones')} sub={t('lab.phones.b')} icon={<Smartphone className="size-5" />} />
      <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2 2xl:grid-cols-3">
        {workers.map((w) => <Phone key={w.id} w={w} res={res} now={now} wear={wear[w.id]} events={events} />)}
      </div>
    </Card>
  )
}

const NOW_TONE: Record<string, string> = {
  work: 'from-[#1d4ed8] to-[#0891b2]', break: 'from-[#0e7490] to-[#0891b2]', shaded: 'from-[#334155] to-[#475569]',
  stop: 'from-[#b91c1c] to-[#dc2626]', off: 'from-[#334155] to-[#475569]',
}

function Phone({ w, res, now, wear, events }: { w: any; res: any; now: string | null; wear?: WearInfo; events: Ev[] }) {
  const { t } = useI18n()
  const L = w.lang as Lang
  const dir = L === 'ar' ? 'rtl' : 'ltr'
  const p = w.plan
  const n = w.now
  const task = res.plan.tasks.find((x: any) => x.crew === w.crew)
  const zone = res.world.zones.find((z: any) => z.id === task?.zone)
  const summerSun = res.day.endsWith('08-19') && zone?.outdoor && zone?.direct_sun
  const nowSlot = now ? slotOf(now) : null
  const nextBreak = p.breaks.find((b: any) => nowSlot != null && b.from >= (now ?? '00:00'))
  let nowText = tl(L, 'ph.before')
  if (now) {
    if (n.state === 'stop' && n.code === 'water') nowText = tl(L, 'ph.now.water', { place: n.rest_area })
    else if (n.state === 'stop') nowText = tl(L, 'ph.now.symptom', { place: n.rest_area })
    else if (n.state === 'break' && n.code === 'wearable') nowText = tl(L, 'ph.now.wearable', { place: n.rest_area, until: n.until })
    else if (n.state === 'break') nowText = tl(L, 'ph.now.break', { place: n.rest_area, until: n.until })
    else if (n.state === 'work') nowText = nextBreak ? tl(L, 'ph.now.work', { next: nextBreak.from }) : tl(L, 'ph.now.work_nobreak')
    else if (n.state === 'shaded') nowText = tl(L, 'ph.now.shaded')
    else if (n.code === 'midday') nowText = tl(L, 'ph.now.midday')
    else nowText = tl(L, 'ph.now.off')
  }
  const changedAt = now && (res.changes ?? []).some((c: any) => c.task === w.crew) ? now : null
  const tone = now ? NOW_TONE[n.state] ?? NOW_TONE.off : NOW_TONE.off
  return (
    <div className="mx-auto w-full max-w-[19rem] rounded-[2.2rem] border-[6px] border-[#0b1324] bg-[#0b1324] shadow-float">
      <div className="overflow-hidden rounded-[1.7rem] bg-canvas" dir={dir} lang={L}>
        <div className="flex items-center justify-between px-4 pt-3 text-[11px] font-semibold text-muted">
          <span className="num" dir="ltr">{now ?? '05:00'}</span>
          <span className="flex items-center gap-1">{w.name} · {L === 'ar' ? 'العربية' : 'English'}</span>
        </div>
        <div className={cx('m-2 rounded-2xl bg-gradient-to-br p-3.5 text-white', tone)}>
          <div className="text-[10px] font-bold uppercase tracking-wider text-white/75">{tl(L, 'ph.now')}</div>
          <p className="mt-1 text-[15px] font-bold leading-snug">{nowText}</p>
          {changedAt && <p className="mt-1.5 text-[11px] text-white/80">{tl(L, 'ph.changed', { t: changedAt })}</p>}
        </div>
        <div className="space-y-1.5 px-3.5 pb-3 text-[12.5px] leading-snug">
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted">{tl(L, 'ph.today')}</div>
          <p className="font-semibold">{tl(L, 'ph.task', { task: p.task })}</p>
          {p.work.length ? <p dir={dir}>{tl(L, 'ph.work', { r: '' })}<span dir="ltr" className="num">{p.work.join(', ')}</span></p> : <p>{tl(L, 'ph.nowork')}</p>}
          {p.shaded.length > 0 && <p>{tl(L, 'ph.shaded', { r: '' })}<span dir="ltr" className="num">{p.shaded.join(', ')}</span></p>}
          {p.breaks.length > 0
            ? <div><p>{tl(L, 'ph.breaks', { place: p.rest_area })}</p>
              <div className="mt-1 flex flex-wrap gap-1">{p.breaks.slice(0, 8).map((b: any) => <span key={b.from} className="num rounded-md bg-cyan-soft px-1.5 py-0.5 text-[11px] font-semibold text-cyan" dir="ltr">{b.from}·{b.minutes}′</span>)}</div></div>
            : p.work.length > 0 && <p className="text-muted">{tl(L, 'ph.nobreaks')}</p>}
          {p.work.length > 0 && <p className="flex gap-1.5 text-muted"><Droplets className="mt-0.5 size-3.5 shrink-0 text-cyan" />{tl(L, 'ph.water')}</p>}
          {p.own_rest?.length > 0 && <p className="text-muted">{tl(L, 'ph.own_rest', { r: '' })}<span dir="ltr" className="num">{p.own_rest.join(', ')}</span></p>}
          {summerSun && p.work.length > 0 && <p className="text-muted">{tl(L, 'ph.midday')}</p>}
          {w.wearable && <WatchPanel L={L} wear={wear} share={w.share_status} />}
        </div>
      </div>
    </div>
  )
}

function WatchPanel({ L, wear, share }: { L: Lang; wear?: WearInfo; share: boolean }) {
  const level = wear?.level ?? 'no_reading'
  const tone = level === 'high' ? 'border-stop/40 bg-stop-soft text-stop' : level === 'rising' ? 'border-warn/40 bg-warn-soft text-warn' : 'border-line bg-surface-2 text-ink-2'
  return (
    <div className={cx('mt-2 rounded-xl border p-2.5', tone)}>
      <div className="flex items-center justify-between gap-2 text-[11px] font-bold">
        <span className="inline-flex items-center gap-1"><Watch className="size-3.5" />{tl(L, 'ph.wear.title')}</span>
        <span className="rounded-full bg-white/60 px-1.5 py-0.5 text-[10px] text-ink-2">{tl(L, 'ph.wear.private')}</span>
      </div>
      <p className="mt-1 text-[12px] font-semibold leading-snug">{tl(L, `ph.wear.${level}`)}</p>
      {wear?.hr != null && <p className="mt-0.5 text-[11px]">{tl(L, 'ph.hr')}: <span className="num font-bold" dir="ltr">{wear.hr} {tl(L, 'ph.bpm')}</span></p>}
      {level === 'high' && <p className="mt-1 text-[11px]">{share && wear?.shared ? tl(L, 'ph.wear.shared') : tl(L, 'ph.wear.not_shared')}</p>}
    </div>
  )
}
