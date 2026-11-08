import {
  AlertTriangle, CheckCircle2, ChevronDown, Clock3, FileCheck2, Flag, History, ListChecks, MessageSquareWarning,
  PlayCircle, Send, ShieldCheck, Undo2, UserCheck,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Badge, Button, Card, Empty, ErrorNote, PageHeader, Skeleton, Tabs, TierChip, cx } from '../../components/ui'
import { actOnce } from '../../lib/api'
import { fmtTime, useActorNames, useApi, useCan, useRole } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'

/* A finding typed without a full stop still reads as its own sentence before the next one. */
const endSentence = (s: string) => { const x = s.trim(); return !x || /[.!?؟…»”"')]$/.test(x) ? x : `${x}.` }

/* Evidence kinds that can support each action class (mirrors the server's scope check, B.5). */
const EVIDENCE: Record<string, string[]> = {
  WATER_RESTORE: ['supervisor_attestation', 'photo', 'water_point_check', 'independent_spot_check'],
  SHADE_EXTEND: ['supervisor_attestation', 'photo', 'capacity_record', 'independent_spot_check'],
  COOLING_FIX: ['supervisor_attestation', 'photo', 'instrument_record', 'independent_spot_check'],
  AC_FIX: ['supervisor_attestation', 'photo', 'room_temperature_record', 'independent_spot_check'],
  STOP_AFFECTED_WORK: ['supervisor_attestation', 'photo', 'instrument_record', 'independent_spot_check'],
  ENHANCED_SCHEDULE: ['supervisor_attestation', 'independent_spot_check'],
  CHECK_WORKER: ['supervisor_attestation'],
  NEW_WORKER_REVIEW: ['review_record', 'supervisor_attestation'],
  TRAINING_DUE: ['training_record'],
  MOVE_TO_SHADED_TASK: ['supervisor_attestation', 'independent_spot_check'],
  BREAK_ACCESS: ['supervisor_attestation', 'independent_spot_check'],
  HSE_REVIEW: ['review_record'],
  CLINIC_TRANSPORT: ['supervisor_attestation'],
}
const TIER: Record<string, string> = {
  acknowledgement: 'E1', supervisor_attestation: 'E2', worker_confirmation: 'E2', review_record: 'E2', training_record: 'E2',
  photo: 'E3', photo_old: 'E3', water_point_check: 'E3', capacity_record: 'E3', instrument_record: 'E3', room_temperature_record: 'E3',
  independent_spot_check: 'E4',
}
const OPEN = new Set(['assigned', 'accepted', 'in_progress', 'reported_complete', 'disputed', 'escalated', 'reopened'])
const PRIORITY: Record<string, number> = { escalated: 0, disputed: 1, assigned: 2, reopened: 2, accepted: 3, in_progress: 4, reported_complete: 5, verified: 8, cancelled: 9 }

export default function Tasks() {
  const { t } = useI18n()
  const q = useApi<any>('/tasks', { refetch: 10000 })
  const [filter, setFilter] = useState<'open' | 'all'>('open')
  const tasks: any[] = q.data?.tasks ?? []
  const shown = useMemo(() => tasks
    .filter((x) => filter === 'all' || OPEN.has(x.state))
    .sort((a, b) => (PRIORITY[a.state] ?? 6) - (PRIORITY[b.state] ?? 6) || b.created_at.localeCompare(a.created_at)), [tasks, filter])
  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const x of tasks) c[x.state] = (c[x.state] ?? 0) + 1
    return c
  }, [tasks])

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader title={t('t.title')} sub={t('t.sub')} icon={<ListChecks className="size-6" />}
        actions={<Tabs value={filter} onChange={setFilter} items={[{ id: 'open', label: `${t('t.filter.open')} · ${tasks.filter((x) => OPEN.has(x.state)).length}` }, { id: 'all', label: `${t('t.filter.all')} · ${tasks.length}` }]} />} />
      <div className="flex flex-wrap gap-2">
        {Object.entries(counts).map(([k, v]) => <Badge key={k} tone={k === 'verified' ? 'ok' : k === 'escalated' || k === 'disputed' ? 'stop' : 'neutral'}>{t(`task.state.${k}`)} · {v}</Badge>)}
      </div>
      {q.isLoading ? <Skeleton className="h-64" /> : q.error ? <ErrorNote error={q.error} onRetry={() => q.refetch()} /> :
        shown.length === 0 ? <Empty icon={<CheckCircle2 className="size-6" />}>{t('t.empty')}</Empty> :
          <div className="space-y-4">{shown.map((task) => <TaskCard key={task.id} task={task} clock={q.data.clock} />)}</div>}
    </div>
  )
}

function TaskCard({ task, clock }: { task: any; clock: string }) {
  const { t, lang } = useI18n()
  const can = useCan()
  const role = useRole()
  const name = useActorNames()
  const qc = useQueryClient()
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<unknown>(null)
  const [hist, setHist] = useState(false)
  const kinds = (EVIDENCE[task.action_code] ?? ['supervisor_attestation']).filter((k) => k !== 'independent_spot_check' || role === 'hse')
  const withOld = kinds.includes('photo') ? [...kinds, 'photo_old'] : kinds
  const [kind, setKind] = useState<string>(kinds[0])
  const [note, setNote] = useState('')
  const [delivered, setDelivered] = useState(false)
  const [finding, setFinding] = useState('')
  const actable = can('task.act')
  const overdue = task.state === 'assigned' && task.start_by < clock
  const tone = task.state === 'verified' ? 'ok' : ['escalated', 'disputed'].includes(task.state) ? 'stop' : task.state === 'reported_complete' ? 'warn' : 'neutral'

  function evidence() {
    if (kind === 'photo_old') {
      const old = new Date(Date.parse(clock) - 2 * 3600_000 + 4 * 3600_000).toISOString().slice(0, 19) + '+04:00'
      return { kind: 'photo', in_app: false, observed_at: old, zone: task.zone_id, scope: note || 'Photo chosen from the phone gallery' }
    }
    const ev: any = { kind, scope: note || t(`ev.default.${kind}`) }
    if (kind === 'photo') Object.assign(ev, { in_app: true, zone: task.zone_id, observed_at: clock })
    if (kind === 'water_point_check' && delivered) ev.water_actually_delivered = true
    return ev
  }
  async function act(action: string, withEvidence = false) {
    setBusy(action); setErr(null)
    try {
      await actOnce(`task:${task.id}:${task.version}:${action}`, `/tasks/${task.id}/events`, { action, ...(withEvidence ? { evidence: evidence() } : {}), ...(action === 'resolve_dispute' ? { reason: finding } : {}), expected_version: task.version })
      await qc.invalidateQueries()
      setNote('')
      if (action === 'resolve_dispute') setFinding('')
    } catch (e) { setErr(e) } finally { setBusy(null) }
  }
  const s = task.state
  const rationale = lang === 'ar' ? task.rationale_ar ?? task.rationale : task.rationale

  return (
    <Card className={cx('overflow-hidden', ['escalated', 'disputed'].includes(s) && 'border-stop/40')}>
      <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-bold">{task.label}</h3>
            {task.zone_id && <Badge tone="brand">{t('common.zone')} {task.zone_id}</Badge>}
            {task.crew && <Badge tone="neutral">{task.crew}</Badge>}
            {task.mandatory && <Badge tone="sun" icon={<ShieldCheck className="size-3" />}>{t('t.mandatory')}</Badge>}
          </div>
          <p className="mt-1.5 max-w-3xl text-sm text-ink-2">{rationale}</p>
        </div>
        <Badge tone={tone as any} className="text-sm">{t(`task.state.${s}`)}</Badge>
      </div>
      <div className="flex flex-wrap items-center gap-2 px-5 pt-3 text-xs">
        <span className="font-semibold text-muted">{t('t.needs')}</span><TierChip tier={task.required_tier} />
        <span className="ms-2 font-semibold text-muted">{t('t.has')}</span><TierChip tier={task.achieved_tier} />
        <span className={cx('ms-2 inline-flex items-center gap-1', overdue ? 'font-bold text-stop' : 'text-muted')}><Clock3 className="size-3.5" />{t('t.deadline', { t: fmtTime(task.start_by) })}{overdue ? ` · ${t('t.overdue')}` : ''}</span>
        <span className="inline-flex items-center gap-1 text-muted"><UserCheck className="size-3.5" />{t('t.owner')}: {t(`role.${task.owner_role}`)}</span>
        <span className="text-muted">· {t(`src.${task.source.split(':')[0]}`)}</span>
      </div>

      {task.disputes?.length > 0 && (
        <div className="mx-5 mt-3 space-y-1.5 rounded-xl border border-stop/30 bg-stop-soft/60 p-3 text-sm">
          {task.disputes.map((d: any) => (
            <div key={d.id} className="flex items-start gap-2">
              <MessageSquareWarning className="mt-0.5 size-4 shrink-0 text-stop" />
              <div><span className="font-semibold">{t('t.dispute_by_worker')}</span> · <span dir="auto">“{d.text}”</span> <span className="num text-xs text-muted" dir="ltr">{fmtTime(d.raised_at)}</span> {d.open ? <Badge tone="stop">{t('t.open')}</Badge> : <Badge tone="ok">{t('t.resolved')}</Badge>}
                {!d.open && d.resolved_by === 'independent_check' && <div className="mt-1 text-xs text-ink-2" dir="auto">{t('t.resolved_by_check', { t: fmtTime(d.resolution?.checked_at), r: endSentence(d.resolution?.reason ?? '') })} {t('t.can_challenge')}</div>}
                {!d.open && d.resolved_by === 'worker_confirmation' && <div className="mt-1 text-xs text-ink-2">{t('t.resolved_by_worker')}</div>}
              </div>
            </div>
          ))}
          <div className="text-xs text-muted">{t('t.no_names')}</div>
        </div>
      )}

      {task.evidence?.length > 0 && (
        <ul className="mx-5 mt-3 space-y-1.5">
          {task.evidence.map((e: any, i: number) => (
            <li key={i} className="flex flex-wrap items-center gap-2 rounded-xl bg-surface-2 px-3 py-2 text-xs">
              <FileCheck2 className="size-4 text-brand" /><TierChip tier={e.tier} /><span className="font-semibold">{t(`ev.${e.kind}`)}</span>
              <span className="text-muted">· {t(`role.${e.actor_role}`)} · {name(e.actor_ref)}</span>
              <span className="num text-muted" dir="ltr">{fmtTime(e.observed_at)}</span>
              {e.scope && <span className="min-w-0 flex-1 truncate text-ink-2" dir="auto">— {e.scope}</span>}
            </li>
          ))}
        </ul>
      )}

      {actable && s !== 'verified' && s !== 'cancelled' && (
        <div className="mt-4 space-y-3 border-t border-line bg-surface-2/40 px-5 py-4">
          {s === 'escalated' && role !== 'hse' && <p className="text-sm font-semibold text-stop">{t('t.escalated_to_hse')}</p>}
          {['in_progress', 'accepted', 'reported_complete', 'escalated', 'disputed', 'assigned'].includes(s) && !(s === 'escalated' && role !== 'hse') && (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,14rem)_1fr]">
              <label className="text-xs font-semibold">{t('t.evidence')}
                <select value={kind} onChange={(e) => setKind(e.target.value)} className="mt-1 block h-10 w-full rounded-xl border border-line bg-surface px-2 text-sm">
                  {withOld.map((k) => <option key={k} value={k}>{t(`ev.${k}`)} ({TIER[k]})</option>)}
                </select>
              </label>
              <label className="text-xs font-semibold">{t('t.note')}
                <input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t(`ev.default.${kind}`)} className="mt-1 block h-10 w-full rounded-xl border border-line bg-surface px-3 text-sm" dir="auto" />
              </label>
              {kind === 'water_point_check' && role === 'supervisor' && (
                <label className="flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" checked={delivered} onChange={(e) => setDelivered(e.target.checked)} className="size-4" />{t('t.delivered')}</label>
              )}
              {kind === 'photo' && <p className="text-xs text-muted sm:col-span-2">{t('t.photo_in_app')}</p>}
              {kind === 'photo_old' && <p className="text-xs text-warn sm:col-span-2">{t('t.photo_old_note')}</p>}
            </div>
          )}
          {role === 'hse' && task.open_disputes > 0 && (
            <div className="rounded-xl border border-stop/30 bg-surface p-3">
              <label className="block text-xs font-semibold">{t('t.resolve_reason')}
                <input value={finding} onChange={(e) => setFinding(e.target.value)} placeholder={t('t.resolve_ph')} className="mt-1 block h-10 w-full rounded-xl border border-line bg-surface px-3 text-sm" dir="auto" />
              </label>
              <p className="mt-1.5 text-xs text-muted">{t('t.resolve_help')}</p>
              <Button size="sm" variant="outline" className="mt-2" onClick={() => act('resolve_dispute')} loading={busy === 'resolve_dispute'} disabled={finding.trim().length < 8} icon={<MessageSquareWarning className="size-4" />}>{t('t.resolve')}</Button>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {(s === 'assigned' || s === 'reopened' || (s === 'escalated' && role === 'hse')) && <Button size="sm" onClick={() => act('accept')} loading={busy === 'accept'} icon={<UserCheck className="size-4" />}>{t('t.accept')}</Button>}
            {s === 'accepted' && <Button size="sm" onClick={() => act('start')} loading={busy === 'start'} icon={<PlayCircle className="size-4" />}>{t('t.start')}</Button>}
            {s === 'disputed' && <Button size="sm" onClick={() => act('start')} loading={busy === 'start'} icon={<Undo2 className="size-4" />}>{t('t.rework')}</Button>}
            {s === 'in_progress' && <Button size="sm" onClick={() => act('report_complete', true)} loading={busy === 'report_complete'} icon={<Send className="size-4" />}>{t('t.report')}</Button>}
            {(['accepted', 'in_progress', 'reported_complete'].includes(s) || (s === 'escalated' && role === 'hse')) && <Button size="sm" variant="soft" onClick={() => act('add_evidence', true)} loading={busy === 'add_evidence'} icon={<FileCheck2 className="size-4" />}>{t('t.evidence')}</Button>}
            {s === 'reported_complete' && <Button size="sm" variant="sun" onClick={() => act('verify')} loading={busy === 'verify'} icon={<CheckCircle2 className="size-4" />}>{t('t.verify')}</Button>}
            {['assigned', 'accepted', 'in_progress', 'disputed'].includes(s) && <Button size="sm" variant="ghost" onClick={() => act('escalate')} loading={busy === 'escalate'} icon={<Flag className="size-4 text-stop" />}>{t('t.escalate')}</Button>}
          </div>
          {err ? <div className="flex items-start gap-2 rounded-xl border border-stop/30 bg-stop-soft p-3 text-sm text-stop"><AlertTriangle className="mt-0.5 size-4 shrink-0" />{(err as any)?.detail ?? (err as any)?.message}</div> : null}
        </div>
      )}

      <button onClick={() => setHist((v) => !v)} aria-expanded={hist} className="flex w-full items-center gap-2 border-t border-line px-5 py-3 text-sm font-semibold text-muted hover:bg-surface-2">
        <History className="size-4" />{t('t.history')} · {task.history.length}<ChevronDown className={cx('ms-auto size-4 transition-transform', hist && 'rotate-180')} />
      </button>
      {hist && (
        <ol className="space-y-1.5 px-5 pb-4 text-xs">
          {task.history.map((h: any) => (
            <li key={h.id} className="flex flex-wrap items-center gap-2">
              <span className="num text-muted" dir="ltr">{fmtTime(h.at)}</span>
              <Badge tone="neutral">{t(`hist.${h.kind}`)}</Badge>
              <span className="text-muted">{t(`role.${h.actor_role}`)}</span>
              <span className="ms-auto text-muted">→ {t(`task.state.${h.state_after}`)}</span>
            </li>
          ))}
        </ol>
      )}
    </Card>
  )
}
