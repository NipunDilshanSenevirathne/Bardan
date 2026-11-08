/*
 * The phone's offline matcher must read a report exactly as the server's matcher does: same intents, same
 * polarity (negation), same evidence words, same urgency. Cases and expected results come from the server matcher
 * (backend/scripts/lexicon_parity.py), whose own behaviour is held to the specification's Speak set.
 */
import { describe, expect, it } from 'vitest'
import parity from '../../../shared/lexicon_parity.json'
import { LEXICON_VERSION, offlineParse, urgentNow } from './lexicon'

const cases = (parity as any).cases as { text: string; language: string; uncertain: boolean; candidates: any[]; urgent: string[] }[]

describe('offline phrase matcher on the phone (parity with the server)', () => {
  it('uses the same lexicon version as the parity file', () => {
    expect(LEXICON_VERSION).toBe((parity as any).lexicon)
  })
  it.each(cases.map((c) => [c.text || '(empty)', c] as const))('reads %s like the server', (_, c) => {
    const p = offlineParse(c.text)
    expect(p.language).toBe(c.language)
    expect(p.uncertain).toBe(c.uncertain)
    expect(p.candidates).toEqual(c.candidates)
    expect(urgentNow(c.text).map((x) => x.intent)).toEqual(c.urgent)
  })
  it('opens the emergency card for urgent words with no network (T68)', () => {
    expect(urgentNow('my friend collapsed').length).toBeGreaterThan(0)
    expect(urgentNow('صاحبي طاح وما يصحى').length).toBeGreaterThan(0)
    expect(urgentNow('I am not dizzy')).toEqual([])
  })
})
