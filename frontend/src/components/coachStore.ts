/* Where the step-by-step guided tour is: which tour step, and which hint inside it.
   Kept outside React and in sessionStorage, so it survives the person switch and a reload. */
import { useSyncExternalStore } from 'react'

export type CoachState = { step: number; hint: number } | null

const KEY = 'bardan.coach'
const subs = new Set<() => void>()
let state: CoachState = read()

function read(): CoachState {
  try {
    const v = JSON.parse(sessionStorage.getItem(KEY) || 'null')
    return v && typeof v.step === 'number' && typeof v.hint === 'number' ? v : null
  } catch { return null }
}

export function getCoach(): CoachState { return state }

export function setCoach(s: CoachState) {
  state = s
  try { if (s) sessionStorage.setItem(KEY, JSON.stringify(s)); else sessionStorage.removeItem(KEY) } catch { /* private mode */ }
  subs.forEach((f) => f())
}

export function useCoach(): CoachState {
  return useSyncExternalStore((cb) => { subs.add(cb); return () => { subs.delete(cb) } }, () => state, () => state)
}
