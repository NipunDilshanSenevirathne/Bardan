import { CheckCircle2, FileHeart, Languages, Lock, Microscope, NotebookPen, ShieldAlert, Sparkles, UserRound } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Badge, Button, Card, CardHeader, Empty, ErrorNote, KV, PageHeader, Skeleton, Tabs, cx } from '../../components/ui'
import { api } from '../../lib/api'
import { fmtDate, useApi, useCan } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'
import { useVizColors } from '../../lib/viz'

export default function Patient() {
  const { id = 'W07' } = useParams()
  const { t, lang } = useI18n()
  const can = useCan()
  const queue = useApi<any>('/clinical/queue')
  const q = useApi<any>(`/clinical/patients/${id}`)
  const patients: any[] = queue.data?.patients ?? []
  return (
    <div className="space-y-6">
      <PageHeader title={t('cl.patient')} sub={t('cl.patient_sub')} icon={<UserRound className="size-6" />}
        actions={patients.length > 0 && (
          <nav aria-label={t('cl.patients')} className="inline-flex flex-wrap gap-1 rounded-2xl bg-surface-2 p-1">
            {patients.map((p) => (
              <Link key={p.worker_ref} to={`/app/clinic/patient/${p.worker_ref}`} aria-current={p.worker_ref === id ? 'page' : undefined}
                className={cx('inline-flex min-h-10 items-center rounded-xl px-3.5 text-sm font-semibold', p.worker_ref === id ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-ink')}>
                {p.name.split(' ')[0]}
              </Link>
            ))}
          </nav>
        )} />
      {q.isLoading ? <Skeleton className="h-96" /> : q.error ? <ErrorNote error={q.error} onRetry={() => q.refetch()} /> : <Body d={q.data} id={id} canWrite={can('clinical.write')} lang={lang} />}
    </div>
  )
}

function Body({ d, id, canWrite, lang }: { d: any; id: string; canWrite: boolean; lang: 'en' | 'ar' }) {
  const { t } = useI18n()
  const p = d.patient
  const acr = d.results.filter((r: any) => r.analyte === 'urine_acr')
  return (
    <>
      <Card>
        <div className="flex flex-wrap items-center gap-4 p-5">
          <span className="grid size-14 place-items-center rounded-2xl bg-brand text-xl font-bold text-brand-ink">{p.name[0]}</span>
          <div className="min-w-0 flex-1">
            <div className="text-xl font-bold">{p.name}</div>
            <div className="mt-1 flex flex-wrap gap-1.5 text-xs">
              <Badge tone="neutral"><span dir="ltr">{p.patient_ref}</span></Badge>
              <Badge tone="neutral">{p.lang === 'ar' ? 'العربية' : 'English'}</Badge>
              <Badge tone="neutral">{t('cl.yob')} {p.year_of_birth}</Badge>
              <Badge tone={p.kidney_pathway === 'enrolled' ? 'brand' : 'neutral'}>{t(`path.${p.kidney_pathway}`)}</Badge>
              <Badge tone="sun">{t('common.synthetic')}</Badge>
            </div>
          </div>
          <div className="text-xs text-muted"><Lock className="me-1 inline size-3.5" />{t('cl.access_logged')}</div>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title={t('h.results')} sub={t('cl.category_note')} icon={<Microscope className="size-5" />} />
          <div className="space-y-4 p-5">
            {acr.length > 1 && <AcrChart rows={acr} />}
            <div className="relative scroll-thin overflow-x-auto">
              <table className="w-full min-w-[560px] text-sm">
                <thead className="text-xs text-muted"><tr><th className="py-1.5 pe-3 text-start">{t('cl.test')}</th><th className="px-3 py-1.5 text-end">{t('common.result')}</th><th className="px-3 py-1.5 text-start">{t('cl.category')}</th><th className="px-3 py-1.5 text-start">{t('cl.specimen')}</th><th className="py-1.5 ps-3 text-start">{t('common.method')}</th></tr></thead>
                <tbody className="divide-y divide-line">
                  {d.results.map((r: any) => (
                    <tr key={r.id}>
                      <td className="py-2.5 pe-3"><div className="font-semibold">{t(`an.${r.analyte}`)}</div><code className="text-[10px] text-muted" dir="ltr">LOINC {r.loinc}</code></td>
                      <td className="num px-3 py-2.5 text-end font-bold" dir="ltr">{r.value} <span className="text-xs font-normal text-muted">{r.unit}</span></td>
                      <td className="px-3 py-2.5">{r.category ? <Badge tone={r.category === 'A1' ? 'neutral' : 'warn'}>{r.category}</Badge> : '–'}</td>
                      <td className="whitespace-nowrap px-3 py-2.5">{fmtDate(r.specimen_at, lang)}</td>
                      <td className="py-2.5 ps-3 text-xs text-muted">{r.method}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {d.results.some((r: any) => r.interpretation_note) && <p className="rounded-xl bg-warn-soft p-3 text-xs font-medium text-warn">{lang === 'ar' ? t('cl.interpretation_note') : d.results.find((r: any) => r.interpretation_note).interpretation_note}</p>}
          </div>
        </Card>
        <Card>
          <CardHeader title={t('cl.consents')} icon={<Lock className="size-5" />} />
          <ul className="divide-y divide-line">
            {d.consents.map((c: any) => (
              <li key={c.purpose} className="flex items-start justify-between gap-2 px-5 py-3 text-sm">
                <span className="min-w-0">{lang === 'ar' ? c.label_ar : c.label_en}</span>
                <Badge tone={c.active ? 'ok' : 'neutral'}>{c.active ? t('d.on') : t('d.off')}</Badge>
              </li>
            ))}
          </ul>
          <p className="px-5 pb-4 text-xs text-muted">{d.checkins_shared ? t('cl.checkins_shared') : t('cl.checkins_not_shared')}</p>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Restriction id={id} current={d.restriction} canWrite={canWrite} name={p.name} />
        <Card>
          <CardHeader title={t('h.referrals')} icon={<ShieldAlert className="size-5" />} action={<Link to="/app/clinic" className="text-sm font-semibold text-brand">{t('cl.queue')}</Link>} />
          <ul className="space-y-2 p-5">
            {d.referrals.length === 0 && <Empty>{t('common.none')}</Empty>}
            {d.referrals.map((r: any) => (
              <li key={r.id} className="rounded-xl bg-surface-2 p-3 text-sm">
                <div className="flex items-center justify-between gap-2"><span className="font-semibold">{r.id}</span><Badge tone="brand">{t(`ref.${r.state}`)}</Badge></div>
                <ol className="mt-2 flex flex-wrap gap-1 text-[11px] text-muted">{r.history.map((h: any, i: number) => <li key={i} className="rounded-full bg-surface px-2 py-0.5">{t(`ref.${h.state}`)} <span dir="ltr">{h.at.slice(5, 16).replace('T', ' ')}</span></li>)}</ol>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Summary id={id} patientLang={p.lang} summaries={d.summaries} />
    </>
  )
}

function AcrChart({ rows }: { rows: any[] }) {
  const { t, lang } = useI18n()
  const c = useVizColors()
  const data = rows.map((r) => ({ x: Date.parse(r.specimen_at), v: r.value, d: fmtDate(r.specimen_at, lang) })).sort((a, b) => a.x - b.x)
  return (
    <div>
      <div className="mb-1 text-xs font-semibold text-muted">{t('cl.acr_trend')}</div>
      <div className="h-36" dir="ltr" role="img" aria-label={t('cl.acr_trend')}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 16, right: 24, bottom: 0, left: -20 }}>
            <CartesianGrid stroke={c.grid} vertical={false} />
            <XAxis dataKey="d" tick={{ fill: c.muted, fontSize: 11 }} axisLine={{ stroke: c.line }} tickLine={false} />
            <YAxis domain={[0, (m: number) => Math.max(80, Math.ceil(m / 20) * 20)]} tick={{ fill: c.muted, fontSize: 11 }} axisLine={false} tickLine={false} />
            <ReferenceLine y={30} stroke={c.ink2} strokeWidth={1} label={{ value: '30 mg/g', position: 'insideBottomRight', fill: c.ink2, fontSize: 10 }} />
            <Line dataKey="v" stroke={c.s1} strokeWidth={2} dot={{ r: 4, fill: c.s1, stroke: c.surface, strokeWidth: 2 }} isAnimationActive={false}
              label={{ position: 'top', fill: c.ink, fontSize: 11 }} />
            <Tooltip content={({ active, payload }: any) => active && payload?.length ? <div className="rounded-xl border border-line bg-surface px-3 py-2 text-xs shadow-float"><div className="text-muted">{payload[0].payload.d}</div><div className="num font-bold" dir="ltr">{payload[0].payload.v} mg/g</div></div> : null} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function Restriction({ id, current, canWrite, name }: { id: string; current: any; canWrite: boolean; name: string }) {
  const { t } = useI18n()
  const qc = useQueryClient()
  const [label, setLabel] = useState(current?.label ?? 'shaded_light_duty')
  const [until, setUntil] = useState('16:00')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<unknown>(null)
  async function save(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null)
    try {
      await api('/clinical/restrictions', { body: { worker_ref: id, label, until: `2025-08-19T${until}:00+04:00`, reason_private: reason || 'Clinical reason recorded in the care record' } })
      await qc.invalidateQueries()
    } catch (x) { setErr(x) } finally { setBusy(false) }
  }
  const projection = label === 'none' ? t('cl.no_projection') : t('cl.projection_text', { name, time: until })
  return (
    <Card>
      <CardHeader title={t('cl.restriction')} sub={t('cl.restriction_sub')} icon={<ShieldAlert className="size-5" />} />
      <form onSubmit={save} className="space-y-3 p-5">
        {current && <div className="rounded-xl bg-brand-soft p-3 text-sm text-brand">{t('cl.current')}: {t(`rl.${current.label}`)} · <span dir="ltr">{current.until.slice(11, 16)}</span></div>}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="text-sm font-semibold">{t('common.label')}
            <select value={label} onChange={(e) => setLabel(e.target.value)} disabled={!canWrite} className="mt-1 block h-11 w-full rounded-xl border border-line bg-surface px-3">
              {['shaded_light_duty', 'no_heat_work', 'none'].map((x) => <option key={x} value={x}>{t(`rl.${x}`)}</option>)}
            </select>
          </label>
          <label className="text-sm font-semibold">{t('cl.until')}
            <input type="time" value={until} onChange={(e) => setUntil(e.target.value)} disabled={!canWrite} className="mt-1 block h-11 w-full rounded-xl border border-line bg-surface px-3" dir="ltr" />
          </label>
        </div>
        <label className="block text-sm font-semibold">{t('cl.reason_private')}
          <input value={reason} onChange={(e) => setReason(e.target.value)} disabled={!canWrite} maxLength={200} placeholder={t('cl.reason_private_ph')} className="mt-1 block h-11 w-full rounded-xl border border-line bg-surface px-3" dir="auto" />
        </label>
        <div className="rounded-xl border border-dashed border-line p-3 text-sm"><div className="text-xs font-semibold text-muted">{t('cl.projection')}</div><div className="mt-1 font-semibold">{projection}</div></div>
        {canWrite && <Button type="submit" loading={busy} icon={<CheckCircle2 className="size-4" />}>{t('cl.save_restriction')}</Button>}
        {err ? <ErrorNote error={err} /> : null}
      </form>
    </Card>
  )
}

function Summary({ id, patientLang, summaries }: { id: string; patientLang: string; summaries: any[] }) {
  const { t } = useI18n()
  const can = useCan()
  const qc = useQueryClient()
  const [note, setNote] = useState('Urine ACR 64 mg/g on 28 Jul 2025 (repeat test). eGFR 88. Clinic visit booked 19 Aug 14:00 with transport. Keep drinking water during shifts. Repeat ACR in 3 months.')
  const [lng, setLng] = useState<'ar' | 'en'>(patientLang === 'ar' ? 'ar' : 'en')
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<unknown>(null)
  const [manual, setManual] = useState('')
  const latest = summaries[summaries.length - 1]
  async function draft() {
    setBusy('draft'); setErr(null)
    try { await api('/clinical/summaries/draft', { body: { worker_ref: id, note, lang: lng } }); await qc.invalidateQueries() } catch (e) { setErr(e) } finally { setBusy(null) }
  }
  async function approve(text?: string) {
    if (!latest) return
    setBusy('approve'); setErr(null)
    try { await api(`/clinical/summaries/${latest.id}/approve`, { body: text ? { text } : {} }); await qc.invalidateQueries() } catch (e) { setErr(e) } finally { setBusy(null) }
  }
  if (!can('clinical.summary_approve')) return null
  const noAi = latest && !latest.summary && latest.status !== 'approved'
  return (
    <Card>
      <CardHeader title={t('cl.summary')} sub={t('cl.summary.b')} icon={<FileHeart className="size-5" />} />
      <div className="grid grid-cols-1 gap-5 p-5 lg:grid-cols-2">
        <div className="space-y-3">
          <label className="block text-sm font-semibold"><NotebookPen className="me-1 inline size-4" />{t('cl.note')}
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={6} className="mt-1 block w-full rounded-xl border border-line bg-surface p-3 text-sm leading-relaxed" dir="auto" />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <Tabs value={lng} onChange={setLng} items={[{ id: 'ar', label: 'العربية' }, { id: 'en', label: 'English' }]} />
            <Button onClick={draft} loading={busy === 'draft'} icon={<Sparkles className="size-4" />}>{t('cl.draft_btn')}</Button>
          </div>
          <p className="text-xs text-muted">{t('cl.draft_note')}</p>
        </div>
        <div className="space-y-3">
          {!latest && <Empty icon={<Languages className="size-6" />}>{t('cl.no_summary')}</Empty>}
          {latest?.summary && (
            <>
              <div className="rounded-2xl border border-line p-4">
                <div className="mb-1 flex items-center justify-between gap-2 text-xs font-semibold text-muted">{t('cl.draft')}
                  <Badge tone={latest.status === 'approved' ? 'ok' : latest.status === 'flagged_for_clinician' ? 'warn' : 'neutral'}>{t(`sum.${latest.status}`)}</Badge></div>
                <p className="text-sm leading-relaxed" dir={latest.lang === 'ar' ? 'rtl' : 'ltr'} lang={latest.lang}>{latest.summary}</p>
              </div>
              {latest.back_translation && (
                <div className="rounded-2xl border border-dashed border-line p-4">
                  <div className="mb-1 text-xs font-semibold text-muted">{t('cl.back')}</div>
                  <p className="text-sm leading-relaxed" dir="ltr">{latest.back_translation}</p>
                  {latest.discrepancies?.length > 0 && <div className="mt-2 text-xs font-semibold text-warn">{t('cl.discrepancies')}: <span dir="ltr">{latest.discrepancies.join(', ')}</span></div>}
                </div>
              )}
              {latest.source === 'clinician_written' && <Badge tone="neutral">{t('cl.clinician_written')}</Badge>}
              {latest.status !== 'approved' && <Button variant="sun" onClick={() => approve()} loading={busy === 'approve'} icon={<CheckCircle2 className="size-4" />}>{t('cl.approve')}</Button>}
              {latest.status === 'approved' && <div className="rounded-xl bg-ok-soft p-3 text-sm font-semibold text-ok">{t('cl.sent_to_worker')}</div>}
            </>
          )}
          {noAi && (
            <div className="space-y-2 rounded-2xl border border-unknown/30 bg-unknown-soft p-4">
              <div className="text-sm font-semibold">{t('cl.ai_unavailable')}</div>
              <textarea value={manual || t(`cl.template_${latest.lang === 'ar' ? 'ar' : 'en'}`)} onChange={(e) => setManual(e.target.value)} rows={5}
                className="block w-full rounded-xl border border-line bg-surface p-3 text-sm leading-relaxed" dir={latest.lang === 'ar' ? 'rtl' : 'ltr'} lang={latest.lang} />
              <Button onClick={() => approve(manual || t(`cl.template_${latest.lang === 'ar' ? 'ar' : 'en'}`))} loading={busy === 'approve'} icon={<CheckCircle2 className="size-4" />}>{t('cl.approve_manual')}</Button>
            </div>
          )}
          {err ? <ErrorNote error={err} /> : null}
          <KV k={t('cl.status_label')} v={latest ? t(`sum.${latest.status}`) : '–'} />
        </div>
      </div>
    </Card>
  )
}

