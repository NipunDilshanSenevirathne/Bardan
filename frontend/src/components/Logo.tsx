import { Link } from 'react-router-dom'
import { useI18n } from '../lib/i18n'
import { cx } from './ui'

export function Logo({ to = '/', light, compact }: { to?: string; light?: boolean; compact?: boolean }) {
  const { t, lang } = useI18n()
  return (
    <Link to={to} className="group inline-flex items-center gap-2.5" aria-label={t('app.name')}>
      <img src="/icons/logo-96.png" alt="" width={40} height={40} className="size-10 drop-shadow-sm transition-transform group-hover:scale-105" />
      {!compact && (
        <span className="flex flex-col leading-none">
          <span className={cx('text-xl font-extrabold tracking-tight', light ? 'text-white' : 'text-ink')}>{t('app.name')}</span>
          <span className={cx('mt-1 text-[10px] font-semibold tracking-[0.2em] uppercase', light ? 'text-white/70' : 'text-muted')}>
            {lang === 'ar' ? 'Bardan' : 'بَرْدًا'}
          </span>
        </span>
      )}
    </Link>
  )
}
