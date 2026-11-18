import { Bot, ClipboardPlus, FlaskConical, Send, ShieldCheck, ShieldX, Siren, UserRound } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { EmergencyCard } from '../../components/EmergencyCard'
import { ListenButton } from '../../components/ListenButton'
import { Badge, Button, ErrorNote, PageHeader, cx } from '../../components/ui'
import { api } from '../../lib/api'
import { useApi } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'

type Msg = { role: 'me' | 'bot'; text: string; source?: string; gate?: string; trace?: string; emergency?: boolean; checkin?: boolean }

export default function Ask() {
  const { t, lang } = useI18n()
  const st = useApi<any>('/sandbox/state')
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<unknown>(null)
  const [em, setEm] = useState(false)
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs])

  async function ask(question: string) {
    if (!question.trim()) return
    setErr(null); setBusy(true)
    setMsgs((m) => [...m, { role: 'me', text: question }])
    setQ('')
    try {
      const r = await api('/assist/chat', { body: { question } })
      setMsgs((m) => [...m, { role: 'bot', text: r.answer.text, source: r.answer.source, gate: r.gate, trace: r.trace_id,
        emergency: !!r.answer.open_emergency, checkin: !!r.answer.open_checkin }])
      // Urgent words open the emergency card at once; nothing waits for a confirmation (T68).
      if (r.answer.open_emergency) setEm(true)
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  const redteam = st.data?.settings?.redteam_mode

  return (
    <div className="mx-auto flex max-w-3xl flex-col">
      <PageHeader title={t('a.title')} sub={t('a.sub')} icon={<Bot className="size-6" />} />
      {redteam && (
        <div className="mb-4 flex items-start gap-3 rounded-2xl border border-sun/40 bg-sun-soft p-4 text-sm">
          <FlaskConical className="mt-0.5 size-5 shrink-0 text-sun" />
          <div><div className="font-bold text-sun">{t('a.redteam_on')}</div><div className="text-ink-2">{t('settings.redteam.b')}</div></div>
        </div>
      )}
      <div className="flex min-h-[40vh] flex-col gap-4 rounded-3xl border border-line bg-surface p-4 sm:p-6">
        {msgs.length === 0 && (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {['a.suggest1', 'a.suggest2', 'a.suggest3', 'a.suggest4'].map((k) => (
              <button key={k} onClick={() => ask(t(k))} className="rounded-2xl border border-line p-4 text-start text-sm font-semibold hover:border-brand hover:bg-brand-soft">{t(k)}</button>
            ))}
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={cx('flex gap-3', m.role === 'me' && 'flex-row-reverse')}>
            <span className={cx('grid size-9 shrink-0 place-items-center rounded-full', m.role === 'me' ? 'bg-brand text-brand-ink' : 'bg-surface-3')}>
              {m.role === 'me' ? <UserRound className="size-5" /> : <img src="/icons/logo-96.png" alt="" className="size-7" />}
            </span>
            <div data-tour={m.role === 'bot' ? 'ask-answer' : undefined} className={cx('max-w-[85%] rounded-3xl px-4 py-3', m.role === 'me' ? 'bg-brand text-brand-ink' : 'bg-surface-2')}>
              <p dir="auto" className="whitespace-pre-line leading-relaxed">{m.text}</p>
              {m.emergency && <Button variant="danger" size="sm" className="mt-3" icon={<Siren className="size-4" />} onClick={() => setEm(true)}>{t('a.open_emergency')}</Button>}
              {m.checkin && <Link to="/app/worker/report" className="mt-3 inline-flex min-h-10 items-center gap-2 rounded-xl bg-brand px-3 text-sm font-semibold text-brand-ink"><ClipboardPlus className="size-4" />{t('a.open_checkin')}</Link>}
              {m.role === 'bot' && (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <ListenButton text={m.text} />
                  <Badge tone={m.source === 'ai_assisted' ? 'cyan' : 'neutral'}>{m.source === 'ai_assisted' ? t('a.ai') : t('a.approved')}</Badge>
                  {m.gate === 'blocked'
                    ? <Badge tone="sun" icon={<ShieldX className="size-3" />}>{t('a.blocked_note')}</Badge>
                    : <Badge tone="ok" icon={<ShieldCheck className="size-3" />}>{t('a.checked')}</Badge>}
                  {m.trace && <Link to="/app/trust" className="text-xs font-semibold text-brand underline">{t('tr.trace')} · {m.trace}</Link>}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && <div className="flex gap-3"><span className="grid size-9 place-items-center rounded-full bg-surface-3"><Bot className="size-5" /></span><div className="rounded-3xl bg-surface-2 px-4 py-3"><span className="inline-flex gap-1"><span className="size-2 animate-bounce rounded-full bg-muted" /><span className="size-2 animate-bounce rounded-full bg-muted [animation-delay:120ms]" /><span className="size-2 animate-bounce rounded-full bg-muted [animation-delay:240ms]" /></span></div></div>}
        <div ref={end} />
      </div>
      {err ? <div className="mt-3"><ErrorNote error={err} /></div> : null}
      <form className="sticky bottom-24 mt-4 flex gap-2 lg:bottom-4" onSubmit={(e) => { e.preventDefault(); void ask(q) }}>
        <label htmlFor="askq" className="sr-only">{t('a.placeholder')}</label>
        <input id="askq" data-tour="ask-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('a.placeholder')} dir="auto"
          className="h-14 min-w-0 flex-1 rounded-2xl border border-line bg-surface px-4 shadow-card" />
        <Button type="submit" size="lg" className="h-14" loading={busy} icon={<Send className="flip-rtl size-5" />}>{t('a.send')}</Button>
      </form>
      <p className="mt-3 text-center text-xs text-muted">{lang === 'ar' ? 'إذا شعرت بمرض شديد، اضغط زر الطوارئ أو اتصل بالرقم 998.' : 'If you feel very sick, press Emergency or call 998.'}</p>
      <EmergencyCard open={em} onClose={() => setEm(false)} />
    </div>
  )
}
