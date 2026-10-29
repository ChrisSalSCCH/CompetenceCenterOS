/** Types mirroring the commercial API (`/api/commercial/*`). Money arrives as numbers, dates as ISO strings. */

export type Stage = 'lead' | 'qualification' | 'bid_decision' | 'proposal' | 'negotiation' | 'won' | 'lost'
export type Risk = 'low' | 'medium' | 'high'
export type BidDecision = 'pending' | 'bid' | 'no_bid' | 'clarify'
export type Currency = string

export interface OppRow {
  id: string
  number: string
  title: string
  stage: Stage
  category: string
  risk: Risk
  value_amount: number | null
  currency: Currency
  probability: number | null
  probability_manual: boolean
  expected_close: string | null
  next_action: string | null
  next_action_due: string | null
  crm_org_id: string
  customer_name: string
  owner_user_id: string | null
  owner_name: string | null
  project_id: string | null
  bid_decision: BidDecision | null
  proposal_count: number
  effective_probability: number
  weighted_value: number | null
  action_overdue: boolean
  close_overdue: boolean
  updated_at: string
  stage_changed_at: string
}

export interface StageSummary {
  stage: Stage
  count: number
  overdue: number
  probability: number
  value: Record<Currency, number> | null
  weighted: Record<Currency, number> | null
}

export interface PipelineData {
  stages: StageSummary[]
  open_count: number
  overdue_count: number
  win_rate: number | null
  defaults: Record<Stage, number>
  money_hidden: boolean
}

export interface OppContact { id: string; first_name: string; last_name: string; job_title: string | null; contact_role: string | null }
export interface OppEntry { id: string; kind: string; name: string }
export interface OppTeamMember { user_id: string; name: string; role_id: string | null; role_name: string | null; team_role: string | null }
export interface ScopedRole { scope_id: string; user_id: string; name: string; role_id: string; role_name: string; scope_type: string }
export interface OppProposalRef { id: string; number: string; title: string; status: ProposalStatus; valid_until: string | null; version_no: number | null; price_total: number | null; currency: string | null }
export interface OppNdaRef { id: string; number: string; title: string; status: string; valid_from: string | null; valid_to: string | null }
export interface OppContractRef { id: string; number: string; title: string; status: string; valid_from: string | null; valid_to: string | null }

export interface OppActivity {
  id: string
  kind: string
  subject: string
  body: string
  occurred_at: string
  follow_up_task_id: string | null
  follow_up_status: string | null
  follow_up_due: string | null
  author_name: string | null
}

export interface OppDetail extends OppRow {
  description: string
  circle_id: string | null
  circle_name: string | null
  source: string | null
  effort_days: number | null
  expected_start: string | null
  expected_end: string | null
  lost_reason: string | null
  converted_at: string | null
  project_name: string | null
  contacts: OppContact[]
  entries: OppEntry[]
  references: { id: string; name: string }[]
  team: OppTeamMember[]
  scoped_roles: ScopedRole[]
  proposals: OppProposalRef[]
  ndas: OppNdaRef[]
  contracts: OppContractRef[]
  activities: OppActivity[]
  bid: { decision: BidDecision; score: number | null; decided_at: string | null; authority_unclear: boolean } | null
  can_edit: boolean
  can_see_cost: boolean
}

export interface ChainRef { type: string; id: string; label: string }
export interface ChainStep { key: string; status: 'done' | 'current' | 'pending'; at: string | null; refs: ChainRef[] }
export interface ChainData { stage: Stage; lost: boolean; lost_reason: string | null; steps: ChainStep[] }

export interface HistoryEvent { id: string; action: string; summary: string; created_at: string; actor_name: string | null; data: Record<string, unknown> | null }

export interface BidScore { criterion: string; rating: number; weight: number; comment: string | null; evidence_url: string | null }
export interface RuleView { id: string; label: string; role_id: string; role_name: string; holders: number; step_order: number; decision_type: string; min_value: number | null; max_value: number | null }
export interface BidAssessment {
  id: string
  decision: BidDecision
  score: number | null
  rationale: string
  conditions: string
  decided_by_name: string | null
  decided_at: string | null
  authority_unclear: boolean
  admin_override: boolean
  override_note: string | null
}
export interface BidInfo {
  assessment: BidAssessment | null
  scores: BidScore[]
  criteria: string[]
  computed: { score: number | null; complete: boolean; rated: number }
  authority: { rules: RuleView[]; unclear: boolean; authorized: boolean; can_override: boolean }
  can_edit: boolean
  can_decide: boolean
}

// ---------------------------------------------------------------- proposals

export type ProposalStatus = 'draft' | 'in_approval' | 'approved' | 'submitted' | 'accepted' | 'rejected' | 'withdrawn' | 'expired'
export type VersionStatus = 'draft' | 'in_approval' | 'approved' | 'submitted' | 'superseded' | 'rejected'
export type CalcUnit = 'day' | 'hour' | 'piece' | 'flat'
export type LineKind = 'labor' | 'material' | 'travel' | 'external' | 'other'

export interface ProposalRow {
  id: string
  number: string
  title: string
  status: ProposalStatus
  valid_until: string | null
  opportunity_id: string
  opportunity_number: string
  opportunity_title: string
  customer_name: string
  version_no: number | null
  version_status: VersionStatus | null
  price_total: number | null
  currency: string | null
  version_count: number
  updated_at: string
}

export interface WorkPackage {
  id: string
  code: string
  title: string
  description: string
  effort_days: number | null
  start_date: string | null
  end_date: string | null
  milestone_title: string | null
  milestone_due: string | null
  position: number
}

export interface CalcLine {
  id: string
  work_package_id: string | null
  line_kind: LineKind
  description: string
  role_label: string | null
  rate_entry_id: string | null
  quantity: number
  unit: CalcUnit
  unit_cost: number | null
  unit_price: number | null
  currency: string
  position: number
}

export interface ApprovalStep {
  id: string
  step_order: number
  label: string
  role_id: string | null
  role_name: string | null
  status: 'pending' | 'approved' | 'rejected'
  decided_by_name: string | null
  decided_at: string | null
  note: string | null
  admin_override: boolean
  can_decide: boolean
  needs_override_note: boolean
}

export interface VersionData {
  id: string
  proposal_id: string
  version_no: number
  kind: 'draft' | 'revision' | 'alternative'
  status: VersionStatus
  label: string | null
  summary: string
  scope_text: string
  assumptions: string
  exclusions: string
  terms: string
  currency: string
  fx_rate: number | null
  fx_note: string | null
  price_total: number | null
  cost_total: number | null
  margin_pct: number | null
  effort_days: number
  locked_at: string | null
  submitted_at: string | null
  snapshot_hash: string | null
  work_packages: WorkPackage[]
  lines: CalcLine[]
  approvals: ApprovalStep[]
  editable: boolean
  can_see_cost: boolean
}

export interface VersionSummary {
  id: string
  version_no: number
  kind: string
  status: VersionStatus
  label: string | null
  price_total: number | null
  currency: string
  locked_at: string | null
  submitted_at: string | null
  author_name: string | null
}

export interface ProposalData {
  id: string
  number: string
  title: string
  status: ProposalStatus
  valid_until: string | null
  opportunity_id: string
  current_version_id: string | null
  opportunity: { id: string; number: string; title: string; stage: Stage; crm_org_id: string }
  versions: VersionSummary[]
  current: VersionData | null
  can_edit: boolean
}

export interface CompareData {
  from: { id: string; version_no: number }
  to: { id: string; version_no: number }
  changed_fields: string[]
  totals: Record<string, { from: number; to: number; delta: number }>
  work_packages_added: string[]
  work_packages_removed: string[]
  lines_added: string[]
  lines_removed: string[]
}

export interface RateRow {
  id: string
  name: string
  role_label: string
  unit: CalcUnit
  cost_rate: number
  sell_rate: number
  currency: string
  valid_from: string
  valid_to: string | null
}

export interface DecisionRule {
  id: string
  decision_type: 'bid' | 'proposal_approval' | 'contract_signature' | 'nda_signature'
  label: string
  role_id: string
  role_name: string
  circle_id: string | null
  circle_name: string | null
  category: string | null
  risk: Risk | null
  min_value: number | null
  max_value: number | null
  min_margin_pct: number | null
  step_order: number
  active: boolean
  holders: number
}

// ------------------------------------------------------------ NDAs, contracts

export type Coverage = 'none' | 'draft' | 'not_started' | 'active' | 'expiring' | 'expired' | 'terminated'

export interface NdaRow {
  id: string
  number: string
  title: string
  nda_kind: 'mutual' | 'one_way_in' | 'one_way_out'
  status: 'draft' | 'in_review' | 'signed' | 'terminated'
  valid_from: string | null
  valid_to: string | null
  signed_at: string | null
  crm_org_id: string
  customer_name: string
  coverage: Coverage
}

export interface NdaCoverage {
  state: Coverage
  ndas: NdaRow[]
  notice: string
}

export interface NdaDetailData extends NdaRow {
  purpose: string
  recipients: string
  notes: string
  signatory_name: string | null
  signed_by_name: string | null
  customer: { id: string; name: string }
  opportunities: { id: string; number: string; title: string }[]
  projects: { id: string; name: string }[]
  notice: string
  can_edit: boolean
}

export type ContractState = 'draft' | 'in_review' | 'signed' | 'active' | 'expiring' | 'expired' | 'terminated'

export interface ContractRow {
  id: string
  number: string
  title: string
  contract_kind: string
  status: string
  valid_from: string | null
  valid_to: string | null
  value_amount: number | null
  currency: string
  crm_org_id: string
  customer_name: string
  parent_contract_id: string | null
  opportunity_id: string | null
  project_count: number
  state: ContractState
  terms_visible: boolean
}

export interface ContractMilestone { id: string; title: string; due_date: string | null; amount: number | null; currency: string; status: 'planned' | 'invoiced' | 'paid'; project_id: string | null; project_name: string | null }
export interface ContractAmendment { id: string; title: string; description: string; effective_date: string | null; value_delta: number | null; new_valid_to: string | null; signed: boolean }

export interface ContractDetailData extends ContractRow {
  notice_period_days: number | null
  auto_renew: boolean
  notes: string | null
  signed_at: string | null
  signatory_name: string | null
  signed_by_name: string | null
  owner_name: string | null
  owner_user_id: string | null
  customer: { id: string; name: string }
  parent: { id: string; number: string; title: string } | null
  children: { id: string; number: string; title: string; status: string; valid_from: string | null; valid_to: string | null }[]
  projects: { id: string; name: string; phase: string }[]
  opportunity: { id: string; number: string; title: string } | null
  proposal: { id: string; number: string; title: string } | null
  milestones: ContractMilestone[]
  amendments: ContractAmendment[]
  can_edit: boolean
}

export interface ReminderItem { entity_type: 'nda' | 'contract' | 'milestone'; entity_id: string; kind: string; due_date: string; number: string; title: string; link: string }

// ---------------------------------------------------------------- documents

export type DocCategory = 'contract' | 'proposal' | 'nda' | 'report' | 'technical' | 'other'
export type DocConfidentiality = 'internal' | 'restricted' | 'confidential'
export type DocKind = 'link' | 'file' | 'sharepoint'
export type DocEntity = 'project' | 'opportunity' | 'proposal' | 'contract' | 'nda' | 'crm_organization'

export interface DocumentItem {
  id: string
  entity_type: DocEntity
  entity_id: string
  name: string
  category: DocCategory
  confidentiality: DocConfidentiality
  storage_kind: DocKind
  filename: string | null
  content_type: string | null
  size_bytes: number | null
  current_version: number
  description: string
  created_at: string
  author_name: string | null
  is_link: boolean
}

export interface DocumentList { items: DocumentItem[]; hidden_count: number; can_edit: boolean }

export type ConvertAction = 'set' | 'fill' | 'conflict'
export interface ConvertRow { field: string; action: ConvertAction; new: string | number | null; current: string | number | null }
export interface ConvertPreview {
  opportunity: { id: string; number: string; title: string; stage: Stage; circle_id: string | null; project_id: string | null }
  source_proposal: { number: string; version_no: number; currency: string; status: string } | null
  mode: 'new' | 'existing'
  existing_project: { id: string; name: string } | null
  fields: ConvertRow[]
  will_link: Record<string, number>
  warnings: string[]
  blocked_reason: string | null
  can_convert: boolean
}
