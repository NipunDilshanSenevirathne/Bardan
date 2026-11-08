import { AlertTriangle, CheckCircle2, Clock3, Droplets, FlaskConical, Gauge, Lock } from 'lucide-react'
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Badge, Button, Card, CardHeader, ErrorNote, PageHeader, Skeleton, cx } from '../../components/ui'
import { api } from '../../lib/api'
import { fmtTime, useApi, useCan } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'

const LEVELS = [
  { lo: '1.000', hi: '1.015', level: 'normal' },
  { lo: '1.016', hi: '1.020', level: 'slight' },
  { lo: '1.021', hi: '1.029', level: 'moderate' },
  { lo: '1.030', hi: '…', level: 'significant' },
]

export default function Hydration() {
  const { t } = useI18n()
  const can = useCan()
  const qc = useQueryClient()
  const queue = useApi<any>('/clinical/queue')
  const [who, setWho] = useState('W01')
  const [usg, setUsg] = useState('1.027')
  const [timing, setTiming] = useState('start_of_shift')
  const [entry, setEntry] = useState('typed')
  const [symptoms, setSymptoms] = useState(false)
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<unknown>(null)
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null); setRes(null)
    try {
      setRes(await api('/clinical/hydration-checks', { body: { worker_ref: who, usg: Number(usg), timing, entry, symptoms } }))
      await qc.invalidateQueries()
    } catch (x) { setErr(x) } finally { setBusy(false) }
  }
  if (queue.isLoading) return <Skeleton className="h-96" />
  const people: any[] = queue.data?.patients ?? []
  const name = people.find((p) => p.worker_ref === who)?.name ?? who
  const level = res?.action_level
  return (
    <div className="space-y-6">
      <PageHeader title={t('cl.hydration')} sub={t('cl.hydration_sub')} icon={<FlaskConical className="size-6" />} />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader title={t('cl.record')} sub={t('cl.instrument_line')} icon={<Gauge className="size-5" />} />
          <form onSubmit={submit} className="space-y-4 p-5">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="text-sm font-semibold">{t('common.worker')}
                <select value={who} onChange={(e) => setWho(e.target.value)} className="mt-1 block h-11 w-full rounded-xl border border-line bg-surface px-3">
                  {people.map((p) => <option key={p.worker_ref} value={p.worker_ref}>{p.name}</option>)}
                </select>
              </label>
              <label className="text-sm font-semibold">{t('cl.usg')}
                <input required inputMode="decimal" value={usg} onChange={(e) => setUsg(e.target.value)} className="mt-1 block h-11 w-full rounded-xl border border-line bg-surface px-3 text-lg font-bold" dir="ltr" />
              </label>
              <label className="text-sm font-semibold">{t('cl.timing')}
                <select value={timing} onChange={(e) => setTiming(e.target.value)} className="mt-1 block h-11 w-full rounded-xl border border-line bg-surface px-3">
                  <option value="start_of_shift">{t('cl.start_shift')}</option><option value="other">{t('cl.other')}</option>
                </select>
              </label>
              <label className="text-sm font-semibold">{t('cl.entry')}
                <select value={entry} onChange={(e) => setEntry(e.target.value)} className="mt-1 block h-11 w-full rounded-xl border border-line bg-surface px-3">
                  <option value="typed">{t('cl.entry_typed')}</option><option value="display_photo_confirmed">{t('cl.entry_photo')}</option>
                </select>
              </label>
            </div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={symptoms} onChange={(e) => setSymptoms(e.target.checked)} className="size-4" />{t('cl.with_symptoms')}</label>
            <div className="flex flex-wrap gap-2">
              {can('clinical.hydration') ? <Button type="submit" loading={busy} icon={<Droplets className="size-4" />}>{t('cl.record')}</Button> : <Badge tone="neutral">{t('cl.nurse_only')}</Badge>}
              <Button type="button" variant="ghost" onClick={() => setUsg('10.24')}>{t('cl.try_implausible')}</Button>
            </div>
            {err ? <ErrorNote error={err} /> : null}
            {res && (
              <div className={cx('space-y-3 rounded-2xl border p-4', level === 'normal' ? 'border-ok/40 bg-ok-soft/50' : level === 'significant' ? 'border-stop/40 bg-stop-soft/50' : 'border-warn/40 bg-warn-soft/50')}>
                <div className="flex flex-wrap items-center gap-2">
                  {level === 'normal' ? <CheckCircle2 className="size-5 text-ok" /> : <AlertTriangle className={cx('size-5', level === 'significant' ? 'text-stop' : 'text-warn')} />}
                  <span className="font-bold">{t('cl.action_level')}: {t(`usg.${level}`)}</span>
                  {res.out_of_range && <Badge tone="warn">{t('cl.out_of_range')}</Badge>}
                </div>
                <ul className="flex flex-wrap gap-1.5">{res.actions.map((a: string) => <Badge key={a} tone="neutral">{t(`hyd.${a}`)}</Badge>)}</ul>
                {res.retest_due_at && <div className="flex items-center gap-2 text-sm"><Clock3 className="size-4" />{t('cl.retest')}: <span className="num font-bold" dir="ltr">{fmtTime(res.retest_due_at)}</span></div>}
                <div className="rounded-xl border border-dashed border-line bg-surface p-3 text-sm">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-muted"><Lock className="size-3.5" />{t('cl.projection')}</div>
                  <div className="mt-1 font-semibold">{res.out_of_range || level === 'significant' ? t('cl.at_clinic_label', { name }) : t('cl.no_projection')}</div>
                </div>
                <div className="text-[11px] text-muted" dir="ltr">{res.instrument.type} {res.instrument.device_id} · cal {res.instrument.calibration_checked} · {res.policy_version}</div>
              </div>
            )}
          </form>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader title={t('cl.levels')} sub={t('cl.levels_sub')} icon={<Droplets className="size-5" />} />
          <table className="w-full text-sm">
            <thead className="bg-surface-2 text-xs text-muted"><tr><th className="px-5 py-2 text-start">USG</th><th className="px-5 py-2 text-start">{t('cl.action_level')}</th></tr></thead>
            <tbody className="divide-y divide-line">
              {LEVELS.map((l) => <tr key={l.level}><td className="num px-5 py-2.5" dir="ltr">{l.lo}–{l.hi}</td><td className="px-5 py-2.5"><Badge tone={l.level === 'normal' ? 'ok' : l.level === 'significant' ? 'stop' : 'warn'}>{t(`usg.${l.level}`)}</Badge></td></tr>)}
            </tbody>
          </table>
          <p className="px-5 py-4 text-xs text-muted">{t('cl.levels_note')}</p>
        </Card>
      </div>
    </div>
  )
}
