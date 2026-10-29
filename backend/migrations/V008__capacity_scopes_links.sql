-- Capacity planning and links between the new commercial entities and existing tables (Phase 3/4). Additive only.

CREATE TABLE IF NOT EXISTS person_capacity (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    weekly_hours NUMERIC(5,1) NOT NULL CHECK (weekly_hours >= 0 AND weekly_hours <= 80),
    valid_from DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to DATE NULL,
    note VARCHAR(300) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);
CREATE INDEX IF NOT EXISTS idx_capacity_user ON person_capacity(organization_id, user_id, valid_from);

-- A planned allocation belongs to a project (planned) or an opportunity (hypothetical, never counted as certain).
CREATE TABLE IF NOT EXISTS project_allocations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id UUID NULL REFERENCES projects(id) ON DELETE CASCADE,
    opportunity_id UUID NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    hours_per_week NUMERIC(5,1) NOT NULL CHECK (hours_per_week > 0 AND hours_per_week <= 80),
    note VARCHAR(300) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL,
    CHECK (end_date >= start_date),
    CHECK ((project_id IS NOT NULL) <> (opportunity_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_alloc_user ON project_allocations(organization_id, user_id, start_date) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_alloc_project ON project_allocations(project_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_alloc_opp ON project_allocations(opportunity_id) WHERE deleted_at IS NULL;

-- Projects remember where they came from. The unique index prevents a second project for the same opportunity.
ALTER TABLE projects ADD COLUMN IF NOT EXISTS source_opportunity_id UUID NULL REFERENCES opportunities(id) ON DELETE SET NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS effort_days NUMERIC(8,1) NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_source_opp ON projects(source_opportunity_id) WHERE source_opportunity_id IS NOT NULL AND deleted_at IS NULL;

-- Role scopes may now also point at an opportunity, a proposal or a contract.
-- The old CHECK constraints have generated names; they are looked up instead of guessed.
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN SELECT conname FROM pg_constraint WHERE conrelid = 'crm_role_scopes'::regclass AND contype = 'c' LOOP
        EXECUTE format('ALTER TABLE crm_role_scopes DROP CONSTRAINT %I', r.conname);
    END LOOP;
END $$;

ALTER TABLE crm_role_scopes ADD COLUMN IF NOT EXISTS opportunity_id UUID NULL REFERENCES opportunities(id) ON DELETE CASCADE;
ALTER TABLE crm_role_scopes ADD COLUMN IF NOT EXISTS proposal_id UUID NULL REFERENCES proposals(id) ON DELETE CASCADE;
ALTER TABLE crm_role_scopes ADD COLUMN IF NOT EXISTS contract_id UUID NULL REFERENCES contracts(id) ON DELETE CASCADE;

ALTER TABLE crm_role_scopes ADD CONSTRAINT chk_crm_scope_type CHECK (scope_type IN ('organization','project','opportunity','proposal','contract'));
ALTER TABLE crm_role_scopes ADD CONSTRAINT chk_crm_scope_target CHECK (
    (scope_type = 'organization' AND crm_org_id IS NOT NULL AND project_id IS NULL AND opportunity_id IS NULL AND proposal_id IS NULL AND contract_id IS NULL)
    OR (scope_type = 'project' AND project_id IS NOT NULL AND crm_org_id IS NULL AND opportunity_id IS NULL AND proposal_id IS NULL AND contract_id IS NULL)
    OR (scope_type = 'opportunity' AND opportunity_id IS NOT NULL AND crm_org_id IS NULL AND project_id IS NULL AND proposal_id IS NULL AND contract_id IS NULL)
    OR (scope_type = 'proposal' AND proposal_id IS NOT NULL AND crm_org_id IS NULL AND project_id IS NULL AND opportunity_id IS NULL AND contract_id IS NULL)
    OR (scope_type = 'contract' AND contract_id IS NOT NULL AND crm_org_id IS NULL AND project_id IS NULL AND opportunity_id IS NULL AND proposal_id IS NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_crm_scope_opp ON crm_role_scopes(role_assignment_id, opportunity_id) WHERE opportunity_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_crm_scope_proposal ON crm_role_scopes(role_assignment_id, proposal_id) WHERE proposal_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_crm_scope_contract ON crm_role_scopes(role_assignment_id, contract_id) WHERE contract_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_crm_scope_opp ON crm_role_scopes(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_crm_scope_proposal ON crm_role_scopes(proposal_id);
CREATE INDEX IF NOT EXISTS idx_crm_scope_contract ON crm_role_scopes(contract_id);

-- Activities: workshop/presentation/negotiation kinds, an opportunity link and an external reference (e.g. mail id).
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN SELECT conname FROM pg_constraint WHERE conrelid = 'crm_activities'::regclass AND contype = 'c' LOOP
        EXECUTE format('ALTER TABLE crm_activities DROP CONSTRAINT %I', r.conname);
    END LOOP;
END $$;

ALTER TABLE crm_activities ADD COLUMN IF NOT EXISTS opportunity_id UUID NULL REFERENCES opportunities(id) ON DELETE SET NULL;
ALTER TABLE crm_activities ADD COLUMN IF NOT EXISTS external_ref VARCHAR(300) NULL;
ALTER TABLE crm_activities ADD CONSTRAINT chk_crm_activity_kind CHECK (kind IN ('call','meeting','email','note','visit','workshop','presentation','negotiation','other'));
ALTER TABLE crm_activities ADD CONSTRAINT chk_crm_activity_target CHECK (crm_org_id IS NOT NULL OR contact_id IS NOT NULL OR project_id IS NOT NULL OR opportunity_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS idx_crm_act_opp ON crm_activities(opportunity_id, occurred_at DESC) WHERE deleted_at IS NULL;
