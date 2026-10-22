export type AccessLevel = 'org_admin' | 'member' | 'observer'
export type GovMode = 'direct' | 'approval' | 'consent' | 'holacracy'
export type Priority = 'low' | 'medium' | 'high'
export type TaskStatus = 'todo' | 'doing' | 'blocked' | 'done'

export interface Item {
  text: string
  detail: string | null
  level: 'decides' | 'consents' | 'consulted' | 'informed' | null
}

export interface Holder {
  assignment_id: string
  role_id: string
  user_id: string
  focus: string | null
  name: string
  avatar_color: string
}

export interface CircleNode {
  id: string
  parent_id: string | null
  name: string
  purpose: string
  description: string
  governance_mode: GovMode | null
  accountabilities: Item[]
  domains: Item[]
  policies: Item[]
}

export interface RoleNode {
  id: string
  circle_id: string
  name: string
  purpose: string
  description: string
  allow_multiple: boolean
  can_govern: boolean
  lead_user_id: string | null
  accountabilities: Item[]
  domains: Item[]
  policies: Item[]
  authorities: Item[]
  holders: Holder[]
}

export interface Structure {
  circles: CircleNode[]
  roles: RoleNode[]
  as_of: string | null
  historical: boolean
}

export interface HeldRole {
  role_id: string
  role_name: string
  circle_id: string
  circle_name: string
  can_govern: boolean
  focus: string | null
}

export interface Session {
  user: { id: string; name: string; email: string; job_title: string | null; skills: string[]; availability: string | null; avatar_color: string; notification_prefs: Record<string, boolean> }
  organization: { id: string; name: string; slug: string; is_demo: boolean; default_governance_mode: GovMode }
  access_level: AccessLevel
  roles: HeldRole[]
  governable_circle_ids: string[]
  unread_notifications: number
  ai_enabled: boolean
}

export interface HistoryEntry {
  id: string
  proposal_id: string | null
  circle_id: string | null
  entity_type: 'circle' | 'role'
  entity_id: string
  op: 'create' | 'update' | 'delete'
  source: 'direct' | 'proposal' | 'seed'
  before_state: Record<string, unknown> | null
  after_state: Record<string, unknown> | null
  summary: string
  reason: string | null
  created_at: string
  actor_name: string | null
  proposal_title: string | null
  decided_by_name: string | null
}

export interface TaskRow {
  id: string
  title: string
  description: string
  status: TaskStatus
  priority: Priority
  due_date: string | null
  assignee_id: string | null
  assignee_name: string | null
  role_id: string | null
  role_name: string | null
  project_id: string | null
  project_name: string | null
  circle_id: string | null
  circle_name: string | null
  is_overdue: boolean | null
}

export interface ProjectRow {
  id: string
  name: string
  description: string
  status: 'planned' | 'active' | 'on_hold' | 'done' | 'cancelled'
  priority: Priority
  start_date: string | null
  due_date: string | null
  circle_id: string
  circle_name: string
  owning_role_id: string | null
  owning_role_name: string | null
  task_count: number
  tasks_done: number
  milestone_count: number
  milestones_done: number
  people: { user_id: string; name: string }[]
}

export interface TensionRow {
  id: string
  title: string
  description: string
  context_type: string
  context_label: string | null
  priority: Priority
  status: 'open' | 'processing' | 'resolved' | 'dropped'
  outcome_type: string | null
  outcome_ref_id: string | null
  resolution_note: string | null
  created_at: string
  circle_id: string | null
  circle_name: string | null
  role_id: string | null
  role_name: string | null
  creator_id: string
  creator_name: string
}

export interface ProposalRow {
  id: string
  title: string
  status: string
  workflow: GovMode
  proposal_type: string
  circle_id: string
  circle_name: string
  initiator_id: string
  initiator_name: string
  ai_generated: boolean
  created_at: string
  decided_at: string | null
  open_objections: number
}

export interface PersonRow {
  id: string
  name: string
  email: string
  job_title: string | null
  skills: string[]
  availability: string | null
  avatar_color: string
  access_level: AccessLevel
  role_count: number
  open_tasks: number
  roles: { role_id: string; role_name: string; circle_id: string; circle_name: string }[]
}

export interface ChangeOpDraft {
  op: 'create_circle' | 'update_circle' | 'delete_circle' | 'create_role' | 'update_role' | 'delete_role'
  id?: string
  data: Record<string, unknown>
}

export interface SearchHit {
  type: string
  id: string
  title: string
  subtitle: string
  snippet: { field: string; text: string } | null
  score: number
  link: string
}

export interface SubmitResult {
  applied: boolean
  mode: GovMode
  entity_id?: string
  proposal_id?: string
}
