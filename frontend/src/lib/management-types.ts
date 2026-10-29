export type MoneyMap = Record<string, number>

export interface OppRef {
  id: string
  number: string
  title: string
  customer_name: string
}

export interface AttentionBucket {
  count: number
  items: OppRef[]
}

export interface CockpitData {
  money_hidden: boolean
  pipeline: {
    open_count: number
    weighted: MoneyMap | null
    by_stage: { stage: string; count: number; value: MoneyMap | null; weighted: MoneyMap | null }[]
  }
  results: { won: number; lost: number; won_value: MoneyMap | null; win_rate: number | null; avg_cycle_days: number | null }
  attention: Record<string, AttentionBucket>
  unfilled_decision_roles: { id: string; label: string; role_name: string; decision_type: string }[]
  proposals: { by_status: Record<string, number>; awaiting_approval: { id: string; number: string; title: string; opportunity_title: string }[] }
  contracts: {
    by_state: Record<string, number>
    expiring: { id: string; number: string; title: string; valid_to: string | null }[]
    active_value: MoneyMap | null
    conditions_visible: boolean
  }
  ndas: Record<string, number>
  projects: {
    by_phase: Record<string, number>
    customer_active: number
    internal_active: number
    research: number
    finance: { currency: string; projects: number; budget: number; costs: number; funding: number }[] | null
  }
  capacity: { overloaded_people: number; people_without_capacity: number; average_utilization: number | null }
}

export interface ForecastData {
  months: string[]
  currencies: Record<string, { categories: Record<string, Record<string, number>>; totals: Record<string, number> }>
  secured_hidden: boolean
  assumptions: string[]
  sources: { opportunities: number; milestones: number }
  generated_at: string
}

export interface WinStats {
  won: number
  lost: number
  open: number
  win_rate: number | null
  won_value: MoneyMap | null
}

export interface AnalyticsData {
  money_hidden: boolean
  by_category: ({ category: string } & WinStats)[]
  customers: ({ crm_org_id: string; name: string; opportunities: number } & WinStats)[]
  industries: { industry: string; projects: number; opportunities: number }[]
  technologies: { id: string; name: string; projects: number; opportunities: number }[]
  lost_reasons: { reason: string; count: number }[]
  cycle_days: { won: number | null; lost: number | null }
  proposals: Record<string, number>
  margin_by_category: { category: string; avg_margin_pct: number; versions: number }[] | null
  contract_value_by_customer: { customer: string; currency: string; value: number }[] | null
}

export type FixAction = 'set_owner' | 'set_manager' | 'set_next_action' | 'set_close_date'

export interface QualityFix {
  action: FixAction | 'merge_contacts'
  keep_id?: string
  merge_ids?: string[]
}

export interface QualityIssue {
  id: string
  kind: string
  severity: 'error' | 'warning' | 'info'
  entity_type: string
  entity_id: string
  label: string
  message: string
  link: string
  fix: QualityFix | null
}

export interface QualityData {
  total: number
  by_kind: Record<string, number>
  items: QualityIssue[]
  truncated: boolean
}
