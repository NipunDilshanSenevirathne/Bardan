import {
  Activity, Bot, CheckCircle2, ClipboardCheck, FileBadge2, GitCompareArrows, Languages, Lock, PlayCircle,
  ScrollText, ShieldAlert, ShieldCheck, ShieldX, Swords, TestTubes, Timer, XCircle,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { DrillSummary, DrillTable } from '../../components/DrillResults'
import { useMemo, useState } from 'react'
import { Badge, Button, Card, CardHeader, Empty, ErrorNote, KV, PageHeader, Pre, Skeleton, Stat, Tabs, cx } from '../../components/ui'
import { evaluate, ENGINE_INFO } from '../../engine/engine'
import { api } from '../../lib/api'
import { fmtTime, useActorNames, useApi, usePublicApi, useRole } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'
import { L } from '../../lib/labels'

type Tab = 'trace' | 'eval' | 'redteam' | 'replay' | 'drills' | 'tests' | 'agents' | 'licences'

export default function TrustCentre() {
  const { t } = useI18n()
  const [tab, setTab] = useState<Tab>(() => { const h = location.hash.slice(1); return (h === 'alert' ? 'drills' : h as Tab) || 'trace' })
  const set = (x: Tab) => { setTab(x); history.replaceState(null, '', `#${x}`) }
  const items: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'trace', label: t('tr.trace'), icon: <Activity className="size-4" /> },
    { id: 'eval', label: t('tr.eval'), icon: <ClipboardCheck className="size-4" /> },
    { id: 'redteam', label: t('tr.redteam'), icon: <Swords className="size-4" /> },
    { id: 'replay', label: t('tr.replay'), icon: <GitCompareArrows className="size-4" /> },
    { id: 'drills', label: t('tr.alert'), icon: <Timer className="size-4" /> },
    { id: 'tests', label: t('tr.tests'), icon: <TestTubes className="size-4" /> },
    { id: 'agents', label: t('tr.agents'), icon: <Bot className="size-4" /> },
    { id: 'licences', label: t('tr.licences'), icon: <FileBadge2 className="size-4" /> },
  ]
  return (
    <div className="space-y-6">
      <PageHeader title={t('tr.title')} sub={t('tr.sub')} icon={<ShieldCheck className="size-6" />} />
      <div className="relative scroll-thin -mx-1 overflow-x-auto px-1 pb-1"><Tabs value={tab} onChange={set} items={items} className="flex-nowrap" /></div>
      {tab === 'trace' && <Trace />}
      {tab === 'eval' && <Evaluation />}
      {tab === 'redteam' && <RedTeam />}
      {tab === 'replay' && <Replay />}
      {tab === 'drills' && <Drills />}
      {tab === 'tests' && <Tests />}
      {tab === 'agents' && <Agents />}
      {tab === 'licences' && <Licences />}
    </div>
  )
}

/* ------------------------------------------------------------------ trace */
function Trace() {
  const { t } = useI18n()
  const q = useApi<any>('/trace', { refetch: 10000 })
  const name = useActorNames()
  const [blockedOnly, setBlockedOnly] = useState(false)
  if (q.isLoading) return <Skeleton className="h-64" />
  if (q.error) return <ErrorNote error={q.error} onRetry={() => q.refetch()} />
  const runs: any[] = (q.data.runs ?? []).slice().reverse().filter((r: any) => !blockedOnly || r.gate?.decision === 'blocked')
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1 space-y-1 text-sm text-muted">
          <p>{t('tr.trace_note')}</p>
          <p className="flex items-start gap-1.5 font-semibold text-ink-2"><Lock className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden />{q.data.scope === 'review_deidentified' ? t('tr.scope_review') : t('tr.scope_own', { n: q.data.withheld ?? 0 })}</p>
        </div>
        <button onClick={() => setBlockedOnly((x) => !x)} aria-pressed={blockedOnly} className={cx('min-h-10 rounded-xl px-3 text-sm font-semibold', blockedOnly ? 'bg-stop text-white' : 'bg-surface-2')}>{t('tr.blocked_only')}</button>
      </div>
      {runs.length === 0 ? <Empty icon={<Activity className="size-6" />}>{t('tr.no_runs')}</Empty> : runs.map((r) => (
        <Card key={r.id} className={cx(r.gate?.decision === 'blocked' && 'border-stop/40')}>
          <div className="flex flex-wrap items-center gap-2 border-b border-line px-5 py-3">
            <Badge tone="brand">{t(`cap.${r.capability}`)}</Badge>
            <code className="text-xs text-muted" dir="ltr">{r.id}</code>
            <span className="text-xs text-muted">{r.subject ? (r.subject === 'worker' ? t('tr.subject.worker') : t(`role.${r.subject}`)) : name(r.actor)} · {r.lang === 'ar' ? 'العربية' : 'English'} · <span dir="ltr">{fmtTime(r.at)}</span>{r.latency_ms != null && <> · <span dir="ltr">{r.latency_ms} ms</span></>}</span>
            <span className="ms-auto"><GateBadge d={r.gate?.decision} /></span>
          </div>
          <div className="grid grid-cols-1 gap-4 p-5 lg:grid-cols-2">
            <div className="space-y-2 text-sm">
              {r.question && <KV k={t('tr.input')} v={<span dir="auto">{r.question}</span>} />}
              {r.worker_words === 'withheld' && <KV k={t('tr.input')} v={<span className="text-muted">{t('tr.words_withheld')}</span>} />}
              {r.clinical_content === 'withheld' && <KV k={t('tr.shown')} v={<span className="text-muted">{t('tr.clinical_withheld')}</span>} />}
              {r.candidates_count != null && <KV k={t('tr.method')} v={<span className="text-muted">{t('tr.candidates_count', { n: r.candidates_count })}</span>} />}
              {r.input_ref && <KV k={t('tr.input')} v={<code dir="ltr">{r.input_ref}</code>} />}
              <KV k={t('tr.method')} v={methodText(r, t)} />
              <KV k={t('tr.prompt')} v={<code dir="ltr">{r.prompt_version}</code>} />
              {r.output_source && <KV k={t('tr.shown')} v={r.output_source === 'approved_template' ? t('a.approved') : r.output_source === 'ai_assisted' ? t('a.ai') : r.output_source} />}
              {(r.fallback || r.ai_unavailable) && <div className="rounded-xl bg-unknown-soft p-2 text-xs text-ink-2">{t('tr.ai_unavailable')}</div>}
              {r.steps && <ol className="space-y-1 text-xs">{r.steps.map((s: any, i: number) => <li key={i} className="flex gap-2"><span className="num font-bold text-muted">{i + 1}.</span><span dir="ltr">{s.step}{s.method ? ` · ${s.method}` : ''}{s.passages ? ` · ${s.passages.join(', ')}` : ''}{s.result ? ` · ${String(s.result).replace(/not_configured/g, 'not configured')}` : ''}</span></li>)}</ol>}
            </div>
            <div className="space-y-3">
              {r.draft && (
                <div className="rounded-2xl border-2 border-dashed border-stop/50 bg-stop-soft/40 p-3">
                  <div className="text-xs font-bold text-stop">{t('tr.draft')}{r.frozen_draft ? ` · ${t('tr.frozen')}` : ''}</div>
                  <p className="mt-1 text-sm line-through decoration-stop/60" dir="auto">{r.draft}</p>
                </div>
              )}
              {r.gate?.reasons?.length > 0 && <div className="flex flex-wrap gap-1.5">{r.gate.reasons.map((x: any, i: number) => <Badge key={i} tone="stop" className="whitespace-normal! text-start" icon={<ShieldX className="size-3 shrink-0" />}>{t(`rule.${x.rule}`)}{x.detail ? ` · ${x.detail}` : ''}</Badge>)}</div>}
              {r.gate?.checks?.length > 0 && (
                <div>
                  <div className="mb-1 text-xs font-semibold text-muted">{t('tr.checks')}</div>
                  <div className="flex flex-wrap gap-1">{r.gate.checks.map((c: any) => <span key={c.rule} className={cx('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold', c.ok ? 'bg-ok-soft text-ok' : 'bg-stop-soft text-stop')}>{c.ok ? <CheckCircle2 className="size-3" /> : <XCircle className="size-3" />}{t(`rule.${c.rule}`)}</span>)}</div>
                </div>
              )}
              {r.gate?.fallback && <div className="text-xs text-muted">{t('tr.fallback')}: <code dir="ltr">{r.gate.fallback.template_id}</code></div>}
              {r.output?.candidates && <Pre>{JSON.stringify(r.output.candidates, null, 2)}</Pre>}
            </div>
          </div>
        </Card>
      ))}
    </div>
  )
}
function methodText(r: any, t: (k: string) => string) {
  const m = r.method ?? r.steps?.find((s: any) => s.method)?.method
  return m ? t(`meth.${m}`) : '–'
}
function GateBadge({ d }: { d?: string }) {
  const { t } = useI18n()
  if (d === 'blocked') return <Badge tone="stop" icon={<ShieldX className="size-3.5" />}>{t('tr.gate')}: {t('common.blocked')}</Badge>
  if (d === 'allowed') return <Badge tone="ok" icon={<ShieldCheck className="size-3.5" />}>{t('tr.gate')}: {t('common.allowed')}</Badge>
  return <Badge tone="neutral">{t('tr.gate')}: {t('tr.not_needed')}</Badge>
}

/* ------------------------------------------------------------- evaluation */
function useEval() { return usePublicApi<any>('/reports/evaluation') }

function Evaluation() {
  const { t, lang } = useI18n()
  const q = useEval()
  const [ai, setAi] = useState<any>(null)
  const [aiErr, setAiErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  if (q.isLoading) return <div className="space-y-3"><Skeleton className="h-24" /><Skeleton className="h-64" /><p className="text-sm text-muted">{t('tr.computing')}</p></div>
  if (q.error) return <ErrorNote error={q.error} onRetry={() => q.refetch()} />
  const e = q.data
  const sp = e.speak.by_language
  const fs = e.foresee.by_zone
  async function runAi() {
    setBusy(true); setAiErr(null)
    try { setAi(await api('/reports/evaluation/ai', { body: {} })) } catch (x) { setAiErr(x) } finally { setBusy(false) }
  }
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <Badge tone="neutral">{t('tr.generated')} <span dir="ltr" className="ms-1">{e.generated_at.slice(0, 16).replace('T', ' ')} UTC</span></Badge>
        <Badge tone="neutral">{t('tr.runtime')} <span dir="ltr" className="ms-1">{e.runtime_s}s</span></Badge>
        <Badge tone={e.ai_configured ? 'cyan' : 'neutral'}>{e.ai_configured ? t('tr.ai_configured') : t('tr.ai_not_configured')}</Badge>
        <span>{t('proof.sub')}</span>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t('proof.replay')} value={`${e.conformance.passed}/${e.conformance.cases}`} tone="brand" />
        <Stat label={t('proof.gate')} value={`${e.gate.passed}/${e.gate.items}`} tone="brand" />
        <Stat label={t('proof.copilot')} value={`${e.copilot.correct_refusals}/${e.copilot.forbidden_items}`} tone="brand" />
        <Stat label={t('proof.redteam')} value={`${e.redteam.blocked}/${e.redteam.attacks_tried}`} tone="brand" />
      </div>

      <Card>
        <CardHeader title={t('tr.eval.speak')} sub={L(e.speak.label, lang)} icon={<Languages className="size-5" />} />
        <div className="relative scroll-thin overflow-x-auto p-5">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="text-xs text-muted"><tr><th className="py-1.5 text-start">{t('tr.language')}</th><th className="py-1.5 text-end">{t('tr.items')}</th><th className="py-1.5 text-end">{t('tr.critical_recall')}</th><th className="py-1.5 text-end">{t('tr.negation')}</th><th className="py-1.5 text-end">{t('tr.urgent_now')}</th><th className="py-1.5 text-end">{t('tr.false_reassurance')}</th></tr></thead>
            <tbody className="divide-y divide-line">
              {Object.entries(sp).map(([lng, m]: [string, any]) => (
                <tr key={lng}><td className="py-2 font-semibold">{lng === 'ar' ? 'العربية' : lng === 'en' ? 'English' : t('tr.mixed')}</td><td className="num py-2 text-end">{m.items}</td>
                  <td className="num py-2 text-end">{pct(m.critical_recall)}</td><td className="num py-2 text-end">{pct(m.negation_accuracy)}</td><td className="num py-2 text-end">{pct(m.urgent_immediate_rate)}</td><td className="num py-2 text-end">{m.false_reassurance}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-muted">{t('tr.targets')}: {t('tr.critical_recall')} ≥ {pct(e.speak.targets.critical_recall)} · {t('tr.negation')} ≥ {pct(e.speak.targets.negation_accuracy)} · {t('tr.false_reassurance')} = 0 · {t('tr.method')}: {t(`meth.${e.speak.method}`)}</p>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title={t('tr.eval.gate')} sub={`${e.gate.version}`} icon={<ShieldAlert className="size-5" />} />
          <div className="p-5">
            <table className="w-full text-sm">
              <thead className="text-xs text-muted"><tr><th className="py-1.5 text-start">{t('tr.language')}</th><th className="py-1.5 text-end">{t('tr.forbidden_blocked')}</th><th className="py-1.5 text-end">{t('tr.false_blocks')}</th></tr></thead>
              <tbody className="divide-y divide-line">{Object.entries(e.gate.by_language).map(([lng, m]: [string, any]) => <tr key={lng}><td className="py-2 font-semibold">{lng === 'ar' ? 'العربية' : 'English'}</td><td className="num py-2 text-end">{m.blocked}/{m.forbidden}</td><td className="num py-2 text-end">{m.false_blocks}/{m.safe}</td></tr>)}</tbody>
            </table>
          </div>
        </Card>
        <Card>
          <CardHeader title={t('tr.eval.copilot_compile')} icon={<ScrollText className="size-5" />} />
          <div className="space-y-1 p-5 text-sm">
            <KV k={t('tr.copilot_exact')} v={`${e.copilot.exact}/${e.copilot.gold_items}`} />
            <KV k={t('tr.copilot_refusals')} v={`${e.copilot.correct_refusals}/${e.copilot.forbidden_items}`} />
            <KV k={t('tr.compile_quotes')} v={pct(e.compile.quote_match_rate)} />
            <KV k={t('tr.compile_gold')} v={`${e.compile.agreement_with_gold}/${e.compile.rules}`} />
            <KV k={t('tr.compile_flags')} v={e.compile.flags_needs_human} />
            <KV k={t('tr.auto_activations')} v={e.compile.automatic_activations} />
            <p className="pt-2 text-xs text-muted">{L(e.copilot.label, lang)}</p>
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title={t('tr.eval.foresee')} sub={`${e.foresee.period} · ${L(e.foresee.label, lang)}`} icon={<Activity className="size-5" />} />
        <div className="relative scroll-thin overflow-x-auto p-5">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="text-xs text-muted"><tr><th className="py-1.5 text-start">{t('common.zone')}</th><th className="py-1.5 text-end">{t('tr.coverage')}</th><th className="py-1.5 text-end">MAE</th><th className="py-1.5 text-end">{t('tr.persistence')}</th><th className="py-1.5 text-end">{t('tr.climatology')}</th><th className="py-1.5 text-end">{t('tr.under')}</th><th className="py-1.5 text-end">{t('tr.false_alarm')}</th></tr></thead>
            <tbody className="divide-y divide-line">
              {Object.entries(fs).map(([z, m]: [string, any]) => (
                <tr key={z} className={cx(z === 'all' && 'font-bold')}><td className="py-2">{z === 'all' ? t('common.all') : z}</td><td className="num py-2 text-end">{pct(m.coverage_90)}</td><td className="num py-2 text-end">{m.mae_model}</td><td className="num py-2 text-end">{m.mae_persistence}</td><td className="num py-2 text-end">{m.mae_climatology}</td><td className="num py-2 text-end">{pct(m.underestimation_rate, 1)}</td><td className="num py-2 text-end">{pct(m.false_alarm_rate)}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-muted">{t('tr.foresee_note')} · {e.foresee.fit.method.point} · {e.foresee.fit.method.cutoff} · {e.foresee.fit.method.interval}</p>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title={t('tr.eval.plan')} sub={L(e.plan.label, lang)} icon={<ClipboardCheck className="size-5" />} />
          <div className="space-y-1 p-5 text-sm">
            <KV k={t('tr.plan_solved')} v={`${e.plan.solved}/${e.plan.site_days}`} />
            <KV k={t('tr.plan_nofeasible')} v={`${e.plan.no_feasible_protected_plan}/${e.plan.site_days}`} />
            {e.plan.solved_after_permitted_remedy != null && <KV k={t('tr.plan_remedied')} v={`${e.plan.solved_after_permitted_remedy}/${e.plan.no_feasible_protected_plan}`} />}
            <KV k={t('tr.plan_reval')} v={pct(e.plan.revalidation_pass_rate)} />
            <KV k={t('tr.plan_faults')} v={e.plan.fault_injections_rejected} />
            <KV k={t('tr.plan_runtime')} v={<span dir="ltr">{e.plan.max_runtime_s}s · 200 {t('common.workers')}: {e.plan_scale.runtime_s}s</span>} />
            <p className="pt-2 text-xs text-muted">{t('tr.plan_note')}</p>
          </div>
        </Card>
        <Card>
          <CardHeader title={t('tr.eval.ai_sample')} sub={t('tr.eval.ai_sample_sub')} icon={<PlayCircle className="size-5" />} />
          <div className="space-y-3 p-5 text-sm">
            <Button onClick={runAi} loading={busy} disabled={!e.ai_configured} icon={<PlayCircle className="size-4" />}>{t('tr.eval.ai')}</Button>
            {!e.ai_configured && <p className="text-xs text-muted">{t('tr.ai_not_configured_note')}</p>}
            {aiErr ? <ErrorNote error={aiErr} /> : null}
            {(ai ?? e.ai_sample) && <AiSample s={ai ?? e.ai_sample} />}
          </div>
        </Card>
      </div>
    </div>
  )
}
function AiSample({ s }: { s: any }) {
  const { t } = useI18n()
  const sec = (ms: number | null | undefined) => (ms == null ? '–' : `${(ms / 1000).toFixed(1)} s`)
  const langName = (l: string) => (l === 'ar' ? t('tr.live.ar') : l === 'en' ? t('tr.live.en') : l)
  return (
    <div className="space-y-3 rounded-xl border border-line p-3">
      <div className="text-xs text-muted">{t('tr.sample_size', { n: s.items_total ?? s.sample_limit })} · <span dir="ltr">{s.generated_at?.slice(0, 16).replace('T', ' ')} UTC</span>
        {s.runtime_s != null && <> · {t('tr.live.runtime')} <span className="num" dir="ltr">{s.runtime_s} s</span></>}</div>
      {s.model_share != null && (
        <div className="grid grid-cols-2 gap-2">
          <Stat label={t('tr.live.model_share')} value={pct(s.model_share)} sub={t('tr.live.model_share_sub')} />
          <Stat label={t('tr.live.latency')} value={<span dir="ltr">{sec(s.latency_ms?.median)}</span>} sub={<span>{t('tr.live.p90')} <span dir="ltr">{sec(s.latency_ms?.p90)}</span></span>} />
          <Stat label={t('tr.live.redteam')} value={`${s.redteam?.blocked}/${s.redteam?.tried}`} tone={s.redteam?.blocked === s.redteam?.tried ? 'brand' : 'stop'} sub={t('tr.live.live_drafts', { n: s.redteam?.live_drafts })} />
          <Stat label={t('tr.live.copilot')} value={`${s.copilot?.correct}/${s.copilot?.items}`} sub={t('tr.live.copilot_sub')} />
        </div>
      )}
      <table className="w-full text-sm"><tbody className="divide-y divide-line">
        {Object.entries(s.speak?.by_language ?? {}).map(([lng, m]: [string, any]) => (
          <tr key={`s-${lng}`}><td className="py-1.5">{t('tr.live.speak')} · {langName(lng)}</td><td className="num py-1.5 text-end">{t('tr.critical_recall')} {pct(m.critical_recall)}</td><td className="num py-1.5 text-end">{t('tr.negation')} {pct(m.negation_accuracy)}</td></tr>
        ))}
        {Object.entries(s.ask?.by_language ?? {}).map(([lng, m]: [string, any]) => (
          <tr key={`a-${lng}`}><td className="py-1.5">{t('tr.live.ask')} · {langName(lng)}</td><td className="num py-1.5 text-end">{t('tr.live.model_answers')} {m.model_answers}/{m.items}</td><td className="num py-1.5 text-end">{t('tr.live.gate_allowed')} {m.gate_allowed}/{m.items}</td></tr>
        ))}
      </tbody></table>
      <p className="text-xs text-muted">{t('tr.live.note')}</p>
    </div>
  )
}
const pct = (v: number | null | undefined, d = 0) => (v == null ? '–' : `${(v * 100).toFixed(d)}%`)

/* ---------------------------------------------------------------- red team */
function RedTeam() {
  const { t, lang } = useI18n()
  const q = useEval()
  const [surface, setSurface] = useState('all')
  if (q.isLoading) return <Skeleton className="h-64" />
  if (q.error) return <ErrorNote error={q.error} />
  const r = q.data.redteam
  const rows = r.rows.filter((x: any) => surface === 'all' || x.surface === surface)
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label={t('tr.attacks')} value={`${r.blocked}/${r.attacks_tried}`} sub={t('common.blocked')} tone={r.blocked === r.attacks_tried ? 'brand' : 'stop'} />
        {Object.entries(r.by_surface).map(([k, v]: [string, any]) => <Stat key={k} label={t(`surf.${k}`)} value={`${v.blocked}/${v.tried}`} />)}
      </div>
      <Card>
        <CardHeader title={t('tr.redteam')} sub={L(r.label, lang)} icon={<Swords className="size-5" />}
          action={<Tabs value={surface} onChange={setSurface} items={[{ id: 'all', label: t('common.all') }, ...Object.keys(r.by_surface).map((k) => ({ id: k, label: t(`surf.${k}`) }))]} />} />
        <div className="relative scroll-thin max-h-[520px] overflow-auto">
          <table className="w-full min-w-[680px] text-sm">
            <thead className="sticky top-0 bg-surface-2 text-xs text-muted"><tr><th className="px-4 py-2 text-start">{t('tr.surface')}</th><th className="px-3 py-2 text-start">{t('tr.kind')}</th><th className="px-3 py-2 text-start">{t('tr.attack')}</th><th className="px-4 py-2 text-start">{t('common.result')}</th></tr></thead>
            <tbody className="divide-y divide-line">
              {rows.map((x: any, i: number) => (
                <tr key={i}>
                  <td className="px-4 py-2"><Badge tone="neutral">{t(`surf.${x.surface}`)}</Badge></td>
                  <td className="px-3 py-2 text-xs">{x.kind}</td>
                  <td className="px-3 py-2" dir="auto">{x.attack}</td>
                  <td className="px-4 py-2">{x.blocked ? <Badge tone="ok" icon={<ShieldCheck className="size-3" />}>{t('common.blocked')}</Badge> : <Badge tone="stop">{t('tr.not_blocked')}</Badge>}{x.rules?.length > 0 && <div className="mt-1 text-[11px] text-muted" dir="ltr">{x.rules.join(', ')}</div>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card>
        <CardHeader title={t('tr.residual')} icon={<ShieldAlert className="size-5" />} />
        <ul className="list-disc space-y-2 p-5 ps-10 text-sm">{r.residual_risks.map((x: string) => <li key={x}>{x}</li>)}</ul>
      </Card>
    </div>
  )
}

/* ------------------------------------------------------------------ replay */
function Replay() {
  const { t } = useI18n()
  const q = usePublicApi<any>('/replay/conformance')
  const [drift, setDrift] = useState(false)
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<unknown>(null)
  const device = useMemo(() => {
    if (!q.data) return []
    return q.data.cases.map((c: any) => {
      const d = evaluate(c.input)
      let out = { id: c.id, state: d.state, band: d.band, actions: d.actions }
      // "Outdated phone pack" demonstration: buffer band wrongly starting at 120 W/m2 instead of 115.
      const v = c.input?.observation?.value
      if (drift && c.input?.observation?.kind === 'twl' && v >= 115 && v < 120 && d.band === 'buffer') {
        out = { ...out, band: 'withdrawal', state: 'stop', actions: ['ESSENTIAL_WORK_ONLY', 'NO_LONE_WORK', 'ASSURED_FLUIDS'] }
      }
      return out
    })
  }, [q.data, drift])
  async function run() {
    setBusy(true); setErr(null)
    try { setRes(await api('/replay/compare', { body: { device: drift ? 'browser-ts-engine (outdated pack demo)' : 'browser-ts-engine', results: device }, auth: false })) } catch (x) { setErr(x) } finally { setBusy(false) }
  }
  if (q.isLoading) return <Skeleton className="h-64" />
  if (q.error) return <ErrorNote error={q.error} />
  const diff = new Set((res?.differences ?? []).map((d: any) => d.id))
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title={t('tr.replay')} sub={t('tr.replay.b')} icon={<GitCompareArrows className="size-5" />} />
        <div className="space-y-4 p-5">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="rounded-2xl border border-line p-4 text-sm"><div className="text-xs font-semibold text-muted">{t('tr.device_engine')}</div><div className="mt-1 font-bold">{ENGINE_INFO.language}</div><div className="text-xs text-muted" dir="ltr">{ENGINE_INFO.packs.join(' · ')}</div></div>
            <div className="rounded-2xl border border-line p-4 text-sm"><div className="text-xs font-semibold text-muted">{t('tr.server_engine')}</div><div className="mt-1 font-bold">Python (FastAPI)</div><div className="text-xs text-muted" dir="ltr">{Object.entries(q.data.versions).map(([k, v]) => `${k}@${v}`).join(' · ')}</div></div>
          </div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={drift} onChange={(e) => { setDrift(e.target.checked); setRes(null) }} className="size-4" />{t('tr.drift')}</label>
          <Button onClick={run} loading={busy} icon={<PlayCircle className="size-4" />}>{t('tr.replay.run')}</Button>
          {err ? <ErrorNote error={err} /> : null}
          {res && (
            <div className={cx('flex items-center gap-3 rounded-2xl p-4', res.differences.length ? 'bg-stop-soft' : 'bg-ok-soft')}>
              {res.differences.length ? <ShieldX className="size-6 text-stop" /> : <ShieldCheck className="size-6 text-ok" />}
              <div><div className={cx('font-bold', res.differences.length ? 'text-stop' : 'text-ok')}>{res.differences.length ? t('tr.mismatch_verdict') : t('tr.identical')}</div>
                <div className="num text-sm" dir="ltr">{res.identical}/{res.compared}</div></div>
            </div>
          )}
        </div>
      </Card>
      <Card>
        <div className="relative scroll-thin max-h-[560px] overflow-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="sticky top-0 bg-surface-2 text-xs text-muted"><tr><th className="px-4 py-2 text-start">#</th><th className="px-3 py-2 text-start">{t('tr.case')}</th><th className="px-3 py-2 text-start">{t('tr.device')}</th><th className="px-3 py-2 text-start">{t('tr.server')}</th><th className="px-4 py-2 text-start">{t('common.result')}</th></tr></thead>
            <tbody className="divide-y divide-line">
              {q.data.cases.map((c: any, i: number) => {
                const dv = device[i]
                const bad = diff.has(c.id)
                return (
                  <tr key={c.id} className={cx(bad && 'bg-stop-soft/50')}>
                    <td className="num px-4 py-2 text-muted">{c.id}</td>
                    <td className="px-3 py-2 text-xs" dir="ltr">{c.description}</td>
                    <td className="px-3 py-2 text-xs"><code dir="ltr">{dv?.state} · {dv?.band ?? '–'}</code></td>
                    <td className="px-3 py-2 text-xs"><code dir="ltr">{c.server.state} · {c.server.band ?? '–'}</code></td>
                    <td className="px-4 py-2">{!res ? <span className="text-xs text-muted">–</span> : bad ? <Badge tone="stop">{t('tr.mismatch')}</Badge> : <Badge tone="ok">✓</Badge>}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

/* ----------------------------------------------------- drills and comparison */
function Drills() {
  const { t, lang } = useI18n()
  const role = useRole()
  const navigate = useNavigate()
  const q = useEval()
  const st = useApi<any>('/sandbox/state', { refetch: 10000 })
  const mine = useApi<any>(role === 'auditor' && st.data?.drill ? '/drills/series' : null)
  if (q.isLoading) return <Skeleton className="h-64" />
  if (q.error) return <ErrorNote error={q.error} />
  const m = q.data.mechanism
  const pub = q.data.drills ?? { series: [] }
  return (
    <div className="space-y-6">
      <Card className="p-5">
        <h2 className="text-lg font-bold">{t('dr.tab_title')}</h2>
        <p className="mt-1 text-sm text-muted">{t('dr.tab_sub')}</p>
        <div className="mt-4 rounded-2xl border border-line bg-surface-2 p-4 text-sm">
          <div className="font-semibold">{t('dr.why.title')}</div>
          <p className="mt-1 text-muted">{t('dr.why.b')}</p>
        </div>
      </Card>

      <Card>
        <CardHeader title={t('dr.mech.title')} sub={t('dr.mech.sub', { p: m.passed, n: m.total })} icon={<ShieldCheck className="size-5" />} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] table-fixed text-sm">
            <colgroup><col className="w-[22%]" /><col className="w-[24%]" /><col className="w-[40%]" /><col className="w-[14%]" /></colgroup>
            <thead className="bg-surface-2 text-xs text-muted">
              <tr><th className="px-5 py-2 text-start">{t('dr.mech.situation')}</th><th className="px-3 py-2 text-start">{t('dr.mech.alert')}</th><th className="px-3 py-2 text-start">{t('dr.mech.bardan')}</th><th className="px-5 py-2 text-start">{t('dr.mech.check')}</th></tr>
            </thead>
            <tbody className="divide-y divide-line align-top">
              {m.rows.map((r: any) => (
                <tr key={r.id}>
                  <td className="px-5 py-3 font-semibold">{t(`dr.mech.${r.id}.s`)}</td>
                  <td className="px-3 py-3 text-muted">{t(`dr.mech.${r.id}.a`)}</td>
                  <td className="px-3 py-3">{t(`dr.mech.${r.id}.b`, r.slots)}<div className="mt-1.5 break-all font-mono text-[10.5px] leading-snug text-muted" dir="ltr">{r.test}</div></td>
                  <td className="px-5 py-3">{r.passed ? <Badge tone="ok" icon={<CheckCircle2 className="size-3" />}>{t('common.pass')}</Badge> : <Badge tone="stop" icon={<XCircle className="size-3" />}>{t('common.fail')}</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="border-t border-line px-5 py-3 text-xs text-muted">{t('dr.mech.alert_note')} {L(m.label, lang)}</p>
      </Card>

      <Card>
        <CardHeader title={t('dr.obs.title')} sub={t('dr.obs.sub')} icon={<Timer className="size-5" />}
          action={role === 'auditor' ? <Button size="sm" onClick={() => navigate('/app/drill')} icon={<PlayCircle className="size-4" />}>{t('dr.open_console')}</Button> : undefined} />
        <div className="space-y-6 p-5">
          {pub.series.length === 0 && <Empty icon={<Timer className="size-6" />}>{t('dr.obs.none')}</Empty>}
          {pub.series.map((s: any) => (
            <div key={s.sha256} className="space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-bold">{s.series.label || s.series.id}</span>
                {s.integrity === 'verified'
                  ? <Badge tone="ok" icon={<ShieldCheck className="size-3" />}>{t('dr.obs.integrity_ok')}</Badge>
                  : <Badge tone="stop" icon={<ShieldX className="size-3" />}>{t('dr.obs.integrity_bad', { p: (s.problems ?? []).join(', ') })}</Badge>}
                {s.published && <span className="text-xs text-muted">{t('dr.obs.conditions')}: {s.published.conditions} · {t('dr.obs.published')} {String(s.published.at).slice(0, 10)}</span>}
              </div>
              {s.integrity === 'verified' && <><DrillTable drills={s.drills} /><DrillSummary summary={s.summary} /></>}
            </div>
          ))}
          {mine.data && (
            <div className="space-y-3 rounded-2xl border border-dashed border-line p-4">
              <div className="text-sm font-bold">{t('dr.this_sandbox')}{mine.data.label ? ` · ${mine.data.label}` : ''}</div>
              <DrillTable drills={mine.data.drills} />
              <DrillSummary summary={mine.data.summary} />
            </div>
          )}
        </div>
      </Card>

      <Card className="p-5 text-sm">
        <div className="flex items-center gap-2 font-bold"><ScrollText className="size-5" />{t('dr.protocol')}</div>
        <p className="mt-1 text-muted">{t('dr.protocol.b')}</p>
        {role !== 'auditor' && <p className="mt-2 text-xs text-muted">{t('dc.not_auditor')}</p>}
      </Card>
    </div>
  )
}

/* -------------------------------------------------------------- load test */
function LoadTest() {
  const { t } = useI18n()
  const q = usePublicApi<any>('/reports/load')
  if (!q.data?.available) return null
  const p = q.data.panel20
  const b = q.data.burst100
  const pick = (r: any) => r?.panel?.steps?.scene_jump_with_planner
  const st = p?.steady
  const worst = st ? Math.max(...Object.values(st.steps).map((x: any) => x.p95_ms)) : null
  const errors = (r: any) => r ? Object.values(r.panel.steps).reduce((n: number, x: any) => n + x.errors, 0) + Object.values(r.steady.steps).reduce((n: number, x: any) => n + x.errors, 0) : 0
  return (
    <Card>
      <CardHeader title={t('lt.title')} sub={t('lt.sub', { cpu: p?.run?.cpu_model ?? '', at: (p?.run?.at ?? '').slice(0, 10) })} icon={<Activity className="size-5" />} />
      <div className="grid grid-cols-1 gap-3 p-5 sm:grid-cols-2 xl:grid-cols-4">
        {st && <Stat label={t('lt.steady', { n: st.judges })} value={`${st.requests_per_s}/s`} sub={t('lt.steady_sub', { p95: worst ?? '–' })} />}
        {p && <Stat label={t('lt.panel', { n: p.panel.judges })} value={`${(pick(p).p95_ms / 1000).toFixed(1)} s`} sub={t('lt.panel_sub', { wall: p.panel.wall_s })} />}
        {b && <Stat label={t('lt.burst', { n: b.panel.judges })} value={`${(pick(b).p95_ms / 1000).toFixed(1)} s`} sub={t('lt.panel_sub', { wall: b.panel.wall_s })} />}
        <Stat label={t('lt.memory')} value={`${b?.memory_mb?.per_sandbox_full_tour ?? p?.memory_mb?.per_sandbox_full_tour} MB`} sub={t('lt.errors', { n: errors(p) + errors(b) })} />
      </div>
      <p className="border-t border-line px-5 py-3 text-xs text-muted">{t('lt.note')}</p>
    </Card>
  )
}

/* ------------------------------------------------------------------ tests */
function Tests() {
  const { t, lang } = useI18n()
  const q = usePublicApi<any>('/reports/tests')
  const [view, setView] = useState<'cases' | 'suites'>('cases')
  const [area, setArea] = useState('all')
  const [failOnly, setFailOnly] = useState(false)
  if (q.isLoading) return <Skeleton className="h-64" />
  if (q.error) return <ErrorNote error={q.error} />
  const d = q.data
  if (!d.available) return <Empty icon={<TestTubes className="size-6" />}>{d.note}</Empty>
  const s = d.summary
  const cases: any[] = d.t_cases ?? []
  const areas: { id: string; en: string; ar: string }[] = []
  for (const c of cases) if (!areas.some((a) => a.id === c.area)) areas.push({ id: c.area, en: c.area_en, ar: c.area_ar })
  const shownCases = cases.filter((c) => (area === 'all' || c.area === area) && (!failOnly || c.status !== 'passed'))
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label={t('tr.tests_total')} value={s.total} />
        <Stat label={t('tr.passed')} value={s.passed} tone="brand" />
        <Stat label={t('tr.failed')} value={s.failed} tone={s.failed ? 'stop' : undefined} />
        <Stat label={t('tr.skipped')} value={s.skipped} />
        <Stat label={t('tr.tcases')} value={`${d.t_cases_covered?.length ?? 0}/${d.t_cases_total ?? 0}`} sub={t('tr.tcases_sub')} />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <Tabs value={view} onChange={setView} items={[{ id: 'cases', label: t('tr.cases') }, { id: 'suites', label: t('tr.suites') }]} />
        <span dir="ltr" className="ms-1">{d.generated_at?.slice(0, 16).replace('T', ' ')} UTC · {s.duration_s}s · {d.runner}</span>
        <button onClick={() => setFailOnly((x) => !x)} aria-pressed={failOnly} className={cx('ms-auto min-h-10 rounded-xl px-3 text-sm font-semibold', failOnly ? 'bg-stop text-white' : 'bg-surface-2 text-ink')}>{t('tr.failed_only')}</button>
      </div>
      {view === 'cases' ? (
        <>
          <p className="text-sm text-muted">{t('tr.cases_note')}</p>
          <div className="flex flex-wrap gap-1.5">
            {[{ id: 'all', en: t('common.all'), ar: t('common.all') }, ...areas].map((a) => (
              <button key={a.id} onClick={() => setArea(a.id)} aria-pressed={area === a.id}
                className={cx('min-h-9 rounded-full border px-3 text-xs font-semibold', area === a.id ? 'border-brand bg-brand text-brand-ink' : 'border-line hover:border-brand')}>
                {lang === 'ar' ? a.ar : a.en}
              </button>
            ))}
          </div>
          <Card>
            <ul className="divide-y divide-line">
              {shownCases.map((c) => (
                <li key={c.id} className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 px-4 py-3 sm:grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-start sm:px-5">
                  <span className="flex items-center gap-2 pt-0.5">
                    {c.status === 'passed' ? <CheckCircle2 className="size-4 text-ok" aria-label={t('common.passed')} /> : <XCircle className="size-4 text-stop" aria-label={t('common.failed')} />}
                    <code className="text-xs font-bold" dir="ltr">{c.id}</code>
                  </span>
                  <div className="min-w-0 text-sm font-semibold" dir="auto">{lang === 'ar' ? c.case_ar : c.case_en}
                    {c.adapted_en && <div className="mt-0.5 text-xs font-normal text-muted">{t('tr.adapted')}: {lang === 'ar' ? c.adapted_ar : c.adapted_en}</div>}
                  </div>
                  <div className="col-start-2 min-w-0 text-sm text-ink-2 sm:col-start-auto" dir="auto">{lang === 'ar' ? c.expected_ar : c.expected_en}</div>
                  <span className="col-start-2 sm:col-start-auto"><Badge tone={c.status === 'passed' ? 'ok' : 'stop'}>{c.tests.length === 1 ? t('tr.tests_1') : t('tr.tests_n', { n: c.tests.length })}</Badge></span>
                </li>
              ))}
            </ul>
          </Card>
        </>
      ) : d.suites.map((su: any) => {
        const tests = su.tests.filter((x: any) => !failOnly || x.outcome !== 'passed')
        if (!tests.length) return null
        return (
          <Card key={su.name}>
            <CardHeader title={<span dir="ltr">{su.name}</span>} sub={`${su.tests.filter((x: any) => x.outcome === 'passed').length}/${su.tests.length} ${t('common.passed')}`} icon={<TestTubes className="size-5" />} />
            <ul className="divide-y divide-line">
              {tests.map((x: any) => (
                <li key={x.id} className="flex flex-wrap items-center gap-2 px-5 py-2 text-sm">
                  {x.outcome === 'passed' ? <CheckCircle2 className="size-4 text-ok" /> : x.outcome === 'skipped' ? <Badge tone="neutral">skip</Badge> : <XCircle className="size-4 text-stop" />}
                  <span className="min-w-0 flex-1 break-words" dir="ltr">{x.name}</span>
                  {(x.t_cases ?? []).map((tc: string) => <Badge key={tc} tone="brand">{tc}</Badge>)}
                </li>
              ))}
            </ul>
          </Card>
        )
      })}
      <LoadTest />
    </div>
  )
}

/* ----------------------------------------------------------------- agents */
function Agents() {
  const { t } = useI18n()
  const q = useApi<any>('/agents')
  if (q.isLoading) return <Skeleton className="h-64" />
  if (q.error) return <ErrorNote error={q.error} />
  return (
    <div className="space-y-6">
      <p className="text-sm text-muted">{t('tr.agents_note')}</p>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {q.data.manifests.map((m: any) => (
          <Card key={m.agent}>
            <CardHeader title={t(`agent.${m.agent}`)} sub={<span dir="ltr">manifest {m.manifest_version} · sig {m.signature.slice(0, 10)}…</span>} icon={<Bot className="size-5" />} action={<Badge tone="neutral">{t('tr.risk')} {m.tier}</Badge>} />
            <div className="space-y-3 p-5 text-sm">
              <div><div className="mb-1 text-xs font-semibold text-muted">{t('tr.tools')}</div><div className="flex flex-wrap gap-1">{Object.entries(m.tools).map(([k, v]) => <code key={k} className="rounded-md bg-surface-2 px-1.5 py-0.5 text-xs" dir="ltr">{k}:{String(v)}</code>)}</div></div>
              <div><div className="mb-1 text-xs font-semibold text-muted">{t('tr.forbidden')}</div><div className="flex flex-wrap gap-1">{m.forbidden.map((f: string) => <code key={f} className="rounded-md bg-stop-soft px-1.5 py-0.5 text-xs text-stop" dir="ltr">{f}</code>)}</div></div>
              <div className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
                <KV k={t('p.budget')} v={<span dir="ltr">{m.budgets.max_steps} steps · {m.budgets.max_wall_s}s</span>} />
                <KV k={t('tr.approval')} v={<span dir="ltr">{Object.entries(m.approval).map(([k, v]) => `${k}: ${v}`).join(', ')}</span>} />
              </div>
            </div>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader title={t('tr.agent_runs')} icon={<Activity className="size-5" />} />
        <ul className="divide-y divide-line">
          {q.data.runs.length === 0 && <li className="p-5 text-sm text-muted">{t('common.none')}</li>}
          {q.data.runs.slice().reverse().map((r: any) => (
            <li key={r.id} className="flex flex-wrap items-center gap-2 px-5 py-2.5 text-sm">
              <Badge tone="brand">{t(`agent.${r.agent}`)}</Badge>
              <span className="text-xs text-muted" dir="ltr">{r.steps.map((s: any) => s.tool).join(' → ')}</span>
              <span className="ms-auto flex items-center gap-2"><Badge tone={r.outcome === 'completed' ? 'ok' : 'stop'}>{t(`outcome.${r.outcome}`)}</Badge><span className="num text-xs text-muted" dir="ltr">{r.wall_ms} ms · {fmtTime(r.at)}</span></span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}

/* --------------------------------------------------------------- licences */
function Licences() {
  const { t, lang: ui } = useI18n()
  const lic = usePublicApi<any>('/reports/licences')
  const lang = usePublicApi<any>('/reports/language')
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
      <Card className="xl:col-span-2">
        <CardHeader title={t('tr.licences')} sub={t('tr.licences_sub')} icon={<FileBadge2 className="size-5" />} />
        {lic.isLoading ? <Skeleton className="m-5 h-40" /> : (
          <ul className="divide-y divide-line">
            {(lic.data?.items ?? []).map((x: any) => (
              <li key={x.name} className="flex flex-wrap items-center gap-2 px-5 py-2.5 text-sm">
                <span className="font-semibold" dir="ltr">{x.name}</span>{x.version && <span className="text-xs text-muted" dir="ltr">{x.version}</span>}
                <Badge tone="neutral">{x.licence}</Badge><span className="text-xs text-muted">{x.use}</span>
                {x.url && <a href={x.url} target="_blank" rel="noreferrer" className="ms-auto text-xs font-semibold text-brand underline" dir="ltr">{x.url.replace(/^https?:\/\//, '').slice(0, 40)}</a>}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card>
        <CardHeader title={t('tr.languages')} icon={<Languages className="size-5" />} />
        <div className="space-y-3 p-5 text-sm">
          {Object.entries(lang.data?.languages ?? {}).map(([k, v]: [string, any]) => (
            <div key={k} className="rounded-xl bg-surface-2 p-3"><div className="flex items-center justify-between"><span className="font-semibold">{v.name}</span><Badge tone="warn">{t(`langstatus.${v.status}`)}</Badge></div><p className="mt-1 text-xs text-muted">{L(v.note, ui)}</p></div>
          ))}
          <p className="text-xs text-muted">{L(lang.data?.policy, ui)}</p>
        </div>
      </Card>
    </div>
  )
}
