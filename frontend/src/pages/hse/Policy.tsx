import {
  AlertTriangle, BookText, CheckCircle2, FileCode2, FileText, Lock, Quote, ScrollText, ShieldCheck, Signature, Sparkles,
  TestTube2, XCircle,
} from 'lucide-react'
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Badge, BandChip, Button, Card, CardHeader, ErrorNote, KV, PageHeader, Pre, Skeleton, TierChip, cx } from '../../components/ui'
import { api } from '../../lib/api'
import { useActorNames, useApi, useCan, useRole } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'
import { L } from '../../lib/labels'

export default function Policy() {
  const { t } = useI18n()
  const can = useCan()
  const qc = useQueryClient()
  const q = useApi<any>('/policy/packs')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<unknown>(null)
  async function compile() {
    setBusy(true); setErr(null)
    try { await api('/policy/drafts', { body: {} }); await qc.invalidateQueries() } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  if (q.isLoading) return <Skeleton className="h-96" />
  if (q.error) return <ErrorNote error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  const [heat, midday] = d.active
  const draft = d.drafts?.[d.drafts.length - 1]
  return (
    <div className="space-y-6">
      <PageHeader title={t('pol.title')} sub={t('pol.sub')} icon={<ScrollText className="size-6" />}
        actions={can('policy.compile') && <Button variant="sun" onClick={compile} loading={busy} icon={<Sparkles className="size-4" />}>{t('pol.compile')}</Button>} />
      {err ? <ErrorNote error={err} /> : null}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <HeatPack p={heat} />
        <MiddayPack p={midday} />
      </div>

      {draft ? <Draft d={draft} /> : (
        <Card className="p-6 text-sm text-muted">
          <div className="flex items-start gap-3"><Sparkles className="mt-0.5 size-5 text-sun" /><div><div className="font-semibold text-ink">{t('pol.compile')}</div><p className="mt-1">{t('pol.compile.b')}</p></div></div>
        </Card>
      )}

      <Card>
        <CardHeader title={t('pol.source')} sub={t('pol.source_sub')} icon={<FileText className="size-5" />} />
        <div className="p-5"><Pre>{d.source_document}</Pre></div>
      </Card>
    </div>
  )
}

function HeatPack({ p }: { p: any }) {
  const { t } = useI18n()
  const fmtRange = (z: any) => {
    const lo = z.min_inclusive ?? z.min_exclusive
    const hi = z.max_inclusive ?? z.max_exclusive
    if (lo == null) return `< ${hi}`
    if (hi == null) return `> ${lo}`
    return `${lo}–${hi}`
  }
  return (
    <Card>
      <CardHeader title={<span dir="ltr">{p.policy_id}@{p.version}</span>} sub={p.jurisdiction} icon={<ShieldCheck className="size-5" />}
        action={<Badge tone="sun">{t('pol.demo_only')}</Badge>} />
      <div className="space-y-4 p-5 text-sm">
        <p className="rounded-xl bg-warn-soft p-3 text-xs font-medium text-warn">{p.notice}</p>
        <div>
          <div className="mb-2 font-semibold">{t('pol.twl_zones')}</div>
          <table className="w-full text-sm">
            <thead className="text-xs text-muted"><tr><th className="py-1 text-start">{t('s.band')}</th><th className="py-1 text-start">TWL (W/m²)</th><th className="py-1 text-start">WBGT demo (°C)</th><th className="py-1 text-start">{t('pol.rest')}</th></tr></thead>
            <tbody className="divide-y divide-line">
              {p.twl_zones.map((z: any, i: number) => (
                <tr key={z.band}>
                  <td className="py-2"><BandChip band={z.band} /></td>
                  <td className="num py-2" dir="ltr">{fmtRange(z)}</td>
                  <td className="num py-2" dir="ltr">{fmtRange(p.wbgt_planning_bands_demo[i])}</td>
                  <td className="num py-2" dir="ltr">{p.rest_minutes_per_hour_demo[z.band]} min/h</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <div className="mb-2 font-semibold">{t('pol.acclimatization')}</div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <KV k={t('pol.new_workers')} v={<span dir="ltr">{p.acclimatization.new_percent_by_day.join(' / ')} %</span>} />
            <KV k={t('pol.returning')} v={<span dir="ltr">{p.acclimatization.experienced_percent_by_day.join(' / ')} %</span>} />
          </div>
        </div>
        <div>
          <div className="mb-2 font-semibold">{t('pol.deadlines')}</div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(p.task_deadlines_minutes as Record<string, number>).map(([k, v]) => (
              <span key={k} className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2.5 py-1 text-xs"><span className="font-semibold">{t(`tl.code.${k}`)}</span><span className="num text-muted" dir="ltr">{v >= 1440 ? `${v / 1440} d` : `${v} min`}</span><TierChip tier={p.evidence_required[k]} /></span>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5 text-xs">
          {Object.entries(p.permissions as Record<string, boolean>).map(([k, v]) => <Badge key={k} tone={v ? 'warn' : 'neutral'} icon={<Lock className="size-3" />}>{t(`pol.perm.${k}`)}: {v ? t('common.yes') : t('common.no')}</Badge>)}
        </div>
        <div className="text-xs text-muted">{t('pol.signature')}: <code dir="ltr">{p.signature}</code> · {p.sources.map((s: any) => `${s.authority} ${s.document} ${s.edition}`).join(' · ')}</div>
      </div>
    </Card>
  )
}

function MiddayPack({ p }: { p: any }) {
  const { t } = useI18n()
  return (
    <Card>
      <CardHeader title={<span dir="ltr">{p.policy_id}@{p.version}</span>} sub={p.jurisdiction} icon={<ShieldCheck className="size-5" />} action={<Badge tone="sun">{t('pol.demo_only')}</Badge>} />
      <div className="space-y-3 p-5 text-sm">
        <p className="rounded-xl bg-warn-soft p-3 text-xs font-medium text-warn">{p.notice}</p>
        <KV k={t('pol.window')} v={<span dir="ltr">{p.window.start}–{p.window.end} ({p.window.timezone})</span>} />
        <KV k={t('pol.season')} v={<span dir="ltr">{p.season.from} → {p.season.to}</span>} />
        <KV k={t('pol.scope')} v={p.scope} />
        <KV k={t('pol.penalty')} v={<span dir="ltr">AED {p.penalties.per_worker_aed.toLocaleString()} / worker · max {p.penalties.max_aed.toLocaleString()}</span>} />
        <KV k={t('pol.report_line')} v={<span dir="ltr">{p.report_violation.phone}</span>} />
        <div>
          <div className="mb-1.5 mt-2 font-semibold">{t('pol.exemptions')}</div>
          <div className="flex flex-wrap gap-1.5">{p.exemptions_require_authorized_record.map((e: string) => <Badge key={e} tone="neutral">{e.replaceAll('_', ' ')}</Badge>)}</div>
        </div>
      </div>
    </Card>
  )
}

function Draft({ d }: { d: any }) {
  const { t, lang } = useI18n()
  const role = useRole()
  const can = useCan()
  const name = useActorNames()
  const qc = useQueryClient()
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  async function call(kind: 'approve' | 'activate') {
    setBusy(kind); setMsg(null)
    try {
      await api(`/policy/drafts/${d.id}/${kind}`, { body: kind === 'approve' ? { note } : {} })
      setMsg({ ok: true, text: kind === 'approve' ? t('pol.approved_ok') : t('pol.activated_ok') })
      await qc.invalidateQueries()
    } catch (e: any) { setMsg({ ok: false, text: e?.detail ?? e?.message }) } finally { setBusy(null) }
  }
  const active = d.activation?.state === 'active_in_sandbox_only'
  return (
    <Card className="border-sun/40">
      <CardHeader title={<span dir="ltr">{d.pack}@{d.version}</span>} sub={`${d.source.document} · ${d.source.edition}`} icon={<FileCode2 className="size-5" />}
        action={<Badge tone={active ? 'brand' : 'warn'}>{active ? t('pol.active_sandbox') : t('pol.awaiting')}</Badge>} />
      <div className="space-y-5 p-5">
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge tone="ok" icon={<Quote className="size-3" />}>{t('pol.quote_match', { p: Math.round(d.quote_match_rate * 100) })}</Badge>
          <Badge tone="neutral">{t('pol.method')}: {d.method}</Badge>
          <Badge tone="neutral">{t('pol.never_merged')}: {d.never_merged_with.join(', ')}</Badge>
          <Badge tone="sun">{L(d.label, lang)}</Badge>
        </div>

        <div className="space-y-3">
          {d.rules.map((r: any) => (
            <div key={r.id} className="grid grid-cols-1 gap-3 rounded-2xl border border-line p-4 lg:grid-cols-2">
              <div>
                <div className="mb-1 flex items-center gap-2 text-xs font-semibold text-muted"><Quote className="size-3.5" />{t('pol.quote')} · §{r.clause} {r.quote_match ? <Badge tone="ok">✓ {t('pol.verbatim')}</Badge> : <Badge tone="stop">✗</Badge>}</div>
                <blockquote className="border-s-4 border-brand ps-3 text-sm leading-relaxed" dir="ltr">“{r.quote}”</blockquote>
              </div>
              <div>
                <div className="mb-1 flex items-center gap-2 text-xs font-semibold text-muted"><BookText className="size-3.5" />{t('pol.rule')} · <code dir="ltr">{r.id}</code></div>
                <div className="rounded-xl bg-surface-2 p-3 text-sm" dir="ltr">
                  <div><span className="text-muted">when</span> <code>TWL {Object.entries(r.when.twl_wm2).map(([k, v]) => `${{ lt: '<', lte: '≤', gt: '>', gte: '≥' }[k] ?? k} ${v}`).join(' and ')}</code></div>
                  <div className="mt-1"><span className="text-muted">require</span> {r.require.map((x: any) => <code key={x.name} className="me-1 inline-block rounded bg-surface px-1.5">{x.name}{x.value !== true ? `=${x.value}${x.unit ? ' ' + x.unit : ''}` : ''}</code>)}</div>
                </div>
                <div className="mt-1 text-[11px] text-warn">{t('pol.boundary_note')}</div>
              </div>
            </div>
          ))}
        </div>

        {d.flags?.length > 0 && (
          <div className="rounded-2xl border border-warn/40 bg-warn-soft/50 p-4">
            <div className="flex items-center gap-2 font-bold text-warn"><AlertTriangle className="size-4" />{t('pol.flags')} · {d.flags.length}</div>
            <ul className="mt-2 space-y-2 text-sm">
              {d.flags.map((f: any) => (
                <li key={f.line}><code className="block rounded-lg bg-surface px-2 py-1 text-xs" dir="ltr">L{f.line}: {f.text}</code><span className="text-xs text-ink-2">{t('pol.flag_action')}</span></li>
              ))}
            </ul>
          </div>
        )}

        <details className="rounded-2xl border border-line p-4">
          <summary className="flex cursor-pointer items-center gap-2 font-semibold"><TestTube2 className="size-4" />{t('pol.tests')} · {d.generated_tests.length}</summary>
          <div className="mt-3 grid grid-cols-1 gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
            {d.generated_tests.map((x: any, i: number) => (
              <div key={i} className="flex items-center justify-between gap-2 rounded-lg bg-surface-2 px-2.5 py-1.5 text-xs" dir="ltr">
                <code>{x.rule}</code><span className="num">TWL {x.twl_wm2}</span><span className={x.expect_applies ? 'font-bold text-brand' : 'text-muted'}>{x.expect_applies ? 'applies' : 'no'}</span>
              </div>
            ))}
          </div>
        </details>

        <div className="rounded-2xl border border-line p-4">
          <div className="flex items-center gap-2 font-semibold"><Signature className="size-4" />{t('pol.approvals')} · {d.approvals.length}/2</div>
          <ul className="mt-2 space-y-1.5 text-sm">
            {d.approvals.length === 0 && <li className="text-muted">{t('common.none')}</li>}
            {d.approvals.map((a: any, i: number) => <li key={i} className="flex flex-wrap items-center gap-2"><CheckCircle2 className="size-4 text-ok" /><span className="font-semibold">{name(a.actor)}</span><Badge tone="neutral">{t(`role.${a.role}`)}</Badge>{a.note && <span className="text-xs text-muted" dir="auto">“{a.note}”</span>}</li>)}
          </ul>
          {can('policy.approve') && !active && (
            <div className="mt-3 space-y-2">
              <label className="block text-sm font-semibold">{t('pol.note')}
                <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder={t('pol.note_ph')} className="mt-1 block w-full rounded-xl border border-line bg-surface p-3 text-sm" dir="auto" />
              </label>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => call('approve')} loading={busy === 'approve'} icon={<Signature className="size-4" />}>{t('pol.approve', { role: t(`role.${role}`) })}</Button>
                <Button variant="outline" onClick={() => call('activate')} loading={busy === 'activate'} icon={<ShieldCheck className="size-4" />}>{t('pol.activate')}</Button>
              </div>
              <p className="text-xs text-muted">{t('pol.two_people')}</p>
            </div>
          )}
          {msg && <div role="status" className={cx('mt-3 flex items-start gap-2 rounded-xl p-3 text-sm', msg.ok ? 'bg-ok-soft text-ok' : 'bg-stop-soft text-stop')}>{msg.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" /> : <XCircle className="mt-0.5 size-4 shrink-0" />}{msg.text}</div>}
          {active && <p className="mt-3 text-xs text-muted">{d.activation.note} · <code dir="ltr">{d.signature}</code></p>}
        </div>
      </div>
    </Card>
  )
}
