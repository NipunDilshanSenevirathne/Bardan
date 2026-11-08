import clsx from 'clsx'
import {
  AlertOctagon, CheckCircle2, HelpCircle, Loader2, ShieldAlert, Siren, X,
} from 'lucide-react'
import { forwardRef, useEffect, useId, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { useI18n } from '../lib/i18n'

export const cx = clsx

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'sun' | 'ghost' | 'soft' | 'danger' | 'outline'
  size?: 'sm' | 'md' | 'lg' | 'xl'
  loading?: boolean
  icon?: ReactNode
}
export const Button = forwardRef<HTMLButtonElement, BtnProps>(function Button(
  { variant = 'primary', size = 'md', loading, icon, className, children, disabled, ...rest }, ref) {
  const v = {
    primary: 'bg-brand text-brand-ink hover:brightness-110 shadow-sm',
    sun: 'bg-sun-bright text-white hover:bg-sun shadow-sm',
    ghost: 'text-ink hover:bg-surface-2',
    soft: 'bg-surface-2 text-ink hover:bg-surface-3',
    danger: 'bg-stop text-white hover:brightness-110',
    outline: 'border border-line text-ink hover:bg-surface-2',
  }[variant]
  const s = { sm: 'h-9 px-3 text-sm gap-1.5 rounded-xl', md: 'h-11 px-4 text-sm gap-2 rounded-xl',
    lg: 'h-12 px-5 text-base gap-2 rounded-2xl', xl: 'h-16 px-6 text-lg gap-3 rounded-2xl' }[size]
  return (
    <button ref={ref} disabled={disabled || loading}
      className={cx('inline-flex items-center justify-center font-semibold transition-all duration-200 select-none',
        'disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]', v, s, className)} {...rest}>
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  )
})

export function Card({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cx('card', className)} {...rest}>{children}</div>
}

export function CardHeader({ title, sub, action, icon }: { title: ReactNode; sub?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
      <div className="flex min-w-0 items-start gap-3">
        {icon && <div className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand">{icon}</div>}
        <div className="min-w-0">
          <h3 className="font-semibold leading-tight">{title}</h3>
          {sub && <p className="mt-1 text-sm text-muted">{sub}</p>}
        </div>
      </div>
      {action}
    </div>
  )
}

export function Badge({ tone = 'neutral', children, className, icon }: {
  tone?: 'neutral' | 'brand' | 'sun' | 'ok' | 'warn' | 'stop' | 'unknown' | 'cyan'; children: ReactNode; className?: string; icon?: ReactNode
}) {
  const t = {
    neutral: 'bg-surface-2 text-ink-2 border-line', brand: 'bg-brand-soft text-brand border-transparent',
    sun: 'bg-sun-soft text-sun border-transparent', ok: 'bg-ok-soft text-ok border-transparent',
    warn: 'bg-warn-soft text-warn border-transparent', stop: 'bg-stop-soft text-stop border-transparent',
    unknown: 'bg-unknown-soft text-unknown border-transparent', cyan: 'bg-cyan-soft text-cyan border-transparent',
  }[tone]
  return <span className={cx('inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap', t, className)}>{icon}{children}</span>
}

export const STATE_META: Record<string, { tone: 'ok' | 'warn' | 'stop' | 'unknown'; Icon: typeof CheckCircle2 }> = {
  routine: { tone: 'ok', Icon: CheckCircle2 },
  enhanced: { tone: 'warn', Icon: ShieldAlert },
  stop: { tone: 'stop', Icon: AlertOctagon },
  emergency: { tone: 'stop', Icon: Siren },
  unavailable: { tone: 'unknown', Icon: HelpCircle },
}

/** Protection state: icon + words + colour, never colour alone (§9.7). */
export function StatePill({ state, size = 'md', label }: { state: string; size?: 'sm' | 'md' | 'lg'; label?: string }) {
  const { t } = useI18n()
  const m = STATE_META[state] ?? STATE_META.unavailable
  const sz = { sm: 'text-xs px-2 py-0.5 gap-1', md: 'text-sm px-3 py-1 gap-1.5', lg: 'text-base px-4 py-2 gap-2' }[size]
  const isz = { sm: 'size-3.5', md: 'size-4', lg: 'size-5' }[size]
  const tone = { ok: 'bg-ok-soft text-ok', warn: 'bg-warn-soft text-warn', stop: 'bg-stop-soft text-stop', unknown: 'bg-unknown-soft text-unknown' }[m.tone]
  return <span className={cx('inline-flex items-center rounded-full font-semibold', sz, tone)}><m.Icon className={isz} aria-hidden />{label ?? t(`state.${state}`)}</span>
}

export const BAND_COLOR: Record<string, string> = {
  unrestricted: 'var(--band-u)', acclimatization: 'var(--band-a)', buffer: 'var(--band-b)', withdrawal: 'var(--band-w)', unavailable: 'var(--unknown)',
}
export function BandChip({ band, className }: { band?: string | null; className?: string }) {
  const { t } = useI18n()
  const b = band ?? 'unavailable'
  return (
    <span className={cx('inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-0.5 text-xs font-semibold', className)}>
      <span className="size-2.5 rounded-full" style={{ background: BAND_COLOR[b] }} aria-hidden />{t(`band.${b}`)}
    </span>
  )
}

export function TierChip({ tier }: { tier: string }) {
  const { t } = useI18n()
  const tone = tier === 'E4' ? 'brand' : tier === 'E3' ? 'cyan' : tier === 'E2' ? 'warn' : 'neutral'
  return <Badge tone={tone as any}>{tier} · {t(`tier.${tier}`)}</Badge>
}

export function Stat({ label, value, sub, tone = 'ink', icon }: { label: ReactNode; value: ReactNode; sub?: ReactNode; tone?: string; icon?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-4">
      <div className="flex items-center gap-2 text-xs font-medium text-muted">{icon}{label}</div>
      <div className={cx('num mt-1 text-2xl font-bold tracking-tight', tone === 'sun' && 'text-sun', tone === 'brand' && 'text-brand', tone === 'ok' && 'text-ok', tone === 'stop' && 'text-stop')}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </div>
  )
}

export function Toggle({ checked, onChange, label, sub, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode; sub?: ReactNode; disabled?: boolean }) {
  const id = useId()
  return (
    <label htmlFor={id} className={cx('flex cursor-pointer items-start justify-between gap-4 rounded-xl p-3 hover:bg-surface-2', disabled && 'opacity-50')}>
      <span className="min-w-0">
        <span className="block text-sm font-semibold">{label}</span>
        {sub && <span className="mt-0.5 block text-xs text-muted">{sub}</span>}
      </span>
      <button id={id} role="switch" aria-checked={checked} disabled={disabled} onClick={() => onChange(!checked)}
        className={cx('relative mt-0.5 h-7 w-12 shrink-0 rounded-full transition-colors', checked ? 'bg-brand' : 'bg-surface-3')}>
        <span className={cx('absolute top-1 size-5 rounded-full bg-white shadow transition-all', checked ? 'start-6' : 'start-1')} />
      </button>
    </label>
  )
}

export function Tabs<T extends string>({ value, onChange, items, className }: { value: T; onChange: (v: T) => void; items: { id: T; label: ReactNode; icon?: ReactNode }[]; className?: string }) {
  return (
    <div role="tablist" className={cx('inline-flex flex-wrap gap-1 rounded-2xl bg-surface-2 p-1', className)}>
      {items.map((it) => (
        <button key={it.id} role="tab" aria-selected={value === it.id} onClick={() => onChange(it.id)}
          className={cx('inline-flex min-h-10 items-center gap-2 rounded-xl px-3.5 text-sm font-semibold transition-colors',
            value === it.id ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-ink')}>
          {it.icon}{it.label}
        </button>
      ))}
    </div>
  )
}

export function Drawer({ open, onClose, title, children, side = 'end', wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; side?: 'end' | 'start'; wide?: boolean }) {
  const { t } = useI18n()
  useEffect(() => {
    if (!open) return
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 m-0" role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : undefined}>
      <div className="absolute inset-0 bg-black/50 backdrop-blur-[2px]" onClick={onClose} />
      <div className={cx('absolute top-0 bottom-0 flex w-full flex-col bg-surface shadow-2xl', wide ? 'max-w-2xl' : 'max-w-md', side === 'end' ? 'end-0' : 'start-0')}>
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="text-lg font-bold">{title}</h2>
          <button onClick={onClose} className="grid size-10 place-items-center rounded-xl hover:bg-surface-2" aria-label={t('common.close')}><X className="size-5" /></button>
        </div>
        <div className="scroll-thin flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  )
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  const { t } = useI18n()
  useEffect(() => {
    if (!open) return
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 m-0 grid place-items-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-[2px]" onClick={onClose} />
      <div className={cx('relative max-h-[90vh] w-full overflow-y-auto rounded-3xl bg-surface p-6 shadow-2xl', wide ? 'max-w-3xl' : 'max-w-lg')}>
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 className="text-lg font-bold">{title}</h2>
          <button onClick={onClose} className="grid size-10 shrink-0 place-items-center rounded-xl hover:bg-surface-2" aria-label={t('common.close')}><X className="size-5" /></button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Empty({ icon, children }: { icon?: ReactNode; children: ReactNode }) {
  return <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-line p-8 text-center text-sm text-muted">{icon}{children}</div>
}

export function Skeleton({ className }: { className?: string }) { return <div className={cx('skeleton', className)} /> }

export function ErrorNote({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useI18n()
  const msg = (error as any)?.message === 'offline' ? t('common.offline_blocked') : (error as any)?.detail || (error as any)?.message || t('common.error')
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-stop/30 bg-stop-soft p-4 text-sm text-stop">
      <AlertOctagon className="mt-0.5 size-5 shrink-0" aria-hidden />
      <div className="flex-1">{msg}</div>
      {onRetry && <button onClick={onRetry} className="font-semibold underline">{t('common.retry')}</button>}
    </div>
  )
}

export function SectionTitle({ overline, title, sub, center }: { overline?: ReactNode; title: ReactNode; sub?: ReactNode; center?: boolean }) {
  return (
    <div className={cx('max-w-3xl', center && 'mx-auto text-center')}>
      {overline && <div className="overline mb-3">{overline}</div>}
      <h2 className="text-3xl font-bold leading-tight tracking-tight sm:text-4xl">{title}</h2>
      {sub && <p className="mt-4 text-base text-muted sm:text-lg">{sub}</p>}
    </div>
  )
}

export function PageHeader({ title, sub, actions, icon }: { title: ReactNode; sub?: ReactNode; actions?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="flex items-start gap-3">
        {icon && <div className="grid size-11 place-items-center rounded-2xl bg-brand text-brand-ink shadow-sm">{icon}</div>}
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>
          {sub && <p className="mt-1 max-w-3xl text-sm text-muted sm:text-base">{sub}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

export function KV({ k, v }: { k: ReactNode; v: ReactNode }) {
  return <div className="flex items-baseline justify-between gap-3 py-1.5 text-sm"><span className="max-w-[55%] shrink-0 text-muted">{k}</span><span className="num min-w-0 break-words text-end font-semibold">{v}</span></div>
}

export function Pre({ children }: { children: ReactNode }) {
  return <pre dir="ltr" className="relative scroll-thin max-h-80 overflow-auto rounded-xl bg-surface-2 p-3 text-xs leading-relaxed">{children}</pre>
}
