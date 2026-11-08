/* Chart colours resolved per theme. Series colours were checked with the dataviz palette validator
   (lightness band, chroma, colour-blind separation and contrast) against the card surface of each theme:
   light #2563eb / #ea580c on #ffffff, dark #4f8dff / #d95926 on #0d1526. Text never wears a series colour. */
import { useMemo } from 'react'
import { useTheme } from './theme'

export type VizColors = {
  s1: string; s2: string; ink: string; ink2: string; muted: string; line: string; grid: string; surface: string
  bands: Record<string, string>; midday: string; stop: string
}

export function useVizColors(): VizColors {
  const { theme } = useTheme()
  return useMemo(() => {
    const cs = getComputedStyle(document.documentElement)
    const v = (n: string) => cs.getPropertyValue(n).trim()
    const dark = theme === 'dark'
    return {
      s1: dark ? '#4f8dff' : '#2563eb',
      s2: dark ? '#d95926' : '#ea580c',
      ink: v('--ink') || (dark ? '#eef3ff' : '#0b1324'),
      ink2: v('--ink-2') || (dark ? '#cfd9ee' : '#1e2a44'),
      muted: v('--muted') || (dark ? '#98a6c1' : '#55657f'),
      line: v('--line') || (dark ? '#22304d' : '#dbe3ef'),
      grid: dark ? '#1a2540' : '#e9eef6',
      surface: v('--surface') || (dark ? '#0d1526' : '#ffffff'),
      bands: {
        unrestricted: v('--band-u') || '#38bdf8', acclimatization: v('--band-a') || '#facc15',
        buffer: v('--band-b') || '#fb923c', withdrawal: v('--band-w') || '#ef4444', unavailable: v('--unknown') || '#475569',
      },
      midday: dark ? 'rgba(148,163,184,0.14)' : 'rgba(71,85,105,0.09)',
      stop: v('--stop') || '#dc2626',
    }
  }, [theme])
}

/** WBGT demonstration planning bands (AE-AD-HEAT demo pack): <28 / 28–31 / 31–33 / ≥33 °C. */
export const WBGT_BANDS = [
  { band: 'unrestricted', from: 20, to: 28 },
  { band: 'acclimatization', from: 28, to: 31 },
  { band: 'buffer', from: 31, to: 33 },
  { band: 'withdrawal', from: 33, to: 40 },
] as const

export const BAND_ORDER = ['unrestricted', 'acclimatization', 'buffer', 'withdrawal'] as const

/** Half-hour slots of the planning grid, 05:00–19:00 (slot 0 = 05:00). */
export const SLOT_COUNT = 28
export function slotLabel(i: number) {
  const m = 5 * 60 + i * 30
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
}
/** Quarter-hour index (from 05:00) to HH:MM. */
export function quarterLabel(q: number) {
  const m = 5 * 60 + q * 15
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
}
