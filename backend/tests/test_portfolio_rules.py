"""Hermetic unit tests for the pure portfolio / catalog rules (no database)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from services.catalog import normalize
from services.portfolio import (
    can_set_verification,
    customer_rule_violated,
    finance_metrics,
    knowledge_completeness,
    normalize_communication,
    public_reference,
)


def test_normalize_treats_spelling_variants_as_equal():
    assert normalize("Node.js") == normalize("NodeJS") == normalize(" node js ")
    assert normalize("C#") != normalize("C")
    assert normalize("C++") != normalize("C")
    assert normalize("...") == ""


def test_customer_projects_need_a_customer():
    assert customer_rule_violated("customer", 0) is True
    assert customer_rule_violated("customer", 1) is False
    assert customer_rule_violated("internal", 0) is False


def test_finance_metrics_are_calculated_from_entered_values():
    fin = {"budget_total": Decimal("480000"), "budget_funding": Decimal("240000"), "costs_to_date": Decimal("310000"), "next_report_due": date(2025, 1, 1), "reporting_cycle": "quarterly"}
    m = finance_metrics(fin, today=date(2025, 2, 1))
    assert m["funding_rate"] == 50.0
    assert m["budget_remaining"] == Decimal("170000")
    assert m["budget_used_pct"] == 64.6
    assert m["report_overdue"] is True


def test_finance_metrics_without_data_are_empty_not_zero():
    m = finance_metrics(None)
    assert m["funding_rate"] is None and m["budget_remaining"] is None and m["report_overdue"] is False
    # no reporting cycle -> a past date is not an overdue report
    assert finance_metrics({"next_report_due": date(2000, 1, 1), "reporting_cycle": "none"})["report_overdue"] is False
    # zero budget must not divide
    assert finance_metrics({"budget_total": 0, "budget_funding": 5})["funding_rate"] is None


def test_reference_flags_are_cleared_when_reference_is_not_allowed():
    out = normalize_communication({"reference_allowed": False, "allow_name": True, "allow_logo": True, "allow_results": True})
    assert not any(out[k] for k in ("allow_name", "allow_logo", "allow_images", "allow_description", "allow_results") if k in out)
    kept = normalize_communication({"reference_allowed": True, "allow_name": True})
    assert kept["allow_name"] is True


def test_public_reference_hides_unreleased_content():
    project = {"id": "p1", "name": "Secret Rollout", "description": "details"}
    hidden = public_reference(project, {"allow_name": False, "allow_description": False}, "Healthcare")
    assert hidden["title"] == "Confidential project (Healthcare)"
    assert hidden["description"] is None and hidden["name_released"] is False
    shown = public_reference(project, {"allow_name": True, "allow_description": True, "allow_logo": True}, None)
    assert shown["title"] == "Secret Rollout" and shown["description"] == "details" and shown["logo_released"] is True


def test_verification_permissions():
    assert can_set_verification("member", False, "ai_draft") is True
    assert can_set_verification("member", False, "verified") is False
    assert can_set_verification("member", True, "verified") is True
    assert can_set_verification("org_admin", False, "approved") is True
    assert can_set_verification("observer", True, "unverified") is False
    assert can_set_verification("member", False, "bogus") is False


def test_knowledge_completeness_counts_only_relevant_sections():
    sections = [
        {"section": "solution", "content": "text", "verification": "verified"},
        {"section": "challenges", "content": "text", "verification": "unverified"},
        {"section": "business_context", "content": "text", "verification": "approved"},
        {"section": "ai_usage", "content": "text", "verification": "verified"},
    ]
    internal = knowledge_completeness(sections, ai_relevant=False, customer=False)
    assert internal["relevant"] == 5  # no business context, no AI section
    assert internal["filled"] == 2 and internal["verified"] == 1
    customer_ai = knowledge_completeness(sections, ai_relevant=True, customer=True)
    assert customer_ai["relevant"] == 7 and customer_ai["filled"] == 4 and customer_ai["verified"] == 3
