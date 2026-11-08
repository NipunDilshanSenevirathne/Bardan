import {
  Armchair, Bell, CheckCircle2, Droplets, DropletOff, Gauge, HardHat, Lock, MapPin, Search, ShieldAlert, ShieldX,
  Siren, Thermometer, TriangleAlert, Users,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  Badge, BandChip, BAND_COLOR, Button, Card, CardHeader, Empty, ErrorNote, PageHeader, Skeleton, StatePill, Stat, cx,
} from '../../components/ui'
import { api, ApiError } from '../../lib/api'
import { fmtTime, useApi, useCan, useRole } from '../../lib/hooks'
import { pick, useI18n } from '../../lib/i18n'
import { L } from '../../lib/labels'

const STATES = ['routine', 'enhanced', 'stop', 'emergency', 'unavailable'] as const

export default function Overview() {
  const { t, lang } = useI18n()
  const q = useApi<any>('/sites/site_demo/operations', { refetch: 15000 })
  const can = useCan()
  const [zone, setZone] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<'all' | 'attention' | 'new'>('all')
  const [denied, setDenied] = useState<string | null>(null)
  const [deniedBusy, setDeniedBusy] = useState(false)
  const role = useRole()
  const qcAck = useQueryClient()
  const [ackBusy, setAckBusy] = useState<string | null>(null)
  async function acknowledge(id: string) {
    setAckBusy(id)
    try { await api(`/emergency/${id}/acknowledge`, { body: {} }); await qcAck.invalidateQueries() } catch { /* shown on retry */ } finally { setAckBusy(null) }
  }

  const d = q.data
  const workers: any[] = d?.workers ?? []
  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const w of workers) c[w.state] = (c[w.state] ?? 0) + 1
    return c
  }, [workers])
  const byZone = useMemo(() => {
    const m: Record<string, any[]> = {}
    for (const w of workers) {
      const z = w.assignment?.zone?.id
      if (z) (m[z] ??= []).push(w)
    }
    return m
  }, [workers])

  if (q.isLoading) return <div className="space-y-4"><Skeleton className="h-24" /><Skeleton className="h-96" /></div>
  if (q.error && !d) return <ErrorNote error={q.error} onRetry={() => q.refetch()} />

  const shown = workers.filter((w) => {
    if (zone && w.assignment?.zone?.id !== zone) return false
    if (filter === 'attention' && !(w.tightened || ['stop', 'emergency', 'unavailable'].includes(w.state))) return false
    if (filter === 'new' && w.acclimatization === 'acclimatized') return false
    if (query && !w.name.toLowerCase().includes(query.toLowerCase())) return false
    return true
  })
  const waterOk = d.water_points.filter((w: any) => w.status === 'available').length

  async function tryClinical() {
    setDeniedBusy(true); setDenied(null)
    try {
      await api('/clinical/patients/W07')
      setDenied('unexpected: allowed')
    } catch (e) {
      setDenied(e instanceof ApiError ? `${e.status} · ${e.detail}` : String((e as any)?.message ?? e))
    } finally { setDeniedBusy(false) }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('s.overview')}
        sub={<span>{d.site.name} · {d.site.city} · <span dir="ltr" className="num">{d.clock.slice(0, 10)} {fmtTime(d.clock)}</span></span>}
        icon={<HardHat className="size-6" />}
        actions={d.active_plan
          ? <Badge tone="brand" icon={<CheckCircle2 className="size-3.5" />}>{t('p.active')} · {d.active_plan.id}</Badge>
          : <Badge tone="warn" icon={<TriangleAlert className="size-3.5" />}>{t('w.off_shift')}</Badge>}
      />

      <div className="flex items-start gap-3 rounded-2xl border border-brand/25 bg-brand-soft p-4 text-sm">
        <Lock className="mt-0.5 size-5 shrink-0 text-brand" aria-hidden />
        <div className="flex-1"><span className="font-semibold text-brand">{t('s.no_clinical')}</span> <span className="text-ink-2">{L(d.label, lang)}</span></div>
      </div>

      {/* Stat tiles */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label={t('s.workers')} value={workers.length} icon={<Users className="size-4" />} sub={t('s.workers_sub')} />
        {STATES.slice(0, 3).map((s) => (
          <Stat key={s} label={<StatePill state={s} size="sm" />} value={counts[s] ?? 0} sub={t(`w.state_meaning.${s}`)} />
        ))}
        <Stat label={t('s.water')} value={`${waterOk}/${d.water_points.length}`} icon={<Droplets className="size-4" />} sub={t('s.water_points_ok')} tone={waterOk < d.water_points.length ? 'stop' : undefined} />
        <Stat label={t('s.emergencies')} value={d.emergencies.length} icon={<Siren className="size-4" />} sub={t('s.emergency_sub')} tone={d.emergencies.some((e: any) => !e.closed) ? 'stop' : undefined} />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
        {/* Zone map */}
        <Card className="xl:col-span-3">
          <CardHeader title={t('s.zones')} sub={t('s.map_sub')} icon={<MapPin className="size-5" />}
            action={zone ? <Button size="sm" variant="ghost" onClick={() => setZone(null)}>{t('common.all')}</Button> : undefined} />
          <div className="p-4 sm:p-5">
            <div className="relative mx-auto aspect-[16/11] w-full overflow-hidden rounded-2xl border border-line bg-[repeating-linear-gradient(45deg,var(--surface-2)_0_10px,var(--surface)_10px_20px)]" dir="ltr">
              {d.zones.map((z: any) => {
                const color = BAND_COLOR[z.band] ?? BAND_COLOR.unavailable
                const here = byZone[z.id]?.length ?? 0
                const selected = zone === z.id
                return (
                  <button key={z.id} onClick={() => setZone(selected ? null : z.id)} aria-pressed={selected}
                    aria-label={`${t('common.zone')} ${z.id}: ${pick(z, 'name', lang)}, ${t(`band.${z.band}`)}`}
                    className={cx('absolute flex flex-col justify-between rounded-xl border-2 p-2 text-start transition-all sm:p-3',
                      selected ? 'z-10 shadow-float ring-4 ring-brand/30' : 'hover:shadow-card')}
                    style={{ left: `${z.map.x}%`, top: `${z.map.y}%`, width: `${z.map.w}%`, height: `${z.map.h}%`,
                      borderColor: color, background: `color-mix(in srgb, ${color} 16%, var(--surface))` }}>
                    <div className="flex items-start justify-between gap-1" dir={lang === 'ar' ? 'rtl' : 'ltr'}>
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="grid size-6 place-items-center rounded-lg bg-ink text-xs font-bold text-surface">{z.id}</span>
                          {!z.outdoor && <Badge tone="cyan" className="hidden sm:inline-flex">{t('s.indoor')}</Badge>}
                        </div>
                        <div className="mt-1 truncate text-xs font-bold sm:text-sm">{pick(z, 'name', lang)}</div>
                      </div>
                      {z.water === 'available'
                        ? <Droplets className="size-4 shrink-0 text-cyan" aria-label={t('s.water.available')} />
                        : <span className="inline-flex items-center gap-1 rounded-full bg-stop px-1.5 py-0.5 text-[10px] font-bold text-white"><DropletOff className="size-3" />{t('s.water.reported_empty')}</span>}
                    </div>
                    <div dir={lang === 'ar' ? 'rtl' : 'ltr'}>
                      <div className="num text-base font-extrabold sm:text-xl" dir="ltr">{z.reading.value ?? '–'} <span className="text-[10px] font-semibold text-muted sm:text-xs">{z.reading.unit}</span></div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-1">
                        <BandChip band={z.band} className="!px-1.5 text-[10px] sm:!px-2.5 sm:text-xs" />
                        <span className="hidden text-[11px] text-muted sm:inline">{z.reading.age_min != null ? t('s.age', { n: z.reading.age_min }) : t('w.no_reading')}</span>
                      </div>
                      <div className="mt-1 hidden items-center gap-1 text-[11px] font-semibold text-ink-2 sm:flex"><Users className="size-3" />{here}</div>
                    </div>
                  </button>
                )
              })}
              {d.rest_areas.map((r: any) => (
                <div key={r.id} className="absolute z-20 -translate-x-1/2 -translate-y-1/2" style={{ left: `${Math.min(97, Math.max(3, r.map.x))}%`, top: `${Math.min(95, Math.max(5, r.map.y))}%` }}>
                  <span title={`${pick(r, 'name', lang)} · ${t('c.seats', { n: r.seats })}`}
                    className={cx('inline-flex items-center gap-1 rounded-full border-2 px-2 py-0.5 text-[10px] font-bold shadow-card sm:text-xs',
                      r.cooled ? 'border-cyan bg-surface text-cyan' : 'border-sun bg-surface text-sun')}>
                    <Armchair className="size-3" />{r.id}<span className="num text-muted" dir="ltr">{r.seats}</span>
                  </span>
                </div>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">
              {['unrestricted', 'acclimatization', 'buffer', 'withdrawal', 'unavailable'].map((b) => <BandChip key={b} band={b} />)}
              <span className="inline-flex items-center gap-1"><Armchair className="size-3.5 text-cyan" />{t('c.cooled')}</span>
              <span className="inline-flex items-center gap-1"><Armchair className="size-3.5 text-sun" />{t('c.shade')}</span>
            </div>
            {zone && <ZoneDetail z={d.zones.find((x: any) => x.id === zone)} canWrite={can('observation.write')} />}
          </div>
        </Card>

        {/* Right column */}
        <div className="space-y-6 xl:col-span-2">
          <Card>
            <CardHeader title={t('s.labels')} icon={<ShieldAlert className="size-5" />} sub={t('s.labels_sub')} />
            <div className="p-5">
              {d.operational_labels.length === 0 ? <Empty>{t('common.none')}</Empty> : (
                <ul className="space-y-2">
                  {d.operational_labels.map((l: any, i: number) => (
                    <li key={i} className="flex items-start gap-2 rounded-xl bg-surface-2 p-3 text-sm"><Gauge className="mt-0.5 size-4 shrink-0 text-brand" /><span>{l.text}</span></li>
                  ))}
                </ul>
              )}
              {can('ops.read') && !can('clinical.read') && (
                <div className="mt-4 rounded-2xl border border-dashed border-line p-4">
                  <div className="text-sm font-semibold">{t('s.try_clinical')}</div>
                  <p className="mt-1 text-xs text-muted">{t('s.try_clinical_b')}</p>
                  <Button className="mt-3" size="sm" variant="outline" onClick={tryClinical} loading={deniedBusy} icon={<ShieldX className="size-4 text-stop" />}>{t('s.try_clinical')}</Button>
                  {denied && (
                    <div role="status" className="mt-3 rounded-xl border border-stop/30 bg-stop-soft p-3 text-sm text-stop">
                      <div className="font-bold">{t('s.denied')}</div>
                      <div className="mt-1 break-words text-xs" dir="ltr">{denied}</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title={t('s.alerts')} icon={<Bell className="size-5" />} action={<Link to="/app/site/tasks" className="text-sm font-semibold text-brand">{t('s.tasks')}</Link>} />
            <ul className="scroll-thin max-h-80 divide-y divide-line overflow-y-auto">
              {d.notifications.length === 0 && <li className="p-5 text-sm text-muted">{t('common.none')}</li>}
              {d.notifications.slice().reverse().map((n: any) => (
                <li key={n.id} className="flex items-start gap-3 px-5 py-3 text-sm">
                  <span className={cx('mt-1 size-2 shrink-0 rounded-full', n.template === 'msg.escalation' ? 'bg-stop' : 'bg-brand')} aria-hidden />
                  <span className="min-w-0 flex-1">{n.text}</span>
                  <span className="num shrink-0 text-xs text-muted" dir="ltr">{fmtTime(n.queued_at)}</span>
                </li>
              ))}
            </ul>
          </Card>

          {d.emergencies.length > 0 && (
            <Card className="border-stop/40">
              <CardHeader title={t('s.emergencies')} icon={<Siren className="size-5" />} />
              <ul className="divide-y divide-line">
                {d.emergencies.map((e: any) => (
                  <li key={e.id} className="px-5 py-3 text-sm">
                    <div className="flex items-center justify-between gap-2"><span className="font-semibold">{t('common.zone')} {e.zone ?? '–'}</span><span className="num text-xs text-muted" dir="ltr">{fmtTime(e.at)}</span></div>
                    <div className="mt-2 flex flex-wrap gap-1">{e.states.map((s: string, i: number) => <Badge key={i} tone={s === 'help_received' || s === 'acknowledged' ? 'ok' : 'stop'}>{t(`em.state.${s}`)}</Badge>)}</div>
                    {e.acknowledged
                      ? <p className="mt-2 text-xs font-semibold text-ok">{t('s.seen_by', { role: t(`role.${e.acknowledged.role}`), t: fmtTime(e.acknowledged.at) })}</p>
                      : !e.closed && role && ['supervisor', 'hse', 'nurse', 'clinician'].includes(role) && (
                        <Button size="sm" variant="danger" className="mt-2" onClick={() => acknowledge(e.id)} loading={ackBusy === e.id} icon={<Siren className="size-4" />}>{t('s.respond')}</Button>
                      )}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>

      {/* Workers */}
      <Card>
        <CardHeader title={t('s.workers')} sub={t('s.workers_table_sub')} icon={<Users className="size-5" />} />
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-5 py-3">
          {(['all', 'attention', 'new'] as const).map((f) => (
            <button key={f} onClick={() => setFilter(f)} aria-pressed={filter === f}
              className={cx('min-h-10 rounded-xl px-3 text-sm font-semibold', filter === f ? 'bg-brand text-brand-ink' : 'bg-surface-2 text-ink-2 hover:bg-surface-3')}>
              {t(`s.filter.${f}`)}
            </button>
          ))}
          {zone && <Badge tone="brand">{t('common.zone')} {zone}</Badge>}
          <label className="relative ms-auto w-full sm:w-64">
            <span className="sr-only">{t('s.search')}</span>
            <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('s.search')}
              className="h-10 w-full rounded-xl border border-line bg-surface ps-9 pe-3 text-sm" />
          </label>
        </div>
        <div className="relative scroll-thin overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="bg-surface-2 text-xs text-muted">
              <tr>
                <th className="px-5 py-2.5 text-start font-semibold">{t('common.worker')}</th>
                <th className="px-3 py-2.5 text-start font-semibold">{t('common.crew')}</th>
                <th className="px-3 py-2.5 text-start font-semibold">{t('s.where')}</th>
                <th className="px-3 py-2.5 text-start font-semibold">{t('common.status')}</th>
                <th className="px-3 py-2.5 text-end font-semibold">{t('s.heat_time')}</th>
                <th className="px-5 py-2.5 text-start font-semibold">{t('s.notes')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {shown.map((w) => (
                <tr key={w.id} className="hover:bg-surface-2/60">
                  <td className="px-5 py-2.5"><div className="font-semibold">{w.name}</div><div className="text-xs text-muted">{w.subcontractor}</div></td>
                  <td className="px-3 py-2.5">{w.crew}</td>
                  <td className="px-3 py-2.5">
                    <div className="max-w-64 truncate">{w.assignment?.task ? pick(w.assignment.task, 'name', lang) : t(`s.kind.${w.assignment?.kind ?? 'off_shift'}`)}</div>
                    <div className="text-xs text-muted">{w.assignment?.zone ? `${t('common.zone')} ${w.assignment.zone.id}` : ''}{w.assignment?.kind && w.assignment.kind !== 'task' ? ` · ${t(`s.kind.${w.assignment.kind}`)}` : ''}{w.assignment?.on_break ? ` · ${t('s.on_break')}` : ''}</div>
                  </td>
                  <td className="px-3 py-2.5"><StatePill state={w.state} size="sm" /></td>
                  <td className="num px-3 py-2.5 text-end" dir="ltr">{w.exposure_percent}%</td>
                  <td className="px-5 py-2.5">
                    <div className="flex flex-wrap gap-1">
                      {w.acclimatization !== 'acclimatized' && <Badge tone="sun">{t(`s.accl.${w.acclimatization}`, { n: w.day })}</Badge>}
                      {w.tightened && <Badge tone="brand" icon={<Thermometer className="size-3" />}>{t('s.tightened')}</Badge>}
                    </div>
                  </td>
                </tr>
              ))}
              {shown.length === 0 && <tr><td colSpan={6} className="p-6 text-center text-muted">{t('common.none')}</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

function ZoneDetail({ z, canWrite }: { z: any; canWrite: boolean }) {
  const { t, lang } = useI18n()
  const qc = useQueryClient()
  const [kind, setKind] = useState<'twl' | 'wbgt'>('twl')
  const [value, setValue] = useState('')
  const [unit, setUnit] = useState('W/m2')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  if (!z) return null
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setMsg(null)
    try {
      const st = await api<any>('/sandbox/state')
      await api('/observations', { body: { zone: z.id, kind, value: Number(value), unit, observed_at: st.clock, provenance: 'measured', instrument: 'Manual entry' } })
      setMsg({ ok: true, text: t('s.reading_saved') })
      await qc.invalidateQueries()
    } catch (err) {
      setMsg({ ok: false, text: err instanceof ApiError ? err.detail : t('common.error') })
    } finally { setBusy(false) }
  }
  async function clear() {
    await api(`/observations/${z.id}`, { method: 'DELETE' })
    setMsg(null); await qc.invalidateQueries()
  }
  return (
    <div className="mt-4 rounded-2xl border border-line p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-bold">{t('common.zone')} {z.id} · {pick(z, 'name', lang)}</div>
        <BandChip band={z.band} />
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
        <div><dt className="text-xs text-muted">{t('w.instrument')}</dt><dd className="font-semibold">{z.reading.instrument}</dd></div>
        <div><dt className="text-xs text-muted">{t('w.reading')}</dt><dd className="num font-semibold" dir="ltr">{z.reading.value} {z.reading.unit}</dd></div>
        <div><dt className="text-xs text-muted">{t('common.source')}</dt><dd className="font-semibold">{t(`prov.${z.reading.provenance}`)} · {t('common.simulation')}</dd></div>
        <div><dt className="text-xs text-muted">{t('s.shade')}</dt><dd className="num font-semibold" dir="ltr">{Math.round(z.shade_fraction * 100)}%</dd></div>
      </dl>
      {canWrite && (
        <form onSubmit={submit} className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-[auto_1fr_auto_auto] sm:items-end">
          <label className="text-xs font-semibold">{t('s.kind_label')}
            <select value={kind} onChange={(e) => { const k = e.target.value as 'twl' | 'wbgt'; setKind(k); setUnit(k === 'twl' ? 'W/m2' : 'C') }} className="mt-1 block h-10 w-full rounded-xl border border-line bg-surface px-2 text-sm">
              <option value="twl">TWL</option><option value="wbgt">WBGT</option>
            </select>
          </label>
          <label className="text-xs font-semibold">{t('w.reading')}
            <input required inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} placeholder={kind === 'twl' ? '128' : '31.5'} className="mt-1 block h-10 w-full rounded-xl border border-line bg-surface px-3 text-sm" dir="ltr" />
          </label>
          <label className="text-xs font-semibold">{t('s.unit')}
            <select value={unit} onChange={(e) => setUnit(e.target.value)} className="mt-1 block h-10 w-full rounded-xl border border-line bg-surface px-2 text-sm" dir="ltr">
              <option value="W/m2">W/m²</option><option value="C">°C</option><option value="F">°F</option>
            </select>
          </label>
          <div className="flex gap-2">
            <Button type="submit" size="md" loading={busy}>{t('s.add_reading')}</Button>
            <Button type="button" size="md" variant="ghost" onClick={clear}>{t('s.clear_reading')}</Button>
          </div>
          <p className="text-xs text-muted sm:col-span-4">{t('s.reading_note')}</p>
          {msg && <div role="status" className={cx('rounded-xl p-3 text-sm sm:col-span-4', msg.ok ? 'bg-ok-soft text-ok' : 'bg-stop-soft text-stop')}>{msg.text}</div>}
        </form>
      )}
    </div>
  )
}
