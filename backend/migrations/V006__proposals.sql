-- Proposals (Phase 3, part 2). Approved versions are immutable - enforced by triggers, not only by the API.

CREATE TABLE IF NOT EXISTS rate_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    role_label VARCHAR(120) NOT NULL,
    unit VARCHAR(8) NOT NULL DEFAULT 'day' CHECK (unit IN ('day','hour','piece','flat')),
    cost_rate NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (cost_rate >= 0),
    sell_rate NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (sell_rate >= 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
    valid_from DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to DATE NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL,
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);
CREATE INDEX IF NOT EXISTS idx_rates_org ON rate_entries(organization_id, role_label) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    number VARCHAR(20) NOT NULL,
    opportunity_id UUID NOT NULL REFERENCES opportunities(id) ON DELETE RESTRICT,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','in_approval','approved','submitted','accepted','rejected','withdrawn','expired')),
    valid_until DATE NULL,
    current_version_id UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_proposals_number ON proposals(organization_id, number);
CREATE INDEX IF NOT EXISTS idx_proposals_opp ON proposals(opportunity_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(organization_id, status) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS proposal_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    proposal_id UUID NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL CHECK (version_no >= 1),
    kind VARCHAR(12) NOT NULL DEFAULT 'draft' CHECK (kind IN ('draft','revision','alternative')),
    status VARCHAR(12) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','in_approval','approved','submitted','superseded','rejected')),
    label VARCHAR(120) NULL,
    summary TEXT NOT NULL DEFAULT '',
    scope_text TEXT NOT NULL DEFAULT '',
    assumptions TEXT NOT NULL DEFAULT '',
    exclusions TEXT NOT NULL DEFAULT '',
    terms TEXT NOT NULL DEFAULT '',
    currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
    fx_rate NUMERIC(14,6) NULL CHECK (fx_rate IS NULL OR fx_rate > 0),
    fx_note VARCHAR(300) NULL,
    price_total NUMERIC(14,2) NOT NULL DEFAULT 0,
    cost_total NUMERIC(14,2) NOT NULL DEFAULT 0,
    margin_pct NUMERIC(7,2) NULL,
    effort_days NUMERIC(8,1) NOT NULL DEFAULT 0,
    snapshot JSONB NULL,
    snapshot_hash VARCHAR(64) NULL,
    locked_at TIMESTAMPTZ NULL,
    submitted_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    UNIQUE (proposal_id, version_no)
);
CREATE INDEX IF NOT EXISTS idx_pver_proposal ON proposal_versions(proposal_id);
ALTER TABLE proposals ADD CONSTRAINT fk_proposals_current_version FOREIGN KEY (current_version_id) REFERENCES proposal_versions(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS proposal_work_packages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    version_id UUID NOT NULL REFERENCES proposal_versions(id) ON DELETE CASCADE,
    code VARCHAR(20) NOT NULL DEFAULT '',
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    effort_days NUMERIC(8,1) NOT NULL DEFAULT 0 CHECK (effort_days >= 0),
    start_date DATE NULL,
    end_date DATE NULL,
    milestone_title VARCHAR(200) NULL,
    milestone_due DATE NULL,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pwpk_version ON proposal_work_packages(version_id);

CREATE TABLE IF NOT EXISTS proposal_calc_lines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    version_id UUID NOT NULL REFERENCES proposal_versions(id) ON DELETE CASCADE,
    work_package_id UUID NULL REFERENCES proposal_work_packages(id) ON DELETE SET NULL,
    line_kind VARCHAR(10) NOT NULL DEFAULT 'labor' CHECK (line_kind IN ('labor','material','travel','external','other')),
    description VARCHAR(300) NOT NULL,
    role_label VARCHAR(120) NULL,
    rate_entry_id UUID NULL REFERENCES rate_entries(id) ON DELETE SET NULL,
    quantity NUMERIC(10,2) NOT NULL DEFAULT 1 CHECK (quantity >= 0),
    unit VARCHAR(8) NOT NULL DEFAULT 'day' CHECK (unit IN ('day','hour','piece','flat')),
    unit_cost NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (unit_cost >= 0),
    unit_price NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (unit_price >= 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
    position INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pcalc_version ON proposal_calc_lines(version_id);

CREATE TABLE IF NOT EXISTS proposal_approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    version_id UUID NOT NULL REFERENCES proposal_versions(id) ON DELETE CASCADE,
    step_order SMALLINT NOT NULL,
    label VARCHAR(120) NOT NULL,
    rule_id UUID NULL REFERENCES decision_rules(id) ON DELETE SET NULL,
    role_id UUID NULL REFERENCES roles(id) ON DELETE SET NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    decided_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    decided_at TIMESTAMPTZ NULL,
    note TEXT NULL,
    admin_override BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (version_id, step_order)
);
CREATE INDEX IF NOT EXISTS idx_papp_role ON proposal_approvals(role_id) WHERE status = 'pending';

-- Immutability: once a version is locked (approved), its content can never change - not even by a bug in the API.
CREATE OR REPLACE FUNCTION guard_locked_proposal_version() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.locked_at IS NOT NULL THEN
            RAISE EXCEPTION 'proposal version % is locked', OLD.id USING ERRCODE = 'check_violation';
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.locked_at IS NOT NULL AND (
        NEW.summary IS DISTINCT FROM OLD.summary OR NEW.scope_text IS DISTINCT FROM OLD.scope_text
        OR NEW.assumptions IS DISTINCT FROM OLD.assumptions OR NEW.exclusions IS DISTINCT FROM OLD.exclusions
        OR NEW.terms IS DISTINCT FROM OLD.terms OR NEW.currency IS DISTINCT FROM OLD.currency
        OR NEW.fx_rate IS DISTINCT FROM OLD.fx_rate OR NEW.price_total IS DISTINCT FROM OLD.price_total
        OR NEW.cost_total IS DISTINCT FROM OLD.cost_total OR NEW.margin_pct IS DISTINCT FROM OLD.margin_pct
        OR NEW.effort_days IS DISTINCT FROM OLD.effort_days OR NEW.snapshot_hash IS DISTINCT FROM OLD.snapshot_hash
        OR NEW.snapshot::text IS DISTINCT FROM OLD.snapshot::text OR NEW.locked_at IS DISTINCT FROM OLD.locked_at
        OR NEW.version_no IS DISTINCT FROM OLD.version_no OR NEW.proposal_id IS DISTINCT FROM OLD.proposal_id
    ) THEN
        RAISE EXCEPTION 'proposal version % is locked', OLD.id USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_guard_proposal_version BEFORE UPDATE OR DELETE ON proposal_versions
    FOR EACH ROW EXECUTE FUNCTION guard_locked_proposal_version();

CREATE OR REPLACE FUNCTION guard_locked_proposal_child() RETURNS trigger AS $$
DECLARE
    vid UUID;
    locked TIMESTAMPTZ;
BEGIN
    IF TG_OP = 'DELETE' THEN
        vid := OLD.version_id;
    ELSE
        vid := NEW.version_id;
    END IF;
    SELECT locked_at INTO locked FROM proposal_versions WHERE id = vid;
    IF locked IS NOT NULL THEN
        RAISE EXCEPTION 'proposal version % is locked', vid USING ERRCODE = 'check_violation';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_guard_pwp BEFORE INSERT OR UPDATE OR DELETE ON proposal_work_packages
    FOR EACH ROW EXECUTE FUNCTION guard_locked_proposal_child();
CREATE TRIGGER trg_guard_pcalc BEFORE INSERT OR UPDATE OR DELETE ON proposal_calc_lines
    FOR EACH ROW EXECUTE FUNCTION guard_locked_proposal_child();
