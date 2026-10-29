import type { Tone } from '@/components/kit'
import type { BidDecision, ContractState, Coverage, Currency, OppRow, ProposalStatus, Risk, Stage, StageSummary } from '@/lib/sales-types'

export const STAGES: Stage[] = ['lead', 'qualification', 'bid_decision', 'proposal', 'negotiation', 'won', 'lost']
export const OPEN_STAGES: Stage[] = ['lead', 'qualification', 'bid_decision', 'proposal', 'negotiation']

export const STAGE_LABEL: Record<Stage, string> = {
  lead: 'Lead',
  qualification: 'Qualification',
  bid_decision: 'Bid / No-Bid',
  proposal: 'Proposal',
  negotiation: 'Negotiation',
  won: 'Won',
  lost: 'Lost',
}

export const BID_CRITERIA: { key: string; label: string; hint: string }[] = [
  { key: 'strategic_fit', label: 'Strategic fit', hint: '5 = fits our strategy very well' },
  { key: 'customer_potential', label: 'Customer potential', hint: '5 = high long-term potential' },
  { key: 'technical_feasibility', label: 'Technical feasibility', hint: '5 = clearly feasible' },
  { key: 'capacity', label: 'Capacity', hint: '5 = people are available' },
  { key: 'competence', label: 'Competence', hint: '5 = we have the skills' },
  { key: 'risk', label: 'Risk', hint: '5 = very low risk' },
  { key: 'margin', label: 'Margin', hint: '5 = very attractive margin' },
  { key: 'funding', label: 'Funding', hint: '5 = funding is secured' },
  { key: 'reference_value', label: 'Reference value', hint: '5 = strong reference' },
  { key: 'reuse_potential', label: 'Reuse potential', hint: '5 = results are reusable' },
  { key: 'win_chance', label: 'Chance to win', hint: '5 = very likely' },
]

export const CHAIN_LABEL: Record<string, string> = {
  lead: 'Lead',
  qualification: 'Qualification',
  bid_decision: 'Bid / No-Bid',
  proposal: 'Proposal',
  negotiation: 'Negotiation',
  contract: 'Contract',
  project: 'Project',
}

const STAGE_TONE: Record<Stage, Tone> = {
  lead: 'neutral',
  qualification: 'neutral',
  bid_decision: 'ochre',
  proposal: 'primary',
  negotiation: 'primary',
  won: 'forest',
  lost: 'danger',
}

export const PROPOSAL_TONE: Record<ProposalStatus, Tone> = {
  draft: 'neutral', in_approval: 'ochre', approved: 'forest', submitted: 'primary', accepted: 'forest', rejected: 'danger', withdrawn: 'neutral', expired: 'neutral',
}

export const COVERAGE_TONE: Record<Coverage, Tone> = {
  none: 'danger', draft: 'neutral', not_started: 'neutral', active: 'forest', expiring: 'ochre', expired: 'danger', terminated: 'neutral',
}

export const CONTRACT_TONE: Record<ContractState, Tone> = {
  draft: 'neutral', in_review: 'ochre', signed: 'primary', active: 'forest', expiring: 'ochre', expired: 'danger', terminated: 'neutral',
}

export function stageTone(stage: Stage): Tone {
  return STAGE_TONE[stage]
}

export function bidTone(decision: BidDecision | null | undefined): Tone {
  if (decision === 'bid') return 'forest'
  if (decision === 'no_bid') return 'danger'
  if (decision === 'clarify') return 'ochre'
  return 'neutral'
}

export function riskTone(risk: Risk): Tone {
  if (risk === 'high') return 'danger'
  if (risk === 'medium') return 'ochre'
  return 'neutral'
}

export function fmtMoney(value: number | null | undefined, currency: Currency, lang: string): string {
  if (value === null || value === undefined) return '–'
  return new Intl.NumberFormat(lang === 'de' ? 'de-AT' : 'en-GB', { style: 'currency', currency, maximumFractionDigits: 0 }).format(value)
}

/** Join several currencies into one line, e.g. "€120,000 · $5,000". Money is never added across currencies. */
export function fmtMoneyMap(map: Record<Currency, number> | null | undefined, lang: string): string {
  if (!map) return '–'
  const parts = Object.entries(map).filter(([, v]) => v !== 0).map(([cur, v]) => fmtMoney(v, cur, lang))
  return parts.length > 0 ? parts.join(' · ') : fmtMoney(0, 'EUR', lang)
}

/** Sum the weighted value of the open stages per currency. */
export function weightedOpen(stages: StageSummary[]): Record<Currency, number> {
  const out: Record<Currency, number> = {}
  for (const s of stages) {
    if (!OPEN_STAGES.includes(s.stage) || !s.weighted) continue
    for (const [cur, v] of Object.entries(s.weighted)) out[cur] = (out[cur] ?? 0) + v
  }
  return out
}

export function groupByStage(rows: OppRow[]): Record<Stage, OppRow[]> {
  const out = Object.fromEntries(STAGES.map((s) => [s, [] as OppRow[]])) as Record<Stage, OppRow[]>
  for (const r of rows) out[r.stage].push(r)
  return out
}

/** Weighted score 0-100 like the server computes it (5 = most favourable). Informational only. */
export function bidScore(items: { rating: number; weight: number }[]): number | null {
  const rated = items.filter((i) => i.rating > 0)
  const totalWeight = rated.reduce((sum, i) => sum + i.weight, 0)
  if (totalWeight === 0) return null
  const achieved = rated.reduce((sum, i) => sum + i.rating * i.weight, 0)
  return Math.round((achieved / (5 * totalWeight)) * 1000) / 10
}

export interface CalcInput {
  line_kind: string
  quantity: number
  unit: string
  unit_cost: number
  unit_price: number
  currency: string
}

const cents = (n: number): number => Math.round((n + Number.EPSILON) * 100) / 100

/** Live preview of the server calculation: every line is rounded to cents, foreign currencies use the documented rate. */
export function calcTotals(lines: CalcInput[], currency: string, fxRate: number | null): { price: number; cost: number; margin: number; marginPct: number | null; effort: number } {
  let price = 0
  let cost = 0
  let effort = 0
  for (const l of lines) {
    const factor = l.currency !== currency && fxRate ? fxRate : 1
    price += cents(cents(l.quantity * l.unit_price) * factor)
    cost += cents(cents(l.quantity * l.unit_cost) * factor)
    if (l.line_kind === 'labor') {
      if (l.unit === 'day') effort += l.quantity
      if (l.unit === 'hour') effort += l.quantity / 8
    }
  }
  const margin = cents(price - cost)
  return { price: cents(price), cost: cents(cost), margin, marginPct: price > 0 ? cents((margin / price) * 100) : null, effort: Math.round(effort * 10) / 10 }
}

export function daysUntil(date: string | null | undefined, today = new Date()): number | null {
  if (!date) return null
  const target = new Date(`${date}T00:00:00`)
  const base = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  return Math.round((target.getTime() - base.getTime()) / 86_400_000)
}
