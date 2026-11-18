import { useQueryClient } from '@tanstack/react-query'
import {
  Activity, BookOpenCheck, Building2, CalendarClock, ChevronLeft, ChevronRight, ClipboardCheck, ClipboardList,
  Cloud, CloudOff, FileSearch, FlaskConical, Gauge, HeartPulse, Home, Languages, LayoutDashboard, ListChecks,
  MessageCircleQuestion, Mic, Moon, Radar, ScrollText, Settings2, ShieldCheck, Siren, Sparkles, Stethoscope, Sun,
  Timer, UserRound, Users, Warehouse, BellRing, PhoneOff, SlidersHorizontal,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api, setOffline, store, switchPersona, useStore, type Role } from '../lib/api'
import { displayName, useApi, usePersona, useRole, useSession } from '../lib/hooks'
import { pick, useI18n } from '../lib/i18n'
import { useTheme } from '../lib/theme'
import { EmergencyCard } from './EmergencyCard'
import { GuidedTour } from './GuidedTour'
import { TourCoach } from './TourCoach'
import { Logo } from './Logo'
import { Badge, Button, Drawer, Toggle, cx } from './ui'

export const ROLE_HOME: Record<Role, string> = {
  worker: '/app/worker', supervisor: '/app/site', hse: '/app/hse', clinician: '/app/clinic', nurse: '/app/clinic', auditor: '/app/trust',
}

type NavItem = { to: string; label: string; icon: ReactNode; end?: boolean }
function useNav(role: Role | null): NavItem[] {
  const { t } = useI18n()
  const i = 'size-5'
  switch (role) {
    case 'worker': return [
      { to: '/app/worker', label: t('w.today'), icon: <Home className={i} />, end: true },
      { to: '/app/worker/report', label: t('w.report'), icon: <Mic className={i} /> },
      { to: '/app/worker/ask', label: t('w.ask'), icon: <MessageCircleQuestion className={i} /> },
      { to: '/app/worker/health', label: t('w.health'), icon: <HeartPulse className={i} /> },
      { to: '/app/worker/data', label: t('w.data'), icon: <ShieldCheck className={i} /> },
    ]
    case 'supervisor': return [
      { to: '/app/site', label: t('s.overview'), icon: <LayoutDashboard className={i} />, end: true },
      { to: '/app/site/plan', label: t('s.plan'), icon: <CalendarClock className={i} /> },
      { to: '/app/site/tasks', label: t('s.tasks'), icon: <ListChecks className={i} /> },
      { to: '/app/lab', label: t('nav.lab'), icon: <SlidersHorizontal className={i} /> },
      { to: '/app/site/capacity', label: t('s.capacity'), icon: <Warehouse className={i} /> },
      { to: '/app/trust', label: t('shell.trust'), icon: <BookOpenCheck className={i} /> },
    ]
    case 'hse': return [
      { to: '/app/hse', label: t('hse.compliance'), icon: <ClipboardCheck className={i} />, end: true },
      { to: '/app/hse/copilot', label: t('hse.copilot'), icon: <Sparkles className={i} /> },
      { to: '/app/site/tasks', label: t('s.tasks'), icon: <ListChecks className={i} /> },
      { to: '/app/site', label: t('s.overview'), icon: <LayoutDashboard className={i} />, end: true },
      { to: '/app/site/plan', label: t('s.plan'), icon: <CalendarClock className={i} /> },
      { to: '/app/lab', label: t('nav.lab'), icon: <SlidersHorizontal className={i} /> },
      { to: '/app/hse/policy', label: t('hse.policy'), icon: <ScrollText className={i} /> },
      { to: '/app/hse/watch', label: t('hse.watch'), icon: <Radar className={i} /> },
      { to: '/app/hse/audit', label: t('hse.audit'), icon: <ClipboardList className={i} /> },
      { to: '/app/trust', label: t('shell.trust'), icon: <BookOpenCheck className={i} /> },
    ]
    case 'clinician': return [
      { to: '/app/clinic', label: t('cl.queue'), icon: <Stethoscope className={i} />, end: true },
      { to: '/app/clinic/patient/W07', label: t('cl.patient'), icon: <UserRound className={i} /> },
      { to: '/app/clinic/documents', label: t('cl.documents'), icon: <FileSearch className={i} /> },
      { to: '/app/clinic/hydration', label: t('cl.hydration'), icon: <FlaskConical className={i} /> },
      { to: '/app/hse/policy', label: t('hse.policy'), icon: <ScrollText className={i} /> },
      { to: '/app/hse/audit', label: t('hse.audit'), icon: <ClipboardList className={i} /> },
      { to: '/app/trust', label: t('shell.trust'), icon: <BookOpenCheck className={i} /> },
    ]
    case 'nurse': return [
      { to: '/app/clinic', label: t('cl.queue'), icon: <Stethoscope className={i} />, end: true },
      { to: '/app/clinic/hydration', label: t('cl.hydration'), icon: <FlaskConical className={i} /> },
      { to: '/app/clinic/patient/W07', label: t('cl.patient'), icon: <UserRound className={i} /> },
      { to: '/app/hse/audit', label: t('hse.audit'), icon: <ClipboardList className={i} /> },
      { to: '/app/trust', label: t('shell.trust'), icon: <BookOpenCheck className={i} /> },
    ]
    case 'auditor': return [
      { to: '/app/trust', label: t('shell.trust'), icon: <BookOpenCheck className={i} />, end: true },
      { to: '/app/lab', label: t('nav.lab'), icon: <SlidersHorizontal className={i} /> },
      { to: '/app/drill', label: t('nav.drill'), icon: <Timer className={i} /> },
      { to: '/app/site', label: t('s.overview'), icon: <LayoutDashboard className={i} />, end: true },
      { to: '/app/site/tasks', label: t('s.tasks'), icon: <ListChecks className={i} /> },
      { to: '/app/hse', label: t('hse.compliance'), icon: <ClipboardCheck className={i} />, end: true },
      { to: '/app/hse/audit', label: t('hse.audit'), icon: <ClipboardList className={i} /> },
    ]
    default: return []
  }
}

export function AppShell() {
  const { t, lang, setLang } = useI18n()
  const { theme, toggle } = useTheme()
  const session = useSession()
  const role = useRole()
  const persona = usePersona()
  const nav = useNav(role)
  const navigate = useNavigate()
  const loc = useLocation()
  const qc = useQueryClient()
  const offline = useStore((s) => s.offline)
  const netDown = useStore((s) => s.netDown)
  const outbox = useStore((s) => s.outbox)
  const [emOpen, setEmOpen] = useState(false)
  const [ctlOpen, setCtlOpen] = useState(false)
  const [tourOpen, setTourOpen] = useState(false)
  const [personaOpen, setPersonaOpen] = useState(false)
  const state = useApi<any>(session ? '/sandbox/state' : null, { refetch: 10000 })
  const personas = useApi<any[]>('/personas')
  const drill = state.data?.drill as { running: boolean; arm: 'current' | 'bardan' | null; index: number | null } | null | undefined
  const drillLive = !!drill?.running
  useEffect(() => { if (store.get().drillLive !== drillLive) store.set({ drillLive }) }, [drillLive])

  useEffect(() => { if (!session) navigate('/start', { replace: true }) }, [session, navigate])
  const switchingPersona = useRef(false)
  useEffect(() => {
    if (role && loc.pathname === '/app' && !switchingPersona.current) navigate(ROLE_HOME[role], { replace: true })
  }, [role, loc.pathname, navigate])

  const scenes: any[] = state.data?.scenes ?? []
  const idx = scenes.findIndex((s) => s.id === state.data?.scene)
  async function goScene(id: string) {
    await api('/sandbox/scene', { body: { scene: id } })
    await qc.invalidateQueries()
  }
  // Leave the current screen before the persona changes, so no screen refetches with the next persona's
  // (narrower) permissions: wait until the neutral /app route has actually replaced it.
  const leftScreen = useRef<(() => void)[]>([])
  useEffect(() => { if (loc.pathname === '/app') leftScreen.current.splice(0).forEach((f) => f()) }, [loc.pathname])
  async function choosePersona(key: string) {
    setPersonaOpen(false)
    switchingPersona.current = true     // stay on the neutral route until the new persona is in place
    try {
      if (loc.pathname !== '/app') {
        await new Promise<void>((resolve) => {
          leftScreen.current.push(resolve)
          navigate('/app')
          setTimeout(resolve, 1500)      // never hang if the route does not change
        })
      }
      await switchPersona(key)
      await qc.invalidateQueries()
      const p = store.get().session?.personas[key]
      if (p) navigate(ROLE_HOME[p.role])
    } finally {
      switchingPersona.current = false
    }
  }
  const clock = state.data?.clock as string | undefined
  const sceneTitle = scenes[idx] ? pick(scenes[idx], 'title', lang) : ''
  // The top bar grows with the drill, offline and reset strips; the new-task banner sits just below it, whatever its height.
  const headerRef = useRef<HTMLElement>(null)
  const [headerH, setHeaderH] = useState(64)
  useEffect(() => {
    const el = headerRef.current
    if (!el) return
    const update = () => setHeaderH(Math.round(el.getBoundingClientRect().height))
    update()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  return (
    <div className="min-h-dvh bg-canvas">
      <header ref={headerRef} className="no-print sticky top-0 z-40 border-b border-line bg-surface/90 backdrop-blur-xl">
        <div className="flex h-16 items-center gap-2 px-3 sm:px-5">
          <Logo to="/" />
          <div className="mx-2 hidden h-8 w-px bg-line lg:block" />
          {/* Scenario clock: SIMULATION, never real time */}
          <div className="hidden min-w-0 flex-1 items-center gap-2 lg:flex">
            <Badge tone="sun">{t('common.simulation')}</Badge>
            {drillLive && <Badge tone="stop" icon={<Timer className="size-3" />}>{t('drill.badge')}</Badge>}
            <span title={t('app.demo_rules_note')}><Badge tone="neutral">{t('app.demo_rules')}</Badge></span>
            <button onClick={() => idx > 0 && goScene(scenes[idx - 1].id)} disabled={idx <= 0 || drillLive} aria-label={t('shell.scene_prev')}
              className="grid size-9 place-items-center rounded-xl hover:bg-surface-2 disabled:opacity-30"><ChevronLeft className="flip-rtl size-5" /></button>
            <select value={state.data?.scene ?? ''} onChange={(e) => goScene(e.target.value)} aria-label={t('shell.scenario')} disabled={drillLive}
              className="h-10 min-w-0 max-w-sm truncate rounded-xl border border-line bg-surface px-3 text-sm font-semibold disabled:opacity-50">
              {scenes.map((s, i) => <option key={s.id} value={s.id}>{i + 1}. {pick(s, 'title', lang)}</option>)}
            </select>
            <button onClick={() => idx < scenes.length - 1 && goScene(scenes[idx + 1].id)} disabled={idx >= scenes.length - 1 || drillLive} aria-label={t('shell.scene_next')}
              className="grid size-9 place-items-center rounded-xl hover:bg-surface-2 disabled:opacity-30"><ChevronRight className="flip-rtl size-5" /></button>
            <div className="ms-1 hidden shrink-0 flex-col whitespace-nowrap leading-tight xl:flex" title="Asia/Dubai">
              <span className="text-[11px] font-medium text-muted">{t('shell.site_time')}</span>
              <span className="num text-sm font-bold" dir="ltr">{clock ? `${clock.slice(0, 10)} ${clock.slice(11, 16)}` : '–'}</span>
            </div>
          </div>
          <div className="ms-auto flex items-center gap-1 sm:gap-1.5">
            <div className="relative">
              <button onClick={() => setPersonaOpen((v) => !v)} className="flex h-11 items-center gap-2 rounded-xl border border-line px-2.5 hover:bg-surface-2" aria-haspopup="menu" aria-expanded={personaOpen}>
                <span className="grid size-7 place-items-center rounded-full bg-brand text-xs font-bold text-brand-ink">{displayName(persona?.name, lang)[0] ?? '?'}</span>
                <span className="hidden text-start leading-tight sm:block">
                  <span className="block max-w-36 truncate text-sm font-semibold">{displayName(persona?.name, lang)}</span>
                  <span className="block text-[11px] text-muted">{role ? t(`role.${role}`) : ''}</span>
                </span>
              </button>
              {personaOpen && (
                <div role="menu" className="absolute end-0 top-12 z-50 w-72 rounded-2xl border border-line bg-surface p-1.5 shadow-float">
                  <div className="px-3 py-2 text-xs font-semibold text-muted">{t('shell.switch')}</div>
                  {(personas.data ?? []).map((p) => (
                    <button key={p.key} role="menuitem" onClick={() => choosePersona(p.key)}
                      className={cx('flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-start hover:bg-surface-2', session?.persona === p.key && 'bg-brand-soft')}>
                      <span className="grid size-8 place-items-center rounded-full bg-surface-3 text-sm font-bold">{displayName(p.name, lang)[0]}</span>
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold">{displayName(p.name, lang)}</span>
                        <span className="block text-xs text-muted">{t(`role.${p.role}`)} · {p.lang === 'ar' ? 'العربية' : 'English'}</span>
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button onClick={() => setLang(lang === 'ar' ? 'en' : 'ar')} className="flex h-11 items-center gap-1.5 rounded-xl px-2.5 text-sm font-bold hover:bg-surface-2" aria-label={t('lang.switch')}>
              <Languages className="size-5" aria-hidden /><span className="hidden sm:inline">{lang === 'ar' ? 'EN' : 'ع'}</span>
            </button>
            <button onClick={toggle} className="grid size-11 place-items-center rounded-xl hover:bg-surface-2" aria-label={t('theme.toggle')}>
              {theme === 'dark' ? <Sun className="size-5" /> : <Moon className="size-5" />}
            </button>
            <button onClick={() => setCtlOpen(true)} className="grid size-11 place-items-center rounded-xl hover:bg-surface-2" aria-label={t('shell.controls')}>
              <Settings2 className="size-5" />
            </button>
            <Button data-tour="shell-emergency" variant="danger" size="md" onClick={() => setEmOpen(true)} icon={<Siren className="size-5" />} className="ms-1">
              <span className="hidden sm:inline">{t('shell.emergency')}</span>
            </Button>
          </div>
        </div>
        {/* Mobile scenario bar */}
        <div className="flex items-center gap-2 border-t border-line px-3 py-2 lg:hidden">
          <Badge tone="sun">{t('common.simulation')}</Badge>
          {drillLive && <Badge tone="stop" icon={<Timer className="size-3" />}>{t('drill.badge')}</Badge>}
          <select value={state.data?.scene ?? ''} onChange={(e) => goScene(e.target.value)} aria-label={t('shell.scenario')} disabled={drillLive || !scenes.length}
            className={cx('h-9 min-w-0 flex-1 truncate rounded-lg border border-line bg-surface px-2 text-xs font-semibold disabled:opacity-50', !scenes.length && 'invisible')}>
            {scenes.map((s, i) => <option key={s.id} value={s.id}>{i + 1}. {pick(s, 'title', lang)} · {s.at.slice(11, 16)}</option>)}
          </select>
          <button onClick={() => setTourOpen(true)} className="h-9 rounded-lg bg-brand-soft px-3 text-xs font-bold text-brand">{t('shell.tour')}</button>
        </div>
        {(offline || netDown) && (
          <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 bg-unknown px-4 py-2 text-center text-sm font-semibold text-white" role="status">
            <CloudOff className="size-4" aria-hidden />{offline ? t('shell.offline') : t('shell.no_network')}
            <span className="rounded-full bg-white/20 px-2 py-0.5 text-xs">{outbox.length ? t('shell.outbox', { n: outbox.length }) : t('shell.synced')}</span>
          </div>
        )}
        {state.data?.reset && <div className="bg-warn-soft px-4 py-2 text-center text-sm font-semibold text-warn">{t('shell.reset_notice')}</div>}
        {drillLive && drill?.arm === 'bardan' && role !== 'auditor' && (
          <div className="flex items-center justify-center gap-2 bg-brand px-4 py-2 text-center text-sm font-semibold text-brand-ink"><Timer className="size-4" aria-hidden />{t('drill.banner.bardan')}</div>
        )}
      </header>
      {drillLive && drill?.arm === 'current' && role !== 'auditor' && <CurrentArmCover key={drill.index ?? 0} />}
      {(role === 'supervisor' || role === 'hse') && <NewTaskAlert top={headerH + 12} />}

      <div className="flex">
        <aside className="no-print sticky top-16 hidden h-[calc(100dvh-4rem)] w-64 shrink-0 flex-col border-e border-line bg-surface px-3 py-4 lg:flex">
          <nav className="flex flex-1 flex-col gap-1" aria-label="Main">
            {nav.map((n) => (
              <NavLink key={n.to + n.label} to={n.to} end={n.end}
                className={({ isActive }) => cx('flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-semibold transition-colors',
                  isActive ? 'bg-brand text-brand-ink shadow-sm' : 'text-ink-2 hover:bg-surface-2')}>
                {n.icon}{n.label}
              </NavLink>
            ))}
          </nav>
          <div className="space-y-2 rounded-2xl bg-surface-2 p-3">
            <div className="text-xs font-semibold text-muted">{sceneTitle}</div>
            <Button variant="soft" size="sm" className="w-full" onClick={() => setTourOpen(true)} icon={<Activity className="size-4" />}>{t('shell.tour')}</Button>
            <p className="text-[11px] leading-snug text-muted">{t('app.synthetic')}</p>
          </div>
        </aside>
        <main className="min-w-0 flex-1 px-3 pb-28 pt-5 sm:px-6 lg:px-8 lg:pb-10">
          <Outlet />
        </main>
      </div>

      {/* Bottom nav (mobile) */}
      <nav className="no-print fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface/95 backdrop-blur-xl lg:hidden" aria-label="Main">
        <div className="mx-auto flex max-w-xl justify-around px-1 pb-[env(safe-area-inset-bottom)]">
          {nav.slice(0, 5).map((n) => (
            <NavLink key={n.to + n.label} to={n.to} end={n.end}
              className={({ isActive }) => cx('flex min-h-16 min-w-16 flex-col items-center justify-center gap-1 rounded-xl px-2 text-[11px] font-semibold',
                isActive ? 'text-brand' : 'text-muted')}>
              {n.icon}<span className="max-w-20 truncate">{n.label}</span>
            </NavLink>
          ))}
        </div>
      </nav>

      <EmergencyCard open={emOpen} onClose={() => setEmOpen(false)} />
      <ControlsDrawer open={ctlOpen} onClose={() => setCtlOpen(false)} settings={state.data?.settings} offline={offline} />
      <GuidedTour open={tourOpen} onClose={() => setTourOpen(false)} goScene={goScene} choosePersona={choosePersona} />
      <TourCoach goScene={goScene} choosePersona={choosePersona} hidden={tourOpen} />
    </div>
  )
}

function ControlsDrawer({ open, onClose, settings, offline }: { open: boolean; onClose: () => void; settings: any; offline: boolean }) {
  const { t, lang, setLang } = useI18n()
  const { theme, set } = useTheme()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const s = settings ?? {}
  const caps: Record<string, boolean> = s.ai_capabilities ?? {}
  async function update(body: any) {
    await api('/sandbox/settings', { body })
    await qc.invalidateQueries()
  }
  async function reset() {
    await api('/sandbox/reset', { body: {} })
    await qc.invalidateQueries()
    onClose()
    navigate('/app')
  }
  const capList = useMemo(() => ['speak', 'chat', 'explain', 'copilot', 'compile', 'document'], [])
  return (
    <Drawer open={open} onClose={onClose} title={t('settings.title')}>
      <div className="space-y-5">
        <div className="rounded-2xl border border-line p-1">
          <Toggle checked={s.ai_enabled !== false} onChange={(v) => update({ ai_enabled: v })} label={t('settings.ai')} sub={t('settings.ai.b')} disabled={offline} />
          <div className="ms-3 border-s border-line ps-2">
            {capList.map((c) => (
              <Toggle key={c} checked={s.ai_enabled !== false && caps[c] !== false} disabled={s.ai_enabled === false || offline}
                onChange={(v) => update({ ai_capabilities: { [c]: v } })} label={t(`settings.cap.${c}`)} />
            ))}
          </div>
        </div>
        <div className="rounded-2xl border border-line p-1">
          <Toggle checked={offline} onChange={(v) => setOffline(v)} label={<span className="inline-flex items-center gap-2">{offline ? <CloudOff className="size-4" /> : <Cloud className="size-4" />}{t('settings.offline')}</span>} sub={t('settings.offline.b')} />
          <Toggle checked={s.forecast_enabled !== false} disabled={offline} onChange={(v) => update({ forecast_enabled: v })} label={t('settings.forecast')} sub={t('settings.forecast.b')} />
          <Toggle checked={!!s.redteam_mode} disabled={offline} onChange={(v) => update({ redteam_mode: v })} label={t('settings.redteam')} sub={t('settings.redteam.b')} />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Button variant={theme === 'light' ? 'primary' : 'soft'} onClick={() => set('light')} icon={<Sun className="size-4" />}>{t('theme.light')}</Button>
          <Button variant={theme === 'dark' ? 'primary' : 'soft'} onClick={() => set('dark')} icon={<Moon className="size-4" />}>{t('theme.dark')}</Button>
          <Button variant={lang === 'en' ? 'primary' : 'soft'} onClick={() => setLang('en')}>English</Button>
          <Button variant={lang === 'ar' ? 'primary' : 'soft'} onClick={() => setLang('ar')}>العربية</Button>
        </div>
        <div className="rounded-2xl border border-stop/30 bg-stop-soft/50 p-4">
          <div className="text-sm font-semibold">{t('settings.reset')}</div>
          <p className="mt-1 text-xs text-muted">{t('settings.reset.b')}</p>
          <Button variant="outline" size="sm" className="mt-3" onClick={reset} disabled={offline}>{t('settings.reset')}</Button>
        </div>
        <p className="text-xs text-muted"><Users className="me-1 inline size-3.5" />{t('app.synthetic')}</p>
        <p className="text-xs text-muted"><Building2 className="me-1 inline size-3.5" />Al Sahil Residences, Site 1 (fictional) · Abu Dhabi · <Gauge className="mx-1 inline size-3.5" />AE-AD-HEAT@0.1.1-demo · {t('app.demo_rules_note')}</p>
      </div>
    </Drawer>
  )
}

/** During a drill that uses the usual way of working, participants' screens are covered: the phone is put away. */
function CurrentArmCover() {
  const { t } = useI18n()
  const [hidden, setHidden] = useState(false)
  if (hidden) return null
  return (
    <div className="fixed inset-0 z-[60] m-0 grid place-items-center bg-[#06122b]/95 p-6 text-center text-white" role="dialog" aria-modal="true" aria-labelledby="drill-cover-title">
      <div className="max-w-md space-y-4">
        <PhoneOff className="mx-auto size-14 text-sun" aria-hidden />
        <h2 id="drill-cover-title" className="text-2xl font-bold">{t('drill.banner.current.title')}</h2>
        <p className="text-base leading-relaxed text-white/85">{t('drill.banner.current.b')}</p>
        <button onClick={() => setHidden(true)} className="text-sm font-semibold text-white/70 underline underline-offset-4 hover:text-white">{t('drill.banner.current.show')}</button>
      </div>
    </div>
  )
}

/** Supervisors and HSE are told when a new task arrives (a banner, and a vibration where the phone supports it).
 *  The prototype has no push notifications yet, so this works while the app is open. */
function NewTaskAlert({ top }: { top: number }) {
  const { t } = useI18n()
  const navigate = useNavigate()
  const q = useApi<any>('/tasks', { refetch: 10000 })
  const seen = useRef<Set<string> | null>(null)
  const [fresh, setFresh] = useState<any | null>(null)
  useEffect(() => {
    const items: any[] = q.data?.tasks ?? []
    if (!q.data) return
    if (seen.current === null) { seen.current = new Set(items.map((x) => x.id)); return }
    const added = items.filter((x) => !seen.current!.has(x.id))
    added.forEach((x) => seen.current!.add(x.id))
    const urgent = added.find((x) => String(x.source ?? '').startsWith('worker_report') || x.source === 'emergency' || x.source === 'help_button' || x.source === 'private_checkin' || x.source === 'wearable_status')
    if (urgent) {
      setFresh(urgent)
      try { navigator.vibrate?.([180, 80, 180]) } catch { /* not supported */ }
    }
  }, [q.data])
  if (!fresh) return null
  // Below the top bar (z-40) and placed under its real height: an open menu, such as the person switcher, stays
  // clickable over the banner, and a taller bar (drill, offline or reset strip) never covers the banner's buttons.
  return (
    <div className="fixed inset-x-3 z-30 mx-auto max-w-lg rounded-2xl border border-warn/40 bg-surface p-4 shadow-float" style={{ top }} role="alert">
      <div className="flex items-start gap-3">
        <BellRing className="mt-0.5 size-5 shrink-0 text-warn" aria-hidden />
        <div className="min-w-0 flex-1">
          <div className="font-bold">{t('newtask.title')}: {fresh.label ?? fresh.action_code}{fresh.zone_id ? ` · ${t('common.zone')} ${fresh.zone_id}` : ''}</div>
          <div className="mt-2 flex gap-2">
            <Button size="sm" onClick={() => { setFresh(null); navigate('/app/site/tasks') }}>{t('newtask.open')}</Button>
            <Button size="sm" variant="ghost" onClick={() => setFresh(null)}>{t('newtask.dismiss')}</Button>
          </div>
        </div>
      </div>
    </div>
  )
}
