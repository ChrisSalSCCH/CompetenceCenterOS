import { describe, expect, it } from 'vitest'
import { customerRuleViolated, daysSince, exactSuggestion, formatMoney, formatPct, fullName, normalizeName, relevantSections } from '@/lib/portfolio'

describe('normalizeName', () => {
  it('matches the backend comparison key', () => {
    expect(normalizeName('Node.js')).toBe(normalizeName('NodeJS'))
    expect(normalizeName(' Open  Source ')).toBe('opensource')
    expect(normalizeName('C#')).not.toBe(normalizeName('C'))
    expect(normalizeName('...')).toBe('')
  })
})

describe('exactSuggestion', () => {
  const items = [
    { name: 'Angular', matched_alias: null },
    { name: 'PostgreSQL', matched_alias: 'Postgres' },
  ]
  it('finds an entry by name regardless of spelling', () => {
    expect(exactSuggestion(items, 'angular')?.name).toBe('Angular')
  })
  it('finds an entry by alias', () => {
    expect(exactSuggestion(items, 'postgres')?.name).toBe('PostgreSQL')
  })
  it('offers no match for new or empty text', () => {
    expect(exactSuggestion(items, 'Svelte')).toBeUndefined()
    expect(exactSuggestion(items, '  ')).toBeUndefined()
  })
})

describe('customerRuleViolated', () => {
  it('requires a customer organization only for customer projects', () => {
    expect(customerRuleViolated('customer', 0)).toBe(true)
    expect(customerRuleViolated('customer', 2)).toBe(false)
    expect(customerRuleViolated('internal', 0)).toBe(false)
  })
})

describe('relevantSections', () => {
  const keys = (c: 'customer' | 'internal', ai: boolean) => relevantSections(c, ai).map((s) => s.key)
  it('shows business context only for customer projects', () => {
    expect(keys('customer', false)).toContain('business_context')
    expect(keys('internal', false)).not.toContain('business_context')
  })
  it('shows the AI section only for AI-relevant projects', () => {
    expect(keys('internal', true)).toContain('ai_usage')
    expect(keys('internal', false)).not.toContain('ai_usage')
  })
})

describe('formatting', () => {
  it('formats money and percentages, with a dash for missing values', () => {
    expect(formatMoney(null)).toBe('–')
    expect(formatMoney(1500, 'EUR', 'en')).toContain('1,500')
    expect(formatPct(null)).toBe('–')
    expect(formatPct(50)).toBe('50.0 %')
  })
  it('builds full names', () => {
    expect(fullName({ first_name: 'Greta', last_name: 'Hollweg' })).toBe('Greta Hollweg')
  })
  it('counts days since a date', () => {
    const now = new Date('2025-03-31T12:00:00Z')
    expect(daysSince('2025-03-21T12:00:00Z', now)).toBe(10)
    expect(daysSince(null, now)).toBeNull()
    expect(daysSince('not a date', now)).toBeNull()
  })
})
