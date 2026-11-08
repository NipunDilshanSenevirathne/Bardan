import { CheckCircle2, ClipboardCheck, Coffee, FileSignature, GraduationCap, Printer, Sun, Users } from 'lucide-react'
import { useState } from 'react'
import { Badge, Button, Card, CardHeader, ErrorNote, PageHeader, Skeleton, Stat, TierChip, cx } from '../../components/ui'
import { api } from '../../lib/api'
import { fmtDate, useApi, useCan } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'
import { L } from '../../lib/labels'

export default function Compliance() {
  const { t, lang } = useI18n()
  const can = useCan()
  const q = useApi<any>('/sites/site_demo/compliance')
  if (q.isLoading) return <Skeleton className="h-96" />
  if (q.error) return <ErrorNote error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  const zeroDays = d.midday.filter((m: any) => m.outdoor_minutes_in_window === 0).length
  const tiers = ['E4', 'E3', 'E2', 'E1']

  return (
    <div className="space-y-6">
      <PageHeader title={t('hse.compliance')} sub={t('co.pack_sub')} icon={<ClipboardCheck className="size-6" />}
        actions={<Button variant="outline" onClick={() => window.print()} icon={<Printer className="size-4" />}>{t('common.print')}</Button>} />
      <div className="rounded-2xl border border-sun/30 bg-sun-soft px-4 py-3 text-sm font-semibold text-sun">{L(d.label, lang)}</div>
      {d.validation && (
        <div className={cx('flex flex-wrap items-center gap-2 rounded-2xl border px-4 py-3 text-sm', d.validation.valid ? 'border-ok/40 bg-ok-soft' : 'border-stop/40 bg-stop-soft')}>
          <span className={cx('font-bold', d.validation.valid ? 'text-ok' : 'text-stop')}>{d.validation.valid ? t('co.valid') : t('co.invalid')}</span>
          {d.validation.checks.map((c: any) => <Badge key={c.check} tone={c.ok ? 'ok' : 'stop'}>{t(`co.check.${c.check}`)}</Badge>)}
          {d.exclusions && <span className="text-ink-2">{t('co.exclusions', { r: d.exclusions.rejected_readings, a: d.exclusions.failed_alerts })}</span>}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t('co.midday_days')} value={`${zeroDays}/${d.midday.length}`} sub={t('co.midday_days_sub')} icon={<Sun className="size-4" />} />
        <Stat label={t('co.verified_tasks')} value={Object.values(d.verified_by_tier as Record<string, number>).reduce((a, b) => a + b, 0)} sub={t('co.tiers_separate')} icon={<CheckCircle2 className="size-4" />} />
        <Stat label={t('co.training')} value={`${d.training.completed}/${d.training.due}`} sub={t('co.training_sub', { n: d.training.overdue })} icon={<GraduationCap className="size-4" />} tone={d.training.overdue ? 'sun' : undefined} />
        <Stat label={t('c.responders')} value={d.responders.filter((r: any) => r.on_shift).length} sub={t('co.responders_sub')} icon={<Users className="size-4" />} />
      </div>

      <Card>
        <CardHeader title={t('co.checklist')} sub={t('co.checklist_sub')} icon={<ClipboardCheck className="size-5" />} />
        <div className="relative scroll-thin overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="bg-surface-2 text-xs text-muted"><tr>
              <th className="px-5 py-2.5 text-start font-semibold">{t('co.duty')}</th><th className="px-3 py-2.5 text-start font-semibold">{t('common.status')}</th>
              <th className="px-3 py-2.5 text-start font-semibold">{t('co.evidence')}</th><th className="px-5 py-2.5 text-start font-semibold">{t('co.tier')}</th></tr></thead>
            <tbody className="divide-y divide-line">
              {d.checklist.map((c: any) => (
                <tr key={c.duty}>
                  <td className="px-5 py-3 font-semibold" dir="auto">{lang === 'ar' ? dutyAr(c.duty) : c.duty}</td>
                  <td className="px-3 py-3"><Badge tone={/overdue/.test(c.status) ? 'warn' : 'ok'}>{statusText(c.status, lang)}</Badge></td>
                  <td className="px-3 py-3 text-ink-2">{lang === 'ar' ? evidenceAr(c.evidence) : c.evidence}</td>
                  <td className="px-5 py-3"><TierChip tier={c.tier} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title={t('co.breaks')} sub={t('co.breaks_sub')} icon={<Coffee className="size-5" />} />
          <ul className="space-y-4 p-5">
            {Object.entries(d.breaks_last_7_days as Record<string, any>).map(([crew, b]) => {
              const pct = b.required ? (b.delivered_full / b.required) * 100 : 0
              return (
                <li key={crew}>
                  <div className="flex items-baseline justify-between gap-2 text-sm"><span className="font-semibold">{t('common.crew')} {crew}</span>
                    <span className="num text-xs text-muted" dir="ltr">{b.required ? `${b.delivered_full}/${b.required} · ${t('co.cut_short', { n: b.cut_short })}` : t('co.not_required')}</span></div>
                  <div className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-brand-soft" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)} aria-label={`${crew} ${Math.round(pct)}%`}>
                    <div className="h-full rounded-full bg-brand" style={{ width: `${pct}%` }} />
                  </div>
                </li>
              )
            })}
          </ul>
        </Card>
        <Card>
          <CardHeader title={t('co.midday')} sub={t('co.midday_sub')} icon={<Sun className="size-5" />} />
          <ul className="divide-y divide-line">
            {d.midday.map((m: any) => (
              <li key={m.date} className="flex items-center justify-between gap-2 px-5 py-2.5 text-sm">
                <span>{fmtDate(m.date + 'T12:00:00+04:00', lang)}</span>
                <span className="flex items-center gap-2">
                  {m.note && <span className="text-xs text-muted">{lang === 'ar' ? 'مباشر: يفرضه محرك القواعد' : m.note}</span>}
                  <Badge tone={m.outdoor_minutes_in_window === 0 ? 'ok' : 'stop'}>{t('co.minutes', { n: m.outdoor_minutes_in_window })}</Badge>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title={t('co.tasks_tiers')} sub={t('co.tiers_never_merged')} icon={<CheckCircle2 className="size-5" />} />
          <div className="space-y-4 p-5">
            <div className="flex flex-wrap gap-2">{Object.entries(d.tasks_by_state as Record<string, number>).map(([k, v]) => <Badge key={k} tone="neutral">{t(`task.state.${k}`)} · {v}</Badge>)}</div>
            <table className="w-full text-sm">
              <thead className="text-xs text-muted"><tr><th className="py-1 text-start">{t('co.tier')}</th><th className="py-1 text-end">{t('co.verified_tasks')}</th></tr></thead>
              <tbody className="divide-y divide-line">{tiers.map((tier) => <tr key={tier}><td className="py-2"><TierChip tier={tier} /></td><td className="num py-2 text-end font-bold" dir="ltr">{d.verified_by_tier[tier] ?? 0}</td></tr>)}</tbody>
            </table>
          </div>
        </Card>
        {can('exemption.record') && <Exemption />}
      </div>
    </div>
  )
}

function Exemption() {
  const { t } = useI18n()
  const [task, setTask] = useState('P1')
  const [ref, setRef] = useState('')
  const [reason, setReason] = useState('')
  const [res, setRes] = useState<any>(null)
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null)
    try { setRes(await api('/exemptions', { body: { task, ref, reason } })) } catch (x) { setErr(x) } finally { setBusy(false) }
  }
  return (
    <Card>
      <CardHeader title={t('co.exemption')} sub={t('co.exemption_sub')} icon={<FileSignature className="size-5" />} />
      <form onSubmit={submit} className="space-y-3 p-5">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="text-sm font-semibold">{t('common.task')}<select value={task} onChange={(e) => setTask(e.target.value)} className="mt-1 block h-11 w-full rounded-xl border border-line bg-surface px-3">{['P1', 'P2', 'P3', 'P4'].map((x) => <option key={x}>{x}</option>)}</select></label>
          <label className="text-sm font-semibold">{t('co.exemption_ref')}<input required minLength={4} value={ref} onChange={(e) => setRef(e.target.value)} placeholder="MOHRE-EX-0000" className="mt-1 block h-11 w-full rounded-xl border border-line bg-surface px-3" dir="ltr" /></label>
        </div>
        <label className="block text-sm font-semibold">{t('common.reason')}<input required minLength={5} value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t('co.exemption_reason_ph')} className="mt-1 block h-11 w-full rounded-xl border border-line bg-surface px-3" dir="auto" /></label>
        <p className="text-xs text-muted">{t('co.exemption_note')}</p>
        <Button type="submit" loading={busy} icon={<FileSignature className="size-4" />}>{t('co.exemption_record')}</Button>
        {err ? <ErrorNote error={err} /> : null}
        {res && <div className={cx('rounded-xl bg-ok-soft p-3 text-sm text-ok')}>{t('co.exemption_done', { ref: res.ref })}</div>}
      </form>
    </Card>
  )
}

function statusText(s: string, lang: string) {
  if (lang !== 'ar') return s.replaceAll('_', ' ')
  const m: Record<string, string> = { in_place: 'قائم', live: 'مباشر', active: 'فعّال', monitored: 'مراقَب', capacity_checked: 'تم فحص السعة', covered: 'مغطى', enforced: 'مُطبّق', '1 overdue': '1 متأخر' }
  return m[s] ?? s
}
function dutyAr(s: string) {
  const m: Record<string, string> = {
    'Heat-stress programme (CoP 11.0 §3.1.1(e))': 'برنامج الإجهاد الحراري (مدونة 11.0 §3.1.1(e))',
    'TWL assessment and zone controls (§3.1.1(f))': 'تقييم TWL وضوابط المناطق (§3.1.1(f))',
    'Acclimatization programme (§3.2(b)(i))': 'برنامج التأقلم (§3.2(b)(i))',
    'Potable water and electrolytes near work (§3.2(b)(v))': 'ماء الشرب والأملاح قرب العمل (§3.2(b)(v))',
    'Shaded work, cooled rest and midday shelters (§3.2(c))': 'العمل المظلل والراحة المكيفة ومظلات منتصف النهار (§3.2(c))',
    'Training within 10 days (§2(d))': 'التدريب خلال 10 أيام (§2(d))',
    'Medical attention and first aid within 3 minutes (§3.1.1(l))': 'الرعاية الطبية والإسعاف خلال 3 دقائق (§3.1.1(l))',
    'Midday break 12:30-15:00 (MoHRE)': 'استراحة منتصف النهار 12:30-15:00 (الموارد البشرية والتوطين)',
  }
  // Section references are left-to-right islands inside Arabic text (Unicode isolates keep their order).
  return (m[s] ?? s).replace(/(§[\d.]+(?:\([a-z]+\))*)/g, '\u2066$1\u2069')
}
function evidenceAr(s: string) {
  const m: Record<string, string> = {
    'Programme record': 'سجل البرنامج', 'Instrument records every 5 min (simulated)': 'سجلات الأجهزة كل 5 دقائق (محاكاة)',
    'Daily reviews': 'مراجعات يومية', 'Water-point checks and worker disputes': 'فحوص نقاط الماء واعتراضات العمال',
    'Capacity certificate': 'شهادة السعة', 'Training register': 'سجل التدريب', '3 responders on shift; drill pending': '3 مسعفين في الوردية؛ التمرين قيد الانتظار',
    'Rule engine + daily report': 'محرك القواعد + تقرير يومي',
  }
  return m[s] ?? s
}
