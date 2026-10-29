import { describe, expect, it } from 'vitest'
import { monthLabel, sumValues, utilizationTone } from '@/lib/management'

describe('management helpers', () => {
  it('formats month keys and leaves other keys alone', () => {
    expect(monthLabel('2026-03', 'en')).toContain('2026')
    expect(monthLabel('undated', 'en')).toBe('undated')
  })

  it('sums values and tolerates missing input', () => {
    expect(sumValues({ a: 1.5, b: 2 })).toBe(3.5)
    expect(sumValues(undefined)).toBe(0)
  })

  it('maps utilization to a tone', () => {
    expect(utilizationTone(null)).toBe('neutral')
    expect(utilizationTone(60)).toBe('forest')
    expect(utilizationTone(90)).toBe('ochre')
    expect(utilizationTone(120)).toBe('danger')
  })
})
