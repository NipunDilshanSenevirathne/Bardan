import { describe, expect, it } from 'vitest'
import suite from '../../../shared/conformance.json'
import { evaluate } from './engine'

describe('device engine conformance (shared suite)', () => {
  for (const c of (suite as any).cases) {
    it(`${c.id} ${c.description}`, () => {
      const got = evaluate(c.input)
      expect(got.state).toBe(c.expected.state)
      expect(got.band).toBe(c.expected.band)
      expect([...got.actions].sort()).toEqual([...c.expected.actions].sort())
      expect(got.reasons).toEqual(c.expected.reasons)
    })
  }
})
