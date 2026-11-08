import QRCode from 'qrcode'
import { Eye, FileDown, HeartHandshake, History, Link2, Lock, Printer, QrCode, ShieldCheck, ShieldOff } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ListenButton } from '../../components/ListenButton'
import { Badge, Button, Card, CardHeader, ErrorNote, Modal, PageHeader, Pre, Skeleton, cx } from '../../components/ui'
import { api, enqueue, useStore } from '../../lib/api'
import { useApi } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'

export default function Data() {
  const { t, lang } = useI18n()
  const qc = useQueryClient()
  const offline = useStore((s) => s.offline)
  const health = useApi<any>('/worker/health')
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<unknown>(null)
  const [fields, setFields] = useState<string[]>(['results', 'referrals'])
  const [recipient, setRecipient] = useState('Dr Shrestha')
  const [region, setRegion] = useState('AE')
  const [preview, setPreview] = useState<any>(null)
  const [link, setLink] = useState<any>(null)
  const [copy, setCopy] = useState<any>(null)

  async function consent(purpose: string, action: 'grant' | 'withdraw') {
    setBusy(purpose); setErr(null); setMsg(null)
    try {
      if (offline) {
        // Local withdrawal stops optional sharing on this device at once; servers update on sync (§20.4).
        enqueue('consent', { purpose, action })
        setMsg(lang === 'ar' ? 'سُجّل التغيير على هذا الهاتف وسيُرسل عند الاتصال.' : 'Saved on this phone; it will be sent when a connection exists.')
      } else {
        const r = await api('/consents/events', { body: { purpose, action } })
        setMsg(r.message)
      }
      await qc.invalidateQueries()
    } catch (e) { setErr(e) } finally { setBusy(null) }
  }
  async function doPreview() {
    setErr(null); setLink(null); setCopy(null)
    try { setPreview(await api('/exports/preview', { body: { fields, recipient_name: recipient, recipient_region: region, online: !offline } })) } catch (e) { setErr(e) }
  }
  async function doExport(kind: 'share_link' | 'worker_copy') {
    setErr(null)
    try {
      const r = await api('/exports', { body: { preview_id: preview.id, confirm: true, kind } })
      if (kind === 'share_link') setLink(r); else setCopy(r)
      await qc.invalidateQueries()
    } catch (e) { setErr(e) }
  }

  if (health.isLoading) return <Skeleton className="h-96" />
  if (health.error) return <ErrorNote error={health.error} onRetry={() => health.refetch()} />
  const d = health.data
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <PageHeader title={t('d.title')} sub={t('d.sub')} icon={<ShieldCheck className="size-6" />} />
      {msg && <div className="rounded-2xl border border-ok/30 bg-ok-soft p-4 text-sm font-semibold text-ok">{msg}</div>}
      {err ? <ErrorNote error={err} /> : null}
      <Promises />

      <Card>
        <CardHeader title={t('d.title')} icon={<Lock className="size-5" />} />
        <ul className="divide-y divide-line">
          {d.consents.map((c: any) => (
            <li key={c.purpose} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 font-semibold">{lang === 'ar' ? c.label_ar : c.label_en}
                  {c.withdrawable ? <Badge tone="neutral">{t('d.optional')}</Badge> : <Badge tone="brand">{t('d.required')}</Badge>}</div>
                <p className="mt-1 text-sm text-muted">{lang === 'ar' ? c.explain_ar : c.explain_en}</p>
              </div>
              {c.withdrawable ? (
                <Button size="md" variant={c.active ? 'outline' : 'primary'} loading={busy === c.purpose}
                  icon={c.active ? <ShieldOff className="size-4" /> : <ShieldCheck className="size-4" />}
                  onClick={() => consent(c.purpose, c.active ? 'withdraw' : 'grant')}>{c.active ? t('d.withdraw') : t('d.grant')}</Button>
              ) : <Badge tone="ok">{t('d.on')}</Badge>}
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <CardHeader title={t('d.passport')} sub={t('d.passport.b')} icon={<QrCode className="size-5" />} />
        <div className="space-y-4 p-5">
          <div className="flex flex-wrap gap-2">
            {['results', 'referrals', 'care_plan', 'hydration'].map((f) => (
              <button key={f} onClick={() => setFields((x) => x.includes(f) ? x.filter((y) => y !== f) : [...x, f])} aria-pressed={fields.includes(f)}
                className={cx('min-h-10 rounded-xl border px-3 text-sm font-semibold', fields.includes(f) ? 'border-brand bg-brand-soft text-brand' : 'border-line')}>{f.replace('_', ' ')}</button>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="text-sm font-semibold">{t('d.recipient')}<input value={recipient} onChange={(e) => setRecipient(e.target.value)} className="mt-1 h-11 w-full rounded-xl border border-line bg-surface px-3" /></label>
            <label className="text-sm font-semibold">{t('d.region')}
              <select value={region} onChange={(e) => setRegion(e.target.value)} className="mt-1 h-11 w-full rounded-xl border border-line bg-surface px-3">
                <option value="AE">{t('d.uae')}</option><option value="NP">{t('d.abroad')}</option>
              </select>
            </label>
          </div>
          <Button onClick={doPreview} icon={<Eye className="size-4" />}>{t('d.preview')}</Button>
          {preview && (
            <div className="space-y-3 rounded-2xl border border-line p-4">
              <div className="text-sm font-bold">{t('d.gate')}</div>
              <ul className="space-y-1 text-sm">
                {preview.gate.checks.map((c: any) => <li key={c.check} className={cx('flex gap-2', c.ok ? 'text-ok' : 'text-stop')}>{c.ok ? '✓' : '✗'} <span>{c.check.replaceAll('_', ' ')}{c.detail ? ` — ${c.detail}` : ''}</span></li>)}
              </ul>
              <p className="rounded-xl bg-warn-soft p-3 text-sm font-semibold text-warn">{t('d.no_recall')}</p>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => doExport('share_link')} disabled={!preview.gate.share_link_permitted} icon={<Link2 className="size-4" />}>{t('d.create_link')}</Button>
                <Button variant="soft" onClick={() => doExport('worker_copy')} disabled={!preview.gate.worker_held_copy_permitted} icon={<FileDown className="size-4" />}>{t('d.my_copy')}</Button>
              </div>
            </div>
          )}
          {link && <ShareLink link={link} />}
        </div>
      </Card>

      <Card>
        <CardHeader title={t('d.who')} icon={<History className="size-5" />} />
        <ul className="divide-y divide-line text-sm">
          {d.who_saw_my_data.length === 0 && <li className="px-5 py-4 text-muted">{t('common.none')}</li>}
          {d.who_saw_my_data.slice().reverse().map((e: any) => (
            <li key={e.seq} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3">
              <span><span className="font-semibold">{e.actor}</span> · {e.role} · {e.action}</span>
              <span className="flex items-center gap-2"><Badge tone={e.decision === 'denied' ? 'stop' : 'neutral'}>{e.decision}</Badge><span className="text-xs text-muted" dir="ltr">{e.at.slice(11, 16)}</span></span>
            </li>
          ))}
        </ul>
      </Card>
      <Modal open={!!copy} onClose={() => setCopy(null)} title={t('d.passport')} wide>
        {copy && <PassportPrint bundle={copy.bundle} />}
      </Modal>
    </div>
  )
}

/* What Bardan promises every worker (finalsystem.md §7.5): plain words, read aloud in the worker's language. */
const PROMISES = ['pr.1', 'pr.2', 'pr.3', 'pr.4', 'pr.5', 'pr.6']
function Promises() {
  const { t } = useI18n()
  return (
    <Card>
      <CardHeader title={t('pr.title')} sub={t('pr.sub')} icon={<HeartHandshake className="size-5" />}
        action={<ListenButton text={`${t('pr.title')}. ${PROMISES.map((k) => t(k)).join(' ')}`} />} />
      <ol className="grid grid-cols-1 gap-2 p-5 sm:grid-cols-2">
        {PROMISES.map((k, i) => (
          <li key={k} className="flex gap-3 rounded-2xl bg-surface-2 p-3 text-sm leading-relaxed">
            <span className="num grid size-7 shrink-0 place-items-center rounded-full bg-brand text-xs font-bold text-brand-ink">{i + 1}</span>
            <span>{t(k)}</span>
          </li>
        ))}
      </ol>
    </Card>
  )
}

function ShareLink({ link }: { link: any }) {
  const { t } = useI18n()
  const [qr, setQr] = useState('')
  const url = `${window.location.origin}${link.path}?code=${link.passcode}`
  useEffect(() => { void QRCode.toDataURL(url, { margin: 1, width: 220 }).then(setQr) }, [url])
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-brand/30 bg-brand-soft p-5 text-center sm:flex-row sm:text-start">
      {qr && <img src={qr} alt="QR code for the share link" className="size-40 rounded-xl bg-white p-2" />}
      <div className="min-w-0 space-y-1 text-sm">
        <div className="font-bold text-brand">{t('d.link_ready')}</div>
        <div className="break-all" dir="ltr">{url}</div>
        <div>{t('d.passcode')}: <span className="num font-bold" dir="ltr">{link.passcode}</span> · {t('d.expires')}: <span dir="ltr">{link.expires_at.slice(0, 16).replace('T', ' ')}</span></div>
        <div className="font-semibold text-warn">{t('d.no_recall')}</div>
      </div>
    </div>
  )
}

export function PassportPrint({ bundle }: { bundle: any }) {
  const { t, lang } = useI18n()
  const res = bundle.entry.map((e: any) => e.resource)
  const patient = res.find((r: any) => r.resourceType === 'Patient')
  const obs = res.filter((r: any) => r.resourceType === 'Observation')
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-line p-5">
        <div className="flex items-center justify-between"><img src="/icons/logo-96.png" alt="" className="size-10" /><Badge tone="sun">SYNTHETIC</Badge></div>
        <h3 className="mt-3 text-xl font-bold">{lang === 'ar' ? 'جواز الكلى: ملخص رعاية' : 'Kidney Passport: care summary'}</h3>
        <p className="text-sm text-muted">{patient?.name?.[0]?.text} · {bundle.timestamp.slice(0, 10)}</p>
        <table className="mt-4 w-full text-sm">
          <thead><tr className="text-start text-muted"><th className="py-1 text-start">Test</th><th className="text-start">Result</th><th className="text-start">Date</th></tr></thead>
          <tbody>{obs.map((o: any) => <tr key={o.id} className="border-t border-line"><td className="py-2">{o.code.text}</td><td className="num" dir="ltr">{o.valueQuantity.value} {o.valueQuantity.unit}</td><td dir="ltr">{o.effectiveDateTime.slice(0, 10)}</td></tr>)}</tbody>
        </table>
        <p className="mt-4 text-xs text-muted">{lang === 'ar' ? 'ملخص وقائعي وليس تشخيصاً. لا يمكن استرجاع النسخ التي تم تنزيلها.' : 'A factual summary, not a diagnosis. Downloaded copies cannot be recalled.'}</p>
      </div>
      <details><summary className="cursor-pointer text-sm font-semibold">FHIR R4 Bundle (JSON)</summary><Pre>{JSON.stringify(bundle, null, 2)}</Pre></details>
      <div className="flex gap-2">
        <Button onClick={() => window.print()} icon={<Printer className="size-4" />}>{t('common.print')}</Button>
        <Button variant="soft" icon={<FileDown className="size-4" />} onClick={() => {
          const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/fhir+json' }))
          a.download = 'kidney-passport-SYNTHETIC.json'; a.click()
        }}>FHIR JSON</Button>
      </div>
    </div>
  )
}
