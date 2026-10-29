import { describe, expect, it } from 'vitest'
import { bidScore, calcTotals, daysUntil, fmtMoney, fmtMoneyMap, groupByStage, weightedOpen } from '@/lib/sales'
import type { OppRow, StageSummary } from '@/lib/sales-types'
import { fmtBytes } from '@/lib/upload'

describe('bidScore', () => {
  it('is null without ratings and weighted otherwise', () => {
    expect(bidScore([])).toBeNull()
    expect(bidScore([{ rating: 0, weight: 3 }])).toBeNull()
    expect(bidScore([{ rating: 5, weight: 3 }, { rating: 3, weight: 3 }])).toBe(80)
    expect(bidScore([{ rating: 1, weight: 5 }, { rating: 5, weight: 1 }])).toBe(33.3)
  })
})

describe('calcTotals', () => {
  const labor = { line_kind: 'labor', quantity: 10, unit: 'day', unit_cost: 600, unit_price: 1000, currency: 'EUR' }
  const travel = { line_kind: 'travel', quantity: 1, unit: 'piece', unit_cost: 300.25, unit_price: 500.5, currency: 'EUR' }

  it('adds lines, effort and margin', () => {
    const t = calcTotals([labor, travel], 'EUR', null)
    expect(t.price).toBe(10500.5)
    expect(t.cost).toBe(6300.25)
    expect(t.margin).toBe(4200.25)
    expect(t.marginPct).toBe(40)
    expect(t.effort).toBe(10)
  })

  it('counts hours as eighths of a day and ignores non-labor effort', () => {
    expect(calcTotals([{ ...labor, unit: 'hour', quantity: 16 }, travel], 'EUR', null).effort).toBe(2)
  })

  it('converts foreign currency lines with the documented rate', () => {
    const usd = { ...labor, quantity: 2, unit_cost: 10, unit_price: 100, currency: 'USD' }
    expect(calcTotals([usd], 'EUR', 0.9).price).toBe(180)
  })

  it('has no margin percentage without a price', () => {
    expect(calcTotals([], 'EUR', null).marginPct).toBeNull()
  })
})

describe('money formatting', () => {
  it('formats single values and never adds currencies together', () => {
    expect(fmtMoney(null, 'EUR', 'en')).toBe('–')
    expect(fmtMoney(1500, 'EUR', 'en')).toContain('1,500')
    const text = fmtMoneyMap({ EUR: 1000, USD: 500 }, 'en')
    expect(text).toContain('1,000')
    expect(text).toContain('500')
    expect(text).toContain('·')
    expect(fmtMoneyMap(null, 'en')).toBe('–')
  })

  it('sums only the weighted value of open stages', () => {
    const stages = [
      { stage: 'lead', weighted: { EUR: 100 } },
      { stage: 'proposal', weighted: { EUR: 200, USD: 50 } },
      { stage: 'won', weighted: { EUR: 9999 } },
      { stage: 'lost', weighted: null },
    ] as unknown as StageSummary[]
    expect(weightedOpen(stages)).toEqual({ EUR: 300, USD: 50 })
  })
})

describe('pipeline helpers', () => {
  it('groups opportunities by stage', () => {
    const rows = [{ id: '1', stage: 'lead' }, { id: '2', stage: 'won' }, { id: '3', stage: 'lead' }] as unknown as OppRow[]
    const grouped = groupByStage(rows)
    expect(grouped.lead.map((r) => r.id)).toEqual(['1', '3'])
    expect(grouped.won).toHaveLength(1)
    expect(grouped.negotiation).toEqual([])
  })

  it('counts days until a date', () => {
    const today = new Date(2026, 4, 1)
    expect(daysUntil('2026-05-04', today)).toBe(3)
    expect(daysUntil('2026-04-29', today)).toBe(-2)
    expect(daysUntil(null, today)).toBeNull()
  })

  it('formats file sizes', () => {
    expect(fmtBytes(null)).toBe('–')
    expect(fmtBytes(512)).toBe('512 B')
    expect(fmtBytes(2048)).toBe('2.0 KB')
    expect(fmtBytes(5 * 1024 * 1024)).toBe('5.0 MB')
  })
})
