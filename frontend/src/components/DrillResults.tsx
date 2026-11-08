/* Observed drill results: per way of working, then drill by drill. Small numbers, shown as they are. */
import { useI18n } from '../lib/i18n'
import { L } from '../lib/labels'
import { Badge, cx } from './ui'

const ARMS = ['current', 'bardan'] as const

function spread(t: (k: string, v?: Record<string, string | number>) => string, s: any) {
  if (!s || !s.n) return '–'
  if (s.n === 1) return t('dr.s.single', { v: s.median })
  return t('dr.s.median_range', { median: s.median, min: s.min, max: s.max, n: s.n })
}

function mm(v: number | null | undefined) {
  return v == null ? '–' : (Math.round(v * 10) / 10).toString()
}

export function DrillSummary({ summary }: { summary: any }) {
  const { t, lang } = useI18n()
  if (!summary) return null
  const a = summary.arms
  const rows: { k: string; f: (x: any) => string }[] = [
    { k: 'dr.s.drills', f: (x) => String(x.drills_run) },
    { k: 'dr.s.restored', f: (x) => spread(t, x.minutes_to_restored) },
    { k: 'dr.s.verified', f: (x) => spread(t, x.minutes_to_verified) },
    { k: 'dr.s.not_verified', f: (x) => String(x.not_verified) },
    { k: 'dr.s.verified_by_deadline', f: (x) => t('dr.s.k_of_n', x.verified_by_deadline) },
    { k: 'dr.s.false_reports', f: (x) => x.false_reports.n ? t('dr.s.k_of_n', { k: x.false_reports.caught, n: x.false_reports.n }) : '–' },
    { k: 'dr.s.false_confirmations', f: (x) => String(x.false_confirmations) },
  ]
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-2xl border border-line">
        <table className="w-full min-w-[520px] text-sm">
          <thead className="bg-surface-2 text-xs text-muted">
            <tr><th className="px-4 py-2 text-start" />{ARMS.map((arm) => <th key={arm} className="px-4 py-2 text-end">{t(`dr.arm.${arm}`)}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((r) => (
              <tr key={r.k}>
                <td className="px-4 py-2">{t(r.k, { m: summary.deadline_min })}</td>
                {ARMS.map((arm) => <td key={arm} className="num px-4 py-2 text-end font-semibold" dir="ltr">{r.f(a[arm])}</td>)}
              </tr>
            ))}
            <tr>
              <td className="px-4 py-2">{t('dr.s.app_use')}</td>
              <td className="num px-4 py-2 text-end font-semibold">{a.current.app_actions_in_current_arm ?? 0}</td>
              <td className="px-4 py-2 text-end text-muted">–</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <Badge tone={summary.order_followed ? 'ok' : 'warn'}>{t(summary.order_followed ? 'dr.s.order' : 'dr.s.order_not')}</Badge>
        <span>{t('dr.s.too_few')}</span>
      </div>
      <p className="text-xs text-muted">{L(summary.label, lang)}</p>
    </div>
  )
}

export function DrillTable({ drills }: { drills: any[] }) {
  const { t } = useI18n()
  return (
    <div className="overflow-x-auto rounded-2xl border border-line">
      <table className="w-full min-w-[640px] text-sm">
        <thead className="bg-surface-2 text-xs text-muted">
          <tr>
            <th className="px-3 py-2 text-start">{t('dr.d.n')}</th>
            <th className="px-3 py-2 text-start">{t('dr.d.arm')}</th>
            <th className="px-3 py-2 text-start">{t('dr.d.false_report')}</th>
            <th className="px-3 py-2 text-end">{t('dr.d.restored')}</th>
            <th className="px-3 py-2 text-end">{t('dr.d.verified')}</th>
            <th className="px-3 py-2 text-start">{t('dr.d.by_target')}</th>
            <th className="px-3 py-2 text-end">{t('dr.d.caught')}</th>
            <th className="px-3 py-2 text-start">{t('dr.d.notes')}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {drills.map((d) => {
            const o = d.outcome
            return (
              <tr key={d.id} className={cx(d.state === 'abandoned' && 'text-muted line-through decoration-1')}>
                <td className="num px-3 py-2">{d.index}</td>
                <td className="px-3 py-2">
                  <span className="font-semibold">{t(`dr.arm.${d.arm}`)}</span>
                  {d.state !== 'ended' && <span className="ms-2"><Badge tone={d.state === 'running' ? 'stop' : 'neutral'}>{t(`dr.d.state.${d.state}`)}</Badge></span>}
                </td>
                <td className="px-3 py-2">{d.probe == null ? <span className="text-muted">{t('dr.sealed')}</span> : t(d.probe ? 'dr.yes' : 'dr.no')}</td>
                <td className="num px-3 py-2 text-end" dir="ltr">{mm(o?.minutes_to_restored)}</td>
                <td className="num px-3 py-2 text-end" dir="ltr">{mm(o?.minutes_to_verified)}{o?.false_confirmation ? ' *' : ''}</td>
                <td className="px-3 py-2">{o ? <Badge tone={o.verified_by_deadline ? 'ok' : 'stop'}>{t(o.verified_by_deadline ? 'dr.yes' : 'dr.no')}</Badge> : '–'}</td>
                <td className="num px-3 py-2 text-end" dir="ltr">{o?.probe ? (o.false_report_caught ? mm(o.minutes_to_caught) : t('dr.no')) : '–'}</td>
                <td className="max-w-56 px-3 py-2 text-xs text-muted" dir="auto">{d.abandon_reason ?? d.notes ?? ''}{o?.false_confirmation ? ` * ${t('dr.s.false_confirmations')}` : ''}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
