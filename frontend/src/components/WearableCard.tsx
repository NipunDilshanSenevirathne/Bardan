/* Optional wearable on the worker's phone (programme feedback, November 2026).
   Off by default. Readings are checked on this phone (engine/strain.ts) and kept here for 24 hours. The worker
   decides, with two separate switches, whether the words "needs a break" go to the supervisor and whether a
   buddy is asked to check on them when a serious alert goes unanswered. Nothing here can clear a worker. */
import { BellRing, HeartPulse, Info, Share2, ShieldCheck, Trash2, Users, Watch } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { assess, simulateHeartRate, statusPayload, type Level, type Minute } from '../engine/strain'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Badge, Button, Card, CardHeader, Toggle, cx } from './ui'

const ON_KEY = 'bardan.wearable.on'
const DATA_KEY = 'bardan.wearable.samples'
const AGE_KEY = 'bardan.wearable.age'
const DAY_MS = 24 * 3600 * 1000
const BUDDY_WAIT_MS = 12000      // demo: a real phone would wait about two minutes for an answer

type Stored = { savedAt: number; minutes: Minute[] }
function loadStored(): Minute[] {
  try {
    const s = JSON.parse(localStorage.getItem(DATA_KEY) || 'null') as Stored | null
    if (!s || Date.now() - s.savedAt > DAY_MS) { localStorage.removeItem(DATA_KEY); return [] }
    return s.minutes
  } catch { return [] }
}
function saveStored(minutes: Minute[]) {
  try { localStorage.setItem(DATA_KEY, JSON.stringify({ savedAt: Date.now(), minutes: minutes.slice(-24 * 60) })) } catch { /* storage blocked */ }
}
function readLocal(k: string): string | null { try { return localStorage.getItem(k) } catch { return null } }

export function WearableCard({ consents, onConsent, busy, acclimatized = true }: {
  consents: any[]; onConsent: (purpose: string, action: 'grant' | 'withdraw') => Promise<void>; busy: string | null; acclimatized?: boolean
}) {
  const { t } = useI18n()
  const [on, setOn] = useState<boolean>(() => readLocal(ON_KEY) === '1')
  const [age, setAge] = useState<number | null>(() => { const v = Number(readLocal(AGE_KEY)); return v >= 16 && v <= 75 ? v : null })
  const [minutes, setMinutes] = useState<Minute[]>(() => (readLocal(ON_KEY) === '1' ? loadStored() : []))
  const [harder, setHarder] = useState(false)
  const [queue, setQueue] = useState<Minute[]>([])
  const [alert, setAlert] = useState<{ sent: string; buddy: boolean } | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const buddyTimer = useRef<number | null>(null)
  const quietUntil = useRef(0)      // after the worker answers, no repeat alert for 30 simulated minutes
  const share = consents.find((c) => c.purpose === 'wearable_status_share')
  const buddy = consents.find((c) => c.purpose === 'wearable_buddy_alert')

  useEffect(() => { try { localStorage.setItem(ON_KEY, on ? '1' : '0') } catch { /* ignore */ } }, [on])
  useEffect(() => { if (on) saveStored(minutes) }, [on, minutes])
  useEffect(() => { try { if (age) localStorage.setItem(AGE_KEY, String(age)); else localStorage.removeItem(AGE_KEY) } catch { /* ignore */ } }, [age])

  // Feed queued simulated minutes in quickly, so an hour plays in a few seconds.
  useEffect(() => {
    if (!queue.length) return
    const h = window.setTimeout(() => { setMinutes((m) => [...m, ...queue.slice(0, 6)]); setQueue((q) => q.slice(6)) }, 220)
    return () => clearTimeout(h)
  }, [queue])

  const sim = useMemo(() => simulateHeartRate(minutes, { seed: 11, harderDay: harder, acclimatized }), [minutes, harder, acclimatized])
  const a = useMemo(() => assess(sim.hr.map((hr, i) => ({ hr, working: minutes[i].working })), { age, acclimatized }), [sim, minutes, age, acclimatized])
  const level: Level = minutes.length ? a.level : 'no_reading'
  const lastHr = sim.hr[sim.hr.length - 1]

  // A serious alert stays until the worker answers it. The words "needs a break" go to the supervisor only if
  // the worker chose that; the buddy is asked only if the worker chose that and does not answer.
  useEffect(() => {
    if (level !== 'high' || alert || minutes.length < quietUntil.current) return
    const payload = statusPayload(level, !!share?.active)
    setAlert({ sent: payload ? '' : t('ph.wear.not_shared'), buddy: false })
    if (payload) {
      api('/worker/wearable/status', { body: payload })
        .then(() => setAlert((x) => (x ? { ...x, sent: t('ph.wear.shared') } : x)))
        .catch(() => setAlert((x) => (x ? { ...x, sent: t('ph.wear.not_shared') } : x)))
    }
    if (buddy?.active) {
      buddyTimer.current = window.setTimeout(() => {
        api('/worker/wearable/status', { body: { status: 'check_on_me' } })
          .then(() => setAlert((x) => (x ? { ...x, buddy: true } : x))).catch(() => {})
      }, BUDDY_WAIT_MS)
    }
  }, [level, alert, minutes.length, share?.active, buddy?.active, t])
  useEffect(() => () => { if (buddyTimer.current) clearTimeout(buddyTimer.current) }, [])

  function connect() { setQueue((q) => [...q, ...Array.from({ length: 20 }, () => ({ mW: 180, wbgt: 27, working: true }))]) }
  function hardHour() {
    setHarder(true)
    setQueue((q) => [...q, ...Array.from({ length: 60 }, (_, i) => (i < 50 ? { mW: 415, wbgt: 31, working: true } : { mW: 115, wbgt: 27, working: false }))])
  }
  function coolBreak() { setQueue((q) => [...q, ...Array.from({ length: 20 }, () => ({ mW: 115, wbgt: 19, working: false }))]) }
  function answer() {
    if (buddyTimer.current) { clearTimeout(buddyTimer.current); buddyTimer.current = null }
    quietUntil.current = minutes.length + 30
    setAlert(null)
  }
  function wipe(showNote = true) {
    answer()
    quietUntil.current = 0
    setMinutes([]); setQueue([]); setHarder(false)
    try { localStorage.removeItem(DATA_KEY) } catch { /* ignore */ }
    setNote(showNote ? t('wear.deleted') : null)
  }

  const tone = level === 'rising' ? 'border-warn/40 bg-warn-soft text-warn' : 'border-line bg-surface-2 text-ink-2'
  return (
    <Card data-tour="wear-card">
      <CardHeader title={t('wear.title')} sub={t('wear.sub')} icon={<Watch className="size-5" />}
        action={<Badge tone={on ? 'brand' : 'neutral'}>{on ? t('d.on') : t('d.optional')}</Badge>} />
      <div className="space-y-3 p-4">
        <div className="rounded-2xl border border-line p-1">
          <Toggle checked={on} onChange={(v) => { setOn(v); if (!v) wipe(false) }} label={t('wear.use')} sub={t('wear.use.b')} />
          <Toggle checked={!!share?.active} disabled={!on || busy === 'wearable_status_share'} onChange={(v) => void onConsent('wearable_status_share', v ? 'grant' : 'withdraw')}
            label={<span className="inline-flex items-center gap-2"><Share2 className="size-4" />{t('wear.share')}</span>} sub={t('wear.share.b')} />
          <Toggle checked={!!buddy?.active} disabled={!on || busy === 'wearable_buddy_alert'} onChange={(v) => void onConsent('wearable_buddy_alert', v ? 'grant' : 'withdraw')}
            label={<span className="inline-flex items-center gap-2"><Users className="size-4" />{t('wear.buddy')}</span>} sub={t('wear.buddy.b')} />
        </div>
        <p className="flex items-start gap-2 rounded-xl bg-brand-soft p-3 text-xs font-semibold text-brand"><ShieldCheck className="mt-0.5 size-4 shrink-0" />{t('wear.never')}</p>

        {on && (
          <div className="space-y-3 rounded-2xl border border-line p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-sm font-bold"><HeartPulse className="size-4 text-stop" />{t('wear.demo')}</div>
              <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] font-semibold text-muted">{t('ph.wear.private')}</span>
            </div>
            {alert && (
              <div className="rounded-xl border border-stop/40 bg-stop-soft p-3 text-stop" role="alert">
                <p className="flex items-start gap-2 text-sm font-bold leading-snug"><BellRing className="mt-0.5 size-4 shrink-0" />{t('ph.wear.high')}</p>
                {alert.sent && <p className="mt-1.5 text-xs font-semibold">{alert.sent}</p>}
                {alert.buddy && <p className="mt-1 text-xs font-semibold">{t('wear.no_buddy_sent')}</p>}
                <Button size="sm" variant="outline" className="mt-2 border-stop/40 text-stop" onClick={answer}>{t('wear.alert.answer')}</Button>
              </div>
            )}
            <div className={cx('rounded-xl border p-3', alert ? 'border-line bg-surface-2 text-ink-2' : tone)} role="status" aria-live="polite">
              {!alert && <p className="text-sm font-bold leading-snug">{t(`ph.wear.${level === 'high' ? 'rising' : level}`)}</p>}
              {lastHr != null && minutes.length > 0 && <p className="mt-1 text-xs">{t('ph.hr')}: <span className="num font-bold" dir="ltr">{lastHr} {t('ph.bpm')}</span></p>}
            </div>
            <Spark hr={sim.hr.slice(-90)} />
            <div className="flex flex-wrap gap-2">
              {!minutes.length && <Button data-tour="wear-connect" size="sm" onClick={connect} disabled={queue.length > 0} icon={<Watch className="size-4" />}>{t('wear.demo.start')}</Button>}
              {minutes.length > 0 && <Button data-tour="wear-hard" size="sm" variant="sun" onClick={hardHour} disabled={queue.length > 0}>{t('wear.demo.hard')}</Button>}
              {minutes.length > 0 && <Button size="sm" variant="soft" onClick={coolBreak} disabled={queue.length > 0}>{t('wear.demo.rest')}</Button>}
              <Button size="sm" variant="ghost" onClick={() => wipe()} icon={<Trash2 className="size-4" />}>{t('wear.delete')}</Button>
            </div>
            <label className="flex items-center gap-2 text-xs text-muted">{t('lab.age')}
              <input type="number" min={16} max={75} value={age ?? ''} onChange={(e) => setAge(e.target.value ? Math.max(16, Math.min(75, Number(e.target.value))) : null)}
                className="h-9 w-20 rounded-lg border border-line bg-surface px-2 text-sm font-semibold text-ink" />
            </label>
            {note && <p className="text-xs font-semibold text-ok">{note}</p>}
            <p className="text-[11px] text-muted">{t('wear.kept')}</p>
            <p className="flex items-start gap-1.5 text-[11px] text-muted"><Info className="mt-0.5 size-3.5 shrink-0" />{t('wear.method')}</p>
          </div>
        )}
      </div>
    </Card>
  )
}

/** A small heart-rate trace for the worker only (single series, no axis needed). */
function Spark({ hr }: { hr: number[] }) {
  if (hr.length < 2) return null
  const w = 280, h = 56
  const lo = Math.min(60, ...hr), hi = Math.max(170, ...hr)
  const pts = hr.map((v, i) => `${(i / (hr.length - 1)) * w},${h - ((v - lo) / (hi - lo)) * h}`).join(' ')
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-14 w-full" role="img" aria-label="Heart rate, last 90 minutes" style={{ direction: 'ltr' }}>
      <polyline points={pts} fill="none" stroke="var(--stop)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}
