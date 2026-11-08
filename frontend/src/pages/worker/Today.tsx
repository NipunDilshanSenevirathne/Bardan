import {
  ArrowRightLeft, CalendarClock, CheckCircle2, Clock3, Droplets, Gauge, HandHelping, Info, LifeBuoy, MapPin,
  MessageSquareWarning, ShieldCheck, Sparkles, ThumbsDown, ThumbsUp, Users,
} from 'lucide-react'
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Badge, Button, Card, ErrorNote, Skeleton, STATE_META, StatePill, BandChip, TierChip, cx } from '../../components/ui'
import { EmergencyCard } from '../../components/EmergencyCard'
import { ListenButton } from '../../components/ListenButton'
import { actOnce, api } from '../../lib/api'
import { useApi } from '../../lib/hooks'
import { pick, useI18n } from '../../lib/i18n'
import { reasonText } from '../../lib/reasons'

const TONE_BG: Record<string, string> = {
  ok: 'from-[#1d4ed8] to-[#0891b2]', warn: 'from-[#b45309] to-[#ea580c]', stop: 'from-[#b91c1c] to-[#dc2626]', unknown: 'from-[#334155] to-[#475569]',
}

export default function Today() {
  const { t, lang } = useI18n()
  const q = useApi<any>('/worker/today', { refetch: 15000 })
  const qc = useQueryClient()
  const [why, setWhy] = useState<any>(null)
  const [whyBusy, setWhyBusy] = useState(false)
  const [em, setEm] = useState(false)
  const [busyTask, setBusyTask] = useState<string | null>(null)
  const [taskErr, setTaskErr] = useState<unknown>(null)

  if (q.isLoading) return <div className="mx-auto max-w-2xl space-y-4"><Skeleton className="h-72" /><Skeleton className="h-40" /></div>
  if (q.error && !q.data) return <ErrorNote error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  const st = d.status
  const dec = st.decision
  const meta = STATE_META[dec.state] ?? STATE_META.unavailable
  const obs = st.inputs?.observation
  const a = st.assignment
  const place = a.zone ? pick(a.zone, 'name', lang) : ''

  async function explain() {
    setWhyBusy(true)
    try { setWhy(await api('/worker/explain', { body: {} })) } finally { setWhyBusy(false) }
  }
  async function taskAct(id: string, kind: 'dispute' | 'confirm') {
    setBusyTask(id); setTaskErr(null)
    try {
      await actOnce(`${kind}:${id}`, `/worker/tasks/${id}/${kind}`, kind === 'dispute' ? { text: lang === 'ar' ? 'ما زالت غير متوفرة' : 'Still missing' } : {})
      await qc.invalidateQueries()
    } catch (e) { setTaskErr(e) } finally { setBusyTask(null) }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      {/* 1. What to do now */}
      <section aria-labelledby="now" className={cx('relative overflow-hidden rounded-[2rem] bg-gradient-to-br p-6 text-white shadow-float sm:p-8', TONE_BG[meta.tone])}>
        <div className="absolute -end-10 -top-10 size-48 rounded-full bg-white/10" aria-hidden />
        <div className="relative">
          <div className="flex items-center justify-between gap-3">
            <h1 id="now" className="text-sm font-semibold uppercase tracking-wider text-white/80">{t('w.now')}</h1>
            <div className="flex items-center gap-2">
              <ListenButton onColor text={`${st.state_label}. ${st.message.text}`} />
              <span className="rounded-full bg-white/15 px-3 py-1 text-xs font-semibold" dir="ltr">{st.clock.slice(11, 16)}</span>
            </div>
          </div>
          <div className="mt-4 flex items-center gap-4">
            <div className="grid size-16 shrink-0 place-items-center rounded-2xl bg-white text-ink"><meta.Icon className={cx('size-9', { ok: 'text-ok', warn: 'text-warn', stop: 'text-stop', unknown: 'text-unknown' }[meta.tone])} /></div>
            <div>
              <div className="text-3xl font-extrabold leading-tight sm:text-4xl">{st.state_label}</div>
              {dec.band && <div className="mt-1 text-sm font-semibold text-white/85">{t('s.band')}: {t(`band.${dec.band}`)}</div>}
            </div>
          </div>
          <p className="mt-5 text-lg font-semibold leading-relaxed">{st.message.text}</p>
          <div className="mt-5 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
            <div className="flex items-center gap-2 rounded-xl bg-white/12 px-3 py-2"><MapPin className="size-4 shrink-0" />{a.kind === 'midday_rest' ? (lang === 'ar' ? 'المقصف المكيف' : 'Cooled canteen') : place || '–'}</div>
            <div className="flex items-center gap-2 rounded-xl bg-white/12 px-3 py-2"><Clock3 className="size-4 shrink-0" />{obs?.age_min != null ? t('w.checked', { n: obs.age_min }) : t('w.no_reading')}</div>
          </div>
          {a.task && <div className="mt-2 flex items-center gap-2 rounded-xl bg-white/12 px-3 py-2 text-sm"><Gauge className="size-4 shrink-0" />{pick(a.task, 'name', lang)}</div>}
        </div>
      </section>

      {st.tightened && (
        <div className="flex items-start gap-3 rounded-2xl border border-brand/30 bg-brand-soft p-4 text-sm">
          <ArrowRightLeft className="mt-0.5 size-5 shrink-0 text-brand" />
          <div><div className="font-bold text-brand">{t('w.tightened')}</div>{a.from_task && <div className="mt-1 text-ink-2">{pick(a.from_task, 'name', lang)} → {pick(a.task, 'name', lang)}</div>}</div>
        </div>
      )}

      {/* 2. Why */}
      <Card className="p-5">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-bold">{t('w.why')}</h2>
          <Button size="sm" variant="soft" onClick={explain} loading={whyBusy} icon={<Sparkles className="size-4 text-sun" />}>{t('w.explain')}</Button>
        </div>
        <ul className="mt-3 space-y-2 text-sm">
          {dec.reasons.map((r: string) => <li key={r} className="flex gap-2"><Info className="mt-0.5 size-4 shrink-0 text-brand" />{reasonText(r, lang, { value: obs?.value })}</li>)}
        </ul>
        {why && (
          <div className="mt-4 rounded-2xl bg-surface-2 p-4 text-sm">
            <p className="font-semibold">{why.explanation.text}</p>
            <div className="mt-2 flex items-center gap-2 text-xs text-muted">
              <ShieldCheck className="size-3.5 text-ok" />{why.explanation.source === 'ai_assisted' ? t('w.source.ai') : t('w.source.template')}
            </div>
          </div>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          {st.actions.map((x: any) => <Badge key={x.code} tone="brand">{x.label}</Badge>)}
        </div>
        {obs && (
          <div className="mt-4 grid grid-cols-2 gap-2 rounded-2xl border border-line p-3 text-xs sm:grid-cols-4">
            <div><div className="text-muted">{t('w.reading')}</div><div className="num font-bold" dir="ltr">{obs.value ?? '–'} {obs.unit}</div></div>
            <div><div className="text-muted">{t('w.instrument')}</div><div className="font-semibold">{obs.instrument}</div></div>
            <div><div className="text-muted">{t('common.source')}</div><div className="font-semibold">{t(`prov.${obs.provenance}`)} · {t('common.simulation')}</div></div>
            <div><div className="text-muted">{t('common.time')}</div><div className="num font-semibold" dir="ltr">{obs.observed_at?.slice(11, 16)}</div></div>
          </div>
        )}
        {st.worker.exposure_percent < 100 && <p className="mt-3 flex items-center gap-2 text-xs text-muted"><Users className="size-4" />{t('w.exposure', { p: st.worker.exposure_percent })}</p>}
      </Card>

      {/* Breaks */}
      {st.breaks?.length > 0 && (
        <Card className="p-5">
          <h2 className="font-bold">{t('w.breaks')}</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {st.breaks.map((b: any) => <span key={b.time} className="inline-flex items-center gap-2 rounded-xl bg-cyan-soft px-3 py-2 text-sm font-semibold text-cyan"><Clock3 className="size-4" /><span dir="ltr">{b.time}</span> · {b.rest_area} · {b.minutes} {t('common.min')}</span>)}
          </div>
        </Card>
      )}

      {/* 3. Protection status near you */}
      <Card className="p-5">
        <h2 className="font-bold">{t('w.protection')}</h2>
        {taskErr ? <div className="mt-3"><ErrorNote error={taskErr} /></div> : null}
        <div className="mt-3 space-y-3">
          {d.tasks.filter((x: any) => ['WATER_RESTORE', 'SHADE_EXTEND', 'COOLING_FIX', 'MOVE_TO_SHADED_TASK', 'BREAK_ACCESS'].includes(x.action_code)).length === 0 &&
            <p className="text-sm text-muted">{lang === 'ar' ? 'لا توجد فجوات حماية مفتوحة قربك.' : 'No open protection gaps near you.'}</p>}
          {d.tasks.filter((x: any) => ['WATER_RESTORE', 'SHADE_EXTEND', 'COOLING_FIX', 'MOVE_TO_SHADED_TASK', 'BREAK_ACCESS'].includes(x.action_code)).map((task: any) => (
            <div key={task.id} className="rounded-2xl border border-line p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 font-semibold"><Droplets className="size-4 text-cyan" />{task.label ?? task.action_code}{task.zone_id ? ` · ${t('common.zone')} ${task.zone_id}` : ''}</div>
                <Badge tone={task.state === 'verified' ? 'ok' : task.state === 'escalated' || task.state === 'disputed' ? 'stop' : 'warn'}>{t(`task.state.${task.state}`)}</Badge>
              </div>
              <div className="mt-2 flex flex-wrap gap-2"><TierChip tier={task.achieved_tier} />{task.open_disputes > 0 && <Badge tone="stop" icon={<MessageSquareWarning className="size-3" />}>{t('t.disputes', { n: task.open_disputes })}</Badge>}</div>
              {['reported_complete', 'verified', 'in_progress', 'accepted', 'escalated'].includes(task.state) && (
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <Button variant="outline" size="lg" onClick={() => taskAct(task.id, 'dispute')} loading={busyTask === task.id} icon={<ThumbsDown className="size-5 text-stop" />}>{t('w.dispute')}</Button>
                  <Button variant="soft" size="lg" onClick={() => taskAct(task.id, 'confirm')} disabled={busyTask === task.id} icon={<ThumbsUp className="size-5 text-ok" />}>{t('w.confirm')}</Button>
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>

      {d.tomorrow && (
        <Card className="border-sun/30 p-5">
          <h2 className="flex items-center gap-2 font-bold"><CalendarClock className="size-5 text-sun" />{t('w.tomorrow')}</h2>
          <p className="mt-2 text-sm leading-relaxed">{d.tomorrow.text}</p>
        </Card>
      )}

      {d.notifications?.length > 0 && (
        <Card className="p-5">
          <h2 className="font-bold">{t('w.messages')}</h2>
          <ul className="mt-3 space-y-2">
            {d.notifications.slice().reverse().map((n: any) => <li key={n.id} className="flex gap-2 rounded-xl bg-surface-2 p-3 text-sm"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-brand" /><span>{n.text}<span className="ms-2 text-xs text-muted" dir="ltr">{n.queued_at.slice(11, 16)}</span></span></li>)}
          </ul>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Button variant="outline" size="xl" onClick={async () => { await api('/worker/reports', { body: { intent: 'HELP_REQUEST' } }); await qc.invalidateQueries() }} icon={<HandHelping className="size-6 text-brand" />}>{t('w.help')}</Button>
        <Button variant="danger" size="xl" onClick={() => setEm(true)} icon={<LifeBuoy className="size-6" />}>{t('shell.emergency')}</Button>
      </div>
      {st.worker.buddy && <p className="text-center text-xs text-muted">{t('w.buddy')}: {st.worker.buddy_name ?? st.worker.buddy}</p>}
      <EmergencyCard open={em} onClose={() => setEm(false)} />
      <div className="flex justify-center"><BandChip band={dec.band} /> <span className="ms-2"><StatePill state={dec.state} size="sm" /></span></div>
    </div>
  )
}
