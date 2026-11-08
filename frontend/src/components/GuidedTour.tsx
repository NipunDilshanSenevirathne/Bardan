import { CheckCircle2, Circle, Compass } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setOffline } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Button, Drawer, cx } from './ui'

const LANG_KEY = 'bardan.tour.lang_before'

const STEPS = [
  { n: 1, scene: 'evening', persona: 'joseph', route: '/app/site/plan' },
  { n: 2, scene: 'harsh', persona: 'ravi', route: '/app/worker' },
  { n: 3, scene: 'water', persona: 'anwar', route: '/app/worker/report', lang: 'ar' },
  { n: 4, scene: 'water', persona: 'joseph', route: '/app/site/tasks' },
  { n: 5, scene: 'ask', persona: 'anwar', route: '/app/worker/ask', redteam: true },
  { n: 6, scene: 'emergency', persona: 'ravi', route: '/app/worker', offline: true },
  { n: 7, scene: 'clinic', persona: 'joseph', route: '/app/site' },
]

export function GuidedTour({ open, onClose, goScene, choosePersona }: {
  open: boolean; onClose: () => void; goScene: (id: string) => Promise<void>; choosePersona: (k: string) => Promise<void>
}) {
  const { t, lang, setLang } = useI18n()
  const navigate = useNavigate()
  const [done, setDone] = useState<number[]>(() => { try { return JSON.parse(localStorage.getItem('bardan.tour') || '[]') } catch { return [] } })
  const [busy, setBusy] = useState<number | null>(null)
  function mark(n: number) {
    const next = Array.from(new Set([...done, n]))
    setDone(next)
    try { localStorage.setItem('bardan.tour', JSON.stringify(next)) } catch { /* ignore */ }
    void api('/sandbox/tour', { body: { step: `step_${n}` } }).catch(() => {})
  }
  async function go(s: (typeof STEPS)[number]) {
    setBusy(s.n)
    try {
      setOffline(false)
      await choosePersona(s.persona)
      await goScene(s.scene)
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
      mark(s.n)
      onClose()
    } finally { setBusy(null) }
  }
  return (
    <Drawer open={open} onClose={onClose} title={<span className="inline-flex items-center gap-2"><Compass className="size-5 text-sun" />{t('tour.title')}</span>}>
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
