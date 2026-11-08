import { Armchair, Droplets, DropletOff, HeartHandshake, Snowflake, Table2, Toilet, Umbrella, Warehouse } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Badge, Card, CardHeader, Empty, ErrorNote, KV, PageHeader, Skeleton, TierChip, cx } from '../../components/ui'
import { fmtTime, useApi } from '../../lib/hooks'
import { pick, useI18n } from '../../lib/i18n'
import { quarterLabel, SLOT_COUNT, useVizColors } from '../../lib/viz'

export default function Capacity() {
  const { t, lang } = useI18n()
  const ops = useApi<any>('/sites/site_demo/operations', { refetch: 20000 })
  const plans = useApi<any>('/plans')
  const activeId = plans.data?.active
  const plan = useApi<any>(activeId ? `/plans/${activeId}` : null)

  const crewSize = useMemo(() => {
    const m: Record<string, number> = {}
    for (const w of ops.data?.workers ?? []) m[w.crew] = (m[w.crew] ?? 0) + 1
    return m
  }, [ops.data])

  if (ops.isLoading) return <Skeleton className="h-96" />
  if (ops.error) return <ErrorNote error={ops.error} onRetry={() => ops.refetch()} />
  const d = ops.data

  return (
    <div className="space-y-6">
      <PageHeader title={t('c.title')} sub={t('c.sub')} icon={<Warehouse className="size-6" />} />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {d.rest_areas.map((r: any) => <RestCard key={r.id} r={r} plan={plan.data?.plan} crewSize={crewSize} />)}
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader title={t('s.water')} icon={<Droplets className="size-5" />} />
          <ul className="divide-y divide-line">
            {d.water_points.map((w: any) => (
              <li key={w.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 text-sm">
                <div className="flex items-center gap-2 font-semibold">{w.status === 'available' ? <Droplets className="size-4 text-cyan" /> : <DropletOff className="size-4 text-stop" />}{pick(w, 'name', lang)}</div>
                <div className="flex items-center gap-2">
                  <Badge tone={w.status === 'available' ? 'ok' : 'stop'}>{t(`s.water.${w.status}`)}</Badge>
                  <span className="text-xs text-muted">{t('c.last_check')} <span dir="ltr" className="num">{fmtTime(w.last_check)}</span></span>
                  {w.last_check_tier && <TierChip tier={w.last_check_tier} />}
                </div>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <CardHeader title={t('c.responders')} icon={<HeartHandshake className="size-5" />} />
          <ul className="divide-y divide-line">
            {d.responders.map((r: any) => (
              <li key={r.id} className="flex items-center justify-between gap-2 px-5 py-3 text-sm">
                <span className="font-semibold">{responderName(r, lang)}</span>
                <span className="flex items-center gap-2">{r.on_shift ? <Badge tone="ok">{t('c.on_shift')}</Badge> : <Badge tone="stop">{t('c.off_shift')}</Badge>}<span className="text-xs text-muted">{t('c.target', { n: r.response_target_min })}</span></span>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <CardHeader title={t('c.toilets')} icon={<Toilet className="size-5" />} />
          <ul className="divide-y divide-line">
            {d.toilets.map((x: any) => (
              <li key={x.id} className="flex items-center justify-between gap-2 px-5 py-3 text-sm">
                <span className="font-semibold">{lang === 'ar' ? `دورات المياه ${x.id.slice(1)}` : x.name}</span>
                <span className="flex items-center gap-2"><span className="text-xs text-muted">{t('c.near')} {x.near.join(', ')}</span>{x.working ? <Badge tone="ok">{t('c.working')}</Badge> : <Badge tone="stop">{t('c.broken')}</Badge>}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  )
}

function responderName(r: any, lang: string) {
  if (lang !== 'ar') return r.name
  if (r.id === 'CL1') return 'ممرضة عيادة الموقع'
  return `مسعف ${r.id.slice(2)} (${r.name.split('(')[1]?.replace(')', '').replace('Zones', 'المناطق') ?? ''})`
}

function RestCard({ r, plan, crewSize }: { r: any; plan: any; crewSize: Record<string, number> }) {
  const { t, lang } = useI18n()
  const c = useVizColors()
  const [table, setTable] = useState(false)
  const data = useMemo(() => {
    const Q = SLOT_COUNT * 2
    const dem = Array(Q).fill(0)
    for (const b of plan?.breaks ?? []) {
      if (b.rest_area !== r.id) continue
      const n = (b.crews ?? [b.crew]).reduce((s: number, cr: string) => s + (crewSize[cr] ?? 0), 0)
      for (let q = b.start_q; q < b.start_q + (b.quarters ?? 1); q++) if (q < Q) dem[q] += n
    }
    return dem.map((v, q) => ({ q, time: quarterLabel(q), v }))
  }, [plan, r.id, crewSize])
  const peak = Math.max(0, ...data.map((x) => x.v))
  const used = data.filter((x) => x.v > 0)
  return (
    <Card>
      <CardHeader title={pick(r, 'name', lang)} icon={r.cooled ? <Snowflake className="size-5" /> : <Umbrella className="size-5" />}
        sub={<span>{r.cooled ? t('c.cooled') : t('c.shade')} · <span dir="ltr">{r.open}–{r.close}</span></span>}
        action={<button onClick={() => setTable((v) => !v)} aria-pressed={table} aria-label={t('common.table')} className={cx('grid size-10 place-items-center rounded-xl', table ? 'bg-brand text-brand-ink' : 'hover:bg-surface-2')}><Table2 className="size-4" /></button>} />
      <div className="p-5">
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="rounded-xl bg-surface-2 p-2"><div className="text-[11px] text-muted">{t('c.seats_label')}</div><div className="text-xl font-bold">{r.seats}</div></div>
          <div className="rounded-xl bg-surface-2 p-2"><div className="text-[11px] text-muted">{t('c.peak')}</div><div className={cx('text-xl font-bold', peak > r.seats && 'text-stop')}>{peak}</div></div>
          <div className="rounded-xl bg-surface-2 p-2"><div className="text-[11px] text-muted">{t('c.status')}</div><div className="mt-1">{r.working ? <Badge tone="ok">{t('c.working')}</Badge> : <Badge tone="stop">{t('c.broken')}</Badge>}</div></div>
        </div>
        {!plan ? <div className="mt-4"><Empty icon={<Armchair className="size-5" />}>{t('c.no_plan')}</Empty></div> : table ? (
          <div className="relative scroll-thin mt-4 max-h-56 overflow-auto rounded-xl border border-line">
            <table className="w-full text-sm"><thead className="sticky top-0 bg-surface-2 text-xs text-muted"><tr><th className="px-3 py-1.5 text-start">{t('common.time')}</th><th className="px-3 py-1.5 text-end">{t('c.people')}</th></tr></thead>
              <tbody className="divide-y divide-line">{used.length === 0 ? <tr><td colSpan={2} className="p-3 text-muted">{t('common.none')}</td></tr> : used.map((x) => <tr key={x.q}><td className="num px-3 py-1.5" dir="ltr">{x.time}</td><td className={cx('num px-3 py-1.5 text-end', x.v > r.seats && 'font-bold text-stop')} dir="ltr">{x.v}/{r.seats}</td></tr>)}</tbody></table>
          </div>
        ) : (
          <div className="mt-4 h-44" dir="ltr" role="img" aria-label={`${pick(r, 'name', lang)}: ${t('c.peak')} ${peak} / ${r.seats}`}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ top: 10, right: 6, bottom: 0, left: -24 }} barCategoryGap={1}>
                <CartesianGrid stroke={c.grid} vertical={false} />
                <XAxis dataKey="time" interval={7} tick={{ fill: c.muted, fontSize: 10 }} axisLine={{ stroke: c.line }} tickLine={false} />
                <YAxis allowDecimals={false} domain={[0, Math.max(r.seats + 4, peak + 2)]} tick={{ fill: c.muted, fontSize: 10 }} axisLine={false} tickLine={false} />
                <ReferenceLine y={r.seats} stroke={c.ink2} strokeWidth={1} label={{ value: t('c.seats', { n: r.seats }), position: 'insideTopRight', fill: c.ink2, fontSize: 10 }} />
                <Bar dataKey="v" radius={[3, 3, 0, 0]} maxBarSize={12} isAnimationActive={false}>
                  {data.map((x) => <Cell key={x.q} fill={x.v > r.seats ? c.stop : c.s1} />)}
                </Bar>
                <Tooltip cursor={{ fill: c.grid }} content={({ active, payload }: any) => active && payload?.length ? (
                  <div className="rounded-xl border border-line bg-surface px-3 py-2 text-xs shadow-float">
                    <div className="num font-semibold text-muted" dir="ltr">{payload[0].payload.time}</div>
                    <div className="num font-bold" dir="ltr">{payload[0].payload.v} / {r.seats}</div>
                  </div>) : null} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
        <div className="mt-3 text-xs text-muted">
          <KV k={t('c.near')} v={r.near.join(', ')} />
          <KV k={t('c.accessible')} v={r.accessible ? t('common.yes') : t('common.no')} />
        </div>
      </div>
    </Card>
  )
}
