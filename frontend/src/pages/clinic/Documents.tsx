import { Ban, CheckCircle2, FileImage, FileSearch, ScanText, ShieldCheck, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Badge, Button, Card, CardHeader, ErrorNote, PageHeader, Skeleton, cx } from '../../components/ui'
import { api } from '../../lib/api'
import { useApi } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'

export default function Documents() {
  const { t } = useI18n()
  const qc = useQueryClient()
  const queue = useApi<any>('/clinical/queue')
  const docs: any[] = queue.data?.documents ?? []
  const patients: any[] = queue.data?.patients ?? []
  const [doc, setDoc] = useState('doc_lab_anwar')
  const [who, setWho] = useState('W07')
  const [img, setImg] = useState<string | null>(null)
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<unknown>(null)

  useEffect(() => {
    let url: string | null = null
    setImg(null); setRes(null)
    api<Blob>(`/clinical/documents/${doc}/image`).then((b) => { url = URL.createObjectURL(b); setImg(url) }).catch(() => setImg(null))
    return () => { if (url) URL.revokeObjectURL(url) }
  }, [doc])

  async function extract() {
    setBusy(true); setErr(null)
    try { setRes(await api('/clinical/documents/extract', { body: { doc_id: doc, worker_ref: who } })); await qc.invalidateQueries() } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  if (queue.isLoading) return <Skeleton className="h-96" />
  if (queue.error) return <ErrorNote error={queue.error} onRetry={() => queue.refetch()} />
  const quarantined = res?.status === 'quarantined'

  return (
    <div className="space-y-6">
      <PageHeader title={t('cl.documents')} sub={t('cl.documents_sub')} icon={<FileSearch className="size-6" />} />
      <div className="flex flex-wrap gap-2">
        {docs.map((d) => (
          <button key={d.id} onClick={() => setDoc(d.id)} aria-pressed={doc === d.id}
            className={cx('min-h-11 rounded-2xl border px-4 text-start text-sm font-semibold', doc === d.id ? 'border-brand bg-brand-soft text-brand' : 'border-line bg-surface hover:bg-surface-2')}>
            <FileImage className="me-2 inline size-4" />{t(`doc.${d.id}`)}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card className="overflow-hidden">
          <CardHeader title={t('cl.original')} sub={t('cl.original_sub')} icon={<FileImage className="size-5" />} action={<Badge tone="sun">{t('common.synthetic')}</Badge>} />
          <div className="bg-surface-2 p-4">
            {img ? <img src={img} alt={t('cl.original_alt')} className="mx-auto max-h-[640px] w-auto rounded-lg border border-line bg-white shadow-card" /> : <Skeleton className="h-96" />}
          </div>
        </Card>
        <Card>
          <CardHeader title={t('cl.extract')} sub={t('cl.extract_sub')} icon={<ScanText className="size-5" />} />
          <div className="space-y-4 p-5">
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-sm font-semibold">{t('cl.expected_patient')}
                <select value={who} onChange={(e) => setWho(e.target.value)} className="mt-1 block h-11 rounded-xl border border-line bg-surface px-3">
                  {patients.map((p) => <option key={p.worker_ref} value={p.worker_ref}>{p.name}</option>)}
                </select>
              </label>
              <Button onClick={extract} loading={busy} icon={<ScanText className="size-4" />}>{t('cl.extract')}</Button>
            </div>
            {err ? <ErrorNote error={err} /> : null}
            {res && (
              <>
                <div className={cx('flex items-start gap-3 rounded-2xl p-4', quarantined ? 'bg-stop-soft' : 'bg-brand-soft')}>
                  {quarantined ? <Ban className="mt-0.5 size-5 text-stop" /> : <ShieldCheck className="mt-0.5 size-5 text-brand" />}
                  <div>
                    <div className={cx('font-bold', quarantined ? 'text-stop' : 'text-brand')}>{quarantined ? t('cl.quarantined') : t('cl.draft_for_verification')}</div>
                    {quarantined && <div className="mt-1 flex flex-wrap gap-1">{res.problems.map((p: string) => <Badge key={p} tone="stop">{t(`prob.${p}`)}</Badge>)}</div>}
                    <div className="mt-1 text-xs text-ink-2">{t('cl.method_label')}: {res.method === 'text_layer_parser' ? t('cl.method_text') : t('cl.method_ai')}</div>
                  </div>
                </div>
                <div>
                  <div className="mb-2 text-sm font-semibold">{t('cl.verify_fields')}</div>
                  <table className="w-full text-sm">
                    <tbody className="divide-y divide-line">
                      {Object.entries(res.fields).filter(([k]) => k !== 'evidence').map(([k, v]) => (
                        <tr key={k}><td className="py-2 text-muted">{t(`fld.${k}`)}</td><td className="num py-2 text-end font-semibold" dir="ltr">{String(v ?? '–')}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div>
                  <div className="mb-2 text-sm font-semibold">{t('cl.checks')}</div>
                  <ul className="space-y-1.5 text-sm">
                    {res.checks.map((c: any) => <li key={c.check} className={cx('flex items-center gap-2', c.ok ? 'text-ok' : 'text-stop')}>{c.ok ? <CheckCircle2 className="size-4" /> : <XCircle className="size-4" />}{t(`chk.${c.check}`)}{c.note && <span className="text-xs text-muted">· {t('cl.never_converted')}</span>}</li>)}
                  </ul>
                </div>
                <div>
                  <div className="mb-2 text-sm font-semibold">{t('cl.evidence_lines')}</div>
                  <ul className="space-y-1">
                    {res.evidence_highlights.map((e: any, i: number) => <li key={i} className="rounded-lg bg-warn-soft/60 px-2 py-1"><code className="text-xs" dir="ltr">{e.text}</code></li>)}
                  </ul>
                </div>
                <p className="text-xs text-muted">{quarantined ? t('cl.quarantine_note') : t('cl.verify_note')}</p>
                {!quarantined && <Link to="/app/clinic" className="inline-flex text-sm font-semibold text-brand underline">{t('cl.go_import')}</Link>}
              </>
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}
