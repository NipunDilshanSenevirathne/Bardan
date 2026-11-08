/* Drill console (finalsystem.md §29.7; docs/DRILL-PROTOCOL.md). The observer runs counterbalanced drills, records what
   they see, and exports the result. Nothing here is simulated: times are real and come from the observer or the ledger. */
import { useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle2, ClipboardCopy, Download, Eye, EyeOff, Flag, Play, QrCode, ShieldAlert, Square, Timer, Undo2, Users,
} from 'lucide-react'
import QRCode from 'qrcode'
import { useEffect, useMemo, useState } from 'react'
import { DrillSummary, DrillTable } from '../../components/DrillResults'
import { Badge, Button, Card, CardHeader, ErrorNote, PageHeader, Skeleton, Toggle, cx } from '../../components/ui'
import { api, startSession } from '../../lib/api'
import { useApi, useRole } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'

const MARKS = ['reported', 'fix_started', 'reported_fixed', 'restored_seen', 'independent_check', 'false_report_caught'] as const
const LOCAL = 'bardan.drills.backup.v1'

function clockText(s: number) {
  const m = Math.floor(s / 60)
  const r = Math.floor(s % 60)
  return `${m}:${String(r).padStart(2, '0')}`
}

function minuteText(min: number | null | undefined) {
  if (min == null) return '–'
  return clockText(Math.max(0, Math.round(min * 60)))
}

export default function DrillConsole() {
  const { t } = useI18n()
  const role = useRole()
  const [fast, setFast] = useState(false)
  // The shell already reads the sandbox state; it says whether this sandbox holds a drill series.
  const st = useApi<any>(role === 'auditor' ? '/sandbox/state' : null, { refetch: 10000 })
  const hasSeries = !!st.data?.drill
  const q = useApi<any>(role === 'auditor' && hasSeries ? '/drills/series' : null, { refetch: fast ? 2000 : 8000 })
  const running = useMemo(() => (q.data?.drills ?? []).find((d: any) => d.state === 'running'), [q.data])
  useEffect(() => { setFast(!!running) }, [running])

  if (role !== 'auditor') return <Card className="p-6 text-sm">{t('dc.not_auditor')}</Card>
  const noSeries = (!!st.data && !hasSeries) || (q.error as any)?.status === 404
  return (
    <div className="space-y-6">
      <PageHeader title={t('dc.title')} sub={t('dc.sub')} icon={<Timer className="size-6" />}
        actions={q.data ? <ExportButton /> : undefined} />
      <Safety />
      {(st.isLoading || (hasSeries && q.isLoading)) && <Skeleton className="h-64" />}
      {noSeries && <Setup />}
      {st.error ? <ErrorNote error={st.error} /> : null}
      {q.error && !noSeries ? <ErrorNote error={q.error} /> : null}
      {q.data && <Series s={q.data} running={running} />}
    </div>
  )
}

function Safety() {
  const { t } = useI18n()
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-stop/30 bg-stop-soft/40 p-4 text-sm">
      <ShieldAlert className="mt-0.5 size-5 shrink-0 text-stop" aria-hidden />
      <div><div className="font-bold">{t('dc.safety.title')}</div><p className="mt-1 leading-relaxed">{t('dc.safety.b')}</p></div>
    </div>
  )
}

/* ------------------------------------------------------------------ setup */
function Setup() {
  const { t } = useI18n()
  const qc = useQueryClient()
  const [label, setLabel] = useState('')
  const [scenario, setScenario] = useState<'water_out' | 'shade_full'>('water_out')
  const [perArm, setPerArm] = useState(2)
  const [target, setTarget] = useState(20)
  const [probes, setProbes] = useState(true)
  const [people, setPeople] = useState(4)
  const [langs, setLangs] = useState<string[]>(['en'])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<unknown>(null)
  useEffect(() => { setTarget(scenario === 'water_out' ? 20 : 25) }, [scenario])
  async function create() {
    setBusy(true); setErr(null)
    try {
      const r = await api<any>('/drills/series', { body: { label, scenario, per_arm: perArm, deadline_min: target, probes, people, languages: langs } })
      await startSession('reviewer', r.sandbox_id)
      await qc.invalidateQueries()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  const field = 'h-11 w-full rounded-xl border border-line bg-surface px-3 text-sm'
  return (
    <Card>
      <CardHeader title={t('dc.setup.title')} sub={t('dc.setup.note')} icon={<Flag className="size-5" />} />
      <div className="grid grid-cols-1 gap-5 p-5 md:grid-cols-2">
        <label className="space-y-1.5 text-sm font-semibold md:col-span-2">{t('dc.setup.label')}
          <input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={80} placeholder={t('dc.setup.label_ph')} className={field} />
        </label>
        <fieldset className="space-y-2 md:col-span-2">
          <legend className="text-sm font-semibold">{t('dc.setup.scenario')}</legend>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {(['water_out', 'shade_full'] as const).map((s) => (
              <button key={s} type="button" onClick={() => setScenario(s)} aria-pressed={scenario === s}
                className={cx('rounded-xl border p-3 text-start text-sm font-semibold', scenario === s ? 'border-brand bg-brand-soft' : 'border-line hover:bg-surface-2')}>
                {t(`dc.sc.${s}`)}
              </button>
            ))}
          </div>
        </fieldset>
        <label className="space-y-1.5 text-sm font-semibold">{t('dc.setup.per_arm')}
          <select value={perArm} onChange={(e) => setPerArm(Number(e.target.value))} className={field}>
            {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="space-y-1.5 text-sm font-semibold">{t('dc.setup.target')}
          <input type="number" min={5} max={60} value={target} onChange={(e) => setTarget(Math.max(5, Math.min(60, Number(e.target.value) || 5)))} className={field} />
          <span className="block text-xs font-normal text-muted">{t('dc.setup.target_b')}</span>
        </label>
        <label className="space-y-1.5 text-sm font-semibold">{t('dc.setup.people')}
          <input type="number" min={2} max={40} value={people} onChange={(e) => setPeople(Math.max(2, Math.min(40, Number(e.target.value) || 2)))} className={field} />
        </label>
        <fieldset className="space-y-1.5">
          <legend className="text-sm font-semibold">{t('dc.setup.langs')}</legend>
          <div className="flex gap-2">
            {[['en', 'English'], ['ar', 'العربية']].map(([k, n]) => (
              <button key={k} type="button" aria-pressed={langs.includes(k)}
                onClick={() => setLangs((x) => x.includes(k) ? (x.length > 1 ? x.filter((y) => y !== k) : x) : [...x, k])}
                className={cx('h-11 rounded-xl border px-4 text-sm font-semibold', langs.includes(k) ? 'border-brand bg-brand-soft' : 'border-line')}>{n}</button>
            ))}
          </div>
        </fieldset>
        <div className="rounded-2xl border border-line p-1 md:col-span-2">
          <Toggle checked={probes} onChange={setProbes} label={t('dc.setup.probes')} sub={t('dc.setup.probes_b')} />
        </div>
        {err ? <div className="md:col-span-2"><ErrorNote error={err} /></div> : null}
        <div className="md:col-span-2"><Button onClick={create} loading={busy} icon={<Play className="size-4" />}>{t('dc.setup.create')}</Button></div>
      </div>
    </Card>
  )
}

/* ----------------------------------------------------------------- series */
function Series({ s, running }: { s: any; running: any }) {
  const { t } = useI18n()
  const next = s.drills.find((d: any) => d.state === 'planned')
  // Keep a copy on this device after each drill, in case the server restarts between drills.
  const ended = s.drills.filter((d: any) => d.state !== 'planned' && d.state !== 'running').length
  useEffect(() => {
    if (!ended) return
    void api<any>('/drills/export').then((body) => { try { localStorage.setItem(LOCAL, JSON.stringify(body)) } catch { /* storage full */ } }).catch(() => {})
  }, [ended])
  return (
    <>
      {running ? <Running s={s} d={running} /> : next ? <Next s={s} d={next} /> : (
        <Card className="p-5">
          <div className="flex items-center gap-2 font-bold"><CheckCircle2 className="size-5 text-ok" />{t('dc.done.title')}</div>
          <p className="mt-1 text-sm text-muted">{t('dc.done.b')}</p>
          <div className="mt-3"><ExportButton /></div>
        </Card>
      )}
      <Invites sandboxId={s.sandbox_id} />
      <Card>
        <CardHeader title={t('dc.results.title')} sub={s.label || undefined} icon={<Users className="size-5" />} />
        <div className="space-y-4 p-5">
          <DrillTable drills={s.drills} />
          <DrillSummary summary={s.summary} />
          <p className="text-xs text-muted">{t('dc.saved_local')}</p>
        </div>
      </Card>
    </>
  )
}

function Next({ s, d }: { s: any; d: any }) {
  const { t } = useI18n()
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<unknown>(null)
  async function start() {
    setBusy(true); setErr(null)
    try { await api('/drills/start', { body: { drill_id: d.id } }); await qc.invalidateQueries() } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  return (
    <Card className="border-brand/40">
      <CardHeader title={t('dc.next.title', { i: d.index, n: s.drills.length })} sub={<span className="font-semibold">{t(`dr.arm.${d.arm}`)} · {t(`dc.sc.${d.scenario}`)}</span>} icon={<Flag className="size-5" />} />
      <div className="space-y-4 p-5">
        <div className="rounded-2xl bg-surface-2 p-4">
          <div className="text-xs font-semibold text-muted">{t('dc.brief')}</div>
          <p className="mt-1 text-base leading-relaxed">{t(`dc.brief.${d.arm}`)} {t(`dc.brief.failure.${d.scenario}`)}</p>
        </div>
        <div className={cx('rounded-2xl border p-4 text-sm', d.probe ? 'border-sun/40 bg-sun-soft' : 'border-line')}>
          <div className="text-xs font-semibold text-muted">{t('dc.private.title')}</div>
          <p className="mt-1 font-semibold">{d.probe ? t('dc.private.b') : t('dc.private.none')}</p>
        </div>
        {err ? <ErrorNote error={err} /> : null}
        <Button size="lg" onClick={start} loading={busy} icon={<Play className="size-5" />}>{t('dc.start', { i: d.index })}</Button>
      </div>
    </Card>
  )
}

function Running({ s, d }: { s: any; d: any }) {
  const { t } = useI18n()
  const qc = useQueryClient()
  const [now, setNow] = useState(() => Date.now())
  const [fetchedAt, setFetchedAt] = useState(() => Date.now())
  const [notes, setNotes] = useState('')
  const [stopOpen, setStopOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<unknown>(null)
  useEffect(() => { setFetchedAt(Date.now()) }, [d.elapsed_s])
  useEffect(() => { const h = setInterval(() => setNow(Date.now()), 500); return () => clearInterval(h) }, [])
  const elapsed = (d.elapsed_s ?? 0) + Math.max(0, (now - fetchedAt) / 1000)
  const left = d.deadline_min * 60 - elapsed
  async function call(path: string, body: any, key: string) {
    setBusy(key); setErr(null)
    try { await api(path, { body }); await qc.invalidateQueries() } catch (e) { setErr(e) } finally { setBusy(null) }
  }
  const marks = MARKS.filter((m) => m !== 'false_report_caught' || d.probe)
  return (
    <Card className="border-stop/40">
      <CardHeader title={t('dc.running', { i: d.index })} sub={<span className="font-semibold">{t(`dr.arm.${d.arm}`)} · {t(`dc.sc.${d.scenario}`)}</span>} icon={<Timer className="size-5 text-stop" />} />
      <div className="space-y-5 p-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-xs font-semibold text-muted">{t('dc.elapsed')}</div>
            <div className="num text-5xl font-bold tabular-nums" dir="ltr" aria-live="off">{clockText(elapsed)}</div>
          </div>
          <Badge tone={left > 0 ? 'warn' : 'stop'}>{left > 0 ? t('dc.target_in', { m: Math.ceil(left / 60) }) : t('dc.target_passed')}</Badge>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-surface-3" aria-hidden>
          <div className={cx('h-full rounded-full', left > 0 ? 'bg-warn' : 'bg-stop')} style={{ width: `${Math.min(100, (elapsed / (d.deadline_min * 60)) * 100)}%` }} />
        </div>
        {d.probe && <div className="rounded-xl border border-sun/40 bg-sun-soft px-3 py-2 text-sm font-semibold">{t('dc.private.title')}: {t('dc.private.b')}</div>}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {marks.map((m) => {
            const own = d.marks?.[m]
            const sys = d.system_marks?.[m]
            const minute = own ? (Date.parse(own.at) - Date.parse(d.started_at)) / 60000 : sys ? (Date.parse(sys.at) - Date.parse(d.started_at)) / 60000 : null
            const primary = m === 'restored_seen'
            return (
              <div key={m} className={cx('flex items-center gap-2 rounded-2xl border p-2', own ? 'border-brand bg-brand-soft' : sys ? 'border-ok/40 bg-ok-soft' : 'border-line')}>
                <button onClick={() => call(`/drills/${d.id}/mark`, { mark: m }, m)} disabled={busy === m}
                  className={cx('flex min-h-14 flex-1 flex-col items-start justify-center rounded-xl px-3 text-start', primary ? 'font-bold' : 'font-semibold')}>
                  <span className="text-sm">{t(`dc.mark.${m}`)}</span>
                  <span className="text-xs text-muted">{minute == null ? t('dc.mark.tap') : <><span className="num font-bold text-ink" dir="ltr">+{minuteText(minute)}</span> · {own ? t('dc.mark.observer') : t('dc.mark.system')}</>}</span>
                </button>
                {own && <button onClick={() => call(`/drills/${d.id}/mark`, { mark: m, undo: true }, `u-${m}`)} className="grid size-11 place-items-center rounded-xl hover:bg-surface-2" aria-label={t('dc.mark.undo')}><Undo2 className="size-4" /></button>}
              </div>
            )
          })}
        </div>
        {d.arm === 'bardan' && (
          <div className="rounded-2xl border border-line">
            <div className="border-b border-line px-4 py-2 text-xs font-semibold text-muted">{t('dc.feed.title')}</div>
            {d.feed?.length ? (
              <ol className="divide-y divide-line text-sm">
                {d.feed.map((e: any, i: number) => (
                  <li key={i} className="flex items-center justify-between gap-3 px-4 py-2">
                    <span>{t(`dc.ev.${e.kind}`)} <span className="text-xs text-muted">· {t(`role.${e.role}`)}</span></span>
                    <span className="num font-semibold" dir="ltr">+{minuteText(e.minute)}</span>
                  </li>
                ))}
              </ol>
            ) : <p className="px-4 py-3 text-sm text-muted">{t('dc.feed.empty')}</p>}
          </div>
        )}
        <label className="block space-y-1.5 text-sm font-semibold">{t('dc.notes')}
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={300} rows={2} className="w-full rounded-xl border border-line bg-surface p-3 text-sm font-normal" />
        </label>
        {err ? <ErrorNote error={err} /> : null}
        <div className="flex flex-wrap gap-2">
          <Button size="lg" onClick={() => call(`/drills/${d.id}/end`, { notes }, 'end')} loading={busy === 'end'} icon={<Square className="size-5" />}>{t('dc.end')}</Button>
          <Button variant="ghost" onClick={() => setStopOpen((v) => !v)}>{t('dc.abandon')}</Button>
        </div>
        {stopOpen && (
          <div className="flex flex-wrap items-end gap-2 rounded-2xl border border-line p-3">
            <label className="min-w-56 flex-1 space-y-1.5 text-sm font-semibold">{t('dc.abandon_reason')}
              <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={200} className="h-11 w-full rounded-xl border border-line bg-surface px-3 text-sm font-normal" />
            </label>
            <Button variant="outline" disabled={reason.trim().length < 4} loading={busy === 'abandon'} onClick={() => call(`/drills/${d.id}/abandon`, { reason }, 'abandon')}>{t('dc.abandon')}</Button>
          </div>
        )}
      </div>
    </Card>
  )
}

/* ---------------------------------------------------------------- invites */
const INVITES = [
  { persona: 'ravi', role: 'worker', lang: 'English' },
  { persona: 'anwar', role: 'worker', lang: 'العربية' },
  { persona: 'joseph', role: 'supervisor', lang: 'English' },
  { persona: 'sara', role: 'hse', lang: 'العربية' },
]

function Invites({ sandboxId }: { sandboxId: string }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(true)
  return (
    <Card>
      <CardHeader title={t('dc.invite.title')} sub={t('dc.invite.b')} icon={<QrCode className="size-5" />}
        action={<button onClick={() => setOpen((v) => !v)} className="grid size-10 place-items-center rounded-xl hover:bg-surface-2" aria-label={t('dc.invite.title')}>{open ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button>} />
      {open && (
        <div className="grid grid-cols-1 gap-3 p-5 sm:grid-cols-2 xl:grid-cols-4">
          {INVITES.map((i) => <Invite key={i.persona} sandboxId={sandboxId} persona={i.persona} role={i.role} lang={i.lang} />)}
        </div>
      )}
    </Card>
  )
}

function Invite({ sandboxId, persona, role, lang }: { sandboxId: string; persona: string; role: string; lang: string }) {
  const { t } = useI18n()
  const url = `${location.origin}/start?join=${sandboxId}&as=${persona}`
  const [qr, setQr] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  useEffect(() => { void QRCode.toDataURL(url, { margin: 1, width: 240 }).then(setQr) }, [url])
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-line p-3 text-center">
      <div className="text-sm font-bold">{t(`dc.role.${role}`)}</div>
      <div className="text-xs text-muted">{lang}</div>
      {qr && <img src={qr} alt={`QR code: ${t(`dc.role.${role}`)}`} className="size-36 rounded-xl bg-white p-1.5" />}
      <Button size="sm" variant="soft" icon={<ClipboardCopy className="size-4" />}
        onClick={async () => { try { await navigator.clipboard.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch { /* no clipboard */ } }}>
        {copied ? t('dc.invite.copied') : t('dc.invite.copy')}
      </Button>
    </div>
  )
}

function ExportButton() {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)
  async function go() {
    setBusy(true)
    try {
      const body = await api<any>('/drills/export')
      const blob = new Blob([JSON.stringify(body, null, 1)], { type: 'application/json' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `bardan-drills-${body.series.id}.json`
      a.click()
      setTimeout(() => URL.revokeObjectURL(a.href), 2000)
    } finally { setBusy(false) }
  }
  return <Button variant="outline" onClick={go} loading={busy} icon={<Download className="size-4" />}>{t('dc.export')}</Button>
}
