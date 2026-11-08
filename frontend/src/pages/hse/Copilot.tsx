import { Ban, Database, Fingerprint, Search, ShieldCheck, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge, Button, Card, ErrorNote, PageHeader, Pre, TierChip, cx } from '../../components/ui'
import { api } from '../../lib/api'
import { useI18n } from '../../lib/i18n'

type Turn = { q: string; r: any }

export default function Copilot() {
  const { t } = useI18n()
  const [q, setQ] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<unknown>(null)
  async function ask(question: string) {
    if (!question.trim()) return
    setBusy(true); setErr(null)
    try {
      const r = await api('/copilot/query', { body: { question } })
      setTurns((x) => [{ q: question, r }, ...x])
      setQ('')
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader title={t('co.title')} sub={t('co.sub')} icon={<Sparkles className="size-6" />} />
      <form onSubmit={(e) => { e.preventDefault(); void ask(q) }} className="flex gap-2">
        <label htmlFor="coq" className="sr-only">{t('co.placeholder')}</label>
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute start-4 top-1/2 size-5 -translate-y-1/2 text-muted" />
          <input id="coq" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('co.placeholder')} dir="auto"
            className="h-14 w-full rounded-2xl border border-line bg-surface ps-12 pe-4 shadow-card" />
        </div>
        <Button type="submit" size="lg" className="h-14" loading={busy}>{t('co.ask')}</Button>
      </form>
      <div className="flex flex-wrap gap-2">
        {['co.s1', 'co.s2', 'co.s4', 'co.s5', 'co.s7', 'co.s3', 'co.s6', 'co.s8'].map((k) => (
          <button key={k} onClick={() => ask(t(k))} className={cx('rounded-full border px-3.5 py-2 text-sm font-semibold transition-colors',
            ['co.s3', 'co.s6', 'co.s8'].includes(k) ? 'border-stop/30 text-stop hover:bg-stop-soft' : 'border-line hover:border-brand hover:bg-brand-soft')}>{t(k)}</button>
        ))}
      </div>
      {err ? <ErrorNote error={err} /> : null}
      <div className="space-y-5">
        {turns.map((x, i) => <Answer key={turns.length - i} turn={x} />)}
      </div>
    </div>
  )
}

function Answer({ turn }: { turn: Turn }) {
  const { t } = useI18n()
  const r = turn.r
  const refused = r.decision === 'refused'
  const cols: string[] = r.rows?.length ? [...new Set<string>(r.rows.flatMap((row: any) => Object.keys(row)))] : []
  return (
    <Card className={cx(refused && 'border-stop/40')}>
      <div className="border-b border-line px-5 py-4">
        <div className="text-xs font-semibold text-muted">{t('co.you_asked')}</div>
        <div className="mt-0.5 font-semibold" dir="auto">{turn.q}</div>
      </div>
      <div className="space-y-4 p-5">
        <div className="flex items-start gap-3">
          <div className={cx('grid size-10 shrink-0 place-items-center rounded-xl', refused ? 'bg-stop-soft text-stop' : 'bg-brand-soft text-brand')}>{refused ? <Ban className="size-5" /> : <Database className="size-5" />}</div>
          <div className="min-w-0 flex-1">
            <p className="text-base font-semibold leading-relaxed" dir="auto">{r.text}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {refused ? <Badge tone="stop" icon={<Ban className="size-3" />}>{t('co.refused')} · {t(`rule.${r.rule}`)}</Badge>
                : <Badge tone={r.source === 'ai_assisted' ? 'cyan' : 'neutral'}>{r.source === 'ai_assisted' ? t('a.ai') : t('co.deterministic')}</Badge>}
              {r.numeric_grounding === 'pass' && <Badge tone="ok" icon={<ShieldCheck className="size-3" />}>{t('co.grounded')}</Badge>}
              {r.period && <Badge tone="neutral"><span dir="ltr">{r.period[0]} → {r.period[1]}</span></Badge>}
              {r.suppression && <Badge tone="neutral">{t('co.suppression')}: n ≥ {r.suppression.min_cell}{r.suppression.applied ? ` · ${t('co.applied')}` : ''}</Badge>}
            </div>
          </div>
        </div>
        {r.rows?.length > 0 && (
          <div className="relative scroll-thin overflow-x-auto rounded-xl border border-line">
            <table className="w-full text-sm">
              <thead className="bg-surface-2 text-xs text-muted"><tr>{cols.map((c) => <th key={c} className="px-3 py-2 text-start font-semibold">{t(`col.${c}`)}</th>)}</tr></thead>
              <tbody className="divide-y divide-line">
                {r.rows.map((row: any, i: number) => (
                  <tr key={i} className={cx(row.suppressed && 'bg-surface-2/60')}>{cols.map((c) => <td key={c} className="num px-3 py-2">{c === 'suppressed' ? (row.suppressed ? <Badge tone="neutral">{t(`co.supp.${row.suppressed}`)}</Badge> : '') : cell(row[c], !!row.suppressed)}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {r.sources?.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-xs"><span className="font-semibold text-muted">{t('common.sources')}:</span>{r.sources.map((s: string) => <code key={s} className="rounded-md bg-surface-2 px-1.5 py-0.5" dir="ltr">{s}</code>)}</div>
        )}
        <details className="rounded-xl border border-line p-3 text-sm">
          <summary className="cursor-pointer font-semibold">{t('co.query')}</summary>
          <Pre>{JSON.stringify(r.plan, null, 2)}</Pre>
          {r.query_hash && <div className="mt-2 flex items-center gap-2 text-xs text-muted"><Fingerprint className="size-3.5" />{t('co.hash')}: <code dir="ltr">{r.query_hash}</code></div>}
          <div className="mt-1 text-xs text-muted">{t('co.method')}: {r.method}</div>
        </details>
        {r.trace_id && <Link to="/app/trust" className="text-xs font-semibold text-brand underline">{t('tr.trace')} · {r.trace_id}</Link>}
      </div>
    </Card>
  )

  function cell(v: any, suppressed = false) {
    if (v === null || v === undefined) return <span className="text-muted" title={suppressed ? t('col.suppressed') : undefined}>{suppressed ? '—' : ''}</span>
    if (v && typeof v === 'object') {
      return <span className="flex flex-wrap gap-1">{Object.entries(v).map(([k, n]) => /^E\d$/.test(k) ? <span key={k} className="inline-flex items-center gap-1"><TierChip tier={k} /><span>×{String(n)}</span></span> : <span key={k}>{k}: {String(n)}</span>)}</span>
    }
    return <span dir="auto">{String(v)}</span>
  }
}
