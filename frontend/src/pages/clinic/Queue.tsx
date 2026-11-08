import {
  AlertOctagon, Ban, CalendarCheck2, CalendarX2, Car, ChevronRight, ClipboardList, Droplets, FlaskConical, Inbox, Lock,
  ShieldAlert, Stethoscope, UserRound,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Badge, Button, Card, CardHeader, Empty, ErrorNote, PageHeader, Skeleton, Stat, cx } from '../../components/ui'
import { api } from '../../lib/api'
import { fmtDate, fmtTime, useApi, useCan } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'

export default function Queue() {
  const { t, lang } = useI18n()
  const can = useCan()
  const qc = useQueryClient()
  const q = useApi<any>('/clinical/queue', { refetch: 20000 })
  const [busy, setBusy] = useState<string | null>(null)
  const [last, setLast] = useState<any>(null)
  const [err, setErr] = useState<unknown>(null)
  async function run(key: string, fn: () => Promise<any>) {
    setBusy(key); setErr(null)
    try { const r = await fn(); await qc.invalidateQueries(); return r } catch (e) { setErr(e) } finally { setBusy(null) }
  }
  if (q.isLoading) return <Skeleton className="h-96" />
  if (q.error) return <ErrorNote error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  const cap = d.capacity

  return (
    <div className="space-y-6">
      <PageHeader title={t('cl.title')} sub={t('cl.sub')} icon={<Stethoscope className="size-6" />} />
      <div className="flex items-start gap-3 rounded-2xl border border-cyan/30 bg-cyan-soft p-4 text-sm"><Lock className="mt-0.5 size-5 shrink-0 text-cyan" /><span className="text-ink-2">{t('cl.boundary')}</span></div>
      {err ? <ErrorNote error={err} /> : null}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t('cl.urgent_slots')} value={`${cap.urgent_used}/${cap.urgent_slots}`} icon={<AlertOctagon className="size-4" />} />
        <Stat label={t('cl.routine_slots')} value={`${cap.routine_used}/${cap.routine_slots}`} icon={<CalendarCheck2 className="size-4" />} />
        <Stat label={t('cl.incoming')} value={d.incoming.length} icon={<Inbox className="size-4" />} />
        <Stat label={t('cl.quarantine')} value={d.quarantine.length} icon={<Ban className="size-4" />} tone={d.quarantine.length ? 'stop' : undefined} />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title={t('cl.incoming')} sub={t('cl.incoming_sub')} icon={<Inbox className="size-5" />} />
          <div className="space-y-3 p-5">
            {d.incoming.length === 0 && <Empty>{t('common.none')}</Empty>}
            {d.incoming.map((r: any) => (
              <div key={r.id} className="rounded-2xl border border-line p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div className="font-semibold">{r.claimed_name}</div>
                  <div className="num text-lg font-bold" dir="ltr">{r.value} <span className="text-sm text-muted">{r.unit}</span></div>
                </div>
                <div className="mt-1 text-xs text-muted">{t(`an.${r.analyte}`)} · {fmtDate(r.specimen_at, lang)} · {r.method} · {r.lab}</div>
                {can('clinical.verify') && (
                  <Button className="mt-3" size="sm" onClick={async () => setLast(await run(r.id, () => api('/clinical/results/import', { body: { lab_id: r.id } })))} loading={busy === r.id} icon={<ShieldAlert className="size-4" />}>{t('cl.import')}</Button>
                )}
              </div>
            ))}
            {last && (
              <div role="status" className={cx('rounded-2xl p-4 text-sm', last.status === 'verified' ? 'bg-ok-soft' : 'bg-stop-soft')}>
                {last.status === 'verified' ? (
                  <>
                    <div className="font-bold text-ok">{t('cl.verified_ok')}</div>
                    <div className="mt-1 flex flex-wrap items-center gap-2"><span className="num font-bold" dir="ltr">{last.result.value} {last.result.unit}</span><Badge tone="warn">{t('cl.category')} {last.result.category}</Badge></div>
                    <p className="mt-1 text-xs text-ink-2">{lang === 'ar' ? t('cl.interpretation_note') : last.result.interpretation_note}</p>
                  </>
                ) : (
                  <>
                    <div className="font-bold text-stop">{t('cl.quarantined')}</div>
                    <div className="mt-1 flex flex-wrap gap-1">{last.item.problems.map((p: string) => <Badge key={p} tone="stop">{t(`prob.${p}`)}</Badge>)}</div>
                    <p className="mt-1 text-xs text-ink-2">{lang === 'ar' ? t('cl.quarantine_explain') : last.item.explain}</p>
                  </>
                )}
              </div>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title={t('cl.quarantine')} sub={t('cl.quarantine_sub')} icon={<Ban className="size-5" />} />
          <div className="space-y-3 p-5">
            {d.quarantine.length === 0 && <Empty>{t('common.none')}</Empty>}
            {d.quarantine.map((x: any, i: number) => (
              <div key={`${x.id}-${i}`} className="rounded-2xl border border-stop/30 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-semibold">{x.claimed_name ?? x.id}</span><code className="text-xs text-muted" dir="ltr">{x.id}</code></div>
                <div className="mt-2 flex flex-wrap gap-1">{(x.problems ?? []).map((p: string) => <Badge key={p} tone="stop">{t(`prob.${p}`)}</Badge>)}</div>
                <p className="mt-2 text-xs text-muted">{lang === 'ar' ? t('cl.quarantine_explain') : x.explain}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Referrals d={d} run={run} busy={busy} />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-1">
          <CardHeader title={t('cl.patients')} icon={<UserRound className="size-5" />} />
          <ul className="divide-y divide-line">
            {d.patients.map((p: any) => (
              <li key={p.worker_ref}>
                <Link to={`/app/clinic/patient/${p.worker_ref}`} className="flex items-center gap-3 px-5 py-3 hover:bg-surface-2">
                  <span className="grid size-9 place-items-center rounded-full bg-brand-soft text-sm font-bold text-brand">{p.name[0]}</span>
                  <span className="min-w-0 flex-1"><span className="block font-semibold">{p.name}</span><span className="text-xs text-muted">{t(`path.${p.pathway}`)}</span></span>
                  <ChevronRight className="flip-rtl size-4 text-muted" />
                </Link>
              </li>
            ))}
          </ul>
        </Card>
        <Card className="xl:col-span-1">
          <CardHeader title={t('cl.triage')} sub={t('cl.triage_sub')} icon={<ClipboardList className="size-5" />} />
          <ul className="space-y-2 p-5">
            {d.triage.length === 0 && <li className="text-sm text-muted">{t('common.none')}</li>}
            {d.triage.map((x: any, i: number) => (
              <li key={i} className="rounded-xl bg-surface-2 p-3 text-sm">
                <div className="flex items-center justify-between gap-2"><span className="font-semibold">{x.name}</span><span className="num text-xs text-muted" dir="ltr">{fmtTime(x.at)}</span></div>
                {x.symptoms ? <div className="mt-1 flex flex-wrap gap-1">{x.symptoms.map((s: string) => <Badge key={s} tone="warn">{t(`sym.${s}`)}</Badge>)}</div> : <div className="mt-1 text-xs text-muted">{t('cl.not_shared')}</div>}
                <div className="mt-1 text-[11px] text-muted">{t(`basis.${x.basis.split(' ')[0]}`)}</div>
              </li>
            ))}
          </ul>
        </Card>
        <Card className="xl:col-span-1">
          <CardHeader title={t('h.hydration')} icon={<Droplets className="size-5" />} action={<Link to="/app/clinic/hydration" className="text-sm font-semibold text-brand">{t('cl.hydration')}</Link>} />
          <ul className="space-y-2 p-5">
            {d.hydration.slice().reverse().map((h: any) => (
              <li key={h.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-surface-2 p-3 text-sm">
                <span className="font-semibold">{h.name}</span>
                <span className="num" dir="ltr">USG {h.reading.usg}</span>
                <Badge tone={h.action_level === 'normal' ? 'ok' : h.action_level === 'significant' ? 'stop' : 'warn'}>{t(`usg.${h.action_level}`)}</Badge>
                <span className="num w-full text-xs text-muted"><span dir="ltr">{h.at.slice(5, 10)} {fmtTime(h.at)}</span>{h.retest ? <> · {t('cl.retest_result')} <span dir="ltr">{h.retest.usg}</span></> : ''}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      {can('clinical.document_ai') && (
        <Link to="/app/clinic/documents" className="flex items-center gap-3 rounded-2xl border border-line bg-surface p-4 text-sm font-semibold hover:border-brand">
          <FlaskConical className="size-5 text-brand" />{t('cl.documents_cta')}<ChevronRight className="flip-rtl ms-auto size-4 text-muted" />
        </Link>
      )}
    </div>
  )
}

function Referrals({ d, run, busy }: { d: any; run: (k: string, fn: () => Promise<any>) => Promise<any>; busy: string | null }) {
  const { t, lang } = useI18n()
  const can = useCan()
  const [who, setWho] = useState('W07')
  const [urgency, setUrgency] = useState('soon')
  const day = '2025-08-19'
  const appt = { start: `${day}T14:00:00+04:00`, end: `${day}T16:00:00+04:00`, place: lang === 'ar' ? 'العيادة الشريكة (وهمية)، مصفح' : 'Partner clinic (fictional), Musaffah', transport: 'booked' }
  const ev = (rid: string, state: string, extra: any = {}) => run(`${rid}:${state}`, () => api(`/clinical/referrals/${rid}/events`, { body: { state, ...extra } }))
  return (
    <Card>
      <CardHeader title={t('cl.referrals')} sub={t('cl.referrals_sub')} icon={<CalendarCheck2 className="size-5" />} />
      {can('clinical.referral') && (
        <div className="flex flex-wrap items-end gap-2 border-b border-line px-5 py-4">
          <label className="text-xs font-semibold">{t('common.worker')}
            <select value={who} onChange={(e) => setWho(e.target.value)} className="mt-1 block h-10 rounded-xl border border-line bg-surface px-2 text-sm">
              {d.patients.map((p: any) => <option key={p.worker_ref} value={p.worker_ref}>{p.name}</option>)}
            </select>
          </label>
          <label className="text-xs font-semibold">{t('cl.urgency')}
            <select value={urgency} onChange={(e) => setUrgency(e.target.value)} className="mt-1 block h-10 rounded-xl border border-line bg-surface px-2 text-sm">
              {['routine', 'soon', 'urgent'].map((u) => <option key={u} value={u}>{t(`urg.${u}`)}</option>)}
            </select>
          </label>
          <Button size="md" onClick={() => run('new', () => api('/clinical/referrals', { body: { worker_ref: who, urgency } }))} loading={busy === 'new'}>{t('cl.new_referral')}</Button>
        </div>
      )}
      <div className="relative scroll-thin overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <thead className="bg-surface-2 text-xs text-muted"><tr>
            <th className="px-5 py-2.5 text-start font-semibold">{t('common.worker')}</th><th className="px-3 py-2.5 text-start font-semibold">{t('cl.urgency')}</th>
            <th className="px-3 py-2.5 text-start font-semibold">{t('common.status')}</th><th className="px-3 py-2.5 text-start font-semibold">{t('cl.appointment')}</th>
            <th className="px-5 py-2.5 text-start font-semibold">{t('cl.next_step')}</th></tr></thead>
          <tbody className="divide-y divide-line">
            {d.referrals.map((r: any) => (
              <tr key={r.id} className={cx(r.state === 'missed' && 'bg-stop-soft/40')}>
                <td className="px-5 py-3"><div className="font-semibold">{r.name}</div><code className="text-[11px] text-muted" dir="ltr">{r.id} · {r.patient_ref}</code></td>
                <td className="px-3 py-3"><Badge tone={r.urgency === 'urgent' ? 'stop' : r.urgency === 'soon' ? 'warn' : 'neutral'}>{t(`urg.${r.urgency}`)}</Badge></td>
                <td className="px-3 py-3"><Badge tone={r.state === 'missed' ? 'stop' : r.state === 'scheduled' ? 'brand' : 'neutral'}>{t(`ref.${r.state}`)}</Badge>
                  {r.state === 'missed' && <div className="mt-1 text-[11px] text-stop">{t('cl.missed_reason', { r: t(`miss.${r.history.at(-1)?.reason ?? 'unknown'}`) })}</div>}</td>
                <td className="px-3 py-3 text-xs">{r.appointment ? <><div className="num" dir="ltr">{r.appointment.start.slice(5, 16).replace('T', ' ')}–{r.appointment.end.slice(11, 16)}</div><div className="text-muted">{r.appointment.place}</div><div className="flex items-center gap-1 text-muted"><Car className="size-3" />{t(`transport.${r.appointment.transport}`)}</div></> : '–'}</td>
                <td className="px-5 py-3">
                  <div className="flex flex-wrap gap-1.5">
                    {r.state === 'offered' && can('clinical.referral') && <Button size="sm" variant="soft" onClick={() => ev(r.id, 'accepted')} loading={busy === `${r.id}:accepted`}>{t('ref.accept_btn')}</Button>}
                    {['accepted', 'missed', 'escalated'].includes(r.state) && <Button size="sm" onClick={() => ev(r.id, 'scheduled', { appointment: appt })} loading={busy === `${r.id}:scheduled`} icon={<CalendarCheck2 className="size-3.5" />}>{t('cl.schedule')}</Button>}
                    {r.state === 'scheduled' && <Button size="sm" variant="soft" onClick={() => ev(r.id, 'attended')} loading={busy === `${r.id}:attended`}>{t('ref.attended_btn')}</Button>}
                    {r.state === 'scheduled' && <Button size="sm" variant="ghost" onClick={() => ev(r.id, 'missed', { reason: 'transport_unavailable' })} loading={busy === `${r.id}:missed`} icon={<CalendarX2 className="size-3.5 text-stop" />}>{t('ref.missed_btn')}</Button>}
                    {r.state === 'missed' && can('clinical.referral') && <Button size="sm" variant="ghost" onClick={() => ev(r.id, 'escalated')} loading={busy === `${r.id}:escalated`}>{t('ref.escalate_btn')}</Button>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="px-5 py-3 text-xs text-muted">{t('cl.referral_privacy')}</p>
    </Card>
  )
}
