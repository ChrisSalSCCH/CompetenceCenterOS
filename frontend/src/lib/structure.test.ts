import { describe, expect, it } from 'vitest'
import { descendantIds, effectiveMode, matchesFilter, pathTo } from '@/lib/structure'
import type { CircleNode } from '@/lib/types'

const base = { purpose: '', description: '', accountabilities: [], domains: [], policies: [] }
const circles: CircleNode[] = [
  { ...base, id: 'root', parent_id: null, name: 'Root', governance_mode: 'holacracy' },
  { ...base, id: 'a', parent_id: 'root', name: 'A', governance_mode: null },
  { ...base, id: 'b', parent_id: 'a', name: 'B', governance_mode: 'direct' },
  { ...base, id: 'c', parent_id: 'b', name: 'C', governance_mode: null },
]

describe('structure helpers', () => {
  it('collects all descendants of a circle', () => {
    expect([...descendantIds(circles, 'a')].sort()).toEqual(['b', 'c'])
  })

  it('builds the path from the root', () => {
    expect(pathTo(circles, 'c').map((c) => c.name)).toEqual(['Root', 'A', 'B', 'C'])
  })

  it('inherits the governance workflow from the nearest ancestor', () => {
    expect(effectiveMode(circles, 'a', 'consent')).toBe('holacracy')
    expect(effectiveMode(circles, 'c', 'consent')).toBe('direct')
  })

  it('falls back to the organization default without any setting', () => {
    const open = circles.map((c) => ({ ...c, governance_mode: null }))
    expect(effectiveMode(open, 'c', 'approval')).toBe('approval')
  })

  it('filters case-insensitively across fields', () => {
    expect(matchesFilter('BID', 'Bid Manager')).toBe(true)
    expect(matchesFilter('x', 'Bid Manager', undefined)).toBe(false)
    expect(matchesFilter('  ', 'anything')).toBe(true)
  })
})
