import {
  Activity, BatteryLow, Bed, Brain, Droplet, Fan, Frown, GlassWater, HeartPulse, LifeBuoy, Loader2, Mic, PersonStanding,
  RotateCcw, Send, ShieldCheck, Square, TimerOff, Umbrella, Waves, Wind, Zap,
} from 'lucide-react'
import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { EmergencyCard } from '../../components/EmergencyCard'
import { Badge, Button, Card, ErrorNote, PageHeader, cx } from '../../components/ui'
import { api, enqueue, useStore } from '../../lib/api'
import { useI18n } from '../../lib/i18n'
import { INTENTS, offlineParse } from '../../engine/lexicon'

const ICON: Record<string, typeof Brain> = {
  'brain': Brain, 'person-standing': PersonStanding, 'zap': Zap, 'heart-pulse': HeartPulse, 'wind': Wind, 'droplet': Droplet,
  'rotate-ccw': RotateCcw, 'frown': Frown, 'waves': Waves, 'activity': Activity, 'battery-low': BatteryLow,
  'glass-water': GlassWater, 'umbrella': Umbrella, 'fan': Fan, 'timer-off': TimerOff, 'bed': Bed, 'life-buoy': LifeBuoy,
}
const QUICK = [
  { intent: 'RESOURCE_WATER_UNAVAILABLE', icon: GlassWater, en: 'No drinking water', ar: 'لا يوجد ماء للشرب' },
  { intent: 'RESOURCE_SHADE_FULL', icon: Umbrella, en: 'Shade or rest area full', ar: 'مكان الراحة ممتلئ' },
  { intent: 'RESOURCE_COOLING_BROKEN', icon: Fan, en: 'Cooling not working', ar: 'التبريد لا يعمل' },
  { intent: 'CANNOT_TAKE_BREAK', icon: TimerOff, en: 'I can’t take my break', ar: 'لا أستطيع أخذ استراحتي' },
  { intent: 'AC_BROKEN_HOUSING', icon: Bed, en: 'Room AC broken', ar: 'مكيف الغرفة معطل' },
  { intent: 'HELP_REQUEST', icon: LifeBuoy, en: 'I need help', ar: 'أحتاج مساعدة' },
]
const SYMPTOMS = [
  { s: 'headache', icon: Frown, en: 'Headache', ar: 'صداع' }, { s: 'dizziness', icon: RotateCcw, en: 'Dizzy', ar: 'دوخة' },
  { s: 'nausea', icon: Waves, en: 'Nausea', ar: 'غثيان' }, { s: 'cramps', icon: Activity, en: 'Cramps', ar: 'تشنجات' },
  { s: 'weakness', icon: BatteryLow, en: 'Unusual weakness', ar: 'ضعف غير معتاد' },
  { s: 'muscle_pain_dark_urine', icon: Droplet, en: 'Strong muscle pain or dark urine', ar: 'ألم عضلي شديد أو بول داكن' },
]

export default function Report() {
  const { t, lang } = useI18n()
  const qc = useQueryClient()
  const offline = useStore((s) => s.offline)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<any>(null)
  const [pol, setPol] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<unknown>(null)
  const [em, setEm] = useState(false)
  const [rec, setRec] = useState(false)
  const [sym, setSym] = useState<string[]>([])
  const mr = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])

  async function quick(intent: string) {
    setErr(null); setMsg(null)
    if (offline) { enqueue('report', { intent }); setMsg(t('shell.outbox', { n: 1 })); return }
    try {
      const r = await api('/worker/reports', { body: { intent } })
      setMsg(r.message?.text ?? t('r.sent'))
      await qc.invalidateQueries()
    } catch (e) { setErr(e) }
  }
  /** The phone reads typed words itself first: urgent words open the emergency card with no network, no server and
   * no AI (T68). Offline, or if the server cannot be reached, the phone's own reading is confirmed and queued. */
  function localRead(txt: string) {
    const p = offlineParse(txt)
    const urgent = p.candidates.filter((c) => INTENTS[c.intent]?.urgent && c.polarity !== 'negated')
    return { ...p, local: true, urgent_now: urgent.length > 0, labels: INTENTS }
  }
  async function intake(body: any) {
    setBusy(true); setErr(null); setMsg(null); setRes(null)
    const local = body.text ? localRead(body.text) : null
    if (local?.urgent_now) setEm(true)
    const useLocal = (r: any) => { setRes(r); setPol(Object.fromEntries(r.candidates.map((c: any) => [c.intent, c.polarity]))) }
    if (offline && local) { useLocal(local); setBusy(false); return }
    try {
      const r = await api('/assist/intake', { body })
      useLocal(r)
      if (r.urgent_now) setEm(true) // urgent words never wait for confirmation (T68)
    } catch (e) {
      if (local) useLocal({ ...local, server_unreachable: true })
      else setErr(e)
    } finally { setBusy(false) }
  }
  function queueLocal(confirmed: { intent: string; polarity: string; about?: string }[]) {
    const symptoms: string[] = []
    let about = 'self'
    let n = 0
    for (const c of confirmed) {
      if (c.polarity !== 'affirmed') continue
      const meta = INTENTS[c.intent]
      if (c.about === 'other_person') about = 'other_person'
      if (meta?.symptom) symptoms.push(meta.symptom)
      else { enqueue('report', { intent: c.intent }); n++ }
    }
    if (symptoms.length) { enqueue('checkin', { symptoms, about }); n++ }
    setMsg(n ? t('shell.outbox', { n }) : t('r.nothing'))
    setRes(null); setText('')
  }
  async function confirm() {
    if (!res) return
    if (res.local) {
      queueLocal(res.candidates.map((c: any) => ({ intent: c.intent, polarity: pol[c.intent] ?? c.polarity, about: c.about })))
      return
    }
    setBusy(true)
    try {
      const confirmed = res.candidates.map((c: any) => ({ intent: c.intent, polarity: pol[c.intent] ?? c.polarity, about: c.about }))
      const r = await api(`/assist/intake/${res.draft_id}/confirm`, { body: { confirmed } })
      const texts = [...(r.resources ?? []).map((x: any) => x.message?.text).filter(Boolean), r.checkin?.message?.text].filter(Boolean)
      setMsg(texts.join(' ') || t('r.sent'))
      if (r.checkin?.urgent) setEm(true)
      setRes(null); setText('')
      await qc.invalidateQueries()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  async function startRec() {
    setErr(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const m = new MediaRecorder(stream)
      chunks.current = []
      m.ondataavailable = (e) => e.data.size && chunks.current.push(e.data)
      m.onstop = async () => {
        stream.getTracks().forEach((tr) => tr.stop())
        const blob = new Blob(chunks.current, { type: m.mimeType || 'audio/webm' })
        const b64 = await new Promise<string>((ok) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1]); r.readAsDataURL(blob) })
        await intake({ audio_b64: b64, mime: m.mimeType || 'audio/webm' })
      }
      mr.current = m
      m.start()
      setRec(true)
    } catch { setErr(new Error(t('r.mic_denied'))) }
  }
  function stopRec() { mr.current?.stop(); setRec(false) }
  async function checkin(list: string[]) {
    setErr(null); setMsg(null)
    if (list.some((s) => ['confusion', 'collapse'].includes(s))) setEm(true)
    if (offline) { enqueue('checkin', { symptoms: list }); setMsg(t('shell.outbox', { n: 1 })); return }
    try {
      const r = await api('/worker/check-ins', { body: { symptoms: list } })
      setMsg(r.message?.text ?? (lang === 'ar' ? 'شكراً لك.' : 'Thank you.'))
      if (r.urgent) setEm(true)
      setSym([])
      await qc.invalidateQueries()
    } catch (e) { setErr(e) }
  }

  const labels = res?.labels ?? {}
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title={t('r.title')} sub={t('r.sub')} icon={<Mic className="size-6" />} />
      {err ? <div className="mb-4"><ErrorNote error={err} /></div> : null}
      {msg && <div className="mb-4 flex items-start gap-3 rounded-2xl border border-ok/30 bg-ok-soft p-4 text-sm font-semibold text-ok"><ShieldCheck className="size-5 shrink-0" />{msg}</div>}

      {/* Speak */}
      <Card className="overflow-hidden">
        <div className="bg-gradient-to-br from-brand to-cyan p-6 text-white">
          <div className="flex flex-col items-center gap-4 sm:flex-row">
            <button onPointerDown={startRec} onPointerUp={stopRec} onPointerLeave={() => rec && stopRec()} disabled={offline || busy}
              aria-label={t('r.voice')} className={cx('grid size-24 shrink-0 place-items-center rounded-full bg-white text-brand shadow-xl transition active:scale-95 disabled:opacity-60',
                rec && 'ring-8 ring-white/40')}>
              {rec ? <Square className="size-9 fill-current" /> : busy ? <Loader2 className="size-9 animate-spin" /> : <Mic className="size-10" />}
            </button>
            <div className="text-center sm:text-start">
              <div className="text-xl font-extrabold">{rec ? t('r.recording') : t('r.voice')}</div>
              <p className="mt-1 text-sm text-white/85">{lang === 'ar' ? 'مثلاً: «ما فيني دوخة، بس الماي خلص»' : 'For example: “I am not dizzy, but the water is finished”'}</p>
            </div>
          </div>
          <form className="mt-5 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) void intake({ text }) }}>
            <label className="sr-only" htmlFor="rtext">{t('r.type')}</label>
            <input id="rtext" value={text} onChange={(e) => setText(e.target.value)} placeholder={t('r.placeholder')}
              className="h-14 min-w-0 flex-1 rounded-2xl border-0 bg-white px-4 text-base text-ink placeholder:text-muted" />
            <Button type="submit" variant="sun" size="lg" className="h-14" loading={busy} disabled={!text.trim()} icon={<Send className="flip-rtl size-5" />}>{t('r.send')}</Button>
          </form>
          {offline && <p className="mt-2 text-xs font-semibold text-white/90">{t('r.offline_typing')}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            {['ما فيني دوخة، بس الماي خلص', 'I am not dizzy, but the water is finished', 'the water خلص و أحس بدوخة', 'my friend is talking strangely'].map((s, i) => (
              <button key={s} data-tour={i === 0 ? 'report-example' : undefined} onClick={() => { setText(s); void intake({ text: s }) }} disabled={busy} className="rounded-full bg-white/15 px-3 py-1.5 text-xs font-semibold hover:bg-white/25">{s}</button>
            ))}
          </div>
        </div>

        {res && (
          <div className="space-y-4 p-6">
            {res.urgent_now && <div className="rounded-2xl bg-stop-soft p-3 text-sm font-bold text-stop">{t('r.urgent')}</div>}
            <div>
              <div className="text-xs font-semibold text-muted">{t('r.heard')}</div>
              <p className="mt-1 rounded-2xl bg-surface-2 p-4 text-lg font-semibold" dir="auto">{highlight(res.transcript, res.candidates.flatMap((c: any) => c.evidence_words))}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
                <ShieldCheck className="size-3.5 text-ok" />{res.local ? (res.server_unreachable ? t('r.read_on_phone_unreachable') : t('r.read_on_phone')) : res.method === 'ai' ? t('a.checked') : t('r.ai_off')}
              </div>
            </div>
            {res.candidates.length === 0 ? <p className="font-semibold">{t('r.not_understood')}</p> : (
              <>
                <div className="font-bold">{t('r.right')}</div>
                <ul className="space-y-3">
                  {res.candidates.map((c: any) => {
                    const L = labels[c.intent] ?? {}
                    const Icon = ICON[L.icon] ?? Brain
                    const v = pol[c.intent] ?? c.polarity
                    return (
                      <li key={c.intent} className={cx('rounded-2xl border p-4', L.urgent ? 'border-stop/40 bg-stop-soft/40' : 'border-line')}>
                        <div className="flex items-center gap-3">
                          <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-surface-2"><Icon className={cx('size-6', L.urgent ? 'text-stop' : 'text-brand')} /></span>
                          <div className="min-w-0 flex-1">
                            <div className="font-bold">{L[lang] ?? c.intent}</div>
                            <div className="text-xs text-muted">{t('r.evidence')}: <span dir="auto" className="font-semibold text-ink-2">“{c.evidence_words.join(' ')}”</span>{c.about === 'other_person' && <> · {t('r.about_other')}</>}</div>
                          </div>
                        </div>
                        <div className="mt-3 grid grid-cols-3 gap-2" role="radiogroup" aria-label={L[lang]}>
                          {(['affirmed', 'negated', 'uncertain'] as const).map((p) => (
                            <button key={p} role="radio" aria-checked={v === p} onClick={() => setPol({ ...pol, [c.intent]: p })}
                              className={cx('min-h-12 rounded-xl border text-sm font-bold', v === p ? (p === 'affirmed' ? 'border-brand bg-brand text-brand-ink' : p === 'negated' ? 'border-ink-2 bg-ink-2 text-surface' : 'border-warn bg-warn-soft text-warn') : 'border-line')}>
                              {p === 'affirmed' ? t('r.happening') : p === 'negated' ? t('r.not') : t('r.unsure')}
                            </button>
                          ))}
                        </div>
                      </li>
                    )
                  })}
                </ul>
                <div className="grid grid-cols-2 gap-2">
                  <Button data-tour="report-confirm" size="lg" onClick={confirm} loading={busy}>{t('r.yes')}</Button>
                  <Button size="lg" variant="soft" onClick={() => setRes(null)}>{t('r.edit')}</Button>
                </div>
              </>
            )}
          </div>
        )}
      </Card>

      {/* Quick icon reports */}
      <h2 className="mt-8 mb-3 font-bold">{t('r.quick')}</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {QUICK.map((q) => (
          <button key={q.intent} onClick={() => quick(q.intent)} className="flex min-h-24 flex-col items-center justify-center gap-2 rounded-2xl border border-line bg-surface p-3 text-center text-sm font-bold shadow-card transition hover:border-brand active:scale-[0.98]">
            <q.icon className="size-8 text-brand" />{lang === 'ar' ? q.ar : q.en}
          </button>
        ))}
      </div>

      {/* Private check-in */}
      <Card className="mt-8 p-5">
        <h2 className="font-bold">{t('r.checkin')}</h2>
        <p className="mt-1 text-sm text-muted">{t('r.checkin.b')}</p>
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {SYMPTOMS.map((s) => (
            <button key={s.s} onClick={() => setSym((x) => x.includes(s.s) ? x.filter((y) => y !== s.s) : [...x, s.s])} aria-pressed={sym.includes(s.s)}
              className={cx('flex min-h-14 items-center gap-2 rounded-xl border px-3 text-start text-sm font-semibold', sym.includes(s.s) ? 'border-warn bg-warn-soft text-warn' : 'border-line')}>
              <s.icon className="size-5 shrink-0" />{lang === 'ar' ? s.ar : s.en}
            </button>
          ))}
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2">
          <Button size="lg" disabled={!sym.length} onClick={() => checkin(sym)}>{t('r.yes')}</Button>
          <Button size="lg" variant="soft" onClick={() => checkin([])}>{t('r.allok')}</Button>
        </div>
        <p className="mt-3 text-xs text-muted"><Badge tone="neutral">{lang === 'ar' ? 'ليس فحص لياقة، ولا يؤثر على الأجر' : 'Not a fitness screen. Never affects pay.'}</Badge></p>
      </Card>
      <EmergencyCard open={em} onClose={() => setEm(false)} subjectDefault="W07" />
    </div>
  )
}

function highlight(text: string, words: string[]) {
  if (!text) return null
  const set = new Set(words.map((w) => w.toLowerCase()))
  return text.split(/(\s+)/).map((tok, i) => {
    const clean = tok.replace(/[.,!?؟،]/g, '').toLowerCase()
    return set.has(clean) ? <mark key={i} className="rounded bg-sun-soft px-0.5 text-sun">{tok}</mark> : <span key={i}>{tok}</span>
  })
}
