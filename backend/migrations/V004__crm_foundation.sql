-- CRM foundation (Phase 1-2). Opportunities, quotes, NDAs and contracts are Phase 3 and NOT part of this schema.

CREATE TABLE IF NOT EXISTS crm_organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    norm_name VARCHAR(200) NOT NULL,
    legal_name VARCHAR(250) NULL,
    vat_id VARCHAR(40) NULL,
    website VARCHAR(300) NULL,
    industry_entry_id UUID NULL REFERENCES catalog_entries(id) ON DELETE SET NULL,
    country VARCHAR(80) NULL,
    city VARCHAR(120) NULL,
    address VARCHAR(300) NULL,
    size_class VARCHAR(20) NULL CHECK (size_class IS NULL OR size_class IN ('micro','small','medium','large','public')),
    parent_id UUID NULL REFERENCES crm_organizations(id) ON DELETE SET NULL,
    relation_types TEXT[] NOT NULL DEFAULT '{}'
        CHECK (relation_types <@ ARRAY['customer','prospect','partner','research_partner','funder','supplier','competitor','other']::text[]),
    owner_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    customer_since DATE NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL,
    CHECK (parent_id IS NULL OR parent_id <> id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_crm_org_name ON crm_organizations(organization_id, norm_name) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_crm_org_vat ON crm_organizations(organization_id, vat_id) WHERE deleted_at IS NULL AND vat_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_crm_org_owner ON crm_organizations(owner_user_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_crm_org_parent ON crm_organizations(parent_id);
CREATE INDEX IF NOT EXISTS idx_crm_org_industry ON crm_organizations(industry_entry_id);

CREATE TABLE IF NOT EXISTS crm_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(254) NULL,
    phone VARCHAR(40) NULL,
    job_title VARCHAR(120) NULL,
    notes TEXT NOT NULL DEFAULT '',
    status VARCHAR(12) NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_crm_contact_email ON crm_contacts(organization_id, lower(email)) WHERE deleted_at IS NULL AND email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_crm_contact_org ON crm_contacts(organization_id, last_name) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS crm_contact_orgs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    contact_id UUID NOT NULL REFERENCES crm_contacts(id) ON DELETE CASCADE,
    crm_org_id UUID NOT NULL REFERENCES crm_organizations(id) ON DELETE CASCADE,
    contact_role VARCHAR(60) NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (contact_id, crm_org_id)
);
CREATE INDEX IF NOT EXISTS idx_cco_org ON crm_contact_orgs(crm_org_id);

CREATE TABLE IF NOT EXISTS project_orgs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    crm_org_id UUID NOT NULL REFERENCES crm_organizations(id) ON DELETE CASCADE,
    relation VARCHAR(20) NOT NULL DEFAULT 'customer' CHECK (relation IN ('customer','partner','research_partner','funder','subcontractor','other')),
    UNIQUE (project_id, crm_org_id, relation)
);
CREATE INDEX IF NOT EXISTS idx_porgs_org ON project_orgs(crm_org_id);

CREATE TABLE IF NOT EXISTS project_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    contact_id UUID NOT NULL REFERENCES crm_contacts(id) ON DELETE CASCADE,
    contact_role VARCHAR(60) NULL,
    UNIQUE (project_id, contact_id)
);
CREATE INDEX IF NOT EXISTS idx_pcontacts_contact ON project_contacts(contact_id);

CREATE TABLE IF NOT EXISTS crm_activities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    crm_org_id UUID NULL REFERENCES crm_organizations(id) ON DELETE CASCADE,
    contact_id UUID NULL REFERENCES crm_contacts(id) ON DELETE CASCADE,
    project_id UUID NULL REFERENCES projects(id) ON DELETE SET NULL,
    kind VARCHAR(12) NOT NULL DEFAULT 'note' CHECK (kind IN ('call','meeting','email','note','visit','other')),
    subject VARCHAR(200) NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    follow_up_task_id UUID NULL REFERENCES tasks(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL,
    CHECK (crm_org_id IS NOT NULL OR contact_id IS NOT NULL OR project_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_crm_act_org ON crm_activities(crm_org_id, occurred_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_crm_act_contact ON crm_activities(contact_id, occurred_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_crm_act_tenant ON crm_activities(organization_id, occurred_at DESC) WHERE deleted_at IS NULL;

-- A role holder's assignment can be scoped to a customer organization or a project (e.g. Key Account for Customer X).
-- Scope is informational context for who is responsible; it grants no approval authority.
CREATE TABLE IF NOT EXISTS crm_role_scopes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role_assignment_id UUID NOT NULL REFERENCES role_assignments(id) ON DELETE CASCADE,
    scope_type VARCHAR(12) NOT NULL CHECK (scope_type IN ('organization','project')),
    crm_org_id UUID NULL REFERENCES crm_organizations(id) ON DELETE CASCADE,
    project_id UUID NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    CHECK ((scope_type = 'organization' AND crm_org_id IS NOT NULL AND project_id IS NULL)
        OR (scope_type = 'project' AND project_id IS NOT NULL AND crm_org_id IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_crm_scope_org ON crm_role_scopes(role_assignment_id, crm_org_id) WHERE crm_org_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_crm_scope_project ON crm_role_scopes(role_assignment_id, project_id) WHERE project_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_crm_scope_org ON crm_role_scopes(crm_org_id);
CREATE INDEX IF NOT EXISTS idx_crm_scope_project ON crm_role_scopes(project_id);
