import { Filter, Link2, ScrollText, ShieldCheck, ShieldX } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Badge, Card, ErrorNote, PageHeader, Skeleton, Tabs, cx } from '../../components/ui'
import { fmtTime, useActorNames, useApi } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'

export default function Audit() {
  const { t } = useI18n()
  const q = useApi<any>('/audit', { refetch: 15000 })
  const name = useActorNames()
  const [cat, setCat] = useState<string>('all')
  const [deniedOnly, setDeniedOnly] = useState(false)
  const entries: any[] = q.data?.entries ?? []
  const cats = useMemo(() => ['all', ...new Set(entries.map((e) => e.category))], [entries])
  const shown = entries.filter((e) => (cat === 'all' || e.category === cat) && (!deniedOnly || e.decision === 'denied')).slice().reverse()
  if (q.isLoading) return <Skeleton className="h-96" />
  if (q.error) return <ErrorNote error={q.error} onRetry={() => q.refetch()} />
  const v = q.data.verify
  return (
    <div className="space-y-6">
      <PageHeader title={t('audit.title')} sub={t('audit.sub')} icon={<ScrollText className="size-6" />} />
      <div className={cx('flex flex-wrap items-center gap-3 rounded-2xl border p-4', v.valid ? 'border-ok/40 bg-ok-soft' : 'border-stop/40 bg-stop-soft')}>
        {v.valid ? <ShieldCheck className="size-6 text-ok" /> : <ShieldX className="size-6 text-stop" />}
        <div className="min-w-0 flex-1">
          <div className={cx('font-bold', v.valid ? 'text-ok' : 'text-stop')}>{v.valid ? t('audit.valid') : t('audit.broken')}</div>
          <div className="text-xs text-ink-2">{t('audit.entries', { n: v.entries })} · {t('audit.scoped', { n: q.data.total })}</div>
        </div>
        <code className="max-w-full truncate rounded-lg bg-surface px-2 py-1 text-[11px]" dir="ltr"><Link2 className="me-1 inline size-3" />head {v.head?.slice(0, 24)}…</code>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Tabs value={cat} onChange={setCat} items={cats.map((c) => ({ id: c, label: c === 'all' ? t('common.all') : t(`audit.cat.${c}`) }))} />
        <button onClick={() => setDeniedOnly((x) => !x)} aria-pressed={deniedOnly} className={cx('inline-flex min-h-10 items-center gap-2 rounded-xl px-3 text-sm font-semibold', deniedOnly ? 'bg-stop text-white' : 'bg-surface-2')}>
          <Filter className="size-4" />{t('audit.denied_only')}
        </button>
      </div>
      <Card>
        <div className="relative scroll-thin overflow-x-auto">
          <table className="w-full min-w-[820px] text-sm">
            <thead className="bg-surface-2 text-xs text-muted"><tr>
              <th className="px-4 py-2.5 text-start font-semibold">#</th><th className="px-3 py-2.5 text-start font-semibold">{t('common.time')}</th>
              <th className="px-3 py-2.5 text-start font-semibold">{t('audit.who')}</th><th className="px-3 py-2.5 text-start font-semibold">{t('audit.action')}</th>
              <th className="px-3 py-2.5 text-start font-semibold">{t('audit.resource')}</th><th className="px-3 py-2.5 text-start font-semibold">{t('audit.decision')}</th>
              <th className="px-4 py-2.5 text-start font-semibold">{t('audit.hash')}</th></tr></thead>
            <tbody className="divide-y divide-line">
              {shown.map((e) => (
                <tr key={e.seq} className={cx(e.decision === 'denied' && 'bg-stop-soft/50')}>
                  <td className="num px-4 py-2 text-muted" dir="ltr">{e.seq}</td>
                  <td className="num px-3 py-2" dir="ltr">{e.at.slice(5, 10)} {fmtTime(e.at)}</td>
                  <td className="px-3 py-2"><div className="font-semibold">{name(e.actor)}</div><div className="text-xs text-muted">{t(`role.${e.role}`)}</div></td>
                  <td className="px-3 py-2"><code className="text-xs" dir="ltr">{e.action}</code>{e.reason && <div className="text-xs text-muted">{e.reason}</div>}</td>
                  <td className="px-3 py-2"><code className="text-xs" dir="ltr">{e.resource}</code>{e.subject && <div className="text-xs text-muted" dir="ltr">↳ {e.subject}</div>}</td>
                  <td className="px-3 py-2"><Badge tone={e.decision === 'denied' ? 'stop' : 'neutral'}>{e.decision === 'denied' ? t('audit.denied') : t('common.allowed')}</Badge></td>
                  <td className="px-4 py-2"><code className="text-[11px] text-muted" dir="ltr">{e.hash.slice(0, 10)}…</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
