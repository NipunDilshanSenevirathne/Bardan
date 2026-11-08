/*
 * Emergency card. Works with no network and no AI: content and rules are in the app bundle (finalsystem.md §8.4,
 * §12.3, invariants 7-8). It never claims more than has happened, and keeps apart: dialler opened, alert saved on
 * this phone, received by the Bardan server (a real receipt), seen by the site team (a responder acknowledged it,
 * with role and time) and help received (confirmed on the spot). The dialler is a MOCK and never calls anyone.
 */
import { Brain, CheckCircle2, Droplets, HeartPulse, MapPin, PersonStanding, Phone, Siren, Snowflake, Users, Wind, X, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, deviceNow, enqueue, store, useStore } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { evaluate } from '../engine/engine'
import { Button, cx } from './ui'

const TEXT = {
  en: {
    title: 'Emergency', who: 'Who needs help?', me: 'Me', other: 'Someone else (I am the buddy)',
    pick: 'What do you see? Tap one. Help starts at once, no test needed.',
    stepsTitle: 'Do this now',
    steps: ['Stop work.', 'Call 998 or ask someone to call.', 'Stay with the worker.', 'Move to shade or a cool place if you can, and start the site’s cooling steps.',
      'Do not give drinks if they cannot swallow safely.', 'Do not wait for any test.'],
    concerning: ['Stop and move to a cool place.', 'Ask your buddy or the first aider for help.', 'If it gets worse, or confusion, collapse, chest or breathing problems start, call 998.'],
    urine: ['Strong muscle pain or very dark urine after work needs a clinician today.', 'Stop work and go to the clinic now.', 'If you feel very unwell, call 998.'],
    call: 'Call 998', dialler: 'Dialler opened', dialler_b: 'Demo: this is a mock dialler. No real call was placed.',
    queued: 'Alert saved on this phone', received: 'Received by the Bardan server', seen: 'Seen by the site team',
    pending: 'No connection: the alert waits on this phone and sends when a network exists',
    notSeen: 'Nobody on the site team has confirmed yet. Keep calling 998 and stay with the worker.',
    help: 'Help received', help_q: 'Has help arrived?', helpPoint: 'Physical help point: site gate first-aid room (cross sign). Printed steps are posted at every rest area.',
    statusTitle: 'What has really happened', notYet: 'not yet', close: 'Close', ai: 'Works with AI and internet off',
    newAlert: 'Start a new alert',
    symptoms: { confusion: 'Confused or talking strangely', collapse: 'Collapsed or fainted', seizure: 'Seizure', chest_pain: 'Chest pain',
      breathing_difficulty: 'Hard to breathe', muscle_pain_dark_urine: 'Strong muscle pain or dark urine', dizziness: 'Dizzy, headache, nausea or cramps' },
  },
  ar: {
    title: 'طوارئ', who: 'من يحتاج المساعدة؟', me: 'أنا', other: 'شخص آخر (أنا الزميل)',
    pick: 'ماذا ترى؟ اضغط واحداً. تبدأ المساعدة فوراً ولا يلزم أي فحص.',
    stepsTitle: 'افعل هذا الآن',
    steps: ['أوقف العمل.', 'اتصل بالرقم 998 أو اطلب من أحد الاتصال.', 'ابقَ مع العامل.', 'انقله إلى الظل أو مكان بارد إن أمكن، وابدأ خطوات التبريد في الموقع.',
      'لا تعطه أي شراب إذا لم يستطع البلع بأمان.', 'لا تنتظر أي فحص.'],
    concerning: ['توقف وانتقل إلى مكان بارد.', 'اطلب المساعدة من زميلك أو المسعف.', 'إذا ساءت حالتك أو بدأ ارتباك أو سقوط أو مشكلة في الصدر أو التنفس، اتصل بالرقم 998.'],
    urine: ['ألم العضلات الشديد أو البول الداكن جداً بعد العمل يحتاج إلى طبيب اليوم.', 'أوقف العمل واذهب إلى العيادة الآن.', 'إذا شعرت بتوعك شديد، اتصل بالرقم 998.'],
    call: 'اتصل بالرقم 998', dialler: 'فُتح الاتصال', dialler_b: 'للعرض: هذا اتصال تجريبي. لم يتم إجراء أي مكالمة حقيقية.',
    queued: 'حُفظ التنبيه على هذا الهاتف', received: 'وصل إلى خادم بَرْدًا', seen: 'اطّلع عليه فريق الموقع',
    pending: 'لا يوجد اتصال: ينتظر التنبيه على هذا الهاتف ويُرسل عند توفر الشبكة',
    notSeen: 'لم يؤكد أحد من فريق الموقع بعد. واصل الاتصال بالرقم 998 وابقَ مع العامل.',
    help: 'وصلت المساعدة', help_q: 'هل وصلت المساعدة؟', helpPoint: 'نقطة المساعدة: غرفة الإسعافات عند بوابة الموقع (علامة الصليب). الخطوات مطبوعة في كل مكان راحة.',
    statusTitle: 'ما الذي حدث فعلاً', notYet: 'ليس بعد', close: 'إغلاق', ai: 'تعمل دون ذكاء اصطناعي ودون إنترنت',
    newAlert: 'ابدأ تنبيهاً جديداً',
    symptoms: { confusion: 'ارتباك أو كلام غريب', collapse: 'سقوط أو إغماء', seizure: 'نوبة تشنج', chest_pain: 'ألم في الصدر',
      breathing_difficulty: 'صعوبة في التنفس', muscle_pain_dark_urine: 'ألم عضلي شديد أو بول داكن', dizziness: 'دوخة أو صداع أو غثيان أو شد عضلي' },
  },
}
const ICONS: Record<string, typeof Brain> = { confusion: Brain, collapse: PersonStanding, seizure: Zap, chest_pain: HeartPulse,
  breathing_difficulty: Wind, muscle_pain_dark_urine: Droplets, dizziness: Snowflake }

type Status = { opened?: string; dialler?: string; queued?: string; received?: string; seen?: { at: string; role: string }; help?: string }
const ROLE: Record<string, { en: string; ar: string }> = {
  supervisor: { en: 'Site supervisor', ar: 'مشرف الموقع' }, hse: { en: 'HSE lead', ar: 'مسؤول السلامة' },
  nurse: { en: 'Occupational health nurse', ar: 'ممرضة الصحة المهنية' }, clinician: { en: 'Clinician', ar: 'الطبيب' },
}

/* The alert in progress is kept on the phone, so closing the card, reloading the app or losing the network never
   hides what has really happened to it. A new alert can always be started. */
const KEEP_MS = 3 * 3600 * 1000
type Active = { symptom: string; about: 'me' | 'other'; st: Status; eventIds: string[]; emergencyId?: string; savedAt: number }
function activeKey() {
  const s = store.get().session
  return `bardan.emergency.active.v1:${s?.sandboxId ?? ''}:${s?.persona ?? ''}`
}
function loadActive(): Active | null {
  try {
    const a = JSON.parse(localStorage.getItem(activeKey()) || 'null') as Active | null
    return a && Date.now() - a.savedAt < KEEP_MS && !a.st.help ? a : null
  } catch { return null }
}
function saveActive(a: Active | null) {
  try { if (a) localStorage.setItem(activeKey(), JSON.stringify(a)); else localStorage.removeItem(activeKey()) } catch { /* storage blocked */ }
}

export function EmergencyCard({ open, onClose, subjectDefault }: { open: boolean; onClose: () => void; subjectDefault?: string }) {
  const { lang } = useI18n()
  const T = TEXT[lang]
  const offline = useStore((s) => s.offline)
  const netDown = useStore((s) => s.netDown)
  const acks = useStore((s) => s.acks)
  const [about, setAbout] = useState<'me' | 'other'>('me')
  const [symptom, setSymptom] = useState<string | null>(null)
  const [st, setSt] = useState<Status>({})
  const [showDialler, setShowDialler] = useState(false)
  const [eventIds, setEventIds] = useState<string[]>([])
  const [savedId, setSavedId] = useState<string | undefined>(undefined)

  useEffect(() => {
    if (open) {
      const a = loadActive()
      if (a) { setSymptom(a.symptom); setAbout(a.about); setSt(a.st); setEventIds(a.eventIds); setSavedId(a.emergencyId) }
    } else { setSymptom(null); setSt({}); setShowDialler(false); setEventIds([]); setSavedId(undefined) }
  }, [open])
  // "Received" only from the server's own receipt for one of this card's events, never from a local guess.
  const receipt = eventIds.map((id) => acks[id]).find((a) => a && a.status !== 'rejected')
  const emergencyId: string | undefined = receipt?.result?.emergency ?? savedId
  useEffect(() => {
    if (receipt && !st.received) setSt((s) => ({ ...s, received: receipt.server_received_at ?? deviceNow() }))
  }, [receipt, st.received])
  useEffect(() => {
    if (open && symptom) saveActive({ symptom, about, st, eventIds, emergencyId, savedAt: Date.now() })
  }, [open, symptom, about, st, eventIds, emergencyId])
  function newAlert() { saveActive(null); setSymptom(null); setSt({}); setEventIds([]); setSavedId(undefined) }
  // "Seen by the site team" only when a responder has acknowledged the alert on the server.
  useEffect(() => {
    if (!open || !emergencyId || st.seen || offline) return
    let stop = false
    const poll = async () => {
      try {
        const r = await api<any>(`/emergency/${emergencyId}`)
        if (!stop && r.acknowledged) setSt((s) => ({ ...s, seen: r.acknowledged }))
      } catch { /* keep the honest state */ }
    }
    void poll()
    const id = setInterval(poll, 4000)
    return () => { stop = true; clearInterval(id) }
  }, [open, emergencyId, st.seen, offline])

  if (!open) return null
  const session = store.get().session
  const me = session ? session.personas[session.persona] : null
  const subject = about === 'me' ? me?.actor : (subjectDefault ?? 'W07')

  // Local deterministic decision: no model, no network (§12.3).
  const decision = symptom ? evaluate({ now: deviceNow(), symptoms: [symptom] }) : null
  const urgent = decision?.state === 'emergency'

  function choose(s: string) {
    const t0 = performance.now()
    setSymptom(s)
    const opened = deviceNow()
    setSt({ opened })
    const ev = enqueue('emergency', { kind: 'card_opened', subject, symptoms: s === 'dizziness' ? ['dizziness'] : [s], device_time: opened })
    setEventIds((x) => [...x, ev.event_id])
    setSt((x) => ({ ...x, queued: opened }))
    // Measured locally for the acceptance target (structured input -> card < 1 s).
    ;(window as any).__bardanEmergencyMs = Math.round(performance.now() - t0)
  }
  function dial() {
    const now = deviceNow()
    setShowDialler(true)
    setSt((x) => ({ ...x, dialler: now }))
    const ev = enqueue('emergency', { kind: 'dialler_opened', subject, device_time: now })
    setEventIds((x) => [...x, ev.event_id])
  }
  function helpArrived() {
    const now = deviceNow()
    setSt((x) => ({ ...x, help: now }))
    const ev = enqueue('emergency', { kind: 'help_received', subject, device_time: now })
    setEventIds((x) => [...x, ev.event_id])
  }

  return (
    <div className="fixed inset-0 z-[60] m-0 overflow-y-auto bg-stop text-white" role="dialog" aria-modal="true" aria-label={T.title}>
      <div className="mx-auto flex min-h-full max-w-2xl flex-col px-4 pb-10 pt-4 sm:px-6">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="grid size-12 place-items-center rounded-2xl bg-white text-stop"><Siren className="size-7" aria-hidden /></div>
            <div>
              <h2 className="text-2xl font-extrabold">{T.title}</h2>
              <p className="text-xs font-semibold text-white/80">{T.ai}</p>
            </div>
          </div>
          <button onClick={onClose} className="grid size-12 place-items-center rounded-2xl bg-white/15 hover:bg-white/25" aria-label={T.close}><X className="size-6" /></button>
        </div>

        {!symptom && (
          <>
            <div className="mt-6 grid grid-cols-2 gap-2 rounded-2xl bg-white/10 p-1.5">
              {(['me', 'other'] as const).map((a) => (
                <button key={a} onClick={() => setAbout(a)} className={cx('min-h-12 rounded-xl px-3 text-sm font-bold', about === a ? 'bg-white text-stop' : 'text-white')}>
                  {a === 'me' ? T.me : <span className="inline-flex items-center gap-1.5"><Users className="size-4" />{T.other}</span>}
                </button>
              ))}
            </div>
            <p className="mt-5 text-base font-semibold">{T.pick}</p>
            <div className="mt-3 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {Object.entries(T.symptoms).map(([k, label]) => {
                const Icon = ICONS[k]
                return (
                  <button key={k} onClick={() => choose(k)}
                    className="flex min-h-16 items-center gap-3 rounded-2xl bg-white px-4 py-3 text-start text-base font-bold text-stop shadow-lg transition active:scale-[0.98]">
                    <Icon className="size-7 shrink-0" aria-hidden />{label}
                  </button>
                )
              })}
            </div>
          </>
        )}

        {symptom && (
          <div className="mt-6 space-y-5">
            <div className="rounded-3xl bg-white p-5 text-ink shadow-xl">
              <h3 className="text-lg font-extrabold text-stop">{T.stepsTitle}</h3>
              <ol className="mt-3 space-y-2.5">
                {(urgent ? T.steps : symptom === 'muscle_pain_dark_urine' ? T.urine : T.concerning).map((s, i) => (
                  <li key={i} className="flex gap-3 text-base font-semibold">
                    <span className="grid size-7 shrink-0 place-items-center rounded-full bg-stop text-sm text-white">{i + 1}</span>{s}
                  </li>
                ))}
              </ol>
              <Button variant="danger" size="xl" className="mt-5 w-full" icon={<Phone className="size-6" />} onClick={dial}>{T.call}</Button>
            </div>

            <div className="rounded-3xl bg-black/20 p-5">
              <h3 className="text-sm font-bold uppercase tracking-wider text-white/80">{T.statusTitle}</h3>
              <ul className="mt-3 space-y-2 text-sm">
                <StatusRow ok={!!st.dialler} label={T.dialler} note={st.dialler ? T.dialler_b : T.notYet} />
                <StatusRow ok={!!st.queued} label={T.queued} note={st.queued ? ((offline || netDown) && !st.received ? T.pending : '') : T.notYet} />
                <StatusRow ok={!!st.received} label={T.received} note={st.received ? '' : T.notYet} />
                <StatusRow ok={!!st.seen} label={T.seen} note={st.seen ? `${ROLE[st.seen.role]?.[lang] ?? st.seen.role} · ${st.seen.at.slice(11, 16)}` : st.received ? T.notSeen : T.notYet} />
                <StatusRow ok={!!st.help} label={T.help} note={st.help ? '' : T.notYet} />
              </ul>
              {!st.help && <Button variant="soft" className="mt-4 w-full bg-white/15 text-white hover:bg-white/25" onClick={helpArrived}>{T.help_q}</Button>}
            </div>

            <div className="flex items-start gap-3 rounded-2xl bg-white/10 p-4 text-sm">
              <MapPin className="mt-0.5 size-5 shrink-0" aria-hidden />{T.helpPoint}
            </div>
            <button onClick={newAlert} className="w-full rounded-2xl border border-white/40 px-4 py-3 text-sm font-bold text-white hover:bg-white/10">{T.newAlert}</button>
          </div>
        )}
      </div>
      {showDialler && (
        <div className="fixed inset-0 z-[70] m-0 grid place-items-center bg-black/70 p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-sm rounded-3xl bg-surface p-6 text-center text-ink">
            <div className="mx-auto grid size-16 place-items-center rounded-full bg-ok-soft text-ok"><Phone className="size-8" /></div>
            <div className="mt-4 text-3xl font-extrabold tracking-widest" dir="ltr">998</div>
            <p className="mt-2 font-bold">{T.dialler}</p>
            <p className="mt-1 text-sm text-muted">{T.dialler_b}</p>
            <Button className="mt-5 w-full" onClick={() => setShowDialler(false)}>{T.close}</Button>
          </div>
        </div>
      )}
    </div>
  )
}

function StatusRow({ ok, label, note }: { ok: boolean; label: string; note?: string }) {
  return (
    <li className="flex items-start gap-3">
      {ok ? <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-white" aria-hidden /> : <span className="mt-1 size-4 shrink-0 rounded-full border-2 border-white/60" aria-hidden />}
      <span><span className={cx('font-bold', !ok && 'text-white/70')}>{label}</span>{note && <span className="block text-xs text-white/75">{note}</span>}</span>
    </li>
  )
}
