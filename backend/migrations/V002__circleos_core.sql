-- CircleOS core schema (additive only).
-- Every business table carries organization_id for tenant isolation.

CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(120) NOT NULL,
    slug VARCHAR(60) NOT NULL UNIQUE,
    default_governance_mode VARCHAR(20) NOT NULL DEFAULT 'consent'
        CHECK (default_governance_mode IN ('direct','approval','consent','holacracy')),
    is_demo BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    access_level VARCHAR(20) NOT NULL DEFAULT 'member'
        CHECK (access_level IN ('org_admin','member','observer')),
    job_title VARCHAR(120) NULL,
    skills TEXT[] NOT NULL DEFAULT '{}',
    availability VARCHAR(120) NULL,
    avatar_color VARCHAR(9) NOT NULL DEFAULT '#C2512D',
    notification_prefs JSONB NOT NULL DEFAULT '{"governance":true,"tasks":true,"meetings":true,"tensions":true}',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    UNIQUE (organization_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_memberships_user ON memberships(user_id);

CREATE TABLE IF NOT EXISTS circles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    parent_id UUID NULL REFERENCES circles(id) ON DELETE NO ACTION,
    name VARCHAR(120) NOT NULL,
    purpose TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    governance_mode VARCHAR(20) NULL
        CHECK (governance_mode IS NULL OR governance_mode IN ('direct','approval','consent','holacracy')),
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL,
    CHECK (parent_id IS NULL OR parent_id <> id)
);
CREATE INDEX IF NOT EXISTS idx_circles_org ON circles(organization_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_circles_parent ON circles(parent_id);

CREATE TABLE IF NOT EXISTS roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    circle_id UUID NOT NULL REFERENCES circles(id) ON DELETE NO ACTION,
    name VARCHAR(120) NOT NULL,
    purpose TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    allow_multiple BOOLEAN NOT NULL DEFAULT FALSE,
    can_govern BOOLEAN NOT NULL DEFAULT FALSE,
    lead_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    template_key VARCHAR(60) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_roles_org ON roles(organization_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_roles_circle ON roles(circle_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS role_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    focus VARCHAR(200) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_role_assignment_active ON role_assignments(role_id, user_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_assignments_user ON role_assignments(user_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_assignments_org ON role_assignments(organization_id) WHERE deleted_at IS NULL;

-- Accountabilities, domains, policies and decision authorities of a circle OR a role.
CREATE TABLE IF NOT EXISTS governance_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    circle_id UUID NULL REFERENCES circles(id) ON DELETE CASCADE,
    role_id UUID NULL REFERENCES roles(id) ON DELETE CASCADE,
    kind VARCHAR(20) NOT NULL CHECK (kind IN ('accountability','domain','policy','decision_authority')),
    text VARCHAR(600) NOT NULL,
    detail TEXT NULL,
    authority_level VARCHAR(20) NULL
        CHECK (authority_level IS NULL OR authority_level IN ('decides','consents','consulted','informed')),
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL,
    CHECK ((circle_id IS NOT NULL) <> (role_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_gitems_role ON governance_items(role_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_gitems_circle ON governance_items(circle_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_gitems_org ON governance_items(organization_id, kind) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS tensions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    creator_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    context_type VARCHAR(20) NOT NULL DEFAULT 'circle'
        CHECK (context_type IN ('circle','role','project','responsibility','process')),
    circle_id UUID NULL REFERENCES circles(id) ON DELETE SET NULL,
    role_id UUID NULL REFERENCES roles(id) ON DELETE SET NULL,
    project_id UUID NULL,
    context_label VARCHAR(300) NULL,
    priority VARCHAR(10) NOT NULL DEFAULT 'medium' CHECK (priority IN ('low','medium','high')),
    status VARCHAR(20) NOT NULL DEFAULT 'open' CHECK (status IN ('open','processing','resolved','dropped')),
    outcome_type VARCHAR(20) NULL CHECK (outcome_type IS NULL OR outcome_type IN ('task','project','proposal','decision','resolution')),
    outcome_ref_id UUID NULL,
    resolution_note TEXT NULL,
    resolved_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_tensions_org ON tensions(organization_id, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tensions_creator ON tensions(creator_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tensions_circle ON tensions(circle_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS meetings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    circle_id UUID NOT NULL REFERENCES circles(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    meeting_type VARCHAR(20) NOT NULL DEFAULT 'tactical'
        CHECK (meeting_type IN ('tactical','governance','general','custom')),
    scheduled_at TIMESTAMPTZ NOT NULL,
    duration_min INTEGER NOT NULL DEFAULT 60 CHECK (duration_min BETWEEN 5 AND 600),
    facilitator_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled','in_progress','completed','cancelled')),
    current_step INTEGER NOT NULL DEFAULT 0,
    checkin_notes TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_meetings_org ON meetings(organization_id, scheduled_at) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_meetings_circle ON meetings(circle_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS meeting_participants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    attended BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (meeting_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_mparticipants_user ON meeting_participants(user_id);

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    circle_id UUID NOT NULL REFERENCES circles(id) ON DELETE CASCADE,
    owning_role_id UUID NULL REFERENCES roles(id) ON DELETE SET NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','active','on_hold','done','cancelled')),
    priority VARCHAR(10) NOT NULL DEFAULT 'medium' CHECK (priority IN ('low','medium','high')),
    start_date DATE NULL,
    due_date DATE NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_org ON projects(organization_id, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_projects_circle ON projects(circle_id) WHERE deleted_at IS NULL;
ALTER TABLE tensions ADD CONSTRAINT fk_tensions_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS project_people (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (project_id, user_id)
);

CREATE TABLE IF NOT EXISTS project_milestones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    due_date DATE NULL,
    done BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_milestones_project ON project_milestones(project_id);

CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id UUID NULL REFERENCES projects(id) ON DELETE SET NULL,
    circle_id UUID NULL REFERENCES circles(id) ON DELETE SET NULL,
    role_id UUID NULL REFERENCES roles(id) ON DELETE SET NULL,
    assignee_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    tension_id UUID NULL REFERENCES tensions(id) ON DELETE SET NULL,
    meeting_id UUID NULL REFERENCES meetings(id) ON DELETE SET NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','doing','blocked','done')),
    priority VARCHAR(10) NOT NULL DEFAULT 'medium' CHECK (priority IN ('low','medium','high')),
    due_date DATE NULL,
    position INTEGER NOT NULL DEFAULT 0,
    completed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_org ON tasks(organization_id, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_circle ON tasks(circle_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_role ON tasks(role_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS task_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    author_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_task_comments_task ON task_comments(task_id);

CREATE TABLE IF NOT EXISTS task_activity (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    actor_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(60) NOT NULL,
    detail TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_task_activity_task ON task_activity(task_id);

CREATE TABLE IF NOT EXISTS attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    entity_type VARCHAR(20) NOT NULL CHECK (entity_type IN ('task','role','project','circle')),
    entity_id UUID NOT NULL,
    name VARCHAR(200) NOT NULL,
    url VARCHAR(1000) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_attachments_entity ON attachments(entity_type, entity_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS governance_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    circle_id UUID NOT NULL REFERENCES circles(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    expected_impact TEXT NOT NULL DEFAULT '',
    proposal_type VARCHAR(30) NOT NULL DEFAULT 'modify_role'
        CHECK (proposal_type IN ('create_role','modify_role','remove_role','create_circle','restructure_circle','change_accountabilities','change_domains','update_policies','change_authorities')),
    workflow VARCHAR(20) NOT NULL DEFAULT 'consent' CHECK (workflow IN ('direct','approval','consent','holacracy')),
    status VARCHAR(20) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','submitted','clarifying','reactions','objections','integration','accepted','rejected','withdrawn')),
    changes JSONB NOT NULL DEFAULT '[]',
    initiator_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    source_tension_id UUID NULL REFERENCES tensions(id) ON DELETE SET NULL,
    meeting_id UUID NULL REFERENCES meetings(id) ON DELETE SET NULL,
    ai_generated BOOLEAN NOT NULL DEFAULT FALSE,
    decided_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    decided_at TIMESTAMPTZ NULL,
    decision_note TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_proposals_org ON governance_proposals(organization_id, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_proposals_circle ON governance_proposals(circle_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS proposal_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    proposal_id UUID NOT NULL REFERENCES governance_proposals(id) ON DELETE CASCADE,
    author_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    kind VARCHAR(20) NOT NULL CHECK (kind IN ('question','answer','reaction','objection','comment','integration')),
    body TEXT NOT NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','withdrawn')),
    resolution_note TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pcomments_proposal ON proposal_comments(proposal_id);

CREATE TABLE IF NOT EXISTS governance_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    circle_id UUID NULL REFERENCES circles(id) ON DELETE SET NULL,
    proposal_id UUID NULL REFERENCES governance_proposals(id) ON DELETE SET NULL,
    meeting_id UUID NULL REFERENCES meetings(id) ON DELETE SET NULL,
    title VARCHAR(200) NOT NULL,
    outcome VARCHAR(20) NOT NULL CHECK (outcome IN ('accepted','rejected','withdrawn','recorded')),
    rationale TEXT NOT NULL DEFAULT '',
    decided_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_decisions_org ON governance_decisions(organization_id, created_at DESC);

-- Versioned, auditable record of every structural change (before/after snapshots).
CREATE TABLE IF NOT EXISTS governance_changes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    proposal_id UUID NULL REFERENCES governance_proposals(id) ON DELETE SET NULL,
    circle_id UUID NULL,
    entity_type VARCHAR(10) NOT NULL CHECK (entity_type IN ('circle','role')),
    entity_id UUID NOT NULL,
    op VARCHAR(10) NOT NULL CHECK (op IN ('create','update','delete')),
    source VARCHAR(12) NOT NULL DEFAULT 'direct' CHECK (source IN ('direct','proposal','seed')),
    before_state JSONB NULL,
    after_state JSONB NULL,
    summary VARCHAR(300) NOT NULL DEFAULT '',
    actor_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_gchanges_org ON governance_changes(organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_gchanges_entity ON governance_changes(entity_type, entity_id, created_at);
CREATE INDEX IF NOT EXISTS idx_gchanges_circle ON governance_changes(circle_id);

CREATE TABLE IF NOT EXISTS agenda_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    title VARCHAR(200) NOT NULL,
    kind VARCHAR(20) NOT NULL DEFAULT 'custom' CHECK (kind IN ('checkin','checklist','metrics','projects','tension','custom','closing')),
    tension_id UUID NULL REFERENCES tensions(id) ON DELETE SET NULL,
    project_id UUID NULL REFERENCES projects(id) ON DELETE SET NULL,
    notes TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT '',
    status VARCHAR(10) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agenda_meeting ON agenda_items(meeting_id, position);

CREATE TABLE IF NOT EXISTS objectives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    circle_id UUID NOT NULL REFERENCES circles(id) ON DELETE CASCADE,
    role_id UUID NULL REFERENCES roles(id) ON DELETE SET NULL,
    parent_id UUID NULL REFERENCES objectives(id) ON DELETE SET NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    period VARCHAR(30) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL,
    CHECK (parent_id IS NULL OR parent_id <> id)
);
CREATE INDEX IF NOT EXISTS idx_objectives_org ON objectives(organization_id) WHERE deleted_at IS NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS objective_id UUID NULL REFERENCES objectives(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS key_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    objective_id UUID NOT NULL REFERENCES objectives(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    unit VARCHAR(20) NOT NULL DEFAULT '',
    start_value NUMERIC(14,2) NOT NULL DEFAULT 0,
    target_value NUMERIC(14,2) NOT NULL DEFAULT 100,
    current_value NUMERIC(14,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_kr_objective ON key_results(objective_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    circle_id UUID NOT NULL REFERENCES circles(id) ON DELETE CASCADE,
    role_id UUID NULL REFERENCES roles(id) ON DELETE SET NULL,
    name VARCHAR(160) NOT NULL,
    unit VARCHAR(20) NOT NULL DEFAULT '',
    direction VARCHAR(4) NOT NULL DEFAULT 'up' CHECK (direction IN ('up','down')),
    target_value NUMERIC(14,2) NOT NULL DEFAULT 0,
    current_value NUMERIC(14,2) NOT NULL DEFAULT 0,
    period VARCHAR(20) NOT NULL DEFAULT 'monthly' CHECK (period IN ('weekly','monthly','quarterly','yearly')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_org ON metrics(organization_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS metric_readings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    metric_id UUID NOT NULL REFERENCES metrics(id) ON DELETE CASCADE,
    value NUMERIC(14,2) NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    note VARCHAR(300) NULL,
    recorded_by UUID NULL
);
CREATE INDEX IF NOT EXISTS idx_readings_metric ON metric_readings(metric_id, recorded_at);

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind VARCHAR(30) NOT NULL,
    title VARCHAR(250) NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    link VARCHAR(300) NULL,
    read_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    actor_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(60) NOT NULL,
    entity_type VARCHAR(40) NOT NULL,
    entity_id UUID NULL,
    summary VARCHAR(400) NOT NULL DEFAULT '',
    data JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_org ON audit_events(organization_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ai_provider_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL UNIQUE REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(80) NOT NULL DEFAULT 'Custom provider',
    base_url VARCHAR(300) NOT NULL DEFAULT '',
    model VARCHAR(120) NOT NULL DEFAULT '',
    api_key_encrypted TEXT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL
);

CREATE TABLE IF NOT EXISTS saved_filters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(80) NOT NULL,
    query VARCHAR(300) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_saved_filters_user ON saved_filters(user_id);
