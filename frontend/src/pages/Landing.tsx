import {
  ArrowRight, BadgeCheck, Brain, CalendarClock, CheckCircle2, ClipboardCheck, CloudSun, FileCode2, FileSearch,
  HeartHandshake, Languages, Lock, Menu, MessagesSquare, Mic, Moon, Radar, RefreshCcw, Route, ShieldAlert, ShieldCheck, Siren, Sparkles,
  Stethoscope, Sun, Undo2, UserRound, X,
} from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import { useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { Button, cx, SectionTitle } from '../components/ui'
import { startSession, switchPersona, store } from '../lib/api'
import { usePublicApi } from '../lib/hooks'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../lib/theme'
import { ROLE_HOME } from '../components/AppShell'

function useStart() {
  const navigate = useNavigate()
  const [busy, setBusy] = useState<string | null>(null)
  async function start(persona: string) {
    setBusy(persona)
    try {
      const s = store.get().session
      if (s) await switchPersona(persona)
      else await startSession(persona)
      const p = store.get().session!.personas[persona]
      navigate(ROLE_HOME[p.role])
    } finally { setBusy(null) }
  }
  return { start, busy }
}

export default function Landing() {
  const { t, lang, setLang } = useI18n()
  const { theme, toggle } = useTheme()
  const [menu, setMenu] = useState(false)
  const reduce = useReducedMotion()
  const { start, busy } = useStart()
  const ev = usePublicApi<any>('/reports/evaluation')
  const fade = reduce ? {} : { initial: { opacity: 0, y: 18 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, margin: '-60px' }, transition: { duration: 0.55 } }

  return (
    <div className="bg-canvas">
      {/* HERO: full-bleed photo, dark overlay, centred headline, pill CTA, live hotspots (Panto-inspired) */}
      <section className="relative isolate min-h-[94dvh] overflow-hidden">
        <img src="/img/hero-slab.webp" srcSet="/img/hero-slab-640.webp 640w, /img/hero-slab.webp 1920w" sizes="100vw"
          alt="" className="absolute inset-0 -z-20 size-full object-cover object-[50%_65%]" fetchPriority="high" />
        <div className="absolute inset-0 -z-10 bg-gradient-to-b from-[#06122b]/90 via-[#0b1a3a]/70 to-canvas" />
        <div className="absolute inset-x-0 top-0 -z-10 h-72 bg-gradient-to-b from-[#06122b] to-transparent" />

        <header className="container-x flex h-20 items-center justify-between">
          <Logo light />
          <nav className="hidden items-center gap-8 text-sm font-medium text-white/85 md:flex">
            <a href="#how" className="hover:text-white">{t('nav.how')}</a>
            <a href="#ai" className="hover:text-white">{t('nav.ai')}</a>
            <a href="#proof" className="hover:text-white">{t('nav.proof')}</a>
            <a href="#sandbox" className="hover:text-white">{t('nav.sandbox')}</a>
          </nav>
          <div className="flex items-center gap-1.5">
            <button onClick={() => setLang(lang === 'ar' ? 'en' : 'ar')} className="h-10 rounded-full px-3 text-sm font-bold text-white hover:bg-white/10" aria-label={t('lang.switch')}>
              {lang === 'ar' ? 'English' : 'العربية'}
            </button>
            <button onClick={toggle} className="grid size-10 place-items-center rounded-full text-white hover:bg-white/10" aria-label={t('theme.toggle')}>
              {theme === 'dark' ? <Sun className="size-5" /> : <Moon className="size-5" />}
            </button>
            <Link to="/start" className="ms-2 hidden h-10 items-center rounded-full bg-white px-4 text-sm font-bold text-[#0b1324] hover:bg-white/90 sm:inline-flex">{t('nav.open')}</Link>
            <button className="grid size-10 place-items-center rounded-full text-white md:hidden" onClick={() => setMenu(!menu)} aria-label="Menu">{menu ? <X /> : <Menu />}</button>
          </div>
        </header>
        {menu && (
          <div className="container-x md:hidden">
            <div className="glass flex flex-col rounded-2xl p-2 text-white">
              {['how', 'ai', 'proof', 'sandbox'].map((k) => <a key={k} href={`#${k}`} onClick={() => setMenu(false)} className="rounded-xl px-4 py-3 font-semibold hover:bg-white/10">{t(`nav.${k}`)}</a>)}
            </div>
          </div>
        )}

        <div className="container-x relative pt-14 pb-40 text-center sm:pt-20">
          <motion.div {...(reduce ? {} : { initial: { opacity: 0, y: 24 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.7 } })}>
            <div className="mx-auto mb-6 inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-1.5 text-xs font-semibold text-white/90 backdrop-blur">
              <span className="size-2 rounded-full bg-sun-bright" />{t('hero.overline')}
            </div>
            <h1 className="mx-auto max-w-4xl text-4xl font-extrabold leading-[1.08] tracking-tight text-white sm:text-6xl lg:text-7xl">
              {t('hero.title1')}<br /><span className="bg-gradient-to-r from-[#7dd3fc] via-white to-[#fdba74] bg-clip-text text-transparent">{t('hero.title2')}</span>
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-base text-white/85 sm:text-lg">{t('hero.sub')}</p>
            <div className="mx-auto mt-9 flex max-w-xl flex-col items-center justify-center gap-3 sm:flex-row">
              <button onClick={() => start('joseph')} disabled={!!busy}
                className="group flex h-14 w-full items-center justify-between gap-4 rounded-full border border-white/25 bg-white/10 ps-6 pe-2 text-start text-white backdrop-blur-md transition hover:bg-white/15 sm:w-auto sm:min-w-96">
                <span className="font-semibold">{t('hero.cta')}</span>
                <span className="grid size-10 place-items-center rounded-full bg-sun-bright text-white transition group-hover:scale-105"><ArrowRight className="flip-rtl size-5" /></span>
              </button>
              <a href="#how" className="h-14 rounded-full px-5 text-sm font-semibold leading-[3.5rem] text-white/85 hover:text-white">{t('hero.cta2')}</a>
            </div>
          </motion.div>
          {/* Hotspots: live protection states pinned on the photo */}
          <div aria-hidden className="pointer-events-none absolute inset-0 hidden lg:block">
            <Hotspot className="start-[8%] top-[64%]" tone="ok" title={t('hero.hot1')} sub={t('hero.hot1b')} />
            <Hotspot className="end-[7%] top-[58%]" tone="warn" title={t('hero.hot2')} sub={t('hero.hot2b')} />
            <Hotspot className="start-[24%] top-[84%]" tone="brand" title={t('hero.hot3')} sub={t('hero.hot3b')} />
            <Hotspot className="end-[22%] top-[86%]" tone="sun" title={t('hero.hot4')} sub={t('hero.hot4b')} />
          </div>
        </div>
        <p className="absolute bottom-4 inset-x-0 text-center text-[11px] text-muted">{t('hero.note')}</p>
      </section>

      {/* WHY */}
      <section id="how" className="container-x scroll-mt-20 py-20 sm:py-28">
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-[0.9fr_2fr]">
          <motion.div {...fade}>
            <div className="overline mb-3">{t('why.overline')}</div>
            <h2 className="text-3xl font-bold leading-tight tracking-tight sm:text-4xl">{t('why.title')}</h2>
          </motion.div>
          <div className="grid grid-cols-1 gap-8 sm:grid-cols-3">
            {[{ i: <CalendarClock />, k: 1 }, { i: <BadgeCheck />, k: 2 }, { i: <Lock />, k: 3 }].map(({ i, k }) => (
              <motion.div key={k} {...fade} className="group">
                <div className="mb-4 grid size-12 place-items-center rounded-2xl bg-brand-soft text-brand transition group-hover:bg-brand group-hover:text-brand-ink">{i}</div>
                <h3 className="text-lg font-bold">{t(`why.${k}.title`)}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">{t(`why.${k}.body`)}</p>
                <a href="#ai" className="link-arrow mt-4">{t('why.more')} <ArrowRight className="flip-rtl size-4" /></a>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* LOOP with photo collage */}
      <section className="relative overflow-hidden bg-surface-2/60 py-20 sm:py-28">
        <div className="container-x grid grid-cols-1 items-center gap-14 lg:grid-cols-2">
          <motion.div {...fade}>
            <SectionTitle overline={t('loop.overline')} title={t('loop.title')} />
            <ol className="mt-8 space-y-3">
              {[CloudSun, Route, Languages, ClipboardCheck, ShieldAlert, Stethoscope, Radar].map((I, n) => (
                <li key={n} className="flex items-center gap-4 rounded-2xl border border-line bg-surface p-3.5 shadow-card">
                  <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-brand to-cyan text-white"><I className="size-5" /></span>
                  <span className="min-w-0">
                    <span className="block font-bold">{n + 1}. {t(`loop.${n + 1}`)}</span>
                    <span className="block text-sm text-muted">{t(`loop.${n + 1}b`)}</span>
                  </span>
                  {n < 6 && <ArrowRight className="flip-rtl ms-auto hidden size-4 text-sun sm:block" />}
                  {n === 6 && <RefreshCcw className="ms-auto hidden size-4 text-sun sm:block" />}
                </li>
              ))}
            </ol>
          </motion.div>
          <motion.div {...fade} className="relative grid grid-cols-5 gap-4">
            <div className="col-span-2 space-y-4 pt-10">
              <Photo src="/img/rebar-crew-640.webp" className="h-56" />
              <Photo src="/img/crane-lift-640.webp" className="h-44" />
            </div>
            <div className="col-span-3">
              <Photo src="/img/sunset-crane.webp" className="h-[26rem]" />
              <div className="relative -mt-16 ms-6 me-[-1rem] rounded-2xl border border-line bg-surface p-4 shadow-float">
                <div className="flex items-center gap-2 text-xs font-semibold text-muted"><CheckCircle2 className="size-4 text-ok" />{lang === 'ar' ? 'شهادة الجدوى · محاكاة' : 'Feasibility certificate · SIMULATION'}</div>
                <div className="mt-1 text-sm font-bold">{lang === 'ar' ? 'الصب 05:30–09:30 · الاستراحات متدرجة لتناسب 20 مقعداً' : 'Pour 05:30–09:30 · breaks staggered for 20 seats'}</div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* AI */}
      <section id="ai" className="container-x scroll-mt-20 py-20 sm:py-28">
        <SectionTitle center overline={t('ai.overline')} title={t('ai.title')} sub={t('ai.sub')} />
        <div className="mt-14 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['speak', Mic], ['foresee', CloudSun], ['plan', Route], ['ask', MessagesSquare],
            ['compile', FileCode2], ['read', FileSearch], ['watch', Radar], ['guardian', ShieldCheck],
          ].map(([k, I]: any, n) => (
            <motion.div key={k} {...fade}
              className={cx('group relative overflow-hidden rounded-3xl border p-6 transition hover:-translate-y-1 hover:shadow-float',
                k === 'guardian' ? 'border-transparent bg-gradient-to-br from-[#0b1a3a] to-[#123a7a] text-white' : 'border-line bg-surface')}>
              <div className={cx('mb-5 grid size-12 place-items-center rounded-2xl', k === 'guardian' ? 'bg-white/15 text-white' : 'bg-sun-soft text-sun')}>
                <I className="size-6" />
              </div>
              <div className={cx('text-xs font-semibold', k === 'guardian' ? 'text-white/70' : 'text-muted')}>{k === 'guardian' ? 'P0' : n === 0 ? 'P0' : n < 5 ? 'P0+' : 'P1'}</div>
              <h3 className="mt-1 text-lg font-bold">{t(`ai.${k}`)}</h3>
              <p className={cx('mt-2 text-sm leading-relaxed', k === 'guardian' ? 'text-white/80' : 'text-muted')}>{t(`ai.${k}.b`)}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* PROOF: real numbers from this server */}
      <section id="proof" className="scroll-mt-20 bg-gradient-to-br from-[#06122b] via-[#0b1f4a] to-[#0d2f6b] py-20 text-white sm:py-28">
        <div className="container-x">
          <div className="grid grid-cols-1 items-end gap-8 lg:grid-cols-[1.3fr_1fr]">
            <div>
              <div className="overline mb-3 text-[#fdba74]">{t('proof.overline')}</div>
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">{t('proof.title')}</h2>
              <p className="mt-4 max-w-2xl text-white/75">{t('proof.sub')}</p>
            </div>
            <div className="lg:text-end"><Button variant="sun" size="lg" onClick={() => start('reviewer')} loading={busy === 'reviewer'}>{t('proof.open')} <ArrowRight className="flip-rtl size-5" /></Button></div>
          </div>
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <ProofStat label={t('proof.replay')} value={ev.data ? `${ev.data.conformance.passed}/${ev.data.conformance.cases}` : '…'} icon={<Undo2 />} />
            <ProofStat label={t('proof.gate')} value={ev.data ? `${sum(ev.data.gate.by_language, 'blocked')}/${sum(ev.data.gate.by_language, 'forbidden')}` : '…'} icon={<ShieldCheck />} />
            <ProofStat label={t('proof.copilot')} value={ev.data ? `${ev.data.copilot.correct_refusals}/${ev.data.copilot.forbidden_items}` : '…'} icon={<MessagesSquare />} />
            <ProofStat label={t('proof.plan')} value={ev.data ? `${Math.round(ev.data.plan.revalidation_pass_rate * 100)}%` : '…'} sub={ev.data ? `${ev.data.plan.solved}/${ev.data.plan.site_days} site-days solved · ${ev.data.plan.no_feasible_protected_plan} “no feasible protected plan”` : ''} icon={<Route />} />
            <ProofStat label={t('proof.foresee')} value={ev.data ? `${Math.round(ev.data.foresee.by_zone.all.coverage_90 * 1000) / 10}%` : '…'} sub={ev.data ? `target 85–95% · underestimation ${Math.round(ev.data.foresee.by_zone.all.underestimation_rate * 1000) / 10}%` : ''} icon={<CloudSun />} />
            <ProofStat label={t('proof.redteam')} value={ev.data ? `${ev.data.redteam.blocked}/${ev.data.redteam.attacks_tried}` : '…'} icon={<Siren />} />
          </div>
        </div>
      </section>

      {/* PERSONAS */}
      <section id="sandbox" className="container-x scroll-mt-20 py-20 sm:py-28">
        <SectionTitle center overline={t('personas.overline')} title={t('personas.title')} sub={t('personas.sub')} />
        <div className="mt-14 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {[
            { k: 'ravi', name: 'Ravi Kumar', img: '/img/rebar-aerial-640.webp', icon: <UserRound />, role: 'role.worker' },
            { k: 'anwar', name: 'Anwar Hussain', img: '/img/rebar-inspect-640.webp', icon: <Mic />, role: 'role.worker' },
            { k: 'joseph', name: 'Joseph Mathew', img: '/img/rebar-crew-640.webp', icon: <CalendarClock />, role: 'role.supervisor' },
            { k: 'sara', name: 'Sara Al Mansoori', img: '/img/tower-crane-640.webp', icon: <Sparkles />, role: 'role.hse' },
            { k: 'fatima', name: 'Dr Fatima Al Hashimi', img: '/img/dubai-skyline-640.webp', icon: <Stethoscope />, role: 'role.clinician' },
            { k: 'reviewer', name: lang === 'ar' ? 'مُقيِّم ضيف' : 'Guest reviewer', img: '/img/frame-worker-640.webp', icon: <Brain />, role: 'role.auditor' },
          ].map((p) => (
            <motion.button key={p.k} {...fade} onClick={() => start(p.k)} disabled={!!busy}
              className="group overflow-hidden rounded-3xl border border-line bg-surface text-start shadow-card transition hover:-translate-y-1 hover:shadow-float">
              <div className="relative h-40 overflow-hidden">
                <img src={p.img} alt="" loading="lazy" className="size-full object-cover transition duration-500 group-hover:scale-105" />
                <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
                <span className="absolute bottom-3 start-3 rounded-full bg-white/90 px-3 py-1 text-xs font-bold text-[#0b1324]">{t(p.role)}</span>
              </div>
              <div className="flex items-center gap-3 p-5">
                <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-brand-soft text-brand">{p.icon}</span>
                <span className="min-w-0 flex-1">
                  <span className="block font-bold">{p.name}</span>
                  <span className="block text-sm text-muted">{t(`personas.${p.k}`)}</span>
                </span>
                <span className="grid size-10 place-items-center rounded-full bg-sun-bright text-white">{busy === p.k ? '…' : <ArrowRight className="flip-rtl size-5" />}</span>
              </div>
            </motion.button>
          ))}
        </div>
      </section>

      <footer className="border-t border-line bg-surface">
        <div className="container-x grid grid-cols-1 gap-10 py-14 md:grid-cols-[1.2fr_2fr]">
          <div>
            <Logo />
            <p className="mt-4 max-w-sm text-sm text-muted">{t('app.tagline')} {t('app.tagline2')}</p>
            <p className="mt-4 inline-flex items-center gap-2 rounded-full bg-sun-soft px-3 py-1 text-xs font-semibold text-sun"><HeartHandshake className="size-4" />{t('app.synthetic')}</p>
          </div>
          <div className="space-y-3 text-sm text-muted">
            <p className="font-semibold text-ink">{t('footer.claims')}</p>
            <p>{t('footer.data')}</p>
            <p>{t('footer.challenge')}</p>
            <Link to="/credits" className="link-arrow">{t('footer.credits')} <ArrowRight className="flip-rtl size-4" /></Link>
          </div>
        </div>
      </footer>
    </div>
  )
}

function sum(obj: Record<string, any>, k: string) { return Object.values(obj ?? {}).reduce((a: number, b: any) => a + (b?.[k] ?? 0), 0) }

function Hotspot({ className, title, sub, tone }: { className: string; title: string; sub: string; tone: 'ok' | 'warn' | 'brand' | 'sun' }) {
  const c = { ok: 'bg-ok', warn: 'bg-warn', brand: 'bg-brand', sun: 'bg-sun-bright' }[tone]
  return (
    <div className={cx('absolute flex items-center gap-3', className)}>
      <span className="relative grid size-6 place-items-center">
        <span className={cx('hotspot-ring absolute inset-0 rounded-full', c)} />
        <span className="relative size-3.5 rounded-full border-2 border-white bg-white/90" />
      </span>
      <span className="glass rounded-2xl px-3.5 py-2 text-start text-white shadow-lg">
        <span className="flex items-center gap-1.5 text-sm font-bold"><span className={cx('size-2 rounded-full', c)} />{title}</span>
        <span className="block text-[11px] text-white/75">{sub}</span>
      </span>
    </div>
  )
}

function Photo({ src, className }: { src: string; className?: string }) {
  return <div className={cx('overflow-hidden rounded-3xl shadow-float', className)}><img src={src} alt="" loading="lazy" className="size-full object-cover" /></div>
}

function ProofStat({ label, value, sub, icon }: { label: string; value: string; sub?: string; icon: ReactNode }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.06] p-6 backdrop-blur">
      <div className="flex items-center gap-2 text-sm text-white/70"><span className="text-[#fdba74] [&>svg]:size-5">{icon}</span>{label}</div>
      <div className="num mt-3 text-4xl font-extrabold tracking-tight">{value}</div>
      {sub && <div className="mt-1 text-xs text-white/60">{sub}</div>}
    </div>
  )
}
