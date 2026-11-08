import { BellRing, CheckCircle2, EyeOff, Radar, ShieldCheck, ShieldOff } from 'lucide-react'
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Badge, Button, Card, CardHeader, ErrorNote, KV, PageHeader, Skeleton, cx } from '../../components/ui'
import { api } from '../../lib/api'
import { useApi, useCan } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'
import { useVizColors } from '../../lib/viz'
import { L } from '../../lib/labels'

export default function Watch() {
  const { t, lang } = useI18n()
  const q = useApi<any>('/insights/signals')
  const ev = useApi<any>('/reports/evaluation')
  if (q.isLoading) return <Skeleton className="h-96" />
  if (q.error) return <ErrorNote error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  return (
    <div className="space-y-6">
      <PageHeader title={t('watch.title')} sub={t('watch.sub')} icon={<Radar className="size-6" />} />
      <div className="flex flex-wrap gap-2">
        {d.never.map((n: string) => <Badge key={n} tone="neutral" icon={<ShieldOff className="size-3" />}>{t('watch.never')}: {t(`watch.never.${n.replaceAll(' ', '_').replaceAll('-', '_')}`)}</Badge>)}
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {d.signals.map((s: any, i: number) => s.suppressed
          ? <Suppressed key={i} s={s} />
          : <SignalCard key={s.signal_id} s={s} reviewed={d.review_tasks.some((r: any) => r.signal === s.signal_id)} />)}
      </div>
      {ev.data?.watch && (
        <Card>
          <CardHeader title={t('watch.eval')} sub={L(ev.data.watch.label, lang)} icon={<ShieldCheck className="size-5" />} />
          <div className="grid grid-cols-1 gap-4 p-5 md:grid-cols-2">
            {(['supply_failure', 'gradual_x4'] as const).map((k) => {
              const r = ev.data.watch[k]
              return (
                <div key={k} className="rounded-2xl border border-line p-4">
                  <div className="flex items-center justify-between gap-2"><div className="font-semibold">{t(`watch.scn.${k}`)}</div>
                    <Badge tone={r.met_targets ? 'ok' : 'warn'}>{r.met_targets ? t('tr.met') : t('tr.not_met')}</Badge></div>
                  <KV k={t('watch.detect2d')} v={<span dir="ltr">{Math.round(r.detection_rate_2d * 100)}% ({r.detected_within_2_days}/{r.injected}) · {t('common.target')} ≥ 90%</span>} />
                  {r.ceiling_2d != null && <KV k={t('watch.ceiling')} v={<span dir="ltr">{Math.round(r.ceiling_2d * 100)}%</span>} />}
                  {r.detection_rate_7d != null && <KV k={t('watch.detect7d')} v={<span dir="ltr">{Math.round(r.detection_rate_7d * 100)}% ({r.detected_within_7_days}/{r.injected})</span>} />}
                  <KV k={t('watch.false_alerts')} v={<span dir="ltr">{r.false_alerts_per_site_month} / site-month · {t('common.target')} ≤ 1</span>} />
                  <KV k={t('watch.delay')} v={<span dir="ltr">{r.median_delay_days ?? '–'} d</span>} />
                  {r.target_note && <p className="mt-2 text-xs leading-relaxed text-muted">{t('watch.target_note', { p: Math.round(r.ceiling_2d * 100) })}</p>}
                </div>
              )
            })}
          </div>
        </Card>
      )}
    </div>
  )
}

function SignalCard({ s, reviewed }: { s: any; reviewed: boolean }) {
  const { t, lang } = useI18n()
  const can = useCan()
  const c = useVizColors()
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<unknown>(null)
  const data = s.dates.map((d: string, i: number) => ({ d, v: s.cusum_path[i] }))
  const h = s.detector.threshold_h
  async function review() {
    setBusy(true); setErr(null)
    try { await api('/insights/review-tasks', { body: { signal_id: s.signal_id } }); await qc.invalidateQueries() } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  const sub = s.scope.subcontractor.replace('Subcontractor', lang === 'ar' ? 'المقاول' : 'Subcontractor')
  return (
    <Card className={cx(s.alarm && 'border-sun/50')}>
      <CardHeader title={sub} sub={t('watch.water_gaps')} icon={s.alarm ? <BellRing className="size-5" /> : <Radar className="size-5" />}
        action={s.alarm ? <Badge tone="sun" icon={<BellRing className="size-3.5" />}>{t('watch.alarm')} · <span dir="ltr">{s.alarm_date}</span></Badge> : <Badge tone="ok" icon={<CheckCircle2 className="size-3.5" />}>{t('watch.quiet')}</Badge>} />
      <div className="space-y-3 p-5">
        <div className="h-40" dir="ltr" role="img" aria-label={`${sub}: CUSUM, ${s.alarm ? t('watch.alarm') : t('watch.quiet')}`}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
              <CartesianGrid stroke={c.grid} vertical={false} />
              <XAxis dataKey="d" tickFormatter={(v) => v.slice(5)} interval={6} tick={{ fill: c.muted, fontSize: 10 }} axisLine={{ stroke: c.line }} tickLine={false} />
              <YAxis domain={[0, (dmax: number) => Math.max(h + 1, Math.ceil(dmax))]} tick={{ fill: c.muted, fontSize: 10 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <ReferenceLine y={h} stroke={c.ink2} strokeWidth={1} label={{ value: `h = ${h}`, position: 'insideTopLeft', fill: c.ink2, fontSize: 10 }} />
              <Line dataKey="v" stroke={c.s1} strokeWidth={2} dot={false} isAnimationActive={false} />
              <Tooltip cursor={{ stroke: c.ink2, strokeWidth: 1 }} content={({ active, payload }: any) => active && payload?.length ? (
                <div className="rounded-xl border border-line bg-surface px-3 py-2 text-xs shadow-float"><div className="num text-muted" dir="ltr">{payload[0].payload.d}</div><div className="num font-bold" dir="ltr">CUSUM {Number(payload[0].payload.v).toFixed(2)}</div></div>) : null} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="rounded-xl bg-surface-2 p-2"><div className="text-[11px] text-muted">{t('watch.last3')}</div><div className="num text-lg font-bold">{s.water_gap_minutes_last_3_days}′</div></div>
          <div className="rounded-xl bg-surface-2 p-2"><div className="text-[11px] text-muted">{t('watch.usual')}</div><div className="num text-lg font-bold">{s.baseline_minutes_per_3_days}′</div></div>
          <div className="rounded-xl bg-surface-2 p-2"><div className="text-[11px] text-muted">{t('watch.events3')}</div><div className="num text-lg font-bold">{s.observed_last_3_days}</div></div>
        </div>
        {s.explanation && <p className="rounded-xl bg-sun-soft p-3 text-sm font-semibold text-ink" dir="auto">{s.explanation[lang] ?? s.explanation.en}</p>}
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
          <span dir="ltr">{s.detector.method} v{s.detector.version}</span>·<span>{t('watch.no_individuals')}</span>·<span>{t('co.suppression')}: n ≥ {s.suppression.min_cell}</span>
        </div>
        {s.alarm && can('insights.approve') && (
          <div>
            <Button onClick={review} disabled={reviewed} loading={busy} icon={<CheckCircle2 className="size-4" />}>{reviewed ? t('watch.review_created') : t('watch.approve')}</Button>
            <p className="mt-1.5 text-xs text-muted">{t('watch.approve_note')}</p>
          </div>
        )}
        {err ? <ErrorNote error={err} /> : null}
      </div>
    </Card>
  )
}

function Suppressed({ s }: { s: any }) {
  const { t, lang } = useI18n()
  return (
    <Card className="border-dashed">
      <CardHeader title={s.scope.subcontractor.replace('Subcontractor', lang === 'ar' ? 'المقاول' : 'Subcontractor')} icon={<EyeOff className="size-5" />} action={<Badge tone="unknown">{t('watch.suppressed')}</Badge>} />
      <p className="p-5 text-sm text-ink-2">{lang === 'ar' ? 'مجموعة من 3 عمال أقل من الحد الأدنى البالغ 5؛ لا يُعرض شيء (T92). وتُحجب الخلايا المكمّلة أيضاً.' : s.reason}</p>
    </Card>
  )
}
