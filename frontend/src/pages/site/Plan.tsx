import {
  ArrowDown, ArrowRight, ArrowUp, BadgeCheck, Bot, CalendarClock, CheckCircle2, ClipboardCheck, Copy, FlaskConical,
  Hammer, Info, MessageSquareText, Minus, PlayCircle, Rocket, Scale, ShieldCheck, ShieldX, Sparkles, Wand2,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ForecastPanel } from '../../components/ForecastPanel'
import { PlanTimeline } from '../../components/PlanTimeline'
import { Badge, Button, Card, CardHeader, Empty, ErrorNote, KV, PageHeader, Skeleton, Tabs, cx } from '../../components/ui'
import { api } from '../../lib/api'
import { fmtDate, fmtNum, useApi, useCan } from '../../lib/hooks'
import { pick, useI18n } from '../../lib/i18n'
import { L } from '../../lib/labels'

const METRICS: { key: string; label: string; unit: 'wh' | 'h' | 'n' }[] = [
  { key: 'heavy_harsh_worker_hours', label: 'p.metric.heavy', unit: 'wh' },
  { key: 'withdrawal_work_hours', label: 'p.metric.withdrawal', unit: 'wh' },
  { key: 'midday_violation_hours', label: 'p.metric.midday', unit: 'wh' },
  { key: 'rest_conflicts', label: 'p.metric.rest', unit: 'n' },
  { key: 'missing_rest_hours', label: 'p.metric.missing_rest', unit: 'n' },
  { key: 'unacclimatized_violations', label: 'p.metric.unaccl', unit: 'n' },
  { key: 'deferred_work_hours', label: 'p.metric.deferred', unit: 'wh' },
]

export default function Plan() {
  const { t, lang } = useI18n()
  const can = useCan()
  const qc = useQueryClient()
  const [mode, setMode] = useState<'scenario' | 'live'>('scenario')
  const st = useApi<any>('/sandbox/state')
  const fc = useApi<any>(`/sites/site_demo/forecast?mode=${mode}`, { refetch: 30000 })
  const plans = useApi<any>('/plans')
  const ops = useApi<any>('/sites/site_demo/operations')
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<unknown>(null)
  const [view, setView] = useState<'proposal' | 'draft'>('proposal')

  const list: any[] = plans.data?.plans ?? []
  const draftSum = [...list].reverse().find((p) => p.kind === 'draft')
  const propSum = [...list].reverse().find((p) => p.kind === 'optimised')
  const draft = useApi<any>(draftSum ? `/plans/${draftSum.scenario_id}` : null)
  const prop = useApi<any>(propSum ? `/plans/${propSum.scenario_id}` : null)

  const crewSize = useMemo(() => {
    const m: Record<string, number> = {}
    for (const w of ops.data?.workers ?? []) m[w.crew] = (m[w.crew] ?? 0) + 1
    return m
  }, [ops.data])
  const workers = useMemo(() => {
    const m: Record<string, any> = {}
    for (const w of ops.data?.workers ?? []) m[w.id] = w
    return m
  }, [ops.data])

  async function run(kind: string, fn: () => Promise<any>) {
    setBusy(kind); setErr(null)
    try { await fn(); await qc.invalidateQueries() } catch (e) { setErr(e) } finally { setBusy(null) }
  }
  const evaluate = () => run('evaluate', () => api('/plans/evaluate', { body: {} }).then(() => setView('draft')))
  const optimise = () => run('optimise', () => api('/plans/optimise', { body: {} }).then(() => setView('proposal')))
  const approve = (id: string) => run('approve', () => api(`/plans/${id}/approve`, { body: {} }))
  const activate = (id: string) => run('activate', () => api(`/plans/${id}/activate`, { body: {} }))

  const p = prop.data
  const dr = draft.data
  const ok = p && ['OPTIMAL', 'FEASIBLE'].includes(p.status)
  const shown = view === 'proposal' && ok ? p : dr

  return (
    <div className="space-y-6">
      <PageHeader title={t('p.title')} icon={<CalendarClock className="size-6" />}
        sub={<>{t('p.sub')} <Badge tone="sun" className="ms-1">{t('common.simulation')}</Badge></>}
        actions={<>
          {can('plan.evaluate') && <Button variant="outline" onClick={evaluate} loading={busy === 'evaluate'} icon={<ClipboardCheck className="size-4" />}>{t('p.evaluate')}</Button>}
          {can('plan.optimise') && <Button variant="sun" onClick={optimise} loading={busy === 'optimise'} icon={<Wand2 className="size-4" />}>{t('p.optimise')}</Button>}
        </>} />
      {err ? <ErrorNote error={err} /> : null}

      {fc.isLoading ? <Skeleton className="h-96" /> : fc.error ? <ErrorNote error={fc.error} onRetry={() => fc.refetch()} /> :
        <ForecastPanel fc={fc.data} mode={mode} onMode={setMode} clock={st.data?.clock} />}

      {/* Evaluate / optimise results */}
      {!dr && !p && (
        <Card className="p-6">
          <Empty icon={<Hammer className="size-6" />}>
            <div className="max-w-md">{t('p.empty')}</div>
            {can('plan.evaluate') && <Button className="mt-3" onClick={evaluate} loading={busy === 'evaluate'} icon={<ClipboardCheck className="size-4" />}>{t('p.evaluate')}</Button>}
          </Empty>
        </Card>
      )}

      {(dr || p) && (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <PlanCard title={t('p.draft')} icon={<Hammer className="size-5" />} data={dr} />
          <ProposalCard data={p} busy={busy} onApprove={approve} onActivate={activate} canApprove={can('plan.approve')} canActivate={can('plan.activate')} />
        </div>
      )}

      {dr && p && ok && <MetricsCompare draft={dr.metrics} plan={p.metrics} />}

      {p?.status === 'FORECAST_UNAVAILABLE' && (
        <Card className="border-unknown/40 p-5">
          <div className="font-bold">{p.message?.[lang] ?? t('p.unavailable')}</div>
          <p className="mt-2 text-sm text-muted">{lang === 'ar' ? p.fallback?.label_ar : p.fallback?.label_en}</p>
        </Card>
      )}
      {p && !ok && p.status !== 'FORECAST_UNAVAILABLE' && <NoPlan p={p} />}

      {shown?.plan && (
        <Card>
          <CardHeader title={t('p.timeline')} sub={t('p.timeline_sub')} icon={<CalendarClock className="size-5" />}
            action={ok && dr ? <Tabs value={view} onChange={setView} items={[{ id: 'proposal', label: t('p.proposal_short') }, { id: 'draft', label: t('p.draft_short') }]} /> : undefined} />
          <div className="p-4 sm:p-5">
            <PlanTimeline plan={shown.plan} draft={view === 'proposal' ? dr?.plan : undefined} grid={shown.grid ?? p?.grid ?? dr?.grid}
              crewSize={crewSize} restAreas={ops.data?.rest_areas ?? []} workers={workers} />
          </div>
        </Card>
      )}

      {ok && (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <Changes p={p} />
          <AgentRunCard p={p} />
        </div>
      )}
      {ok && <Messages p={p} workers={workers} />}
      {(dr || ok) && (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <WhatIf base={ok ? p.scenario_id : 'draft'} />
          {ok && <Faults id={p.scenario_id} />}
        </div>
      )}
      <FairnessWeek />
    </div>
  )
}

/* Week-level fairness by crew (T78): a table, crews only, never individual workers. */
function FairnessWeek() {
  const { t, lang } = useI18n()
  const q = useApi<any>('/sites/site_demo/fairness')
  if (q.isLoading) return <Skeleton className="h-48" />
  if (q.error) return <ErrorNote error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  const flag = d.flag
  const today = d.today_plan?.per_worker ?? null
  return (
    <Card>
      <CardHeader title={t('fair.title')} sub={t('fair.sub')} icon={<Scale className="size-5" />}
        action={flag ? <Badge tone="warn">{t('fair.flag')}</Badge> : <Badge tone="ok">{t('fair.ok')}</Badge>} />
      <div className="space-y-4 p-4 sm:p-5">
        <div className={cx('rounded-xl border p-3 text-sm leading-relaxed', flag ? 'border-warn/40 bg-warn-soft' : 'border-line bg-surface-2')} dir="auto">
          {d.message?.[lang] ?? d.message?.en}
        </div>
        <div className="relative scroll-thin overflow-x-auto rounded-xl border border-line">
          <table className="w-full min-w-[640px] text-sm">
            <caption className="sr-only">{t('fair.sub')}</caption>
            <thead className="bg-surface-2 text-xs text-muted">
              <tr>
                <th scope="col" className="px-3 py-2 text-start font-semibold">{t('fair.crew')}</th>
                {d.dates.map((x: string) => <th key={x} scope="col" className="px-2 py-2 text-end font-semibold">{fmtDate(`${x}T12:00:00+04:00`, lang)}</th>)}
                <th scope="col" className="px-3 py-2 text-end font-semibold">{t('fair.total')}</th>
                <th scope="col" className="px-3 py-2 text-start font-semibold">{t('fair.most')}</th>
                {today && <th scope="col" className="px-3 py-2 text-end font-semibold">{t('fair.today')}</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {d.crews.map((c: any) => {
                const flagged = flag?.crew === c.crew
                const top = (i: number) => c.heat_work && c.daily[i] > 0 && c.daily[i] === Math.max(...d.crews.filter((o: any) => o.heat_work).map((o: any) => o.daily[i]))
                return (
                  <tr key={c.crew} className={cx(flagged && 'bg-warn-soft/60')}>
                    <th scope="row" className="px-3 py-2 text-start font-semibold">{lang === 'ar' ? c.name_ar ?? c.name : c.name}</th>
                    {c.daily.map((v: number, i: number) => (
                      <td key={i} className={cx('num px-2 py-2 text-end', top(i) ? 'font-bold' : 'text-ink-2')}>{c.heat_work ? fmtNum(v, 1) : '–'}</td>
                    ))}
                    <td className="num px-3 py-2 text-end font-bold">{c.heat_work ? fmtNum(c.harsh_h_per_worker, 1) : '–'}</td>
                    <td className="px-3 py-2">{c.heat_work ? <span className="num">{t('fair.days', { n: c.days_most_exposed, d: d.dates.length })}</span> : <span className="text-muted">{t('fair.indoor')}</span>}</td>
                    {today && <td className="num px-3 py-2 text-end">{c.heat_work ? fmtNum(today[c.crew] ?? 0, 1) : '–'}</td>}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-muted">{t('fair.note')} · {L(d.label, lang)}</p>
      </div>
    </Card>
  )
}

function PlanCard({ title, icon, data }: { title: string; icon: React.ReactNode; data: any }) {
  const { t, lang } = useI18n()
  if (!data) return <Card className="p-6"><Empty>{t('p.no_draft_yet')}</Empty></Card>
  const rv = data.revalidation
  return (
    <Card>
      <CardHeader title={title} icon={icon} sub={<span dir="ltr" className="num">{data.scenario_id}</span>}
        action={rv && <Badge tone={rv.result === 'valid' ? 'ok' : 'stop'} icon={rv.result === 'valid' ? <ShieldCheck className="size-3.5" /> : <ShieldX className="size-3.5" />}>{rv.result === 'valid' ? t('p.valid') : t('p.invalid')}</Badge>} />
      <div className="space-y-4 p-5">
        {data.forecast_available === false && <div className="rounded-xl bg-unknown-soft p-3 text-sm font-semibold text-unknown">{t('p.unavailable')}</div>}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {METRICS.slice(0, 6).map((m) => (
            <div key={m.key} className="rounded-xl bg-surface-2 p-3">
              <div className="text-[11px] leading-tight text-muted">{t(m.label)}</div>
              <div className={cx('num mt-1 text-lg font-bold', (data.metrics?.[m.key] ?? 0) > 0 ? 'text-stop' : 'text-ink')}>{fmtNum(data.metrics?.[m.key], m.unit === 'wh' ? 0 : 0)}</div>
            </div>
          ))}
        </div>
        {rv && (
          <div className="rounded-xl border border-line p-3">
            <div className="flex items-center justify-between gap-2 text-sm"><span className="font-semibold">{t('p.revalidation')}</span><span className="num text-xs text-muted">{t('p.checks', { n: rv.checks })} · {rv.engine}</span></div>
            {rv.violation_count > 0 && (
              <ul className="scroll-thin mt-2 max-h-44 space-y-1 overflow-y-auto text-xs">
                {rv.violations.map((v: any, i: number) => <li key={i} className="flex gap-2 text-stop"><ShieldX className="mt-0.5 size-3.5 shrink-0" /><span>{violationText(v, lang)}</span></li>)}
                {rv.violation_count > rv.violations.length && <li className="text-muted">+{rv.violation_count - rv.violations.length}</li>}
              </ul>
            )}
          </div>
        )}
      </div>
    </Card>
  )
}

function ProposalCard({ data, busy, onApprove, onActivate, canApprove, canActivate }: { data: any; busy: string | null; onApprove: (id: string) => void; onActivate: (id: string) => void; canApprove: boolean; canActivate: boolean }) {
  const { t, lang } = useI18n()
  const [copied, setCopied] = useState(false)
  if (!data) return <Card className="p-6"><Empty icon={<Sparkles className="size-6 text-sun" />}>{t('p.no_proposal_yet')}</Empty></Card>
  const ok = ['OPTIMAL', 'FEASIBLE'].includes(data.status)
  const cert = data.certificate
  const approved = data.approval?.state === 'approved'
  const active = data.activation?.state === 'active'
  return (
    <Card className={cx(ok && 'border-brand/30')}>
      <CardHeader title={t('p.proposal')} icon={<Sparkles className="size-5" />} sub={<span dir="ltr" className="num">{data.scenario_id} · {data.solver?.engine} · {data.solver?.runtime_s}s</span>}
        action={ok ? <Badge tone={active ? 'brand' : approved ? 'ok' : 'neutral'} icon={active ? <Rocket className="size-3.5" /> : approved ? <CheckCircle2 className="size-3.5" /> : undefined}>{active ? t('p.active') : approved ? t('p.approved') : t('p.pending')}</Badge> : <Badge tone="stop">{data.status}</Badge>} />
      {ok && (
        <div className="space-y-4 p-5">
          {data.explanation && (
            <div className="rounded-2xl bg-brand-soft p-4 text-sm">
              <p className="leading-relaxed text-ink" dir="auto">{data.explanation.text}</p>
              <div className="mt-2 flex items-center gap-1.5 text-xs text-muted"><ShieldCheck className="size-3.5 text-ok" />{data.explanation.source === 'ai_assisted' ? t('w.source.ai') : t('w.source.template')}</div>
            </div>
          )}
          {cert && (
            <div className="rounded-2xl border border-ok/40 p-4">
              <div className="flex items-center gap-2 font-bold text-ok"><BadgeCheck className="size-5" />{t('p.certificate')}</div>
              <div className="mt-2 grid grid-cols-1 gap-x-6 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
                <KV k="ID" v={<span dir="ltr">{cert.certificate_id}</span>} />
                <KV k={t('p.revalidation')} v={`${cert.revalidation.result} · ${t('p.checks', { n: cert.revalidation.checks })}`} />
                <KV k={t('p.policy')} v={<span dir="ltr" className="text-xs">{cert.policy_versions.join(', ')}</span>} />
                <KV k={t('p.forecast_issued')} v={<span dir="ltr">{cert.forecast.issued_at.slice(0, 16).replace('T', ' ')}</span>} />
              </div>
              <div className="mt-2 flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded-lg bg-surface-2 px-2 py-1 text-[11px]" dir="ltr">sha256:{cert.sha256}</code>
                <Button size="sm" variant="ghost" icon={<Copy className="size-3.5" />} onClick={() => { void navigator.clipboard?.writeText(cert.sha256); setCopied(true); setTimeout(() => setCopied(false), 1500) }}>{copied ? t('common.copied') : t('common.copy')}</Button>
              </div>
              <p className="mt-2 text-xs text-muted">{lang === 'ar' ? t('p.cert_statement') : cert.statement}</p>
            </div>
          )}
          {data.stages && (
            <div>
              <div className="mb-1 text-xs font-semibold text-muted">{t('p.stages')}</div>
              <ol className="flex flex-wrap gap-1.5 text-xs">
                {data.stages.map((s: any, i: number) => <li key={s.objective} className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2.5 py-1"><span className="num font-bold">{i + 1}</span>{t(`obj.${s.objective}`)}</li>)}
              </ol>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {canApprove && <Button onClick={() => onApprove(data.scenario_id)} disabled={approved} loading={busy === 'approve'} icon={<CheckCircle2 className="size-4" />}>{approved ? t('p.approved') : t('p.approve')}</Button>}
            {canActivate && <Button variant="sun" onClick={() => onActivate(data.scenario_id)} disabled={!approved || active} loading={busy === 'activate'} icon={<PlayCircle className="size-4" />}>{active ? t('p.active') : t('p.activate')}</Button>}
          </div>
          {data.activation?.state === 'rejected' && <div className="rounded-xl bg-stop-soft p-3 text-sm text-stop">{t('p.basis_changed', { c: (data.activation.changed ?? []).join(', ') })}</div>}
          <p className="text-xs text-muted">{t('p.approve_note')}</p>
        </div>
      )}
    </Card>
  )
}

function MetricsCompare({ draft, plan }: { draft: any; plan: any }) {
  const { t } = useI18n()
  return (
    <Card>
      <CardHeader title={t('p.compare')} sub={t('p.compare_sub')} icon={<ArrowRight className="flip-rtl size-5" />} />
      <div className="relative scroll-thin overflow-x-auto">
        <table className="w-full min-w-[520px] text-sm">
          <thead className="bg-surface-2 text-xs text-muted"><tr>
            <th className="px-5 py-2.5 text-start font-semibold">{t('p.metric')}</th>
            <th className="px-3 py-2.5 text-end font-semibold">{t('p.draft_short')}</th>
            <th className="px-3 py-2.5 text-end font-semibold">{t('p.proposal_short')}</th>
            <th className="px-5 py-2.5 text-end font-semibold">{t('p.change')}</th></tr></thead>
          <tbody className="divide-y divide-line">
            {METRICS.map((m) => {
              const a = draft?.[m.key] ?? 0, b = plan?.[m.key] ?? 0
              const d = b - a
              return (
                <tr key={m.key}>
                  <td className="px-5 py-2.5">{t(m.label)}{m.unit === 'wh' && <span className="text-xs text-muted"> · {t('p.worker_hours')}</span>}</td>
                  <td className="num px-3 py-2.5 text-end" dir="ltr">{fmtNum(a)}</td>
                  <td className="num px-3 py-2.5 text-end font-bold" dir="ltr">{fmtNum(b)}</td>
                  <td className="px-5 py-2.5 text-end">
                    <span className={cx('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-bold', d < 0 ? 'bg-ok-soft text-ok' : d > 0 ? 'bg-stop-soft text-stop' : 'bg-surface-2 text-muted')}>
                      {d < 0 ? <ArrowDown className="size-3" /> : d > 0 ? <ArrowUp className="size-3" /> : <Minus className="size-3" />}
                      <span className="num" dir="ltr">{d === 0 ? '0' : `${d > 0 ? '+' : ''}${fmtNum(d)}`}</span>
                      <span className="sr-only">{d < 0 ? t('p.better') : d > 0 ? t('p.worse') : t('p.same')}</span>
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function Changes({ p }: { p: any }) {
  const { t, lang } = useI18n()
  return (
    <Card>
      <CardHeader title={t('p.changes')} icon={<ArrowRight className="flip-rtl size-5" />} />
      <ul className="divide-y divide-line">
        {(p.changes ?? []).length === 0 && <li className="p-5 text-sm text-muted">{t('common.none')}</li>}
        {(p.changes ?? []).map((c: any) => (
          <li key={c.task} className="px-5 py-3.5">
            <div className="font-semibold">{pick(c, 'name', lang)}</div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
              <span className="num rounded-lg bg-stop-soft px-2 py-0.5 text-stop line-through decoration-1" dir="ltr">{c.from}</span>
              <ArrowRight className="flip-rtl size-4 text-muted" />
              <span className="num rounded-lg bg-ok-soft px-2 py-0.5 font-bold text-ok" dir="ltr">{c.to}</span>
            </div>
            <p className="mt-1 text-xs text-muted">{lang === 'ar' ? c.reason_ar ?? c.reason : c.reason}</p>
          </li>
        ))}
      </ul>
    </Card>
  )
}

function AgentRunCard({ p }: { p: any }) {
  const { t } = useI18n()
  const run = p.agent_run
  return (
    <Card>
      <CardHeader title={t('p.explain')} sub={t('p.agent_sub')} icon={<Bot className="size-5" />} />
      <div className="p-5">
        {!run ? <p className="text-sm text-muted">{t('p.agent_none')}</p> : (
          <>
            <ol className="space-y-2">
              {run.steps.map((s: any, i: number) => (
                <li key={i} className="flex items-center gap-3 text-sm">
                  <span className="num grid size-6 shrink-0 place-items-center rounded-full bg-surface-2 text-xs font-bold">{i + 1}</span>
                  <code className="flex-1 text-xs" dir="ltr">{s.tool}</code>
                  <Badge tone="neutral">{s.access}</Badge>
                  <Badge tone={s.decision === 'allowed' ? 'ok' : 'stop'}>{t(`common.${s.decision}`)}</Badge>
                  <span className="num w-14 text-end text-xs text-muted" dir="ltr">{s.ms} ms</span>
                </li>
              ))}
            </ol>
            <div className="mt-3 grid grid-cols-1 gap-x-6 text-xs sm:grid-cols-2">
              <KV k={t('p.budget')} v={<span dir="ltr">{run.budgets.max_steps} steps · {run.budgets.max_wall_s}s</span>} />
              <KV k={t('p.signature')} v={<span dir="ltr" className="text-[11px]">{run.signature.slice(0, 12)}…</span>} />
            </div>
            <p className="mt-2 flex items-start gap-1.5 text-xs text-muted"><Info className="mt-0.5 size-3.5 shrink-0" />{t('p.agent_cannot')}</p>
          </>
        )}
      </div>
    </Card>
  )
}

function Messages({ p, workers }: { p: any; workers: Record<string, any> }) {
  const { t } = useI18n()
  const [all, setAll] = useState(false)
  const msgs: any[] = p.worker_messages ?? []
  const shown = all ? msgs : msgs.filter((m) => ['W01', 'W07', 'W02', 'W03'].includes(m.worker)).concat(msgs.filter((m) => !['W01', 'W07', 'W02', 'W03'].includes(m.worker)).slice(0, 2))
  return (
    <Card>
      <CardHeader title={t('p.messages')} sub={t('p.messages_sub', { n: msgs.length })} icon={<MessageSquareText className="size-5" />}
        action={<Button size="sm" variant="ghost" onClick={() => setAll((v) => !v)}>{all ? t('common.hide') : t('common.show_all')}</Button>} />
      <ul className="grid grid-cols-1 gap-3 p-5 md:grid-cols-2">
        {shown.map((m) => (
          <li key={m.worker} className="rounded-2xl border border-line p-4">
            <div className="flex items-center justify-between gap-2 text-sm"><span className="font-semibold">{workers[m.worker]?.name ?? m.worker}</span><Badge tone={m.lang === 'ar' ? 'cyan' : 'brand'}>{m.lang === 'ar' ? 'العربية' : 'English'}</Badge></div>
            <p className="mt-2 text-sm leading-relaxed" dir={m.lang === 'ar' ? 'rtl' : 'ltr'} lang={m.lang}>{m.text}</p>
          </li>
        ))}
      </ul>
      <p className="px-5 pb-4 text-xs text-muted">{t('p.messages_note')}</p>
    </Card>
  )
}

function WhatIf({ base }: { base: string }) {
  const { t } = useI18n()
  const [pour, setPour] = useState('10:00')
  const [seats, setSeats] = useState(0)
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<unknown>(null)
  async function sim() {
    setBusy(true); setErr(null)
    try { setRes(await api('/plans/simulate', { body: { base, task_starts: { P1: pour }, extra_seats: seats ? { R1: seats } : {} } })) } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  const times = Array.from({ length: 19 }, (_, i) => { const m = 5 * 60 + i * 30; return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}` })
  return (
    <Card>
      <CardHeader title={t('p.whatif')} sub={t('p.whatif.b')} icon={<FlaskConical className="size-5" />} action={<Badge tone="sun">{t('common.simulation')}</Badge>} />
      <div className="space-y-4 p-5">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="text-sm font-semibold">{t('p.whatif.pour')}
            <select value={pour} onChange={(e) => setPour(e.target.value)} className="mt-1 block h-11 w-full rounded-xl border border-line bg-surface px-3" dir="ltr">
              {times.map((x) => <option key={x}>{x}</option>)}
            </select>
          </label>
          <label className="text-sm font-semibold">{t('p.whatif.seats')}
            <input type="number" min={0} max={30} value={seats} onChange={(e) => setSeats(Math.max(0, Math.min(30, Number(e.target.value) || 0)))} className="mt-1 block h-11 w-full rounded-xl border border-line bg-surface px-3" dir="ltr" />
          </label>
        </div>
        <Button onClick={sim} loading={busy} icon={<PlayCircle className="size-4" />}>{t('p.whatif.run')}</Button>
        {err ? <ErrorNote error={err} /> : null}
        {res && (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2 text-sm"><span className="font-semibold">{t('p.revalidation')}</span>
              <Badge tone={res.revalidation.result === 'valid' ? 'ok' : 'stop'}>{res.revalidation.result === 'valid' ? t('p.valid') : `${t('p.invalid')} · ${res.revalidation.violations}`}</Badge></div>
            <div className="grid grid-cols-2 gap-2">
              {METRICS.slice(0, 6).map((m) => {
                const d = res.delta?.[m.key] ?? 0
                return (
                  <div key={m.key} className="rounded-xl bg-surface-2 p-3">
                    <div className="text-[11px] text-muted">{t(m.label)}</div>
                    <div className="mt-1 flex items-baseline gap-2"><span className="num text-lg font-bold">{fmtNum(res.metrics?.[m.key])}</span>
                      <span className={cx('num text-xs font-bold', d < 0 ? 'text-ok' : d > 0 ? 'text-stop' : 'text-muted')} dir="ltr">{d === 0 ? '±0' : `${d > 0 ? '+' : ''}${fmtNum(d, 1)}`}</span></div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}

function Faults({ id }: { id: string }) {
  const { t, lang } = useI18n()
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState<string | null>(null)
  async function inject(kind: string) {
    setBusy(kind)
    try { setRes(await api(`/plans/${id}/fault-injection`, { body: { kind } })) } finally { setBusy(null) }
  }
  return (
    <Card>
      <CardHeader title={t('p.fault')} sub={t('p.fault.b')} icon={<ShieldX className="size-5" />} />
      <div className="space-y-4 p-5">
        <div className="flex flex-wrap gap-2">
          {(['midday', 'withdrawal', 'capacity', 'remove_breaks'] as const).map((k) => <Button key={k} variant="outline" size="sm" onClick={() => inject(k)} loading={busy === k}>{t(`p.fault.${k}`)}</Button>)}
        </div>
        {res && (
          <div className="rounded-2xl border border-stop/30 bg-stop-soft/60 p-4 text-sm">
            <div className="flex flex-wrap items-center gap-2 font-bold text-stop"><ShieldX className="size-4" />{res.revalidation.result === 'valid' ? t('p.valid') : t('p.invalid')} · {t('p.activation_blocked', { n: res.revalidation.violation_count })}</div>
            <ul className="mt-2 space-y-1 text-xs text-stop">{res.revalidation.violations.slice(0, 6).map((v: any, i: number) => <li key={i}>• {violationText(v, lang)}</li>)}</ul>
          </div>
        )}
      </div>
    </Card>
  )
}

/** Arabic counted noun: 3-10 take the plural, 11+ the singular (accusative). */
function arCount(n: number, one: string, few: string, many: string): string {
  const k = Math.round(n)
  return `${k} ${k >= 3 && k <= 10 ? few : k >= 11 ? many : one}`
}
const AR_STATE: Record<string, string> = { stop: 'توقف', emergency: 'طوارئ', unavailable: 'غير متاح', enhanced: 'ضوابط معززة', routine: 'عادي' }

/** Re-validation findings in plain words (EN/AR). */
export function violationText(v: any, lang: 'en' | 'ar'): string {
  const ar = lang === 'ar'
  switch (v.rule) {
    case 'forecast_unavailable': return ar ? `${v.worker} ${v.slot}: التوقعات غير متاحة` : `${v.worker} at ${v.slot}: forecast unavailable`
    case 'acclimatization_schedule': return ar ? `${v.worker}: ${arCount(v.minutes, 'دقيقة', 'دقائق', 'دقيقة')} في الحر تتجاوز المسموح (${arCount(v.allowance_min, 'دقيقة', 'دقائق', 'دقيقة')})` : `${v.worker}: ${v.minutes} min of heat work exceeds the ${Math.round(v.allowance_min)} min allowance`
    case 'required_rest_missing': return ar ? `الطاقم ${v.crew} الساعة ${v.hour}: تنقص ${arCount(v.required_min, 'دقيقة', 'دقائق', 'دقيقة')} راحة` : `Crew ${v.crew} at ${v.hour}: ${v.required_min} min of required rest missing`
    case 'rest_capacity': return ar ? `${v.rest_area} الساعة ${v.time}: ${arCount(v.demand, 'شخص', 'أشخاص', 'شخصاً')} لـ ${arCount(v.seats, 'مقعد', 'مقاعد', 'مقعداً')}` : `${v.rest_area} at ${v.time}: ${v.demand} people for ${v.seats} seats`
    default:
      if (String(v.rule).startsWith('policy_state_')) {
        const st = String(v.rule).replace('policy_state_', '')
        return ar ? `${v.worker} · ${v.task} · ${v.slot}: محرك القواعد يقول «${AR_STATE[st] ?? st}»` : `${v.worker} · ${v.task} · ${v.slot}: rule engine says ${st}`
      }
      return JSON.stringify(v)
  }
}

function NoPlan({ p }: { p: any }) {
  const { t, lang } = useI18n()
  const dg = p.diagnosis
  return (
    <Card className="border-stop/40">
      <CardHeader title={t('p.no_plan')} sub={t('p.no_plan_sub')} icon={<ShieldX className="size-5" />} />
      <div className="grid grid-cols-1 gap-4 p-5 md:grid-cols-2">
        <div>
          <div className="text-sm font-semibold">{t('p.binding')}</div>
          <div className="mt-2 flex flex-wrap gap-1.5">{(dg?.binding_constraints ?? []).map((b: string) => <Badge key={b} tone="stop">{t(`bind.${b}`)}</Badge>)}</div>
          <div className="mt-4 text-sm font-semibold">{t('p.never_relaxed')}</div>
          <div className="mt-2 flex flex-wrap gap-1.5">{(dg?.never_relaxed ?? []).map((b: string) => <Badge key={b} tone="neutral">{t(`bind.${b}`)}</Badge>)}</div>
        </div>
        <div>
          <div className="text-sm font-semibold">{t('p.remedies')}</div>
          <ul className="mt-2 space-y-1.5 text-sm">{(dg?.permitted_remedies ?? []).map((r: any) => <li key={r.remedy} className="flex gap-2"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-brand" />{lang === 'ar' ? r.text_ar ?? r.text : r.text}</li>)}</ul>
        </div>
      </div>
    </Card>
  )
}
