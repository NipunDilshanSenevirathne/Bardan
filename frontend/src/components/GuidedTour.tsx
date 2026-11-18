import { CheckCircle2, Circle, Compass } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setOffline } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { getCoach, setCoach } from './coachStore'
import { Button, Drawer, cx } from './ui'

const LANG_KEY = 'bardan.tour.lang_before'

export const STEPS = [
  { n: 1, scene: 'evening', persona: 'joseph', route: '/app/site/plan' },
  { n: 2, scene: 'harsh', persona: 'ravi', route: '/app/worker' },
  { n: 3, scene: 'water', persona: 'anwar', route: '/app/worker/report', lang: 'ar' },
  { n: 4, scene: 'water', persona: 'joseph', route: '/app/site/tasks' },
  { n: 5, scene: 'ask', persona: 'anwar', route: '/app/worker/ask', redteam: true },
  { n: 6, scene: 'emergency', persona: 'ravi', route: '/app/worker', offline: true },
  { n: 7, scene: 'clinic', persona: 'joseph', route: '/app/site' },
  { n: 8, persona: 'joseph', route: '/app/lab' },
  { n: 9, persona: 'ravi', route: '/app/worker/data' },
] as { n: number; scene?: string; persona: string; route: string; lang?: string; redteam?: boolean; offline?: boolean }[]

export type TourStep = (typeof STEPS)[number]

/** Put the sandbox where a tour step starts: the person, the scene, red-team mode, the language and the page.
 *  Shared by the tour list and the step-by-step guided tour (TourCoach). */
export function useTourGo(goScene: (id: string) => Promise<void>, choosePersona: (k: string) => Promise<void>) {
  const { lang, setLang } = useI18n()
  const navigate = useNavigate()
  return async function go(s: TourStep) {
    setOffline(false)
    await choosePersona(s.persona)
    if (s.scene) await goScene(s.scene)
    if (s.redteam) await api('/sandbox/settings', { body: { redteam_mode: true } })
    // Step 3 switches to Arabic for the worker; the next steps give the judge their own language back.
    let before: string | null = null
    try { before = sessionStorage.getItem(LANG_KEY) } catch { /* private mode */ }
    if (s.lang) {
      if (!before && lang !== s.lang) { try { sessionStorage.setItem(LANG_KEY, lang) } catch { /* ignore */ } }
      setLang(s.lang as 'en' | 'ar')
    } else if (before === 'en' || before === 'ar') {
      setLang(before)
      try { sessionStorage.removeItem(LANG_KEY) } catch { /* ignore */ }
    }
    navigate(s.route)
    void api('/sandbox/tour', { body: { step: `step_${s.n}` } }).catch(() => {})
  }
}

export function GuidedTour({ open, onClose, goScene, choosePersona }: {
  open: boolean; onClose: () => void; goScene: (id: string) => Promise<void>; choosePersona: (k: string) => Promise<void>
}) {
  const { t } = useI18n()
  const run = useTourGo(goScene, choosePersona)
  const [done, setDone] = useState<number[]>(() => { try { return JSON.parse(localStorage.getItem('bardan.tour') || '[]') } catch { return [] } })
  const [busy, setBusy] = useState<number | null>(null)
  function mark(n: number) {
    const next = Array.from(new Set([...done, n]))
    setDone(next)
    try { localStorage.setItem('bardan.tour', JSON.stringify(next)) } catch { /* ignore */ }
    void api('/sandbox/tour', { body: { step: `step_${n}` } }).catch(() => {})
  }
  async function go(s: TourStep) {
    setBusy(s.n)
    try {
      await run(s)
      mark(s.n)
      if (getCoach()) setCoach({ step: s.n, hint: 0 })   // a running guided tour continues from here
      onClose()
    } finally { setBusy(null) }
  }
  async function startCoach() {
    setBusy(0)
    try {
      await run(STEPS[0])
      mark(1)
      setCoach({ step: 1, hint: 0 })
      onClose()
    } finally { setBusy(null) }
  }
  return (
    <Drawer open={open} onClose={onClose} title={<span className="inline-flex items-center gap-2"><Compass className="size-5 text-sun" />{t('tour.title')}</span>}>
      <div className="mb-4 rounded-2xl border border-sun/40 bg-sun-soft/40 p-4">
        <div className="font-bold">{t('coach.start')}</div>
        <p className="mt-1 text-sm text-muted">{t('coach.start_b')}</p>
        <Button className="mt-3" data-tour="coach-start" onClick={() => void startCoach()} loading={busy === 0} icon={<Compass className="size-4" />}>{t('coach.start_go')}</Button>
      </div>
      <ol className="space-y-3">
        {STEPS.map((s) => (
          <li key={s.n} className={cx('rounded-2xl border p-4', done.includes(s.n) ? 'border-ok/40 bg-ok-soft/40' : 'border-line')}>
            <div className="flex items-start gap-3">
              {done.includes(s.n) ? <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-ok" /> : <Circle className="mt-0.5 size-5 shrink-0 text-muted" />}
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-muted">{t('tour.step', { i: s.n, n: STEPS.length })}</div>
                <div className="font-bold">{t(`tour.${s.n}.t`)}</div>
                <p className="mt-1 text-sm text-muted">{t(`tour.${s.n}.b`)}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button size="sm" onClick={() => go(s)} loading={busy === s.n}>{t('tour.go')}</Button>
                  {s.offline && <Button size="sm" variant="outline" onClick={async () => { await api('/sandbox/settings', { body: { ai_enabled: false } }).catch(() => {}); setOffline(true); onClose() }}>{t('settings.offline')}</Button>}
                  <Button size="sm" variant="ghost" onClick={() => mark(s.n)}>{t('tour.done')}</Button>
                </div>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </Drawer>
  )
}
