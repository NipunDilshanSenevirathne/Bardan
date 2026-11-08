import { Loader2, Square, Volume2 } from 'lucide-react'
import { useApi } from '../lib/hooks'
import { useI18n } from '../lib/i18n'
import { useSpeech } from '../lib/speech'
import { cx } from './ui'

/* "Listen": reads a text aloud in the worker's language. `onColor` is for the coloured action card. */
export function ListenButton({ text, onColor = false, className }: { text: string; onColor?: boolean; className?: string }) {
  const { t, lang } = useI18n()
  const s = useSpeech()
  const st = useApi<any>('/sandbox/state')
  const set = st.data?.settings
  const server = !!st.data?.ai_configured && set?.ai_enabled !== false && set?.ai_capabilities?.speech !== false
  const active = s.speaking || s.busy
  return (
    <span className={cx('inline-flex flex-wrap items-center gap-2', className)}>
      <button type="button" aria-pressed={active} aria-label={active ? t('listen.stop') : t('listen.aria')}
        onClick={() => (active ? s.stop() : void s.speak(text, lang, server))}
        className={cx('inline-flex min-h-9 items-center gap-1.5 rounded-xl px-3 text-sm font-semibold transition-colors',
          onColor ? 'bg-white/15 text-white hover:bg-white/25' : 'bg-surface-2 text-ink hover:bg-surface-3')}>
        {s.busy ? <Loader2 className="size-4 animate-spin" aria-hidden />
          : s.speaking ? <Square className="size-3.5" aria-hidden /> : <Volume2 className="flip-rtl size-4" aria-hidden />}
        {active ? t('listen.stop') : t('listen')}
      </button>
      {s.unavailable && <span role="status" className={cx('text-xs', onColor ? 'text-white/85' : 'text-muted')}>{t('listen.unavailable')}</span>}
    </span>
  )
}
