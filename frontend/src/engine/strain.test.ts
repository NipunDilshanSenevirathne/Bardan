/* Optional wearable on the phone: ECTemp, the warning signs, and the rules that keep it worker-controlled. */
import { describe, expect, it } from 'vitest'
import {
  assess, CORE_START, ECTEMP, ectempInit, ectempSeries, ectempStep, hrFromCore, limitWbgt, planEffect,
  simulateHeartRate, statusPayload, type Level, type Sample,
} from './strain'

const flat = (hr: number | null, n: number, working = true): Sample[] => Array.from({ length: n }, () => ({ hr, working }))

describe('ECTemp (Buller 2013) on the phone', () => {
  it('uses the published parameters', () => {
    expect(ECTEMP.gamma2).toBeCloseTo(0.000484, 9)
    expect(ECTEMP.sigma2).toBeCloseTo(356.4544, 4)
    expect([ECTEMP.b0, ECTEMP.b1, ECTEMP.b2]).toEqual([-7887.1, 384.4286, -4.5714])
    expect(CORE_START).toBe(37.1)
  })

  it('maps core temperature to heart rate as published (about 78, 120 and 152 bpm at 37, 38 and 39 °C)', () => {
    expect(hrFromCore(37)).toBeCloseTo(78.5, 0)
    expect(hrFromCore(38)).toBeCloseTo(120.1, 0)
    expect(hrFromCore(39)).toBeCloseTo(152.5, 0)
  })

  it('settles near the temperature a steady heart rate implies, slowly, as a core temperature does', () => {
    const est = ectempSeries(Array(240).fill(120))
    expect(est[9]).toBeLessThan(37.6)
    expect(est[239]).toBeGreaterThan(37.85)
    expect(est[239]).toBeLessThan(38.1)
    const rest = ectempSeries(Array(240).fill(78))
    expect(rest[239]).toBeCloseTo(37.0, 0)
  })

  it('a higher heart rate never gives a lower estimate', () => {
    const lo = ectempSeries(Array(120).fill(110))
    const hi = ectempSeries(Array(120).fill(135))
    lo.forEach((v, i) => expect(hi[i]).toBeGreaterThanOrEqual(v))
  })

  it('a missing or impossible reading keeps the estimate instead of guessing', () => {
    const s = ectempStep(ectempInit(), 130)
    expect(ectempStep(s, null)).toEqual(s)
    expect(ectempStep(s, 0)).toEqual(s)
    expect(ectempStep(s, 400)).toEqual(s)
  })
})

describe('warning signs (ACGIH, NIOSH)', () => {
  it('a heart rate above 180 minus age for five minutes is a high-strain sign; four minutes is not', () => {
    const age = 40     // limit 140
    expect(assess([...flat(100, 30), ...flat(145, 5)], { age }).reasons).toContain('hr_above_180_minus_age')
    expect(assess([...flat(100, 30), ...flat(145, 4)], { age }).reasons).not.toContain('hr_above_180_minus_age')
  })

  it('without an age the heart-rate limit is not guessed', () => {
    expect(assess(flat(170, 10)).reasons).not.toContain('hr_above_180_minus_age')
  })

  it('a heart rate above 120 one minute after stopping work is a high-strain sign', () => {
    const s = [...flat(140, 20, true), { hr: 135, working: false }, { hr: 126, working: false }]
    expect(assess(s).reasons).toContain('recovery_hr_above_120')
    const ok = [...flat(140, 20, true), { hr: 120, working: false }, { hr: 104, working: false }]
    expect(assess(ok).reasons).not.toContain('recovery_hr_above_120')
  })

  it('estimated core temperature: 38.0 is rising and 38.5 is high for acclimatized workers; 38.0 is high otherwise', () => {
    const s = flat(142, 600)                              // settles above 38.5
    expect(assess(s).level).toBe('high')
    const r = flat(124, 600)                              // settles a little above 38.0
    expect(assess(r).level).toBe('rising')
    expect(assess(r, { acclimatized: false }).level).toBe('high')
  })

  it('no reading is shown as no reading, never as steady', () => {
    expect(assess([...flat(120, 30), ...flat(null, 5)]).level).toBe('no_reading')
    expect(assess([]).level).toBe('no_reading')
  })
})

describe('worker control and the one-way rule', () => {
  const levels: Level[] = ['steady', 'rising', 'high', 'no_reading']

  it('no level can shorten a break or mark a worker fit', () => {
    for (const l of levels) {
      const e = planEffect(l)
      expect(e.addRestMin).toBeGreaterThanOrEqual(0)
      expect(Object.keys(e)).not.toContain('fit')
      expect(Object.keys(e)).not.toContain('clear')
    }
    expect(planEffect('high').restNow).toBe(true)
  })

  it('only the words "needs a break" can leave the phone, and only if the worker chose to share', () => {
    expect(statusPayload('high', true)).toEqual({ status: 'needs_break' })
    expect(statusPayload('high', false)).toBeNull()
    for (const l of levels.filter((x) => x !== 'high')) expect(statusPayload(l, true)).toBeNull()
    expect(JSON.stringify(statusPayload('high', true))).not.toMatch(/\d/)
  })
})

describe('demonstration heart rate (synthetic)', () => {
  const hot = (n: number, working: boolean) => Array.from({ length: n }, () => ({ mW: working ? 415 : 115, wbgt: working ? 30 : 19, working }))

  it('is reproducible for a seed and higher on a harder day', () => {
    const a = simulateHeartRate(hot(60, true), { seed: 3 })
    const b = simulateHeartRate(hot(60, true), { seed: 3 })
    expect(a.hr).toEqual(b.hr)
    const harder = simulateHeartRate(hot(60, true), { seed: 3, harderDay: true })
    expect(harder.hr.reduce((s, v) => s + v, 0)).toBeGreaterThan(a.hr.reduce((s, v) => s + v, 0))
  })

  it('planned breaks in a cooled room keep the estimate lower than working straight through', () => {
    const straight = hot(180, true)
    const withBreaks = Array.from({ length: 3 }, () => [...hot(30, true), ...hot(30, false)]).flat()
    const e1 = ectempSeries(simulateHeartRate(straight, { seed: 5 }).hr)
    const e2 = ectempSeries(simulateHeartRate(withBreaks, { seed: 5 }).hr)
    expect(e2[e2.length - 1]).toBeLessThan(e1[e1.length - 1])
  })

  it('uses the same heat limits as the server break planner', () => {
    expect(limitWbgt(300, true)).toBeCloseTo(28.21, 2)
    expect(limitWbgt(300, false)).toBeCloseTo(24.97, 2)
  })
})
