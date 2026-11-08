/* Zone heat forecast: point line, honest 90% range, observed-so-far overlay and the planning-band strip.
   One y-axis (WBGT, °C). Band washes are recessive; a table view carries every value without hovering. */
import { CloudOff, Table2, TrendingUp } from 'lucide-react'
import { useMemo, useState } from 'react'
import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useI18n } from '../lib/i18n'
import { BAND_ORDER, useVizColors, WBGT_BANDS } from '../lib/viz'
import { BandChip, Card, CardHeader, Tabs, cx } from './ui'
import { L } from '../lib/labels'

const H = 3600_000
const toDubai = (ms: number) => new Date(ms + 4 * H).toISOString()
const hhmm = (ms: number) => toDubai(ms).slice(11, 16)

type Row = { x: number; point?: number; range?: [number, number]; observed?: number; band?: string; probs?: Record<string, number> }

export function ForecastPanel({ fc, mode, onMode, clock }: { fc: any; mode: 'scenario' | 'live'; onMode: (m: 'scenario' | 'live') => void; clock?: string }) {
  const { t, lang } = useI18n()
  const c = useVizColors()
  const zones = Object.keys(fc?.zones ?? {})
  const [zone, setZone] = useState<string>('B')
  const [span, setSpan] = useState<'day' | 'all'>('day')
  const [table, setTable] = useState(false)
  const z = zones.includes(zone) ? zone : zones[0]

  // The planning day: 19 Aug in the scenario; tomorrow (site time) for live forecasts.
  const planDay = useMemo(() => {
    if (!fc?.available) return null
    if (mode === 'scenario') return '2025-08-19'
    const first = fc.zones?.[z]?.[0]?.valid_hour as string | undefined
    if (!first) return null
    const d = new Date(Date.parse(first.slice(0, 10) + 'T00:00:00+04:00') + 24 * H)
    return toDubai(d.getTime()).slice(0, 10)
  }, [fc, mode, z])

  const rows: Row[] = useMemo(() => {
    if (!fc?.available || !z) return []
    const m = new Map<number, Row>()
    for (const r of fc.zones[z] ?? []) {
      const x = Date.parse(r.valid_hour)
      m.set(x, { x, point: r.wbgt_c, range: r.wbgt_c_interval_90 as [number, number], band: r.planning_band, probs: r.twl_band_probs })
    }
    for (const o of fc.observed?.[z] ?? []) {
      const x = Date.parse(o.time)
      const row = m.get(x) ?? { x }
      row.observed = o.wbgt_c
      m.set(x, row)
    }
    return [...m.values()].sort((a, b) => a.x - b.x)
  }, [fc, z])

  const dom = useMemo<[number, number] | null>(() => {
    if (!rows.length) return null
    if (span === 'day' && planDay) return [Date.parse(`${planDay}T05:00:00+04:00`), Date.parse(`${planDay}T19:00:00+04:00`)]
    return [rows[0].x, rows[rows.length - 1].x]
  }, [rows, span, planDay])
  const visible = dom ? rows.filter((r) => r.x >= dom[0] && r.x <= dom[1]) : []
  const ticks = useMemo(() => {
    if (!dom) return []
    const step = span === 'day' ? 2 * H : 12 * H
    const out: number[] = []
    for (let x = Math.ceil(dom[0] / step) * step; x <= dom[1]; x += step) out.push(x)
    return out
  }, [dom, span])
  const middays = useMemo(() => {
    if (!dom) return []
    const out: [number, number][] = []
    const d0 = Date.parse(toDubai(dom[0]).slice(0, 10) + 'T00:00:00+04:00')
    for (let d = d0; d <= dom[1]; d += 24 * H) out.push([d + 12.5 * H, d + 15 * H])
    return out
  }, [dom])
  const nowX = clock ? Date.parse(clock) : null

  // Planning-band strip for every zone, hourly 05:00-18:00 on the planning day.
  const strip = useMemo(() => {
    if (!fc?.available || !planDay) return []
    return zones.map((zid) => {
      const cells = []
      for (let h = 5; h <= 18; h++) {
        const iso = `${planDay}T${String(h).padStart(2, '0')}:00:00+04:00`
        const r = (fc.zones[zid] ?? []).find((x: any) => Date.parse(x.valid_hour) === Date.parse(iso))
        cells.push({ h, band: r?.planning_band ?? 'unavailable', point: r?.wbgt_c, hi: r?.wbgt_c_interval_90?.[1] })
      }
      return { zid, cells }
    })
  }, [fc, planDay, zones])

  if (!fc) return null
  return (
    <Card>
      <CardHeader title={t('p.forecast')} sub={t('p.forecast.b')} icon={<TrendingUp className="size-5" />}
        action={<Tabs value={mode} onChange={onMode} items={[{ id: 'scenario', label: t('p.mode_scenario_short') }, { id: 'live', label: t('p.mode_live_short') }]} />} />
      {!fc.available ? (
        <div className="m-5 flex items-start gap-3 rounded-2xl border border-unknown/30 bg-unknown-soft p-4 text-sm">
          <CloudOff className="mt-0.5 size-5 shrink-0 text-unknown" />
          <div><div className="font-bold">{t('p.unavailable')}</div><div className="mt-1 text-muted">{fc.stale ? t('fc.stale', { h: Math.floor(fc.age_hours) }) : L(fc.reason ?? fc.label, lang)}</div></div>
        </div>
      ) : (
        <div className="space-y-4 p-4 sm:p-5">
          <div className="flex flex-wrap items-center gap-2">
            <Tabs value={z} onChange={setZone} items={zones.map((id) => ({ id, label: `${t('common.zone')} ${id}` }))} />
            <div className="ms-auto flex gap-1">
              <button onClick={() => setSpan('day')} aria-pressed={span === 'day'} className={cx('min-h-10 rounded-xl px-3 text-sm font-semibold', span === 'day' ? 'bg-ink text-surface' : 'bg-surface-2')}>{t('p.span_day')}</button>
              <button onClick={() => setSpan('all')} aria-pressed={span === 'all'} className={cx('min-h-10 rounded-xl px-3 text-sm font-semibold', span === 'all' ? 'bg-ink text-surface' : 'bg-surface-2')}>72 h</button>
              <button onClick={() => setTable((v) => !v)} aria-pressed={table} className={cx('inline-flex min-h-10 items-center gap-1.5 rounded-xl px-3 text-sm font-semibold', table ? 'bg-brand text-brand-ink' : 'bg-surface-2')}><Table2 className="size-4" />{t('common.table')}</button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
            <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-5 rounded" style={{ background: c.s1 }} />{t('p.legend.point')}</span>
            <span className="inline-flex items-center gap-1.5"><span className="h-3 w-5 rounded-sm" style={{ background: c.s1, opacity: 0.18 }} />{t('p.legend.range')}</span>
            {fc.observed && <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-5 rounded" style={{ background: c.s2 }} /><span className="size-2 rounded-full" style={{ background: c.s2 }} />{t('p.legend.live')}</span>}
            <span className="inline-flex items-center gap-1.5"><span className="h-3 w-5 rounded-sm" style={{ background: c.midday }} />{t('p.legend.midday')}</span>
          </div>

          {table ? (
            <div className="relative scroll-thin max-h-80 overflow-auto rounded-xl border border-line">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-surface-2 text-xs text-muted"><tr>
                  <th className="px-3 py-2 text-start">{t('common.time')}</th><th className="px-3 py-2 text-end">{t('p.legend.point')}</th>
                  <th className="px-3 py-2 text-end">{t('p.legend.range')}</th><th className="px-3 py-2 text-end">{t('p.legend.live')}</th>
                  <th className="px-3 py-2 text-start">{t('p.planning_band')}</th></tr></thead>
                <tbody className="divide-y divide-line">
                  {visible.map((r) => (
                    <tr key={r.x}>
                      <td className="num px-3 py-1.5" dir="ltr">{span === 'all' ? toDubai(r.x).slice(5, 16).replace('T', ' ') : hhmm(r.x)}</td>
                      <td className="num px-3 py-1.5 text-end" dir="ltr">{r.point?.toFixed(1) ?? '–'}</td>
                      <td className="num px-3 py-1.5 text-end" dir="ltr">{r.range ? `${r.range[0].toFixed(1)}–${r.range[1].toFixed(1)}` : '–'}</td>
                      <td className="num px-3 py-1.5 text-end" dir="ltr">{r.observed?.toFixed(1) ?? '–'}</td>
                      <td className="px-3 py-1.5">{r.band ? <BandChip band={r.band} /> : '–'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="h-72 w-full" dir="ltr" role="img" aria-label={`${t('p.forecast')} · ${t('common.zone')} ${z}`}>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={visible} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
                  {WBGT_BANDS.map((b) => <ReferenceArea key={b.band} y1={b.from} y2={b.to} fill={c.bands[b.band]} fillOpacity={0.09} stroke="none" ifOverflow="hidden" />)}
                  {middays.map(([a, b2]) => <ReferenceArea key={a} x1={a} x2={b2} fill={c.midday} fillOpacity={1} stroke="none" ifOverflow="hidden" />)}
                  <CartesianGrid stroke={c.grid} vertical={false} />
                  <XAxis dataKey="x" type="number" scale="time" domain={dom ?? ['auto', 'auto']} ticks={ticks} allowDataOverflow
                    tickFormatter={(v) => span === 'all' ? toDubai(v).slice(8, 13).replace('T', ' ') + 'h' : hhmm(v)}
                    tick={{ fill: c.muted, fontSize: 11 }} axisLine={{ stroke: c.line }} tickLine={false} />
                  <YAxis domain={[26, 36]} ticks={[26, 28, 31, 33, 36]} tick={{ fill: c.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={44}
                    tickFormatter={(v) => `${v}°`} />
                  {nowX && dom && nowX >= dom[0] && nowX <= dom[1] && <ReferenceLine x={nowX} stroke={c.ink2} strokeWidth={1} label={{ value: t('common.now'), position: 'insideTopRight', fill: c.ink2, fontSize: 11 }} />}
                  <Area dataKey="range" stroke="none" fill={c.s1} fillOpacity={0.16} isAnimationActive={false} connectNulls />
                  <Line dataKey="point" stroke={c.s1} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls strokeLinecap="round" />
                  <Line dataKey="observed" stroke={c.s2} strokeWidth={2} dot={{ r: 3, fill: c.s2, stroke: c.surface, strokeWidth: 2 }} activeDot={{ r: 5 }} isAnimationActive={false} connectNulls />
                  <Tooltip cursor={{ stroke: c.ink2, strokeWidth: 1 }} content={<FcTooltip lang={lang} span={span} />} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Band strip: planning band (upper end of the 90% range) per zone and hour */}
          {strip.length > 0 && (
            <div>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm font-semibold">{t('p.strip_title', { d: planDay ?? '' })}</div>
                <div className="flex flex-wrap gap-1.5">{BAND_ORDER.map((b) => <BandChip key={b} band={b} />)}</div>
              </div>
              <div className="relative scroll-thin overflow-x-auto" dir="ltr">
                <div className="grid min-w-[560px] gap-1" style={{ gridTemplateColumns: `3.25rem repeat(14, minmax(0, 1fr))` }}>
                  <div />
                  {strip[0].cells.map((cl) => <div key={cl.h} className="num text-center text-[10px] text-muted">{String(cl.h).padStart(2, '0')}</div>)}
                  {strip.map((row) => (
                    <div key={row.zid} className="contents">
                      <div className="flex items-center text-xs font-bold">{t('common.zone_short')} {row.zid}</div>
                      {row.cells.map((cl) => (
                        <div key={cl.h} title={`${t('common.zone')} ${row.zid} · ${String(cl.h).padStart(2, '0')}:00 · ${t(`band.${cl.band}`)}${cl.hi != null ? ` · ≤ ${cl.hi.toFixed(1)} °C` : ''}`}
                          className={cx('h-7 rounded-md', cl.h >= 12 && cl.h < 15 && 'ring-1 ring-inset ring-ink/20')}
                          style={{ background: c.bands[cl.band] ?? c.bands.unavailable, opacity: cl.band === 'unavailable' ? 0.4 : 0.85 }}>
                          <span className="sr-only">{t(`band.${cl.band}`)}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
          <div className="grid grid-cols-1 gap-2 text-xs text-muted sm:grid-cols-2">
            <div><span className="font-semibold text-ink-2">{t('p.issued', { t: (fc.issued_at ?? '').slice(0, 16).replace('T', ' ') })}</span> · {L(fc.label, lang)}</div>
            <div>{L(fc.method?.interval, lang)} · {L(fc.method?.planning_band, lang)}</div>
            {fc.observed_label && <div className="sm:col-span-2">{L(fc.observed_label, lang)}</div>}
            {fc.attribution && <div className="sm:col-span-2">{fc.attribution}</div>}
          </div>
        </div>
      )}
    </Card>
  )
}

function FcTooltip({ active, payload, lang, span }: any) {
  const c = useVizColors()
  const { t } = useI18n()
  if (!active || !payload?.length) return null
  const r: Row = payload[0].payload
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2 text-xs shadow-float" dir={lang === 'ar' ? 'rtl' : 'ltr'}>
      <div className="num mb-1 font-semibold text-muted" dir="ltr">{span === 'all' ? toDubai(r.x).slice(5, 16).replace('T', ' ') : hhmm(r.x)}</div>
      {r.point != null && <div className="flex items-center gap-2"><span className="h-0.5 w-3 rounded" style={{ background: c.s1 }} /><span className="num font-bold" dir="ltr">{r.point.toFixed(1)} °C</span><span className="text-muted">{t('p.legend.point')}</span></div>}
      {r.range && <div className="flex items-center gap-2"><span className="h-2 w-3 rounded-sm" style={{ background: c.s1, opacity: 0.25 }} /><span className="num font-bold" dir="ltr">{r.range[0].toFixed(1)}–{r.range[1].toFixed(1)}</span><span className="text-muted">{t('p.legend.range')}</span></div>}
      {r.observed != null && <div className="flex items-center gap-2"><span className="h-0.5 w-3 rounded" style={{ background: c.s2 }} /><span className="num font-bold" dir="ltr">{r.observed.toFixed(1)} °C</span><span className="text-muted">{t('p.legend.live')}</span></div>}
      {r.band && <div className="mt-1.5"><BandChip band={r.band} /></div>}
    </div>
  )
}
