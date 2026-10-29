-- Commercial pipeline (Phase 3, part 1): opportunities, bid/no-bid assessment, decision rules.
-- Additive only. Every table carries organization_id for tenant isolation.

-- Gap-free per-year numbering (OPP-2026-0001, ANG-..., NDA-..., CON-...). Incremented with a single upsert.
CREATE TABLE IF NOT EXISTS commercial_counters (
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    kind VARCHAR(3) NOT NULL CHECK (kind IN ('OPP','ANG','NDA','CON')),
    year SMALLINT NOT NULL,
    last_value INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (organization_id, kind, year)
);

-- Default probability per stage; a row overrides the built-in default of the application.
CREATE TABLE IF NOT EXISTS pipeline_stage_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    stage VARCHAR(20) NOT NULL CHECK (stage IN ('lead','qualification','bid_decision','proposal','negotiation','won','lost')),
    probability SMALLINT NOT NULL CHECK (probability BETWEEN 0 AND 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    UNIQUE (organization_id, stage)
);

CREATE TABLE IF NOT EXISTS opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    number VARCHAR(20) NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    crm_org_id UUID NOT NULL REFERENCES crm_organizations(id) ON DELETE RESTRICT,
    circle_id UUID NULL REFERENCES circles(id) ON DELETE SET NULL,
    stage VARCHAR(20) NOT NULL DEFAULT 'lead' CHECK (stage IN ('lead','qualification','bid_decision','proposal','negotiation','won','lost')),
    stage_changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    category VARCHAR(20) NOT NULL DEFAULT 'other' CHECK (category IN ('research','development','consulting','innovation','operations','other')),
    source VARCHAR(40) NULL,
    risk VARCHAR(10) NOT NULL DEFAULT 'medium' CHECK (risk IN ('low','medium','high')),
    value_amount NUMERIC(14,2) NULL CHECK (value_amount IS NULL OR value_amount >= 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
    probability SMALLINT NULL CHECK (probability IS NULL OR probability BETWEEN 0 AND 100),
    probability_manual BOOLEAN NOT NULL DEFAULT FALSE,
    effort_days NUMERIC(8,1) NULL CHECK (effort_days IS NULL OR effort_days >= 0),
    expected_close DATE NULL,
    expected_start DATE NULL,
    expected_end DATE NULL,
    owner_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    next_action VARCHAR(300) NULL,
    next_action_due DATE NULL,
    lost_reason TEXT NULL,
    closed_at TIMESTAMPTZ NULL,
    project_id UUID NULL REFERENCES projects(id) ON DELETE SET NULL,
    converted_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_opportunities_number ON opportunities(organization_id, number);
CREATE INDEX IF NOT EXISTS idx_opp_stage ON opportunities(organization_id, stage) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_opp_customer ON opportunities(crm_org_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_opp_owner ON opportunities(owner_user_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_opp_close ON opportunities(organization_id, expected_close) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_opp_project ON opportunities(project_id);

CREATE TABLE IF NOT EXISTS opportunity_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    opportunity_id UUID NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    contact_id UUID NOT NULL REFERENCES crm_contacts(id) ON DELETE CASCADE,
    contact_role VARCHAR(60) NULL,
    UNIQUE (opportunity_id, contact_id)
);
CREATE INDEX IF NOT EXISTS idx_oppc_contact ON opportunity_contacts(contact_id);

CREATE TABLE IF NOT EXISTS opportunity_catalog_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    opportunity_id UUID NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    entry_id UUID NOT NULL REFERENCES catalog_entries(id) ON DELETE CASCADE,
    UNIQUE (opportunity_id, entry_id)
);
CREATE INDEX IF NOT EXISTS idx_oppcl_entry ON opportunity_catalog_links(entry_id);

CREATE TABLE IF NOT EXISTS opportunity_references (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    opportunity_id UUID NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    note VARCHAR(300) NULL,
    UNIQUE (opportunity_id, project_id)
);
CREATE INDEX IF NOT EXISTS idx_oppref_project ON opportunity_references(project_id);

CREATE TABLE IF NOT EXISTS opportunity_team (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    opportunity_id UUID NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NULL REFERENCES roles(id) ON DELETE SET NULL,
    team_role VARCHAR(60) NULL,
    UNIQUE (opportunity_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_oppt_user ON opportunity_team(user_id);

-- Who is allowed to take which commercial decision. Authority comes from the ROLE a person holds, not from the job title.
CREATE TABLE IF NOT EXISTS decision_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    decision_type VARCHAR(24) NOT NULL CHECK (decision_type IN ('bid','proposal_approval','contract_signature','nda_signature')),
    label VARCHAR(120) NOT NULL,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    circle_id UUID NULL REFERENCES circles(id) ON DELETE CASCADE,
    category VARCHAR(20) NULL CHECK (category IS NULL OR category IN ('research','development','consulting','innovation','operations','other')),
    risk VARCHAR(10) NULL CHECK (risk IS NULL OR risk IN ('low','medium','high')),
    min_value NUMERIC(14,2) NULL CHECK (min_value IS NULL OR min_value >= 0),
    max_value NUMERIC(14,2) NULL CHECK (max_value IS NULL OR max_value >= 0),
    min_margin_pct NUMERIC(5,2) NULL,
    step_order SMALLINT NOT NULL DEFAULT 1 CHECK (step_order BETWEEN 1 AND 20),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL,
    deleted_at TIMESTAMPTZ NULL,
    CHECK (max_value IS NULL OR min_value IS NULL OR max_value >= min_value)
);
CREATE INDEX IF NOT EXISTS idx_drules_org ON decision_rules(organization_id, decision_type) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_drules_role ON decision_rules(role_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS bid_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    opportunity_id UUID NOT NULL UNIQUE REFERENCES opportunities(id) ON DELETE CASCADE,
    score NUMERIC(5,2) NULL,
    decision VARCHAR(10) NOT NULL DEFAULT 'pending' CHECK (decision IN ('pending','bid','no_bid','clarify')),
    rationale TEXT NOT NULL DEFAULT '',
    conditions TEXT NOT NULL DEFAULT '',
    decided_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    decided_at TIMESTAMPTZ NULL,
    authority_unclear BOOLEAN NOT NULL DEFAULT FALSE,
    authority_rule_id UUID NULL REFERENCES decision_rules(id) ON DELETE SET NULL,
    admin_override BOOLEAN NOT NULL DEFAULT FALSE,
    override_note TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL,
    updated_by UUID NULL
);
CREATE INDEX IF NOT EXISTS idx_bid_org ON bid_assessments(organization_id, decision);

CREATE TABLE IF NOT EXISTS bid_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    assessment_id UUID NOT NULL REFERENCES bid_assessments(id) ON DELETE CASCADE,
    criterion VARCHAR(40) NOT NULL CHECK (criterion IN (
        'strategic_fit','customer_potential','technical_feasibility','capacity','competence','risk',
        'margin','funding','reference_value','reuse_potential','win_chance')),
    rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    weight SMALLINT NOT NULL DEFAULT 3 CHECK (weight BETWEEN 1 AND 5),
    comment VARCHAR(1000) NULL,
    evidence_url VARCHAR(1000) NULL,
    UNIQUE (assessment_id, criterion)
);
