import { CalendarCheck2, Droplets, FileHeart, HeartPulse, Lock, Microscope } from 'lucide-react'
import { Badge, Card, CardHeader, Empty, ErrorNote, PageHeader, Skeleton } from '../../components/ui'
import { fmtDate, useApi } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'

export default function Health() {
  const { t, lang } = useI18n()
  const q = useApi<any>('/worker/health')
  if (q.isLoading) return <Skeleton className="h-96" />
  if (q.error) return <ErrorNote error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <PageHeader title={t('h.title')} sub={t('h.sub')} icon={<Lock className="size-6" />} />
      <div className="rounded-2xl border border-line bg-surface-2 p-4 text-sm font-semibold">{d.consent_message}</div>
      {!d.enrolled && <div className="rounded-2xl border border-brand/30 bg-brand-soft p-4 text-sm text-brand">{t('h.not_enrolled')}</div>}
      <Card>
        <CardHeader title={t('h.results')} icon={<Microscope className="size-5" />} action={<Badge tone="sun">{d.label}</Badge>} />
        <div className="p-5">
          {d.results.length === 0 ? <Empty>{t('h.no_results')}</Empty> : (
            <ul className="space-y-3">
              {d.results.map((r: any) => (
                <li key={r.id} className="rounded-2xl border border-line p-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-semibold">{r.label}</span>
                    <span className="num text-xl font-bold" dir="ltr">{r.value} <span className="text-sm text-muted">{r.unit}</span></span>
                  </div>
                  <div className="mt-1 text-xs text-muted">{fmtDate(r.specimen_at, lang)} · {r.method} · {r.lab}</div>
                  <div className="mt-2"><Badge tone="ok">{r.verification}</Badge></div>
                </li>
              ))}
            </ul>
          )}
          {d.result_message && <p className="mt-4 rounded-2xl bg-cyan-soft p-4 text-sm font-semibold text-cyan">{d.result_message}</p>}
        </div>
      </Card>
      <Card>
        <CardHeader title={t('h.referrals')} icon={<CalendarCheck2 className="size-5" />} />
        <div className="p-5">
          {d.referrals.length === 0 ? <Empty>{t('common.none')}</Empty> : d.referrals.map((r: any) => (
            <div key={r.id} className="mb-3 rounded-2xl border border-line p-4 text-sm">
              <div className="flex flex-wrap justify-between gap-2"><span className="font-semibold">{r.id}</span><Badge tone="brand">{r.state}</Badge></div>
              {r.appointment && <div className="mt-2" dir="ltr">{r.appointment.start.slice(0, 16).replace('T', ' ')} – {r.appointment.end.slice(11, 16)} · {r.appointment.place}</div>}
            </div>
          ))}
        </div>
      </Card>
      <Card>
        <CardHeader title={t('h.hydration')} icon={<Droplets className="size-5" />} />
        <div className="p-5">{d.hydration.length === 0 ? <Empty>{t('common.none')}</Empty> : d.hydration.map((h: any) => (
          <div key={h.id} className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-surface-2 p-3 text-sm">
            <span dir="ltr">{h.at.slice(0, 16).replace('T', ' ')}</span><span className="num font-bold">USG {h.reading.usg}</span><Badge tone="neutral">{h.action_level}</Badge>
          </div>))}
        </div>
      </Card>
      <Card>
        <CardHeader title={t('h.summaries')} icon={<FileHeart className="size-5" />} />
        <div className="p-5">{d.summaries.length === 0 ? <Empty icon={<HeartPulse className="size-6" />}>{t('common.none')}</Empty> : d.summaries.map((s: any) => (
          <p key={s.id} dir="auto" className="mb-2 rounded-xl bg-surface-2 p-4 text-sm leading-relaxed">{s.summary}</p>))}
        </div>
      </Card>
    </div>
  )
}
