import { KeyRound, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { Badge, Button, Card, ErrorNote } from '../components/ui'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { PassportPrint } from './worker/Data'

/* Recipient view of a worker-held care summary: needs the link AND the passcode; expires; revoked on withdrawal. */
export default function Passport() {
  const { t, lang, setLang } = useI18n()
  const { token = '' } = useParams()
  const [params] = useSearchParams()
  const [code, setCode] = useState(params.get('code') ?? '')
  const [data, setData] = useState<any>(null)
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  async function open(c = code) {
    setBusy(true); setErr(null)
    try { setData(await api(`/passport/${encodeURIComponent(token)}?code=${encodeURIComponent(c)}`, { auth: false })) } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  useEffect(() => { if (params.get('code')) void open(params.get('code')!) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="min-h-dvh bg-canvas">
      <header className="no-print border-b border-line bg-surface">
        <div className="container-x flex h-16 items-center justify-between">
          <Logo />
          <Button variant="ghost" onClick={() => setLang(lang === 'ar' ? 'en' : 'ar')}>{lang === 'ar' ? 'English' : 'العربية'}</Button>
        </div>
      </header>
      <main className="container-x max-w-3xl py-10">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid size-12 place-items-center rounded-2xl bg-brand text-brand-ink"><ShieldCheck className="size-6" /></div>
          <div><h1 className="text-2xl font-bold">{t('d.passport')}</h1><p className="text-sm text-muted">{t('pp.sub')}</p></div>
          <Badge tone="sun" className="ms-auto">{t('common.synthetic')}</Badge>
        </div>
        {!data && (
          <Card className="p-6">
            <form onSubmit={(e) => { e.preventDefault(); void open() }} className="flex flex-wrap items-end gap-3">
              <label className="min-w-0 flex-1 text-sm font-semibold">{t('d.passcode')}
                <input value={code} onChange={(e) => setCode(e.target.value)} required inputMode="numeric" className="mt-1 block h-12 w-full rounded-xl border border-line bg-surface px-4 text-lg tracking-widest" dir="ltr" />
              </label>
              <Button type="submit" size="lg" loading={busy} icon={<KeyRound className="size-5" />}>{t('common.open')}</Button>
            </form>
            <p className="mt-3 text-xs text-muted">{t('pp.note')}</p>
            {err ? <div className="mt-4"><ErrorNote error={err} /></div> : null}
          </Card>
        )}
        {data && (
          <div className="space-y-4">
            <div className="rounded-2xl border border-line bg-surface p-4 text-sm"><span className="font-semibold">{t('d.recipient')}:</span> {data.recipient?.name ?? '–'} · {t('d.expires')}: <span dir="ltr">{String(data.expires_at).slice(0, 16).replace('T', ' ')}</span></div>
            <Card className="p-5"><PassportPrint bundle={data.bundle} /></Card>
          </div>
        )}
      </main>
    </div>
  )
}
