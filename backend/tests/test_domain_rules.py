"""Hermetic unit tests for scch/kernel domain rules (no database, no network)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from routes.goals import kr_progress, metric_progress, rollup
from routes.governance import _comment_allowed
from services.analysis import find_overlaps, jaccard, stem, stems, tokenize
from services.assistant import build_role_template, classify, detect_lang
from services.ctx import would_create_cycle
from services.governance import ChangeOp, acceptance_blocker, next_status
from services.search import query_stems, rank_roles


# ------------------------------------------------------------------ circle cycles
class TestCircleCycles:
    parents = {"root": None, "a": "root", "b": "a", "c": "b"}

    def test_moving_under_own_descendant_is_a_cycle(self):
        assert would_create_cycle(self.parents, "a", "c") is True

    def test_moving_under_itself_is_a_cycle(self):
        assert would_create_cycle(self.parents, "b", "b") is True

    def test_moving_to_sibling_branch_is_fine(self):
        parents = {**self.parents, "d": "root"}
        assert would_create_cycle(parents, "c", "d") is False

    def test_corrupt_existing_loop_is_refused(self):
        looped = {"x": "y", "y": "x", "z": None}
        assert would_create_cycle(looped, "z", "x") is True


# ------------------------------------------------------------------ workflows
class TestWorkflowRules:
    def test_holacracy_stage_order(self):
        order = ["submitted"]
        while (nxt := next_status("holacracy", order[-1])) is not None:
            order.append(nxt)
        assert order == ["submitted", "clarifying", "reactions", "objections", "integration"]

    def test_consent_has_only_objection_stage(self):
        assert next_status("consent", "submitted") == "objections"
        assert next_status("consent", "objections") is None

    def test_approval_has_no_further_stage(self):
        assert next_status("approval", "submitted") is None

    def test_open_objection_blocks_consent(self):
        assert acceptance_blocker("consent", "objections", 1) is not None
        assert acceptance_blocker("consent", "objections", 0) is None

    def test_holacracy_cannot_be_accepted_before_objection_round(self):
        assert acceptance_blocker("holacracy", "clarifying", 0) is not None
        assert acceptance_blocker("holacracy", "integration", 0) is None

    def test_closed_or_draft_proposals_cannot_be_accepted(self):
        assert acceptance_blocker("approval", "accepted", 0) is not None
        assert acceptance_blocker("approval", "draft", 0) is not None

    @pytest.mark.parametrize(
        ("workflow", "status", "kind", "allowed"),
        [
            ("holacracy", "clarifying", "question", True),
            ("holacracy", "clarifying", "objection", False),
            ("holacracy", "objections", "objection", True),
            ("approval", "submitted", "objection", False),
            ("consent", "submitted", "objection", True),
            ("consent", "accepted", "comment", False),
        ],
    )
    def test_comment_stage_rules(self, workflow, status, kind, allowed):
        assert _comment_allowed(workflow, status, kind) is allowed

    def test_change_op_rejects_unknown_operations(self):
        with pytest.raises(ValueError):
            ChangeOp(op="drop_database", data={})
        assert ChangeOp(op="create_role", data={"name": "x"}).id is None


# ------------------------------------------------------------------ search & overlaps
class TestTextAnalysis:
    def test_stemming_matches_word_families(self):
        assert stem("acquisition") == stem("acquiring") == "acqui"

    def test_stop_words_are_removed(self):
        assert tokenize("Who is responsible for the new customer project?") == ["customer", "project"]

    def test_overlapping_accountabilities_are_found_between_different_roles(self):
        items = [
            {"role_id": "1", "role_name": "A", "kind": "accountability", "text": "Coordinating personnel development and training plans"},
            {"role_id": "2", "role_name": "B", "kind": "accountability", "text": "Coordinating training and personnel development of members"},
            {"role_id": "3", "role_name": "C", "kind": "accountability", "text": "Operating the build pipeline"},
        ]
        found = find_overlaps(items)
        assert len(found) == 1
        assert {found[0]["a"]["role_id"], found[0]["b"]["role_id"]} == {"1", "2"}

    def test_same_domain_in_two_roles_is_a_conflict(self):
        items = [
            {"role_id": "1", "role_name": "A", "kind": "domain", "text": "Product backlog"},
            {"role_id": "2", "role_name": "B", "kind": "domain", "text": "product backlog"},
        ]
        assert find_overlaps(items)[0]["severity"] == "conflict"

    def test_same_role_never_overlaps_itself(self):
        items = [
            {"role_id": "1", "role_name": "A", "kind": "accountability", "text": "Planning milestones for projects"},
            {"role_id": "1", "role_name": "A", "kind": "accountability", "text": "Planning milestones for projects"},
        ]
        assert find_overlaps(items) == []

    def test_jaccard_bounds(self):
        assert jaccard(set(), {"a"}) == 0.0
        assert jaccard({"a"}, {"a"}) == 1.0
        assert stems("customer acquisition") == {"custo", "acqui"}


def _structure():
    circle = {"id": "c1", "parent_id": None, "name": "Root", "purpose": "", "description": "", "accountabilities": [], "domains": [], "policies": []}
    bid = {
        "id": "r1", "circle_id": "c1", "name": "Bid Manager", "purpose": "Win bids", "description": "",
        "accountabilities": [{"text": "Qualifying and acquiring new customer projects (project acquisition)", "detail": None, "level": None}],
        "domains": [{"text": "Bid templates", "detail": None, "level": None}], "authorities": [], "policies": [], "holders": [],
    }
    lead = {
        "id": "r2", "circle_id": "c1", "name": "Lead", "purpose": "Lead", "description": "", "accountabilities": [], "domains": [],
        "authorities": [{"text": "Deciding whether a new customer project is accepted", "detail": None, "level": "decides"}],
        "policies": [], "holders": [{"user_id": "u1", "name": "Anna"}],
    }
    return {"circles": [circle], "roles": [bid, lead]}


class TestResponsibilitySearch:
    def test_phrase_in_accountability_finds_the_role(self):
        hits = rank_roles(_structure(), "project acquisition")
        assert hits[0]["role_name"] == "Bid Manager"
        assert hits[0]["accountabilities"]

    def test_authority_is_reported_separately_from_accountability(self):
        hits = {h["role_name"]: h for h in rank_roles(_structure(), "accept a new customer project")}
        assert hits["Lead"]["decision_authorities"]
        assert not hits["Lead"]["accountabilities"]
        assert hits["Bid Manager"]["decision_authorities"] == []

    def test_empty_query_returns_nothing(self):
        assert query_stems("the of and") == []
        assert rank_roles(_structure(), "the of and") == []


# ------------------------------------------------------------------ assistant
class TestAssistantRouting:
    @pytest.mark.parametrize(
        ("question", "intent"),
        [
            ("Which roles currently have no assigned person?", "unfilled"),
            ("Welche Rollen sind unbesetzt?", "unfilled"),
            ("Which tasks are overdue in my circles?", "overdue"),
            ("Which governance proposals are awaiting a decision?", "proposals"),
            ("What changed in the organization last month?", "changes"),
            ("What responsibilities overlap?", "overlaps"),
            ("Suggest a role that coordinates innovation activities across multiple circles.", "suggest_role"),
            ("Who decides whether a project can be accepted?", "responsibility"),
        ],
    )
    def test_intent_classification(self, question, intent):
        assert classify(question) == intent

    def test_language_detection_prefers_german_signals(self):
        assert detect_lang("Wer ist für die Kundenakquise zuständig?", "en") == "de"
        assert detect_lang("Who owns the roadmap?", "de") == "de"
        assert detect_lang("Who owns the roadmap?", None) == "en"

    def test_role_template_is_a_draft_with_parent_and_overlaps(self):
        s = build_role_template(_structure(), "Suggest a role that coordinates innovation activities across multiple circles", "en")
        assert "Innovation" in s["name"]
        assert s["parent_circle_id"] == "c1"
        assert s["generated_by"] == "template"
        assert s["accountabilities"]


# ------------------------------------------------------------------ goals
class TestGoalMath:
    def test_key_result_progress_is_clamped(self):
        assert kr_progress(Decimal(0), Decimal(100), Decimal(50)) == 0.5
        assert kr_progress(Decimal(0), Decimal(100), Decimal(250)) == 1.0
        assert kr_progress(Decimal(80), Decimal(98), Decimal(91)) == pytest.approx(11 / 18)

    def test_metric_progress_respects_direction(self):
        assert metric_progress("up", Decimal(35), Decimal(28)) == pytest.approx(0.8)
        assert metric_progress("down", Decimal(8), Decimal(10)) == pytest.approx(0.8)
        assert metric_progress("down", Decimal(8), Decimal(0)) == 1.0

    def test_child_objectives_roll_up_into_the_parent(self):
        parent, child = uuid.uuid4(), uuid.uuid4()
        objs = [
            {"id": parent, "parent_id": None, "key_results": [{"progress": 0.2}]},
            {"id": child, "parent_id": parent, "key_results": [{"progress": 1.0}]},
        ]
        rollup(objs)
        assert objs[1]["progress"] == 1.0
        assert objs[0]["progress"] == pytest.approx(0.6)
