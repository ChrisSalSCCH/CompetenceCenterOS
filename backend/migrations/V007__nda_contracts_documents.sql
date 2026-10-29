-- NDAs, contracts, reminders and documents (Phase 3, part 3). Additive only.

CREATE TABLE IF NOT EXISTS ndas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    number VARCHAR(20) NOT NULL,
    crm_org_id UUID NOT NULL REFERENCES crm_organizations(id) ON DELETE RESTRICT,
    title VARCHAR(200) NOT NULL,
    nda_kind VARCHAR(16) NOT NULL DEFAULT 'mutual' CHECK (nda_kind IN ('mutual','one_way_in','one_way_out')),
    purpose TEXT NOT NULL DEFAULT '',
    recipients TEXT NOT NULL DEFAULT '',
    status VARCHAR(12) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','in_review','signed','terminated')),
    valid_from DATE NULL,
    valid_to DATE NULL,
    signed_at DATE NULL,
    signed_by_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    signatory_name VARCHAR(160) NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL,
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ndas_number ON ndas(organization_id, number);
CREATE INDEX IF NOT EXISTS idx_ndas_customer ON ndas(crm_org_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_ndas_valid ON ndas(organization_id, valid_to) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS nda_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    nda_id UUID NOT NULL REFERENCES ndas(id) ON DELETE CASCADE,
    opportunity_id UUID NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    project_id UUID NULL REFERENCES projects(id) ON DELETE CASCADE,
    CHECK ((opportunity_id IS NOT NULL) <> (project_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_nda_link_opp ON nda_links(nda_id, opportunity_id) WHERE opportunity_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_nda_link_proj ON nda_links(nda_id, project_id) WHERE project_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ndal_opp ON nda_links(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_ndal_proj ON nda_links(project_id);

CREATE TABLE IF NOT EXISTS contracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    number VARCHAR(20) NOT NULL,
    crm_org_id UUID NOT NULL REFERENCES crm_organizations(id) ON DELETE RESTRICT,
    title VARCHAR(200) NOT NULL,
    contract_kind VARCHAR(12) NOT NULL DEFAULT 'project' CHECK (contract_kind IN ('framework','project','service','license','research','other')),
    status VARCHAR(12) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','in_review','signed','terminated')),
    parent_contract_id UUID NULL REFERENCES contracts(id) ON DELETE SET NULL,
    opportunity_id UUID NULL REFERENCES opportunities(id) ON DELETE SET NULL,
    proposal_id UUID NULL REFERENCES proposals(id) ON DELETE SET NULL,
    value_amount NUMERIC(14,2) NULL CHECK (value_amount IS NULL OR value_amount >= 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
    valid_from DATE NULL,
    valid_to DATE NULL,
    signed_at DATE NULL,
    signed_by_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    signatory_name VARCHAR(160) NULL,
    notice_period_days INTEGER NULL CHECK (notice_period_days IS NULL OR notice_period_days >= 0),
    auto_renew BOOLEAN NOT NULL DEFAULT FALSE,
    owner_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL,
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),
    CHECK (parent_contract_id IS NULL OR parent_contract_id <> id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_contracts_number ON contracts(organization_id, number);
CREATE INDEX IF NOT EXISTS idx_contracts_customer ON contracts(crm_org_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_contracts_valid ON contracts(organization_id, valid_to) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_contracts_opp ON contracts(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_contracts_parent ON contracts(parent_contract_id);

CREATE TABLE IF NOT EXISTS contract_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE (contract_id, project_id)
);
CREATE INDEX IF NOT EXISTS idx_cproj_project ON contract_projects(project_id);

CREATE TABLE IF NOT EXISTS contract_milestones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    project_id UUID NULL REFERENCES projects(id) ON DELETE SET NULL,
    title VARCHAR(200) NOT NULL,
    due_date DATE NULL,
    amount NUMERIC(14,2) NULL CHECK (amount IS NULL OR amount >= 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
    status VARCHAR(10) NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','invoiced','paid')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cms_contract ON contract_milestones(contract_id);
CREATE INDEX IF NOT EXISTS idx_cms_due ON contract_milestones(organization_id, due_date) WHERE status = 'planned';

CREATE TABLE IF NOT EXISTS contract_amendments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    effective_date DATE NULL,
    value_delta NUMERIC(14,2) NULL,
    new_valid_to DATE NULL,
    signed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL
);
CREATE INDEX IF NOT EXISTS idx_camend_contract ON contract_amendments(contract_id);

-- Dedupe table: one reminder per entity, kind and due date.
CREATE TABLE IF NOT EXISTS commercial_reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    entity_type VARCHAR(20) NOT NULL,
    entity_id UUID NOT NULL,
    kind VARCHAR(30) NOT NULL,
    due_date DATE NOT NULL,
    notified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (entity_type, entity_id, kind, due_date)
);

-- Documents: links today, uploaded files (object storage) and later SharePoint, with versions and access control.
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    entity_type VARCHAR(20) NOT NULL CHECK (entity_type IN ('project','opportunity','proposal','contract','nda','crm_organization')),
    entity_id UUID NOT NULL,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(12) NOT NULL DEFAULT 'other' CHECK (category IN ('contract','proposal','nda','report','technical','other')),
    confidentiality VARCHAR(12) NOT NULL DEFAULT 'internal' CHECK (confidentiality IN ('internal','restricted','confidential')),
    storage_kind VARCHAR(10) NOT NULL DEFAULT 'link' CHECK (storage_kind IN ('link','file','sharepoint')),
    url VARCHAR(1000) NULL,
    file_key VARCHAR(600) NULL,
    filename VARCHAR(255) NULL,
    content_type VARCHAR(120) NULL,
    size_bytes BIGINT NULL CHECK (size_bytes IS NULL OR size_bytes >= 0),
    current_version INTEGER NOT NULL DEFAULT 1,
    description VARCHAR(1000) NOT NULL DEFAULT '',
    legacy_attachment_id UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL,
    CHECK ((storage_kind = 'file' AND file_key IS NOT NULL) OR (storage_kind IN ('link','sharepoint') AND url IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_legacy ON documents(legacy_attachment_id) WHERE legacy_attachment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_entity ON documents(organization_id, entity_type, entity_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_documents_creator ON documents(created_by) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS document_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL CHECK (version_no >= 1),
    storage_kind VARCHAR(10) NOT NULL CHECK (storage_kind IN ('link','file','sharepoint')),
    url VARCHAR(1000) NULL,
    file_key VARCHAR(600) NULL,
    filename VARCHAR(255) NULL,
    content_type VARCHAR(120) NULL,
    size_bytes BIGINT NULL,
    comment VARCHAR(500) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    UNIQUE (document_id, version_no)
);

-- Explicit access list, used for the confidentiality levels 'restricted' and 'confidential'.
CREATE TABLE IF NOT EXISTS document_access (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (document_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_docaccess_user ON document_access(user_id);

-- Existing project links become documents (idempotent through legacy_attachment_id).
INSERT INTO documents (organization_id, entity_type, entity_id, name, category, confidentiality, storage_kind, url, legacy_attachment_id, created_at, created_by)
SELECT a.organization_id, 'project', a.entity_id, a.name, 'other', 'internal', 'link', a.url, a.id, a.created_at, a.created_by
FROM attachments a
JOIN projects p ON p.id = a.entity_id
WHERE a.entity_type = 'project' AND a.deleted_at IS NULL AND p.deleted_at IS NULL
ON CONFLICT DO NOTHING;
