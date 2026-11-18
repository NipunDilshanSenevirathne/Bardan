/* Optional wearable, processed on the phone only (programme feedback, November 2026).

   ECTemp (Buller et al. 2013, Physiological Measurement 34:781; US patent application US20140180027A1): an
   extended Kalman filter that estimates core body temperature from minute-by-minute heart rate. Published
   accuracy: bias -0.03 °C with 95% of estimates within ±0.63 °C in the laboratory validation; an independent
   field check reported ±1.2 °C. That is too imprecise to clear anyone, so here it can only ADD rest.

   Warning signs: ACGIH TLV documentation for heat strain (sustained heart rate above 180 minus age for several
   minutes; heart rate still above 120 one minute after stopping work; core temperature above 38.5 °C for
   medically selected, acclimatized workers and 38.0 °C for others) and NIOSH 2016 (38.0 °C mild strain).

   Rules this module keeps (tested in strain.test.ts):
   * nothing here can mark a worker fit, clear a stop or shorten a break (the rule pack forbids inferring
     fitness from pulse);
   * no reading means no change: the plan, breaks and water stay as they are;
   * heart rate and the estimate stay on the phone; the only thing that can leave it is the words
     "needs a break", and only if the worker switched sharing on.
*/

export const ECTEMP = { a: 1, gamma2: 0.022 ** 2, b0: -7887.1, b1: 384.4286, b2: -4.5714, sigma2: 18.88 ** 2 } as const
export const CORE_START = 37.1          // a typical resting core temperature; the filter starts certain (v = 0)
export const SUSTAINED_MIN = 5          // "several minutes" above 180 - age
export const RECOVERY_LIMIT = 120       // bpm one minute after work stops

export type EcState = { ct: number; v: number }
export type Level = 'steady' | 'rising' | 'high' | 'no_reading'
export type Sample = { hr: number | null; working: boolean }
export type Assessment = {
  level: Level
  reasons: string[]
  estCore: number | null
  minutesAboveHrLimit: number
  recoveryHr: number | null
}

export function hrFromCore(ct: number): number {
  return ECTEMP.b2 * ct * ct + ECTEMP.b1 * ct + ECTEMP.b0
}

export function ectempInit(ct0: number = CORE_START): EcState {
  return { ct: ct0, v: 0 }
}

/** One minute of the filter. A missing or impossible reading keeps the estimate: it never guesses. */
export function ectempStep(s: EcState, hr: number | null): EcState {
  if (hr == null || !Number.isFinite(hr) || hr < 30 || hr > 230) return s
  const ctPred = ECTEMP.a * s.ct
  const vPred = ECTEMP.a * ECTEMP.a * s.v + ECTEMP.gamma2
  const c = 2 * ECTEMP.b2 * ctPred + ECTEMP.b1
  const k = (vPred * c) / (c * c * vPred + ECTEMP.sigma2)
  return { ct: ctPred + k * (hr - hrFromCore(ctPred)), v: (1 - k * c) * vPred }
}

export function ectempSeries(hrs: (number | null)[], ct0: number = CORE_START): number[] {
  const out: number[] = []
  let s = ectempInit(ct0)
  for (const hr of hrs) { s = ectempStep(s, hr); out.push(s.ct) }
  return out
}

/** Heat strain from the last minutes of readings. `age` is optional and stays on the phone. */
export function assess(samples: Sample[], opts: { age?: number | null; acclimatized?: boolean } = {}): Assessment {
  const acclimatized = opts.acclimatized !== false
  const recent = samples.slice(-SUSTAINED_MIN)
  if (samples.length === 0 || recent.every((x) => x.hr == null)) {
    return { level: 'no_reading', reasons: ['no_reading'], estCore: null, minutesAboveHrLimit: 0, recoveryHr: null }
  }
  const est = ectempSeries(samples.map((x) => x.hr))
  const estCore = est[est.length - 1]
  const reasons: string[] = []
  // Sustained heart rate above 180 - age (only when the worker chose to enter an age on this phone).
  let run = 0
  let best = 0
  if (opts.age && opts.age >= 16) {
    const lim = 180 - opts.age
    for (const x of samples) {
      run = x.hr != null && x.hr > lim ? run + 1 : 0
      best = Math.max(best, run)
    }
    if (run >= SUSTAINED_MIN) reasons.push('hr_above_180_minus_age')
  }
  // Recovery: heart rate one minute after the most recent stop of work.
  let recoveryHr: number | null = null
  for (let i = samples.length - 1; i >= 1; i--) {
    if (!samples[i].working && samples[i - 1].working) {
      const one = samples[i + 1]
      if (one && one.hr != null) recoveryHr = one.hr
      break
    }
  }
  if (recoveryHr != null && recoveryHr > RECOVERY_LIMIT) reasons.push('recovery_hr_above_120')
  const highCore = acclimatized ? 38.5 : 38.0
  if (estCore >= highCore) reasons.push(acclimatized ? 'est_core_38_5' : 'est_core_38_0_not_acclimatized')
  let level: Level = reasons.length ? 'high' : 'steady'
  if (level === 'steady' && acclimatized && estCore >= 38.0) { level = 'rising'; reasons.push('est_core_38_0') }
  return { level, reasons, estCore, minutesAboveHrLimit: best, recoveryHr }
}

/** What an assessment may change: only more rest, never less, and never "fit". */
export function planEffect(level: Level): { addRestMin: number; restNow: boolean; drinkNow: boolean } {
  switch (level) {
    case 'high': return { addRestMin: 30, restNow: true, drinkNow: true }
    case 'rising': return { addRestMin: 0, restNow: false, drinkNow: true }
    default: return { addRestMin: 0, restNow: false, drinkNow: false }
  }
}

/** The only payload that may leave the phone: words, no numbers, and only with the worker's choice. */
export function statusPayload(level: Level, shareChosen: boolean): { status: 'needs_break' } | null {
  return level === 'high' && shareChosen ? { status: 'needs_break' } : null
}

/* ---------------------------------------------------------------- demonstration heart rate (synthetic)
   For the sandbox only: a simple, labelled generator so the pipeline can be shown without a device. Core
   temperature approaches a steady value that rises with metabolic rate, and climbs while the hour's heat is
   above the ISO 7243 / NIOSH limit for that rate; heart rate follows work, core temperature and a "harder
   day" offset. It is not a model of any real person. */

export function limitWbgt(mW: number, acclimatized: boolean): number {
  const m = Math.min(520, Math.max(115, mW))
  return acclimatized ? 56.7 - 11.5 * Math.log10(m) : 59.9 - 14.1 * Math.log10(m)
}

function mulberry32(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export type Minute = { mW: number; wbgt: number; working: boolean }

export function simulateHeartRate(minutes: Minute[], opts: { restHr?: number; harderDay?: boolean; acclimatized?: boolean; seed?: number; core0?: number } = {}) {
  const rnd = mulberry32(opts.seed ?? 7)
  const restHr = opts.restHr ?? 70
  const extra = opts.harderDay ? 14 : 0
  let core = opts.core0 ?? 37.0
  const hr: number[] = []
  const cores: number[] = []
  for (const x of minutes) {
    const ss = 37.0 + 0.0022 * (x.mW - 115) + (opts.harderDay ? 0.25 : 0)
    const over = Math.max(0, x.wbgt - limitWbgt(x.mW, opts.acclimatized !== false))
    core = Math.min(41, Math.max(36.5, core + (ss - core) / 25 + 0.006 * over))
    const noise = (rnd() - 0.5) * 6
    hr.push(Math.round(restHr + 0.12 * (x.mW - 115) + 25 * (core - 37.0) + extra + noise))
    cores.push(core)
  }
  return { hr, core: cores }
}
