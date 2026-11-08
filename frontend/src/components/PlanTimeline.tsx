/* Schedule and staggered breaks on the 05:00-19:00 grid (quarter-hour resolution).
   Task bars sit on a wash of their zone's planning band; breaks, rest-seat demand and new workers' heat time
   are shown underneath. A table view carries the same facts without hover. */
import { Armchair, Coffee, Table2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useI18n, pick } from '../lib/i18n'
import { quarterLabel, slotLabel, SLOT_COUNT, useVizColors } from '../lib/viz'
import { Badge, cx } from './ui'

const Q = SLOT_COUNT * 2   // 56 quarter-hour columns

export function PlanTimeline({ plan, draft, grid, crewSize, restAreas, workers }: {
  plan: any; draft?: any; grid?: any; crewSize: Record<string, number>; restAreas: any[]; workers: Record<string, any>
}) {
  const { t, lang } = useI18n()
  const c = useVizColors()
  const [table, setTable] = useState(false)
  const tasks: any[] = plan?.tasks ?? []
  const breaks: any[] = plan?.breaks ?? []
  const midday: boolean[] = grid?.midday ?? []

  const draftSlots = useMemo(() => {
    const m: Record<string, Set<number>> = {}
    for (const tk of draft?.tasks ?? []) m[tk.id] = new Set(tk.slots)
    return m
  }, [draft])

  // Rest-seat demand per rest area and quarter: sum of crew sizes on break.
  const demand = useMemo(() => {
    const out: Record<string, number[]> = {}
    for (const r of restAreas) out[r.id] = Array(Q).fill(0)
    for (const b of breaks) {
      const n = (b.crews ?? [b.crew]).reduce((s: number, cr: string) => s + (crewSize[cr] ?? 0), 0)
      for (let q = b.start_q; q < b.start_q + (b.quarters ?? 1); q++) if (out[b.rest_area] && q < Q) out[b.rest_area][q] += n
    }
    return out
  }, [breaks, restAreas, crewSize])

  const crews = useMemo(() => [...new Set(tasks.map((x) => x.crew))].sort(), [tasks])
  const newWorkers = useMemo(() => Object.entries(plan?.assignments ?? {}).filter(([wid]) => workers[wid]?.acclimatization !== 'acclimatized').slice(0, 6), [plan, workers])

  const col = (q: number, span = 1) => ({ gridColumn: `${q + 2} / span ${span}` })
  const bandAt = (zone: string, q: number) => grid?.zones?.[zone]?.[Math.floor(q / 2)]?.band ?? 'unavailable'

  if (!plan) return null
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-ink-2">
        <span className="inline-flex items-center gap-1.5"><span className="h-3 w-6 rounded" style={{ background: c.s1 }} />{t('tl.planned')}</span>
        {draft && <span className="inline-flex items-center gap-1.5"><span className="h-3 w-6 rounded border-2" style={{ borderColor: c.muted }} />{t('tl.draft_position')}</span>}
        <span className="inline-flex items-center gap-1.5"><Coffee className="size-3.5" />{t('tl.break')}</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-3 w-6 rounded" style={{ background: c.s2 }} />{t('tl.heat_time')}</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-3 w-6 rounded" style={{ background: c.midday }} />{t('p.legend.midday')}</span>
        <button onClick={() => setTable((v) => !v)} aria-pressed={table} className={cx('ms-auto inline-flex min-h-10 items-center gap-1.5 rounded-xl px-3 text-sm font-semibold', table ? 'bg-brand text-brand-ink' : 'bg-surface-2')}><Table2 className="size-4" />{t('common.table')}</button>
      </div>

      {table ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-line">
            <table className="w-full text-sm"><thead className="bg-surface-2 text-xs text-muted"><tr><th className="px-3 py-2 text-start">{t('common.task')}</th><th className="px-3 py-2 text-start">{t('tl.when')}</th></tr></thead>
              <tbody className="divide-y divide-line">{tasks.map((tk) => <tr key={tk.id}><td className="px-3 py-2">{pick(tk, 'name', lang)} · {t('common.zone')} {tk.zone}</td><td className="num px-3 py-2" dir="ltr">{segments(tk.slots).map(([a, b]) => `${slotLabel(a)}–${slotLabel(b + 1)}`).join(', ') || '–'}</td></tr>)}</tbody></table>
          </div>
          <div className="rounded-xl border border-line">
            <table className="w-full text-sm"><thead className="bg-surface-2 text-xs text-muted"><tr><th className="px-3 py-2 text-start">{t('common.crew')}</th><th className="px-3 py-2 text-start">{t('tl.breaks')}</th></tr></thead>
              <tbody className="divide-y divide-line">{crews.map((cr) => <tr key={cr}><td className="px-3 py-2">{cr}</td><td className="num px-3 py-2" dir="ltr">{breaks.filter((b) => (b.crews ?? [b.crew]).includes(cr)).map((b) => `${quarterLabel(b.start_q)} ${b.rest_area}`).join(', ')}</td></tr>)}</tbody></table>
          </div>
        </div>
      ) : (
        <div className="relative scroll-thin overflow-x-auto rounded-2xl border border-line" dir="ltr">
          <div className="grid min-w-[980px] text-xs" style={{ gridTemplateColumns: `11rem repeat(${Q}, minmax(0, 1fr))` }}>
            {/* hour header */}
            <div className="sticky start-0 z-10 border-b border-line bg-surface-2 px-3 py-2 font-semibold text-muted" style={{ gridColumn: 1 }}>{t('common.time')}</div>
            {Array.from({ length: SLOT_COUNT / 2 + 0 }, (_, i) => i * 4).map((q) => (
              <div key={q} className="num border-b border-s border-line bg-surface-2 py-2 ps-1 text-[10px] text-muted" style={col(q, 4)}>{quarterLabel(q)}</div>
            ))}

            {/* Tasks */}
            <RowLabel>{t('tl.tasks')}</RowLabel>
            {tasks.map((tk) => {
              const set = new Set<number>(tk.slots)
              const dset = draftSlots[tk.id]
              return (
                <div key={tk.id} className="contents">
                  <div className="sticky start-0 z-10 flex min-h-12 flex-col justify-center border-t border-line bg-surface px-3 py-1.5" style={{ gridColumn: 1 }} dir={lang === 'ar' ? 'rtl' : 'ltr'}>
                    <div className="truncate font-semibold">{pick(tk, 'name', lang)}</div>
                    <div className="flex items-center gap-1 text-[10px] text-muted">{t('common.zone')} {tk.zone} · {tk.crew} · {t(`wl.${tk.workload}`)}</div>
                  </div>
                  {Array.from({ length: Q }, (_, q) => {
                    const s = Math.floor(q / 2)
                    const on = set.has(s)
                    const ghost = dset?.has(s)
                    const band = bandAt(tk.zone, q)
                    const startSeg = on && !set.has(s - 1) && q % 2 === 0
                    const endSeg = on && !set.has(s + 1) && q % 2 === 1
                    const gStart = !!ghost && !dset?.has(s - 1) && q % 2 === 0
                    const gEnd = !!ghost && !dset?.has(s + 1) && q % 2 === 1
                    return (
                      <div key={q} className={cx('relative border-t border-line', q % 4 === 0 && 'border-s border-s-line/60')} style={{ ...col(q), background: midday[s] ? c.midday : undefined }}
                        title={`${slotLabel(s)} · ${t(`band.${band}`)}${on ? ` · ${t('tl.planned')}` : ''}${ghost ? ` · ${t('tl.draft_position')}` : ''}`}>
                        <div className="absolute inset-x-0 bottom-0 h-1.5" style={{ background: c.bands[band], opacity: 0.55 }} aria-hidden />
                        {ghost && !on && <div className={cx('absolute top-2 h-5 border-y-2', gStart && 'rounded-s-[4px] border-s-2', gEnd && 'rounded-e-[4px] border-e-2')}
                          style={{ borderColor: c.muted, left: gStart ? 2 : -1, right: gEnd ? 2 : 0 }} aria-hidden />}
                        {on && <div className={cx('absolute top-2 h-5', startSeg && 'rounded-s-[4px]', endSeg && 'rounded-e-[4px]')}
                          style={{ background: c.s1, left: startSeg ? 2 : -1, right: endSeg ? 2 : 0 }} aria-hidden />}
                      </div>
                    )
                  })}
                </div>
              )
            })}

            {/* Breaks per crew */}
            <RowLabel>{t('tl.breaks')}</RowLabel>
            {crews.map((cr) => {
              const qs = new Map<number, string>()
              for (const b of breaks) if ((b.crews ?? [b.crew]).includes(cr)) for (let q = b.start_q; q < b.start_q + (b.quarters ?? 1); q++) qs.set(q, b.rest_area)
              return (
                <div key={cr} className="contents">
                  <div className="sticky start-0 z-10 flex min-h-9 items-center gap-2 border-t border-line bg-surface px-3" style={{ gridColumn: 1 }}>
                    <span className="font-semibold">{cr}</span><span className="text-[10px] text-muted">{crewSize[cr] ?? '–'} {t('common.workers')}</span>
                  </div>
                  {Array.from({ length: Q }, (_, q) => (
                    <div key={q} className={cx('relative border-t border-line', q % 4 === 0 && 'border-s border-s-line/60')} style={{ ...col(q), background: midday[Math.floor(q / 2)] ? c.midday : undefined }}
                      title={qs.has(q) ? `${cr} · ${quarterLabel(q)} · ${qs.get(q)}` : undefined}>
                      {qs.has(q) && <div className="absolute inset-0.5 grid place-items-center rounded-[4px] bg-cyan-soft text-cyan"><Coffee className="size-3" aria-hidden /></div>}
                    </div>
                  ))}
                </div>
              )
            })}

            {/* Rest-seat demand */}
            <RowLabel>{t('tl.seats')}</RowLabel>
            {restAreas.map((r) => {
              const dem = demand[r.id] ?? []
              const open = (q: number) => quarterLabel(q) >= r.open && quarterLabel(q) < r.close
              return (
                <div key={r.id} className="contents">
                  <div className="sticky start-0 z-10 flex min-h-12 flex-col justify-center border-t border-line bg-surface px-3" style={{ gridColumn: 1 }} dir={lang === 'ar' ? 'rtl' : 'ltr'}>
                    <div className="flex items-center gap-1 font-semibold"><Armchair className={cx('size-3.5', r.cooled ? 'text-cyan' : 'text-sun')} />{r.id}</div>
                    <div className="text-[10px] text-muted">{t('c.seats', { n: r.seats })} · <span dir="ltr">{r.open}–{r.close}</span></div>
                  </div>
                  {Array.from({ length: Q }, (_, q) => {
                    const v = dem[q] ?? 0
                    const over = v > r.seats
                    const h = Math.min(100, (v / Math.max(1, r.seats)) * 100)
                    return (
                      <div key={q} className={cx('relative border-t border-line', q % 4 === 0 && 'border-s border-s-line/60', !open(q) && 'bg-[repeating-linear-gradient(135deg,transparent_0_4px,var(--surface-2)_4px_6px)]')}
                        style={col(q)} title={v ? `${r.id} · ${quarterLabel(q)} · ${v}/${r.seats}` : undefined}>
                        {v > 0 && <div className="absolute inset-x-0.5 bottom-0.5 rounded-t-[3px]" style={{ height: `calc(${h}% - 4px)`, minHeight: 4, background: over ? c.stop : c.s1, opacity: over ? 1 : 0.75 }} aria-hidden />}
                        {v > 0 && (q === 0 || (dem[q - 1] ?? 0) !== v) && <span className={cx('num absolute top-0.5 start-0.5 z-[1] text-[9px] font-bold', over ? 'text-stop' : 'text-ink-2')}>{v}</span>}
                      </div>
                    )
                  })}
                </div>
              )
            })}

            {/* New and returning workers: heat time vs shaded work */}
            {newWorkers.length > 0 && <RowLabel>{t('tl.new_workers')}</RowLabel>}
            {newWorkers.map(([wid, a]: [string, any]) => {
              const heat = new Set<number>(a.heat_slots ?? [])
              const shade = new Set<number>(a.shaded_slots ?? [])
              const w = workers[wid]
              return (
                <div key={wid} className="contents">
                  <div className="sticky start-0 z-10 flex min-h-10 flex-col justify-center border-t border-line bg-surface px-3" style={{ gridColumn: 1 }} dir={lang === 'ar' ? 'rtl' : 'ltr'}>
                    <div className="truncate font-semibold">{w?.name ?? wid}</div>
                    <div className="text-[10px] text-muted">{t(`s.accl.${w?.acclimatization ?? 'new'}`, { n: w?.day ?? '' })} · {t('tl.allowance', { m: a.allowance_min })}</div>
                  </div>
                  {Array.from({ length: Q }, (_, q) => {
                    const s = Math.floor(q / 2)
                    return (
                      <div key={q} className={cx('relative border-t border-line', q % 4 === 0 && 'border-s border-s-line/60')} style={{ ...col(q), background: midday[s] ? c.midday : undefined }}
                        title={heat.has(s) ? `${slotLabel(s)} · ${t('tl.heat_time')}` : shade.has(s) ? `${slotLabel(s)} · ${t('tl.shaded')}` : undefined}>
                        {heat.has(s) && <div className="absolute top-2 h-4" style={{ background: c.s2, left: -1, right: 0 }} aria-hidden />}
                        {shade.has(s) && <div className="absolute top-2 h-4 bg-cyan-soft" style={{ left: -1, right: 0 }} aria-hidden />}
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </div>
        </div>
      )}
      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted">
        <Badge tone="neutral" className="whitespace-normal!">{t('tl.note_bands')}</Badge>
        <Badge tone="neutral" className="whitespace-normal!">{t('tl.note_seats')}</Badge>
      </div>
    </div>
  )
}

function RowLabel({ children }: { children: React.ReactNode }) {
  return <div className="sticky start-0 z-10 border-t border-line bg-surface-2 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide text-muted" style={{ gridColumn: `1 / span ${Q + 1}` }}>{children}</div>
}

export function segments(slots: number[]): [number, number][] {
  const out: [number, number][] = []
  for (const s of [...slots].sort((a, b) => a - b)) {
    const last = out[out.length - 1]
    if (last && s === last[1] + 1) last[1] = s
    else out.push([s, s])
  }
  return out
}
