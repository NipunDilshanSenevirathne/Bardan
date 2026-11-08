import { ArrowRight, Loader2, Timer } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ROLE_HOME } from '../components/AppShell'
import { Logo } from '../components/Logo'
import { ErrorNote, cx } from '../components/ui'
import { startSession, store, switchPersona } from '../lib/api'
import { usePublicApi } from '../lib/hooks'
import { useI18n } from '../lib/i18n'

const IMG: Record<string, string> = {
  ravi: '/img/rebar-aerial-640.webp', anwar: '/img/rebar-inspect-640.webp', joseph: '/img/rebar-crew-640.webp',
  sara: '/img/tower-crane-640.webp', fatima: '/img/dubai-skyline-640.webp', mariam: '/img/sunset-crane-640.webp', reviewer: '/img/frame-worker-640.webp',
}

export default function Start() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const personas = usePublicApi<any[]>('/personas')
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<unknown>(null)
  // An invitation link from the drill console: /start?join=<sandbox>&as=<persona>
  const [params] = useSearchParams()
  const join = /^sb_[0-9a-f]{12}$/.test(params.get('join') ?? '') ? params.get('join')! : null
  const asKey = params.get('as')
  const auto = useRef(false)
  async function go(key: string) {
    setBusy(key); setErr(null)
    try {
      const s = store.get().session
      if (join && s?.sandboxId !== join) await startSession(key, join)
      else if (s) await switchPersona(key)
      else await startSession(key)
      const p = store.get().session!.personas[key]
      navigate(ROLE_HOME[p.role], { replace: !!join })
    } catch (e) { setErr(e) } finally { setBusy(null) }
  }
  useEffect(() => {
    if (join && asKey && !auto.current && (personas.data ?? []).some((p) => p.key === asKey)) {
      auto.current = true
      void go(asKey)
    }
  }, [join, asKey, personas.data])
  return (
    <div className="min-h-dvh bg-canvas">
      <div className="relative h-56 overflow-hidden">
        <img src="/img/hero-slab.webp" alt="" className="absolute inset-0 size-full object-cover object-[50%_60%]" />
        <div className="absolute inset-0 bg-gradient-to-b from-[#06122b]/85 to-canvas" />
        <div className="container-x relative pt-6"><Logo light /></div>
      </div>
      <div className="container-x -mt-24 pb-16">
        <div className="card p-6 sm:p-8">
          <h1 className="text-2xl font-bold sm:text-3xl">{t('start.title')}</h1>
          <p className="mt-2 text-muted">{t('start.sub')} {t('personas.sub')}</p>
          {join && (
            <div className="mt-4 flex items-start gap-3 rounded-2xl border border-brand/30 bg-brand-soft p-4 text-sm">
              <Timer className="mt-0.5 size-5 shrink-0 text-brand" aria-hidden />
              <div><div className="font-bold">{t('start.join')}</div><div className="text-muted">{t('start.join_b')}</div></div>
            </div>
          )}
          {err ? <div className="mt-4"><ErrorNote error={err} /></div> : null}
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {(personas.data ?? []).map((p) => (
              <button key={p.key} onClick={() => go(p.key)} disabled={!!busy}
                className={cx('group flex items-center gap-4 overflow-hidden rounded-2xl border border-line bg-surface p-3 text-start transition hover:border-brand hover:shadow-float',
                  busy === p.key && 'border-brand')}>
                <img src={IMG[p.key]} alt="" className="size-20 shrink-0 rounded-xl object-cover" />
                <span className="min-w-0 flex-1">
                  <span className="block text-xs font-semibold text-sun">{t(`role.${p.role}`)}</span>
                  <span className="block truncate font-bold">{p.name}</span>
                  <span className="block text-sm text-muted">{t(`personas.${p.key}`)}</span>
                </span>
                {busy === p.key ? <Loader2 className="size-5 animate-spin text-brand" /> : <ArrowRight className="flip-rtl size-5 text-muted transition group-hover:text-brand" />}
              </button>
            ))}
          </div>
          {busy && <p className="mt-4 text-sm text-muted">{t('start.loading')}</p>}
        </div>
      </div>
    </div>
  )
}
