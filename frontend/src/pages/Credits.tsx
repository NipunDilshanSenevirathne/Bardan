import { ArrowLeft, Camera, Database, FileBadge2, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { Badge, Button, Card, CardHeader, Skeleton } from '../components/ui'
import { usePublicApi } from '../lib/hooks'
import { useI18n } from '../lib/i18n'

const PHOTOS = [
  { file: 'hero-slab', what: 'Workers on a concrete slab' },
  { file: 'rebar-crew', what: 'Rebar crew at work' },
  { file: 'sunset-crane', what: 'Crane at sunset' },
  { file: 'dubai-skyline', what: 'Dubai skyline with tower cranes' },
  { file: 'rebar-inspect', what: 'Rebar inspection' },
  { file: 'rebar-aerial', what: 'Rebar mesh from above' },
  { file: 'crane-lift', what: 'Crane lifting a concrete panel' },
  { file: 'tower-crane', what: 'Tower crane' },
  { file: 'frame-worker', what: 'Worker on a steel frame' },
]

export default function Credits() {
  const { t, lang, setLang } = useI18n()
  const lic = usePublicApi<any>('/reports/licences')
  const photos: any[] = lic.data?.photos ?? []
  return (
    <div className="min-h-dvh bg-canvas">
      <header className="border-b border-line bg-surface">
        <div className="container-x flex h-16 items-center justify-between">
          <Logo />
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => setLang(lang === 'ar' ? 'en' : 'ar')}>{lang === 'ar' ? 'English' : 'العربية'}</Button>
            <Link to="/" className="inline-flex h-11 items-center gap-2 rounded-xl px-3 text-sm font-semibold hover:bg-surface-2"><ArrowLeft className="flip-rtl size-4" />{t('common.back')}</Link>
          </div>
        </div>
      </header>
      <main className="container-x max-w-5xl space-y-6 py-10">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('footer.credits')}</h1>
          <p className="mt-2 max-w-3xl text-muted">{t('cr.sub')}</p>
        </div>
        <Card>
          <CardHeader title={t('cr.photos')} sub={t('cr.photos_sub')} icon={<Camera className="size-5" />} />
          <ul className="grid grid-cols-1 gap-4 p-5 sm:grid-cols-2 lg:grid-cols-3">
            {PHOTOS.map((p) => {
              const meta = photos.find((x) => x.file === p.file)
              return (
                <li key={p.file} className="overflow-hidden rounded-2xl border border-line">
                  <img src={`/img/${p.file}-640.webp`} alt={p.what} loading="lazy" className="aspect-[4/3] w-full object-cover" />
                  <div className="p-3 text-xs">
                    <div className="font-semibold">{meta?.title ?? p.what}</div>
                    <div className="text-muted">{meta ? <>{t('cr.by')} <a href={meta.author_url} target="_blank" rel="noreferrer" className="underline">{meta.author}</a> · <a href={meta.source_url} target="_blank" rel="noreferrer" className="underline">Unsplash</a></> : 'Unsplash'} · {t('cr.unsplash_licence')}</div>
                  </div>
                </li>
              )
            })}
          </ul>
        </Card>
        <Card>
          <CardHeader title={t('cr.data')} icon={<Database className="size-5" />} />
          <ul className="space-y-3 p-5 text-sm">
            <li><span className="font-semibold">NASA POWER</span> — {t('cr.nasa')}</li>
            <li><span className="font-semibold">Open-Meteo.com</span> — {t('cr.openmeteo')} <Badge tone="neutral">CC BY 4.0</Badge></li>
            <li><span className="font-semibold">{t('cr.synthetic_title')}</span> — {t('cr.synthetic')}</li>
          </ul>
        </Card>
        <Card>
          <CardHeader title={t('cr.software')} icon={<FileBadge2 className="size-5" />} />
          {lic.isLoading ? <Skeleton className="m-5 h-40" /> : (
            <ul className="grid grid-cols-1 gap-x-6 p-5 text-sm sm:grid-cols-2">
              {(lic.data?.items ?? []).map((x: any) => (
                <li key={x.name} className="flex items-center justify-between gap-2 border-b border-line py-2">
                  <span className="font-semibold" dir="ltr">{x.name}</span><Badge tone="neutral">{x.licence}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <div className="flex items-start gap-3 rounded-2xl border border-brand/25 bg-brand-soft p-4 text-sm"><ShieldCheck className="mt-0.5 size-5 shrink-0 text-brand" /><span>{t('footer.claims')}</span></div>
      </main>
    </div>
  )
}
