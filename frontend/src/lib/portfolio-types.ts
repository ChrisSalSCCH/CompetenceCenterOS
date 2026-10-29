export type Classification = 'internal' | 'customer'
export type Category = 'research' | 'development' | 'consulting' | 'innovation' | 'operations' | 'other'
export type Phase = 'idea' | 'proposal' | 'running' | 'closing' | 'completed' | 'archived'
export type ProjectStatus = 'planned' | 'active' | 'on_hold' | 'done' | 'cancelled'
export type Verification = 'unverified' | 'verified' | 'ai_draft' | 'approved'
export type KnowledgeSection = 'business_context' | 'solution' | 'challenges' | 'results' | 'reuse' | 'architecture' | 'ai_usage'
export type CatalogKind = 'technology' | 'industry' | 'research_area' | 'competency' | 'method' | 'application_domain' | 'solution_type' | 'reusable_component'
export type OrgRelation = 'customer' | 'partner' | 'research_partner' | 'funder' | 'subcontractor' | 'other'
export type CrmRelationType = 'customer' | 'prospect' | 'partner' | 'research_partner' | 'funder' | 'supplier' | 'competitor' | 'other'
export type ActivityKind = 'call' | 'meeting' | 'email' | 'note' | 'visit' | 'other'

export interface EntryRef {
  id: string
  name: string
  kind: CatalogKind
}

export interface CatalogEntry {
  id: string
  kind: CatalogKind
  name: string
  category: string | null
  description: string
  usage_count: number
  aliases: { id: string; alias: string }[]
}

export interface CatalogSuggestion {
  id: string
  kind: CatalogKind
  name: string
  category: string | null
  matched_alias: string | null
}

export interface PortfolioRow {
  id: string
  name: string
  short_name: string | null
  project_no: string | null
  classification: Classification
  category: Category
  phase: Phase
  status: ProjectStatus
  priority: 'low' | 'medium' | 'high'
  start_date: string | null
  due_date: string | null
  org_unit: string | null
  is_research: boolean
  ai_relevant: boolean
  circle_id: string
  circle_name: string
  manager_id: string | null
  manager_name: string | null
  customers: { id: string; name: string }[]
  entries: EntryRef[]
  reference_allowed: boolean
  knowledge_filled: number
  knowledge_verified: number
  knowledge_review: number
}

export interface KnowledgeSectionData {
  section: KnowledgeSection
  content: string
  verification: Verification
  verified_at: string | null
  updated_at: string | null
  verified_by_name: string | null
}

export interface WorkPackage {
  id: string
  code: string
  title: string
  description: string
  status: 'planned' | 'active' | 'done'
  start_date: string | null
  end_date: string | null
  lead_user_id: string | null
  lead_name: string | null
}

export interface ProjectResult {
  id: string
  title: string
  kind: 'deliverable' | 'kpi' | 'publication' | 'prototype' | 'other'
  work_package_id: string | null
  planned_value: string | null
  demonstrated_value: string | null
  unit: string | null
  evidence_url: string | null
  status: 'planned' | 'achieved' | 'partial' | 'missed'
}

export interface FinanceData {
  budget_total: number | null
  budget_funding: number | null
  budget_own: number | null
  costs_to_date: number | null
  revenue_expected: number | null
  currency: string
  reporting_cycle: 'none' | 'monthly' | 'quarterly' | 'semiannual' | 'yearly'
  next_report_due: string | null
  last_report_at: string | null
  notes: string
}

export interface FinanceBlock {
  restricted: boolean
  data: FinanceData | null
  metrics: { funding_rate: number | null; budget_remaining: number | null; budget_used_pct: number | null; report_overdue: boolean } | null
  calculated: string[]
  can_edit: boolean
  viewers: { user_id: string; name: string }[]
}

export interface Communication {
  reference_allowed: boolean
  allow_name: boolean
  allow_logo: boolean
  allow_images: boolean
  allow_description: boolean
  allow_results: boolean
  approved_by_name: string | null
  approved_at: string | null
  notes: string
}

export interface ProjectOrgLink {
  id: string
  name: string
  relation: OrgRelation
  industry: string | null
}

export interface ProjectContactLink {
  id: string
  first_name: string
  last_name: string
  job_title: string | null
  contact_role: string | null
  email: string | null
  phone: string | null
}

export interface ProjectDetailData {
  id: string
  name: string
  description: string
  short_name: string | null
  project_no: string | null
  classification: Classification
  category: Category
  phase: Phase
  status: ProjectStatus
  priority: 'low' | 'medium' | 'high'
  start_date: string | null
  due_date: string | null
  org_unit: string | null
  manager_id: string | null
  manager_name: string | null
  circle_id: string
  circle_name: string
  owning_role_id: string | null
  owning_role_name: string | null
  is_research: boolean
  funding_program: string | null
  funding_agency: string | null
  funding_ref: string | null
  research_note: string
  ai_relevant: boolean
  orgs: ProjectOrgLink[]
  contacts: ProjectContactLink[]
  entries: (EntryRef & { category: string | null; usage_note: string | null })[]
  work_packages: WorkPackage[]
  results: ProjectResult[]
  relations: { id: string; name: string; relation: string; note: string | null; direction: 'incoming' | 'outgoing' }[]
  communication: Communication | null
  documents: { id: string; name: string; url: string }[]
  team: {
    people: { user_id: string; name: string }[]
    role_holders: { user_id: string; name: string; role_name: string; focus: string | null }[]
    customer_roles: { user_id: string; name: string; role_id: string; role_name: string }[]
  }
  knowledge: { sections: KnowledgeSectionData[]; completeness: { relevant: number; filled: number; verified: number } }
  finance: FinanceBlock
  can_manage: boolean
  work: {
    tasks: { id: string; title: string; status: string; priority: string; due_date: string | null; assignee_name: string | null; is_overdue: boolean }[]
    milestones: { id: string; title: string; due_date: string | null; done: boolean }[]
    task_count: number
    tasks_done: number
  }
}

export interface ReferenceRow {
  project_id: string
  title: string
  name_released: boolean
  description: string | null
  logo_released: boolean
  images_released: boolean
  results_released: boolean
  industry: string | null
  entries: EntryRef[]
  approved_by_name: string | null
  approved_at: string | null
}

export interface CrmOrgRow {
  id: string
  name: string
  city: string | null
  country: string | null
  relation_types: CrmRelationType[]
  status: 'active' | 'inactive'
  owner_user_id: string | null
  owner_name: string | null
  industry_entry_id: string | null
  industry: string | null
  parent_id: string | null
  parent_name: string | null
  contact_count: number
  project_count: number
  last_activity_at: string | null
}

export interface CrmActivity {
  id: string
  kind: ActivityKind
  subject: string
  body: string
  occurred_at: string
  contact_id: string | null
  contact_name: string | null
  project_id: string | null
  project_name: string | null
  follow_up_task_id: string | null
  follow_up_title: string | null
  follow_up_status: string | null
  follow_up_due: string | null
  author_name: string | null
}

export interface CrmOrgDetail extends Omit<CrmOrgRow, 'contact_count' | 'project_count'> {
  legal_name: string | null
  vat_id: string | null
  website: string | null
  address: string | null
  size_class: string | null
  customer_since: string | null
  notes: string
  children: { id: string; name: string }[]
  contacts: { id: string; first_name: string; last_name: string; email: string | null; phone: string | null; job_title: string | null; contact_role: string | null; is_primary: boolean; status: string }[]
  projects: { id: string; name: string; classification: Classification; status: ProjectStatus; phase: Phase; start_date: string | null; due_date: string | null; relation: OrgRelation }[]
  activities: CrmActivity[]
  roles: { scope_id: string; scope_type: 'organization' | 'project'; user_id: string; name: string; role_id: string; role_name: string; role_assignment_id: string; project_id: string | null; project_name: string | null }[]
  next_steps: CrmActivity[]
  stats: { contacts: number; projects: number; active_projects: number }
}

export interface CrmContactRow {
  id: string
  first_name: string
  last_name: string
  email: string | null
  phone: string | null
  job_title: string | null
  status: string
  orgs: { id: string; name: string; contact_role: string | null; is_primary: boolean }[]
}

export interface CrmDashboard {
  active_customers: number
  prospects: number
  partners: number
  without_owner: number
  contacts: number
  active_customer_projects: number
  customers_without_recent_activity: number
  open_follow_ups: number
  overdue_follow_ups: number
  recent_activities: (CrmActivity & { org_name: string | null; crm_org_id: string | null })[]
  customers_without_owner: { id: string; name: string }[]
}

export interface RoleScope {
  id: string
  scope_type: 'organization' | 'project'
  crm_org_id: string | null
  org_name: string | null
  project_id: string | null
  project_name: string | null
  role_assignment_id: string
  role_id: string
  role_name: string
  user_id: string
  user_name: string
}
