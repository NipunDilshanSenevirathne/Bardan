import { describe, expect, it } from 'vitest'
import { evaluate, inMiddayWindow, parseTime } from './engine'

/* Device-side emergency path: works with no network, no model and no language (finalsystem.md §12.3). */
describe('device emergency path', () => {
  it('T05 T06 a tap on "confused" opens the emergency card locally in well under 1 s', () => {
    const t0 = performance.now()
    const d = evaluate({ now: '2025-08-19T11:10:00+04:00', symptoms: ['confusion'] })
    expect(d.state).toBe('emergency')
    expect(d.actions).toEqual(['BUDDY_STAY', 'CALL_998', 'EMERGENCY_CARD', 'START_COOLING'])
    expect(performance.now() - t0).toBeLessThan(1000)
  })
  it('T07 preferences never change the emergency instructions', () => {
    const a = evaluate({ now: '2025-08-19T11:10:00+04:00', symptoms: ['collapse'] })
    const b = evaluate({ now: '2025-08-19T11:10:00+04:00', symptoms: ['collapse'], ...({ preferences: { fasting: true } } as object) })
    expect(b).toEqual(a)
  })
  it('T18 the midday window uses site time whatever the device time zone', () => {
    expect(inMiddayWindow(parseTime('2026-08-06T08:30:00Z'))).toBe(true)
    expect(inMiddayWindow(parseTime('2026-08-06T15:30:00+05:30'))).toBe(true)
    expect(inMiddayWindow(parseTime('2026-08-06T11:00:00Z'))).toBe(false)
  })
  it('T21 an overdue pack gives "assessment unavailable" but never blocks an emergency', () => {
    const late = { now: '2027-07-15T10:00:00+04:00', observation: { kind: 'twl', value: 230, observed_at: '2027-07-15T09:55:00+04:00', provenance: 'measured' } }
    expect(evaluate(late).state).toBe('unavailable')
    expect(evaluate({ ...late, symptoms: ['seizure'] }).state).toBe('emergency')
  })
})
