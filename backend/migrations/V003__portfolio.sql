-- Project portfolio (additive only). The existing `projects` table stays the single project entity,
-- so tasks, milestones, OKRs and tensions keep working. Richer lifecycle goes into `phase`;
-- the legacy `status` column and its CHECK are untouched.

ALTER TABLE projects ADD COLUMN IF NOT EXISTS classification VARCHAR(12) NOT NULL DEFAULT 'internal';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS category VARCHAR(20) NOT NULL DEFAULT 'other';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS phase VARCHAR(20) NOT NULL DEFAULT 'running';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS short_name VARCHAR(60) NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS project_no VARCHAR(40) NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS org_unit VARCHAR(120) NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS manager_id UUID NULL REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS is_research BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS funding_program VARCHAR(160) NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS funding_agency VARCHAR(160) NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS funding_ref VARCHAR(80) NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS research_note TEXT NOT NULL DEFAULT '';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS ai_relevant BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE projects ADD CONSTRAINT chk_projects_classification CHECK (classification IN ('internal','customer'));
ALTER TABLE projects ADD CONSTRAINT chk_projects_category CHECK (category IN ('research','development','consulting','innovation','operations','other'));
ALTER TABLE projects ADD CONSTRAINT chk_projects_phase CHECK (phase IN ('idea','proposal','running','closing','completed','archived'));

CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_no ON projects(organization_id, project_no) WHERE deleted_at IS NULL AND project_no IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_projects_classification ON projects(organization_id, classification) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_projects_manager ON projects(manager_id) WHERE deleted_at IS NULL;

-- Finance lives in its own table so it can be hidden as a unit.
CREATE TABLE IF NOT EXISTS project_finance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id UUID NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
    budget_total NUMERIC(14,2) NULL CHECK (budget_total IS NULL OR budget_total >= 0),
    budget_funding NUMERIC(14,2) NULL CHECK (budget_funding IS NULL OR budget_funding >= 0),
    budget_own NUMERIC(14,2) NULL CHECK (budget_own IS NULL OR budget_own >= 0),
    costs_to_date NUMERIC(14,2) NULL CHECK (costs_to_date IS NULL OR costs_to_date >= 0),
    revenue_expected NUMERIC(14,2) NULL CHECK (revenue_expected IS NULL OR revenue_expected >= 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
    reporting_cycle VARCHAR(20) NOT NULL DEFAULT 'none' CHECK (reporting_cycle IN ('none','monthly','quarterly','semiannual','yearly')),
    next_report_due DATE NULL,
    last_report_at DATE NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL
);
CREATE INDEX IF NOT EXISTS idx_project_finance_org ON project_finance(organization_id);

CREATE TABLE IF NOT EXISTS project_finance_viewers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (project_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_pfv_user ON project_finance_viewers(user_id);

-- Controlled vocabulary shared by projects, roles and people.
CREATE TABLE IF NOT EXISTS catalog_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    kind VARCHAR(30) NOT NULL CHECK (kind IN ('technology','industry','research_area','competency','method','application_domain','solution_type','reusable_component')),
    name VARCHAR(120) NOT NULL,
    norm_name VARCHAR(120) NOT NULL,
    category VARCHAR(60) NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_catalog_norm ON catalog_entries(organization_id, kind, norm_name) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_catalog_org_kind ON catalog_entries(organization_id, kind) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS catalog_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    entry_id UUID NOT NULL REFERENCES catalog_entries(id) ON DELETE CASCADE,
    kind VARCHAR(30) NOT NULL,
    alias VARCHAR(120) NOT NULL,
    norm_alias VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (organization_id, kind, norm_alias)
);
CREATE INDEX IF NOT EXISTS idx_catalog_alias_entry ON catalog_aliases(entry_id);

CREATE TABLE IF NOT EXISTS project_catalog_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    entry_id UUID NOT NULL REFERENCES catalog_entries(id) ON DELETE CASCADE,
    usage_note VARCHAR(300) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, entry_id)
);
CREATE INDEX IF NOT EXISTS idx_pcl_entry ON project_catalog_links(entry_id);

-- Competencies a role or a person is associated with (same vocabulary).
CREATE TABLE IF NOT EXISTS role_catalog_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    entry_id UUID NOT NULL REFERENCES catalog_entries(id) ON DELETE CASCADE,
    UNIQUE (role_id, entry_id)
);
CREATE INDEX IF NOT EXISTS idx_rcl_entry ON role_catalog_links(entry_id);

CREATE TABLE IF NOT EXISTS project_work_packages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code VARCHAR(20) NOT NULL DEFAULT '',
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status VARCHAR(12) NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','active','done')),
    start_date DATE NULL,
    end_date DATE NULL,
    lead_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_pwp_project ON project_work_packages(project_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS project_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    work_package_id UUID NULL REFERENCES project_work_packages(id) ON DELETE SET NULL,
    title VARCHAR(200) NOT NULL,
    kind VARCHAR(20) NOT NULL DEFAULT 'deliverable' CHECK (kind IN ('deliverable','kpi','publication','prototype','other')),
    planned_value VARCHAR(200) NULL,
    demonstrated_value VARCHAR(200) NULL,
    unit VARCHAR(30) NULL,
    evidence_url VARCHAR(1000) NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','achieved','partial','missed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_pres_project ON project_results(project_id) WHERE deleted_at IS NULL;

-- Structured knowledge sections with verification metadata.
CREATE TABLE IF NOT EXISTS project_knowledge (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    section VARCHAR(30) NOT NULL CHECK (section IN ('business_context','solution','challenges','results','reuse','architecture','ai_usage')),
    content TEXT NOT NULL DEFAULT '',
    verification VARCHAR(12) NOT NULL DEFAULT 'unverified' CHECK (verification IN ('unverified','verified','ai_draft','approved')),
    verified_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    verified_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    UNIQUE (project_id, section)
);
CREATE INDEX IF NOT EXISTS idx_pknow_org ON project_knowledge(organization_id);

CREATE TABLE IF NOT EXISTS project_relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    related_project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    relation VARCHAR(20) NOT NULL DEFAULT 'related' CHECK (relation IN ('follow_up','predecessor','reuses','related')),
    note VARCHAR(300) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, related_project_id),
    CHECK (project_id <> related_project_id)
);
CREATE INDEX IF NOT EXISTS idx_prel_related ON project_relations(related_project_id);

-- Reference permission: which content of a project may be used publicly.
CREATE TABLE IF NOT EXISTS project_communication (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id UUID NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
    reference_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    allow_name BOOLEAN NOT NULL DEFAULT FALSE,
    allow_logo BOOLEAN NOT NULL DEFAULT FALSE,
    allow_images BOOLEAN NOT NULL DEFAULT FALSE,
    allow_description BOOLEAN NOT NULL DEFAULT FALSE,
    allow_results BOOLEAN NOT NULL DEFAULT FALSE,
    approved_by_name VARCHAR(160) NULL,
    approved_at DATE NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL
);
CREATE INDEX IF NOT EXISTS idx_pcomm_org ON project_communication(organization_id) WHERE reference_allowed;
