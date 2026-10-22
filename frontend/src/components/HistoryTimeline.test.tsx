import { describe, expect, it } from 'vitest'
import { diffSnapshots } from '@/components/HistoryTimeline'

describe('diffSnapshots', () => {
  it('reports added and removed list entries', () => {
    const before = { name: 'Bid Manager', accountabilities: [{ text: 'Preparing bids' }] }
    const after = { name: 'Bid Manager', accountabilities: [{ text: 'Preparing bids' }, { text: 'Tracking the pipeline' }] }
    expect(diffSnapshots(before, after)).toEqual([{ field: 'accountabilities', removed: [], added: ['Tracking the pipeline'] }])
  })

  it('reports scalar changes with old and new value', () => {
    const diff = diffSnapshots({ purpose: 'Old' }, { purpose: 'New' })
    expect(diff).toEqual([{ field: 'purpose', removed: ['Old'], added: ['New'] }])
  })

  it('returns nothing when snapshots are identical', () => {
    expect(diffSnapshots({ name: 'x', domains: [] }, { name: 'x', domains: [] })).toEqual([])
  })
})
