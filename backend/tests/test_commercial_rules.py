"""Unit tests for the pure commercial rules (no database)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from services.commercial import (
    approval_steps,
    bid_score,
    calc_totals,
    contract_state,
    conversion_plan,
    currency_error,
    diff_versions,
    effective_probability,
    format_number,
    nda_coverage,
    rate_for,
    reminder_dates,
    resolve_authority,
    snapshot_hash,
    stage_transition_error,
    weighted_value,
)


def test_probability_defaults_override_and_closed_stages():
    assert effective_probability("lead", None, False) == 10
    assert effective_probability("proposal", 80, True) == 80
    assert effective_probability("proposal", 80, False) == 50
    assert effective_probability("proposal", None, False, {"proposal": 55}) == 55
    assert effective_probability("won", 20, True) == 100
    assert effective_probability("lost", 90, True) == 0
    assert weighted_value("10000.00", 40) == Decimal("4000.00")
    assert weighted_value(None, 40) is None


def test_stage_transition_rules():
    assert stage_transition_error("lead", "lost", "", None, False, False)[0] == "LOST_REASON_REQUIRED"
    assert stage_transition_error("lead", "lost", "too expensive", None, False, False) is None
    assert stage_transition_error("qualification", "proposal", None, None, False, False)[0] == "BID_DECISION_REQUIRED"
    assert stage_transition_error("qualification", "proposal", None, "bid", False, False) is None
    assert stage_transition_error("lost", "lead", None, None, False, False)[0] == "REOPEN_ADMIN_ONLY"
    assert stage_transition_error("lost", "lead", None, None, False, True) is None
    assert stage_transition_error("won", "lead", None, "bid", True, True)[0] == "ALREADY_CONVERTED"


def test_bid_score_is_weighted_and_informational():
    assert bid_score([])["score"] is None
    result = bid_score([{"criterion": "strategic_fit", "rating": 5, "weight": 3}, {"criterion": "capacity", "rating": 3, "weight": 3}])
    assert result["score"] == Decimal("80.0") and result["complete"] is False
    heavy = bid_score([{"criterion": "margin", "rating": 1, "weight": 5}, {"criterion": "risk", "rating": 5, "weight": 1}])
    assert heavy["score"] == Decimal("33.3")


def test_authority_matching_staffing_and_steps():
    rules = [
        {"id": "r1", "label": "Sales lead", "role_id": "A", "holders": 1, "step_order": 1, "min_value": 0, "max_value": 50000, "active": True},
        {"id": "r2", "label": "Management", "role_id": "B", "holders": 1, "step_order": 2, "min_value": 50000, "active": True},
        {"id": "r3", "label": "Inactive", "role_id": "C", "holders": 1, "step_order": 1, "active": False},
    ]
    small = resolve_authority(rules, {"A"}, value=10000, category="development", risk="low", circle_id=None)
    assert [r["id"] for r in small["matching"]] == ["r1"] and small["authorized"] and not small["unclear"]
    big = resolve_authority(rules, {"A"}, value=90000, category=None, risk=None, circle_id=None)
    assert [r["id"] for r in big["matching"]] == ["r2"] and not big["authorized"]
    unstaffed = resolve_authority([{**rules[0], "holders": 0}], {"A"}, value=1, category=None, risk=None, circle_id=None)
    assert unstaffed["unclear"] is True
    assert resolve_authority([], set(), value=1, category=None, risk=None, circle_id=None)["unclear"] is True
    scoped = resolve_authority([{**rules[0], "category": "research"}], {"A"}, value=1, category="consulting", risk=None, circle_id=None)
    assert scoped["matching"] == []
    assert [s["step_order"] for s in approval_steps([rules[0], rules[1]])] == [1, 2]


def test_calculation_rounds_per_line_and_converts_currency():
    lines = [
        {"line_kind": "labor", "quantity": "10", "unit": "day", "unit_cost": "600", "unit_price": "1000", "currency": "EUR"},
        {"line_kind": "travel", "quantity": "1", "unit": "piece", "unit_cost": "300.25", "unit_price": "500.50", "currency": "EUR"},
    ]
    totals = calc_totals(lines, "EUR")
    assert totals["price_total"] == Decimal("10500.50") and totals["cost_total"] == Decimal("6300.25")
    assert totals["margin"] == Decimal("4200.25") and totals["margin_pct"] == Decimal("40.00") and totals["effort_days"] == Decimal("10.0")
    hours = calc_totals([{"line_kind": "labor", "quantity": "16", "unit": "hour", "unit_cost": "0", "unit_price": "100"}], "EUR")
    assert hours["effort_days"] == Decimal("2.0")
    usd = [{"quantity": "2", "unit_cost": "10", "unit_price": "100", "currency": "USD"}]
    assert currency_error(usd, "EUR", None, None)[0] == "FX_RATE_REQUIRED"
    assert currency_error(usd, "EUR", "0.9", "ECB 2026-01-02") is None
    assert currency_error(usd + [{"currency": "GBP"}], "EUR", "0.9", "x")[0] == "MULTIPLE_CURRENCIES"
    assert calc_totals(usd, "EUR", "0.9")["price_total"] == Decimal("180.00")
    assert calc_totals([], "EUR")["margin_pct"] is None


def test_price_list_validity_and_snapshot_hash():
    rates = [
        {"role_label": "Developer", "valid_from": date(2025, 1, 1), "valid_to": date(2025, 12, 31), "sell_rate": 900},
        {"role_label": "Developer", "valid_from": date(2026, 1, 1), "valid_to": None, "sell_rate": 950},
    ]
    assert rate_for(rates, "developer", date(2025, 6, 1))["sell_rate"] == 900
    assert rate_for(rates, "Developer", date(2026, 6, 1))["sell_rate"] == 950
    assert rate_for(rates, "Designer", date(2026, 6, 1)) is None
    assert snapshot_hash({"a": 1, "b": [Decimal("1.00")]}) == snapshot_hash({"b": [Decimal("1.00")], "a": 1})
    assert snapshot_hash({"a": 1}) != snapshot_hash({"a": 2})


def test_version_diff():
    old = {"summary": "A", "price_total": "1000", "work_packages": [{"title": "Analysis"}], "lines": [{"description": "Dev"}]}
    new = {"summary": "B", "price_total": "1200", "work_packages": [{"title": "Analysis"}, {"title": "Rollout"}], "lines": []}
    diff = diff_versions(old, new)
    assert diff["changed_fields"] == ["summary"] and diff["totals"]["price_total"]["delta"] == Decimal("200")
    assert diff["work_packages_added"] == ["Rollout"] and diff["lines_removed"] == ["Dev"]


def test_nda_and_contract_coverage_and_reminders():
    today = date(2026, 5, 1)
    assert nda_coverage("draft", None, None, today) == "draft"
    assert nda_coverage("signed", date(2026, 1, 1), date(2026, 12, 31), today) == "active"
    assert nda_coverage("signed", date(2026, 1, 1), date(2026, 5, 20), today) == "expiring"
    assert nda_coverage("signed", date(2025, 1, 1), date(2026, 4, 30), today) == "expired"
    assert nda_coverage("signed", date(2026, 6, 1), None, today) == "not_started"
    assert nda_coverage("terminated", None, None, today) == "terminated"
    assert contract_state("signed", date(2026, 1, 1), date(2027, 1, 1), today) == "active"
    assert contract_state("signed", date(2026, 1, 1), date(2026, 6, 15), today) == "expiring"
    assert contract_state("signed", date(2025, 1, 1), date(2026, 1, 1), today) == "expired"
    assert reminder_dates(date(2026, 5, 20), 10, today) == [("expires_soon", date(2026, 5, 20)), ("notice_deadline", date(2026, 5, 10))]
    assert reminder_dates(date(2027, 5, 20), 10, today) == []
    assert reminder_dates(None, 10, today) == []


def test_conversion_plan_never_overwrites_silently():
    source = {"name": "Portal", "description": "New", "effort_days": Decimal("40"), "classification": "customer"}
    fresh = conversion_plan(source, None)
    assert {r["field"]: r["action"] for r in fresh} == {"name": "set", "description": "set", "effort_days": "set", "classification": "set"}
    existing = {"name": "Portal", "description": "", "effort_days": None, "classification": "internal"}
    plan = {r["field"]: r["action"] for r in conversion_plan(source, existing)}
    assert plan == {"description": "fill", "effort_days": "fill", "classification": "conflict"}


def test_numbering():
    assert format_number("OPP", 2026, 7) == "OPP-2026-0007"
