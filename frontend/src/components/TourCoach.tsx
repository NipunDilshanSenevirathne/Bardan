/* The step-by-step guided tour: it follows the tour's steps, puts each person on the right page, rings the
   control to use next and says in one or two sentences what it does. It never clicks for the judge, and the
   ring lets every click through. English and Arabic only. */
import { Compass, X } from 'lucide-react'
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { useNavigate } from 'react-router-dom'
import { setOffline } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { getCoach, setCoach, useCoach } from './coachStore'
import { STEPS, useTourGo } from './GuidedTour'
import { Button } from './ui'

type Hint = {
  sel?: string                 // the control to ring; none = a card in the middle of the top
  click?: boolean              // move on when that control is clicked
  labels?: string[]            // interface labels quoted in the text, as {0}, {1}, in the reader's language
  action?: 'ravi' | 'offline'  // a button that changes the sandbox before the next hint
  en: string
  ar: string
}

export const HINTS: Record<number, Hint[]> = {
  1: [
    { sel: '[data-tour="plan-evaluate"]', click: true, labels: ['p.evaluate'],
      en: 'It is the evening before. Click “{0}”: the rule engine checks Joseph’s usual plan for tomorrow.',
      ar: 'إنه المساء السابق. اضغط «{0}»: يفحص محرك القواعد خطة جوزيف المعتادة للغد.' },
    { sel: '[data-tour="plan-optimise"]', click: true, labels: ['p.optimise'],
      en: 'The draft breaks the heat rules. Click “{0}”: heavy work leaves the harshest hours and breaks fit the shade seats.',
      ar: 'المسودة تخالف قواعد الحرارة. اضغط «{0}»: يبتعد العمل الشاق عن أشد الساعات حرارة وتتوزع الاستراحات على مقاعد الظل.' },
    { sel: '[data-tour="plan-cert"]',
      en: 'An independent rule engine re-checked every worker and every half hour. Only a plan that passes can be approved.',
      ar: 'أعاد محرك قواعد مستقل فحص كل عامل وكل نصف ساعة. لا تُعتمد إلا خطة تجتاز الفحص.' },
    { sel: '[data-tour="plan-approve"]', click: true, labels: ['p.approve'],
      en: 'Click “{0}”. Bardan proposes; a named person decides.',
      ar: 'اضغط «{0}». بَرْدًا يقترح، وشخص مسمّى يقرر.' },
    { sel: '[data-tour="plan-activate"]', click: true, labels: ['p.activate'],
      en: 'Click “{0}”: tomorrow’s plan becomes tasks and messages for each worker.',
      ar: 'اضغط «{0}»: تتحول خطة الغد إلى مهام ورسائل لكل عامل.' },
  ],
  2: [
    { sel: '[data-tour="worker-now"]',
      en: 'Next morning, 09:05. The live reading is harsher than the forecast, so Ravi, a new worker, is moved to shaded work at once.',
      ar: 'صباح اليوم التالي، 09:05. القراءة المباشرة أشد من التوقعات، فيُنقل رافي، العامل الجديد، إلى عمل في الظل فوراً.' },
    { sel: '[data-tour="worker-explain"]', click: true, labels: ['w.explain'],
      en: 'Click “{0}”: the reason comes in his own language, checked by the Guardian before he sees it.',
      ar: 'اضغط «{0}»: يأتي السبب بلغته، ويفحصه الحارس قبل أن يراه.' },
  ],
  3: [
    { sel: '[data-tour="report-example"]', click: true,
      en: 'Anwar works in Arabic. Tap the first example, “I’m not dizzy, but the water’s finished” in Gulf Arabic. Bardan checks it at once.',
      ar: 'يعمل أنور بالعربية. اضغط المثال الأول: «ما فيني دوخة، بس الماي خلص». يفحصه بَرْدًا فوراً.' },
    { sel: '[data-tour="report-confirm"]', click: true, labels: ['r.yes'],
      en: 'Bardan shows the words it heard and understood the “not”: dizzy is already set to No. Nothing is saved until the worker confirms. Click “{0}”.',
      ar: 'يعرض بَرْدًا الكلمات التي سمعها وفهم النفي: «دوخة» محددة بـ«لا». لا يُحفظ شيء حتى يؤكد العامل. اضغط «{0}».' },
  ],
  4: [
    { sel: '[data-tour="task-WATER_RESTORE"]',
      en: 'The water task has an owner, a start-by time and the evidence it needs. Click Accept, Start, then Report complete: only the supervisor’s word.',
      ar: 'لمهمة الماء مسؤول ووقت بدء والدليل الذي تحتاجه. اضغط «قبول» ثم «بدء» ثم «أبلغ عن الإنجاز»: كلمة المشرف وحدها.' },
    { action: 'ravi',
      en: 'Now be Ravi. The water point is still empty.',
      ar: 'كن رافي الآن. نقطة الماء ما زالت فارغة.' },
    { sel: '[data-tour="worker-dispute"]', click: true, labels: ['w.dispute'],
      en: 'Click “{0}”. The task goes to the safety lead, never back to the supervisor, and only an independent check can close it.',
      ar: 'اضغط «{0}». تذهب المهمة إلى مسؤول السلامة ولا تعود إلى المشرف، ولا يغلقها إلا فحص مستقل.' },
  ],
  5: [
    { sel: '[data-tour="ask-input"]', labels: ['a.send'],
      en: 'Red-team mode is on: the model is pushed to be overconfident. Type “Are my kidneys failing?” and press “{0}”.',
      ar: 'وضع الفريق الأحمر مفعّل: يُدفع النموذج إلى الثقة المفرطة. اكتب «هل كليتي تفشل؟» واضغط «{0}».' },
    { sel: '[data-tour="ask-answer"]',
      en: 'Every draft is checked before anyone sees it. An unsafe one is blocked and replaced by an approved answer: no diagnosis, no false reassurance.',
      ar: 'تُفحص كل مسودة قبل أن يراها أحد. تُمنع المسودة غير الآمنة وتُستبدل بإجابة معتمدة: لا تشخيص ولا طمأنة كاذبة.' },
  ],
  6: [
    { action: 'offline',
      en: 'Now a site with no signal. Turn the internet off for this phone.',
      ar: 'الآن موقع بلا تغطية. أوقف الإنترنت لهذا الهاتف.' },
    { sel: '[data-tour="shell-emergency"]', click: true, labels: ['shell.emergency'],
      en: 'Press “{0}” and tap what you see. The steps appear at once with no network, and the card never says help was called before it was.',
      ar: 'اضغط «{0}» واختر ما تراه. تظهر الخطوات فوراً دون شبكة، ولا تقول البطاقة إن المساعدة طُلبت قبل أن يحدث ذلك.' },
    { en: 'Close the card when you are done. The internet comes back with the next step.',
      ar: 'أغلق البطاقة عندما تنتهي. يعود الإنترنت مع الخطوة التالية.' },
  ],
  7: [
    { sel: '[data-tour="privacy-try"]', click: true, labels: ['s.try_clinical'],
      en: 'Click “{0}”. Supervisors have no clinical permission: the server refuses and writes the attempt to the audit log.',
      ar: 'اضغط «{0}». لا يملك المشرف صلاحية طبية: يرفض الخادم ويسجل المحاولة في سجل التدقيق.' },
  ],
  8: [
    { sel: '[data-tour="lab-add-person"]', click: true, labels: ['lab.add_person'],
      en: 'Now your own scenario. Click “{0}”, then give the new worker a name, a phone language and a heat status.',
      ar: 'الآن سيناريو خاص بك. اضغط «{0}» ثم اختر للعامل الجديد اسماً ولغة هاتف وحالة تأقلم.' },
    { sel: 'input[type="range"]',
      en: 'Change the hottest air temperature. The plan, the breaks and every phone update in about a second, and every plan is re-checked.',
      ar: 'غيّر أعلى درجة حرارة للهواء. تتحدث الخطة والاستراحات وكل هاتف في نحو ثانية، وتُفحص كل خطة من جديد.' },
    { sel: '[data-tour="lab-why"]',
      en: 'The break planner: for each hour of each job, the shortest break that keeps the hour within the ISO 7243 / NIOSH heat limit.',
      ar: 'مخطط الاستراحات: لكل ساعة من كل عمل، أقصر استراحة تُبقي الساعة ضمن حد الحرارة في ISO 7243 / NIOSH.' },
    { sel: '[data-tour="lab-step"]', click: true, labels: ['lab.sim.step', 'lab.ev.water_out'],
      en: 'Play the shift: click “{0}”, then try “{1}”. Bardan re-plans from that minute, and what already happened stays.',
      ar: 'شغّل الوردية: اضغط «{0}» ثم جرّب «{1}». يعيد بَرْدًا التخطيط من تلك الدقيقة، ويبقى ما حدث كما هو.' },
  ],
  9: [
    { sel: '[data-tour="wear-card"]', labels: ['wear.use', 'wear.share'],
      en: 'The wearable is optional and off by default. Switch on “{0}” and “{1}”.',
      ar: 'الساعة اختيارية ومتوقفة افتراضياً. فعّل «{0}» و«{1}».' },
    { sel: '[data-tour="wear-connect"]', click: true, labels: ['wear.demo.start'],
      en: 'Click “{0}”. It is simulated: no real device is connected.',
      ar: 'اضغط «{0}». إنها محاكاة: لا يوجد جهاز حقيقي متصل.' },
    { sel: '[data-tour="wear-hard"]', click: true, labels: ['wear.demo.hard'],
      en: 'Click “{0}”. Ravi is warned first; his supervisor sees only “needs a break”, and only because he chose to share.',
      ar: 'اضغط «{0}». يُنبَّه رافي أولاً، ولا يرى مشرفه إلا «يحتاج إلى استراحة»، ولأنه اختار المشاركة فقط.' },
    { en: 'That is the whole loop: plan, protect, prove. Explore freely, or open the Trust Centre for the evidence.',
      ar: 'هذه الحلقة كاملة: تخطيط وحماية وإثبات. استكشف بحرية، أو افتح مركز الثقة لترى الأدلة.' },
  ],
}

const CARD_W = 320

/** Move to the next hint, unless the tour already moved on (a click and the Next button can race). */
function advance(step: number, h: number) {
  const c = getCoach()
  if (!c || c.step !== step || c.hint !== h) return
  setCoach({ step, hint: h + 1 })
}

export function TourCoach({ goScene, choosePersona, hidden }: {
  goScene: (id: string) => Promise<void>; choosePersona: (k: string) => Promise<void>; hidden?: boolean
}) {
  const { t, lang } = useI18n()
  const navigate = useNavigate()
  const run = useTourGo(goScene, choosePersona)
  const coach = useCoach()
  const [rect, setRect] = useState<DOMRect | null>(null)
  const [busy, setBusy] = useState(false)
  const cardRef = useRef<HTMLDivElement>(null)
  const hints = coach ? HINTS[coach.step] ?? [] : []
  const hint = coach && coach.hint < hints.length ? hints[coach.hint] : undefined
  const stepDone = !!coach && coach.hint >= hints.length
  const last = coach?.step === STEPS.length

  // Find the control (it may appear a moment after the page), bring it into view once, and follow it.
  useEffect(() => {
    if (!hint?.sel || hidden) { setRect(null); return }
    let scrolled = false
    const tick = () => {
      const el = document.querySelector(hint.sel!) as HTMLElement | null
      if (el && el.getClientRects().length) {
        if (!scrolled) { el.scrollIntoView({ block: 'center', behavior: 'smooth' }); scrolled = true }
        setRect(el.getBoundingClientRect())
      } else setRect(null)
    }
    tick()
    const h = window.setInterval(tick, 200)
    return () => window.clearInterval(h)
  }, [coach?.step, coach?.hint, hint?.sel, hidden])

  // Move on when the ringed control is used. The judge does the clicking; the tour only follows.
  useEffect(() => {
    if (!coach || !hint?.sel || !hint.click) return
    const at = { ...coach }
    const onClick = (e: MouseEvent) => {
      const el = document.querySelector(hint.sel!)
      if (el && e.target instanceof Node && el.contains(e.target)) window.setTimeout(() => advance(at.step, at.hint), 700)
    }
    document.addEventListener('click', onClick, true)
    return () => document.removeEventListener('click', onClick, true)
  }, [coach?.step, coach?.hint, hint?.sel, hint?.click])

  if (!coach || hidden) return null

  async function nextStep() {
    if (!coach) return
    if (last) { setCoach(null); return }
    setBusy(true)
    try {
      const s = STEPS[coach.step]                           // STEPS is 0-based; steps are numbered from 1
      await run(s)
      setCoach({ step: s.n, hint: 0 })
    } finally { setBusy(false) }
  }
  async function act(a: NonNullable<Hint['action']>) {
    if (!coach) return
    setBusy(true)
    try {
      if (a === 'ravi') { await choosePersona('ravi'); navigate('/app/worker') }
      if (a === 'offline') setOffline(true)
      advance(coach.step, coach.hint)
    } finally { setBusy(false) }
  }

  const text = (h: Hint) => {
    let s = lang === 'ar' ? h.ar : h.en
    ;(h.labels ?? []).forEach((k, i) => { s = s.replace(`{${i}}`, t(k)) })
    return s
  }
  const title = stepDone ? (last ? t('coach.done') : t('coach.step_done', { title: t(`tour.${coach.step + 1}.t`) })) : hint ? text(hint) : ''

  // The card sits below the ringed control, or above it when there is no room; otherwise at the bottom.
  const vw = typeof window !== 'undefined' ? window.innerWidth : 1024
  const vh = typeof window !== 'undefined' ? window.innerHeight : 768
  const w = Math.min(CARD_W, vw - 24)
  let pos: CSSProperties = { bottom: 20, left: Math.max(12, (vw - w) / 2), width: w }
  if (rect && !stepDone && rect.bottom > 0 && rect.top < vh) {   // a control scrolled out of view: card at the bottom
    const cardH = cardRef.current?.offsetHeight ?? 170
    const below = rect.bottom + 14 + cardH < vh
    const top = Math.min(below ? rect.bottom + 14 : Math.max(72, rect.top - 14 - cardH), vh - cardH - 12)
    const left = Math.max(12, Math.min(vw - w - 12, rect.left + rect.width / 2 - w / 2))
    pos = { top, left, width: w }
  }

  return (
    <>
      {rect && !stepDone && (
        <div aria-hidden className="pointer-events-none fixed z-[90] rounded-2xl transition-all duration-200"
          style={{ top: rect.top - 6, left: rect.left - 6, width: rect.width + 12, height: rect.height + 12,
            boxShadow: '0 0 0 3px var(--sun-bright), 0 0 0 9px rgba(249,115,22,0.25), 0 0 0 9999px rgba(11,19,36,0.22)' }} />
      )}
      <div ref={cardRef} role="dialog" aria-modal="false" aria-label={t('coach.title')} data-tour="coach-card"
        className="fixed z-[91] rounded-2xl border border-line bg-surface p-4 shadow-float" style={pos}>
        <div className="flex items-center justify-between gap-2">
          <div className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted">
            <Compass className="size-4 text-sun" aria-hidden />{t('coach.title')} · {t('tour.step', { i: coach.step, n: STEPS.length })}
          </div>
          <button onClick={() => setCoach(null)} aria-label={t('coach.end')} className="grid size-8 place-items-center rounded-lg text-muted hover:bg-surface-2"><X className="size-4" /></button>
        </div>
        {!stepDone && <div className="mt-1 text-sm font-bold">{t(`tour.${coach.step}.t`)}</div>}
        <p className="mt-1 text-sm leading-relaxed" aria-live="polite">{title}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {stepDone
            ? <Button size="sm" onClick={() => void nextStep()} loading={busy} data-tour="coach-next">{last ? t('coach.finish') : t('coach.next_step')}</Button>
            : hint?.action
              ? <Button size="sm" onClick={() => void act(hint.action!)} loading={busy} data-tour="coach-next">{t(`coach.action.${hint.action}`)}</Button>
              : <Button size="sm" variant={hint?.click && rect ? 'soft' : 'primary'} onClick={() => advance(coach.step, coach.hint)} data-tour="coach-next">{t('coach.next')}</Button>}
          <Button size="sm" variant="ghost" onClick={() => setCoach(null)}>{t('coach.end')}</Button>
          {!stepDone && <span className="ms-auto text-xs text-muted" dir="ltr">{coach.hint + 1} / {hints.length}</span>}
        </div>
      </div>
    </>
  )
}
