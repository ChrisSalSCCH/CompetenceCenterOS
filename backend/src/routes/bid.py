"""Bid / No-Bid assessment and the decision rules that define who may decide.

The weighted score is information only: it never decides anything by itself. The decision is taken by
a person who holds a role named in a matching decision rule; without such a rule, only an administrator
may decide, and only with a recorded note.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from services.commercial import BID_CRITERIA, bid_score, resolve_authority
from services.commercial_db import can_edit_opp, get_opp, held_role_ids, load_rules, require_edit_opp
from services.ctx import CtxDep, require_admin, require_circle, require_write
from services.dbx import DbDep, err, q, q1, set_clause, x
from services.events import audit, notify

router = APIRouter(prefix="/api/commercial", tags=["bid"])

Criterion = Literal[
    "strategic_fit", "customer_potential", "technical_feasibility", "capacity", "competence", "risk",
    "margin", "funding", "reference_value", "reuse_potential", "win_chance",
]
DecisionType = Literal["bid", "proposal_approval", "contract_signature", "nda_signature"]
Category = Literal["research", "development", "consulting", "innovation", "operations", "other"]
Risk = Literal["low", "medium", "high"]
BidDecision = Literal["bid", "no_bid", "clarify"]
MAX_MONEY = Decimal("999999999999")
FINAL = ("bid", "no_bid")


class ScoreIn(BaseModel):
    criterion: Criterion
    rating: int = Field(ge=1, le=5)
    weight: int = Field(default=3, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)
    evidence_url: str | None = Field(default=None, max_length=1000, pattern=r"^https?://")


class BidSave(BaseModel):
    scores: list[ScoreIn] = Field(max_length=11)
    rationale: str | None = Field(default=None, max_length=10000)
    conditions: str | None = Field(default=None, max_length=5000)


class BidDecide(BaseModel):
    decision: BidDecision
    rationale: str = Field(default="", max_length=10000)
    conditions: str = Field(default="", max_length=5000)
    override_note: str | None = Field(default=None, max_length=2000)


class RuleCreate(BaseModel):
    decision_type: DecisionType
    label: str = Field(min_length=2, max_length=120)
    role_id: UUID
    circle_id: UUID | None = None
    category: Category | None = None
    risk: Risk | None = None
    min_value: Decimal | None = Field(default=None, ge=0, le=MAX_MONEY)
    max_value: Decimal | None = Field(default=None, ge=0, le=MAX_MONEY)
    min_margin_pct: Decimal | None = Field(default=None, ge=-100, le=100)
    step_order: int = Field(default=1, ge=1, le=20)
    active: bool = True


class RuleUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=2, max_length=120)
    role_id: UUID | None = None
    circle_id: UUID | None = None
    category: Category | None = None
    risk: Risk | None = None
    min_value: Decimal | None = Field(default=None, ge=0, le=MAX_MONEY)
    max_value: Decimal | None = Field(default=None, ge=0, le=MAX_MONEY)
    min_margin_pct: Decimal | None = Field(default=None, ge=-100, le=100)
    step_order: int | None = Field(default=None, ge=1, le=20)
    active: bool | None = None


# ---------------------------------------------------------------- helpers


def _rule_view(rule: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "label", "role_id", "role_name", "holders", "step_order", "decision_type", "min_value", "max_value")
    return {k: rule.get(k) for k in keys}


async def _authority(db, ctx, opp: dict) -> dict[str, Any]:
    rules = await load_rules(db, ctx, "bid")
    held = await held_role_ids(db, ctx)
    return resolve_authority(rules, held, value=opp["value_amount"], category=opp["category"], risk=opp["risk"], circle_id=opp["circle_id"])


async def _assessment(db, opp_id: UUID) -> dict | None:
    return await q1(
        db,
        """SELECT b.*, u.display_name AS decided_by_name FROM bid_assessments b LEFT JOIN users u ON u.id = b.decided_by WHERE b.opportunity_id = :i""",
        i=opp_id,
    )


# ------------------------------------------------------------------ bid


@router.get("/opportunities/{opp_id}/bid", summary="Bid/No-Bid assessment with the authority that applies", responses={404: {"description": "Opportunity not found"}})
async def get_bid(opp_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    opp = await get_opp(db, ctx, opp_id)
    base = await _assessment(db, opp_id)
    scores = await q(db, "SELECT criterion, rating, weight, comment, evidence_url FROM bid_scores WHERE assessment_id = :a", a=base["id"]) if base else []
    auth = await _authority(db, ctx, opp)
    final = bool(base and base["decision"] in FINAL)
    return {
        "assessment": base,
        "scores": scores,
        "criteria": list(BID_CRITERIA),
        "computed": bid_score(scores),
        "authority": {
            "rules": [_rule_view(r) for r in auth["matching"]],
            "unclear": auth["unclear"],
            "authorized": auth["authorized"],
            "can_override": ctx.level == "org_admin",
        },
        "can_edit": await can_edit_opp(db, ctx, opp) and not final,
        "can_decide": ctx.level != "observer" and (auth["authorized"] or ctx.level == "org_admin"),
    }


@router.put("/opportunities/{opp_id}/bid/scores", summary="Save the criteria ratings and notes (does not decide)", responses={409: {"description": "A final decision was taken"}, 403: {"description": "Not on the team"}})
async def save_bid(opp_id: UUID, body: BidSave, ctx: CtxDep, db: DbDep) -> dict:
    opp = await require_edit_opp(db, ctx, opp_id)
    current = await _assessment(db, opp_id)
    if current and current["decision"] in FINAL:
        raise err(409, "BID_DECIDED", "A final decision was taken. Reopen the assessment through a decision to change it.")
    if len({s.criterion for s in body.scores}) != len(body.scores):
        raise err(422, "DUPLICATE_CRITERION", "Each criterion can be rated only once.", "scores")
    computed = bid_score([s.model_dump() for s in body.scores])
    row = await q1(
        db,
        """INSERT INTO bid_assessments (organization_id, opportunity_id, score, rationale, conditions, created_by, updated_by)
           VALUES (:o, :i, :sc, COALESCE(:ra, ''), COALESCE(:co, ''), :u, :u)
           ON CONFLICT (opportunity_id) DO UPDATE SET score = EXCLUDED.score,
             rationale = COALESCE(:ra, bid_assessments.rationale), conditions = COALESCE(:co, bid_assessments.conditions), updated_at = NOW(), updated_by = :u
           RETURNING id""",
        o=ctx.org_id, i=opp_id, sc=computed["score"], ra=body.rationale, co=body.conditions, u=ctx.user_id,
    )
    await x(db, "DELETE FROM bid_scores WHERE assessment_id = :a", a=row["id"])
    for s in body.scores:
        await x(
            db,
            "INSERT INTO bid_scores (organization_id, assessment_id, criterion, rating, weight, comment, evidence_url) VALUES (:o, :a, :c, :r, :w, :cm, :ev)",
            o=ctx.org_id, a=row["id"], c=s.criterion, r=s.rating, w=s.weight, cm=s.comment, ev=s.evidence_url,
        )
    await audit(db, ctx, "opportunity.bid_scored", "opportunity", opp_id, f"{opp['number']}: score {computed['score']}", {"score": str(computed["score"])})
    await db.commit()
    return {"ok": True, "score": computed["score"], "complete": computed["complete"]}


@router.post("/opportunities/{opp_id}/bid/decision", summary="Take or reopen the Bid/No-Bid decision", responses={403: {"description": "No decision authority"}, 422: {"description": "Note required"}})
async def decide_bid(opp_id: UUID, body: BidDecide, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    opp = await get_opp(db, ctx, opp_id)
    current = await _assessment(db, opp_id)
    reopening = bool(current and current["decision"] in FINAL)
    needs_authority = body.decision in FINAL or reopening
    if body.decision in FINAL and not body.rationale.strip():
        raise err(422, "RATIONALE_REQUIRED", "A rationale is required for a Bid or No-Bid decision.", "rationale")
    if opp["stage"] in ("won", "lost") and body.decision != "clarify":
        raise err(409, "OPPORTUNITY_CLOSED", "A closed opportunity cannot be decided.")
    auth = await _authority(db, ctx, opp)
    override = False
    if needs_authority and not auth["authorized"]:
        if ctx.level != "org_admin":
            raise err(403, "AUTHORITY_REQUIRED", "Only the holder of a decision role (or an administrator with a note) can take this decision.")
        if not (body.override_note or "").strip():
            raise err(422, "OVERRIDE_NOTE_REQUIRED", "Without a matching decision role, an administrator must record why the decision is taken.", "override_note")
        override = True
    elif not needs_authority and not await can_edit_opp(db, ctx, opp):
        raise err(403, "OPPORTUNITY_FORBIDDEN", "Only administrators, the owner or the opportunity team can change this opportunity.")
    rule_id = auth["matching"][0]["id"] if auth["matching"] and auth["authorized"] else None
    final = body.decision in FINAL
    await x(
        db,
        """INSERT INTO bid_assessments (organization_id, opportunity_id, decision, rationale, conditions, decided_by, decided_at, authority_unclear,
                                        authority_rule_id, admin_override, override_note, created_by, updated_by)
           VALUES (:o, :i, :d, :ra, :co, CASE WHEN :fin THEN CAST(:u AS uuid) END, CASE WHEN :fin THEN NOW() END, :un, :ru, :ov, :ovn, :u, :u)
           ON CONFLICT (opportunity_id) DO UPDATE SET decision = EXCLUDED.decision, rationale = EXCLUDED.rationale, conditions = EXCLUDED.conditions,
             decided_by = EXCLUDED.decided_by, decided_at = EXCLUDED.decided_at, authority_unclear = EXCLUDED.authority_unclear,
             authority_rule_id = EXCLUDED.authority_rule_id, admin_override = EXCLUDED.admin_override, override_note = EXCLUDED.override_note,
             updated_at = NOW(), updated_by = EXCLUDED.updated_by""",
        o=ctx.org_id, i=opp_id, d=body.decision, ra=body.rationale, co=body.conditions, fin=final, u=ctx.user_id, un=auth["unclear"] and needs_authority,
        ru=rule_id, ov=override, ovn=(body.override_note or None) if override else None,
    )
    moved = None
    if body.decision == "bid" and opp["stage"] in ("lead", "qualification", "bid_decision"):
        moved = "proposal"
    elif body.decision == "no_bid" and opp["stage"] not in ("won", "lost"):
        moved = "lost"
    if moved:
        await x(
            db,
            """UPDATE opportunities SET stage = :s, stage_changed_at = NOW(), lost_reason = CASE WHEN :lost THEN :lr END, closed_at = CASE WHEN :lost THEN NOW() END,
                   probability = CASE WHEN :lost THEN NULL ELSE probability END, probability_manual = CASE WHEN :lost THEN FALSE ELSE probability_manual END,
                   updated_at = NOW(), updated_by = :u WHERE id = :i""",
            s=moved, lost=moved == "lost", lr=f"No-Bid: {body.rationale.strip()}"[:2000], u=ctx.user_id, i=opp_id,
        )
        await audit(db, ctx, "opportunity.stage_changed", "opportunity", opp_id, f"{opp['number']}: {opp['stage']} -> {moved}", {"from": opp["stage"], "to": moved, "by": "bid_decision"})
    await audit(
        db, ctx, "opportunity.bid_decision", "opportunity", opp_id, f"{opp['number']}: {body.decision}",
        {"decision": body.decision, "override": override, "authority_unclear": auth["unclear"], "override_note": body.override_note if override else None},
    )
    if opp["owner_user_id"] and final:
        await notify(db, ctx.org_id, [opp["owner_user_id"]], "task", f"Bid decision for {opp['number']}: {body.decision}", opp["title"], f"/sales/opportunities/{opp_id}", exclude=ctx.user_id)
    await db.commit()
    return {"ok": True, "decision": body.decision, "admin_override": override, "authority_unclear": auth["unclear"], "stage": moved or opp["stage"]}


# ---------------------------------------------------------- decision rules


async def _validate_rule(db, ctx, data: dict[str, Any]) -> None:
    if data.get("role_id"):
        role = await q1(db, "SELECT 1 AS ok FROM roles WHERE id = :r AND organization_id = :o AND deleted_at IS NULL", r=data["role_id"], o=ctx.org_id)
        if role is None:
            raise err(404, "ROLE_NOT_FOUND", "Role not found.", "role_id")
    if data.get("circle_id"):
        await require_circle(db, ctx, data["circle_id"])
    lo, hi = data.get("min_value"), data.get("max_value")
    if lo is not None and hi is not None and hi < lo:
        raise err(422, "INVALID_RANGE", "The maximum value cannot be below the minimum value.", "max_value")


@router.get("/decision-rules", summary="Decision rules: which role may decide what")
async def list_rules(ctx: CtxDep, db: DbDep, decision_type: DecisionType | None = None) -> list[dict]:
    rows = await q(
        db,
        """SELECT dr.id, dr.decision_type, dr.label, dr.role_id, r.name AS role_name, dr.circle_id, c.name AS circle_name, dr.category, dr.risk,
                  dr.min_value, dr.max_value, dr.min_margin_pct, dr.step_order, dr.active,
                  (SELECT COUNT(*) FROM role_assignments ra WHERE ra.role_id = dr.role_id AND ra.deleted_at IS NULL) AS holders
           FROM decision_rules dr JOIN roles r ON r.id = dr.role_id LEFT JOIN circles c ON c.id = dr.circle_id
           WHERE dr.organization_id = :o AND dr.deleted_at IS NULL AND (CAST(:t AS text) IS NULL OR dr.decision_type = CAST(:t AS text)) ORDER BY dr.decision_type, dr.step_order, dr.label""",
        o=ctx.org_id, t=decision_type,
    )
    if ctx.level == "observer":
        for r in rows:
            r["min_value"] = None
            r["max_value"] = None
    return rows


@router.post("/decision-rules", summary="Create a decision rule - administrators only")
async def create_rule(body: RuleCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    await _validate_rule(db, ctx, body.model_dump())
    row = await q1(
        db,
        """INSERT INTO decision_rules (organization_id, decision_type, label, role_id, circle_id, category, risk, min_value, max_value, min_margin_pct, step_order, active, created_by, updated_by)
           VALUES (:o, :t, :l, :r, :c, :ca, :ri, :mn, :mx, :mm, :s, :a, :u, :u) RETURNING id""",
        o=ctx.org_id, t=body.decision_type, l=body.label.strip(), r=body.role_id, c=body.circle_id, ca=body.category, ri=body.risk, mn=body.min_value, mx=body.max_value,
        mm=body.min_margin_pct, s=body.step_order, a=body.active, u=ctx.user_id,
    )
    await audit(db, ctx, "decision_rule.created", "decision_rule", row["id"], f"{body.decision_type}: {body.label}")
    await db.commit()
    return {"id": row["id"]}


@router.patch("/decision-rules/{rule_id}", summary="Update a decision rule - administrators only", responses={404: {"description": "Rule not found"}})
async def update_rule(rule_id: UUID, body: RuleUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    rule = await q1(db, "SELECT * FROM decision_rules WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=rule_id, o=ctx.org_id)
    if rule is None:
        raise err(404, "RULE_NOT_FOUND", "Decision rule not found.")
    data = body.model_dump(exclude_unset=True)
    for required in ("label", "role_id", "step_order", "active"):
        if required in data and data[required] is None:
            raise err(422, "VALIDATION_ERROR", f"{required} cannot be empty.", required)
    await _validate_rule(db, ctx, {**{k: rule[k] for k in ("min_value", "max_value")}, **data})
    sets, params = set_clause(data, {"label", "role_id", "circle_id", "category", "risk", "min_value", "max_value", "min_margin_pct", "step_order", "active"})
    if sets:
        await x(db, f"UPDATE decision_rules SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=rule_id, u=ctx.user_id, **params)  # noqa: S608
        await audit(db, ctx, "decision_rule.updated", "decision_rule", rule_id, rule["label"])
    await db.commit()
    return {"ok": True}


@router.delete("/decision-rules/{rule_id}", summary="Delete a decision rule (soft) - administrators only")
async def delete_rule(rule_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    rule = await q1(db, "SELECT label FROM decision_rules WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=rule_id, o=ctx.org_id)
    if rule is None:
        raise err(404, "RULE_NOT_FOUND", "Decision rule not found.")
    await x(db, "UPDATE decision_rules SET deleted_at = NOW(), updated_by = :u WHERE id = :i", i=rule_id, u=ctx.user_id)
    await audit(db, ctx, "decision_rule.deleted", "decision_rule", rule_id, rule["label"])
    await db.commit()
    return {"ok": True}
