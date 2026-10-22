"""Deterministic, explainable organization search (no LLM required)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from services.analysis import match_count, tokenize, stem
from services.dbx import q
from services.orgdata import load_structure

KIND_LABEL = {
    "accountability": "Accountability",
    "domain": "Domain",
    "policy": "Policy",
    "decision_authority": "Decision authority",
}


def query_stems(query: str) -> list[str]:
    seen: list[str] = []
    for t in tokenize(query):
        s = stem(t)
        if s not in seen:
            seen.append(s)
    return seen


def _score(stems_: list[str], fields: list[tuple[str, str | None, int]]) -> tuple[float, list[dict[str, Any]]]:
    """fields: (label, text, weight). Returns total score and the matched field excerpts."""
    total = 0.0
    matched: list[dict[str, Any]] = []
    covered: set[str] = set()
    for label, text, weight in fields:
        n = match_count(stems_, text)
        if n:
            total += weight * n
            matched.append({"field": label, "text": (text or "")[:220]})
            covered.update(s for s in stems_ if text and s in text.lower())
    if stems_ and len(covered) == len(stems_) and len(stems_) > 1:
        total *= 1.5
    return total, matched


def rank_roles(structure: dict[str, list[dict]], query: str, limit: int = 8) -> list[dict[str, Any]]:
    """Find roles responsible for something, separating accountability, domain and authority."""
    stems_ = query_stems(query)
    if not stems_:
        return []
    cname = {c["id"]: c["name"] for c in structure["circles"]}
    out: list[dict[str, Any]] = []
    for r in structure["roles"]:
        fields: list[tuple[str, str | None, int]] = [("name", r["name"], 10), ("purpose", r["purpose"], 4), ("description", r["description"], 2)]
        fields += [("accountability", i["text"], 6) for i in r["accountabilities"]]
        fields += [("domain", i["text"], 6) for i in r["domains"]]
        fields += [("decision_authority", i["text"], 6) for i in r["authorities"]]
        fields += [("policy", i["text"], 4) for i in r["policies"]]
        score, matched = _score(stems_, fields)
        if score <= 0:
            continue
        by_kind: dict[str, list[str]] = {}
        for m in matched:
            by_kind.setdefault(m["field"], []).append(m["text"])
        out.append(
            {
                "role_id": r["id"],
                "role_name": r["name"],
                "circle_id": r["circle_id"],
                "circle_name": cname.get(r["circle_id"]),
                "score": round(score, 1),
                "holders": [{"user_id": h["user_id"], "name": h["name"]} for h in r["holders"]],
                "purpose": r["purpose"],
                "accountabilities": by_kind.get("accountability", []),
                "domains": by_kind.get("domain", []),
                "decision_authorities": by_kind.get("decision_authority", []),
                "policies": by_kind.get("policy", []),
                "matched_purpose": "purpose" in by_kind,
            }
        )
    out.sort(key=lambda x: -x["score"])
    return out[:limit]


async def search_all(db, org_id: UUID, query: str, types: set[str] | None = None, limit: int = 40) -> list[dict[str, Any]]:
    stems_ = query_stems(query)
    if not stems_:
        return []

    def wanted(t: str) -> bool:
        return not types or t in types

    results: list[dict[str, Any]] = []
    structure = await load_structure(db, org_id)
    cname = {c["id"]: c["name"] for c in structure["circles"]}

    if wanted("circle"):
        for c in structure["circles"]:
            fields = [("name", c["name"], 10), ("purpose", c["purpose"], 4), ("description", c["description"], 2)]
            fields += [("accountability", i["text"], 6) for i in c["accountabilities"]]
            fields += [("domain", i["text"], 6) for i in c["domains"]]
            fields += [("policy", i["text"], 5) for i in c["policies"]]
            score, matched = _score(stems_, fields)
            if score > 0:
                results.append(_hit("circle", c["id"], c["name"], "Circle", matched, score, f"/organization/circles/{c['id']}"))
    if wanted("role"):
        for r in rank_roles(structure, query, limit=limit):
            role = next(x for x in structure["roles"] if x["id"] == r["role_id"])
            fields = [("name", role["name"], 10), ("purpose", role["purpose"], 4)]
            fields += [("accountability", i["text"], 6) for i in role["accountabilities"]]
            fields += [("domain", i["text"], 6) for i in role["domains"]]
            fields += [("decision_authority", i["text"], 6) for i in role["authorities"]]
            fields += [("policy", i["text"], 4) for i in role["policies"]]
            _, matched = _score(stems_, fields)
            holders = ", ".join(h["name"] for h in role["holders"]) or "unfilled"
            results.append(_hit("role", r["role_id"], r["role_name"], f"{r['circle_name']} · {holders}", matched, r["score"], f"/organization/roles/{r['role_id']}"))
    if wanted("person"):
        for p in await q(
            db,
            """SELECT u.id, u.display_name, u.email, m.job_title, m.skills FROM memberships m
               JOIN users u ON u.id = m.user_id WHERE m.organization_id = :o AND m.active""",
            o=org_id,
        ):
            fields = [("name", p["display_name"], 10), ("email", p["email"], 3), ("title", p["job_title"], 4), ("skills", " ".join(p["skills"] or []), 5)]
            score, matched = _score(stems_, fields)
            if score > 0:
                results.append(_hit("person", p["id"], p["display_name"] or p["email"], p["job_title"] or "Person", matched, score, f"/people/{p['id']}"))
    if wanted("proposal"):
        for p in await q(db, "SELECT id, title, description, reason, status, circle_id FROM governance_proposals WHERE organization_id = :o AND deleted_at IS NULL", o=org_id):
            score, matched = _score(stems_, [("title", p["title"], 8), ("description", p["description"], 3), ("reason", p["reason"], 2)])
            if score > 0:
                results.append(_hit("proposal", p["id"], p["title"], f"Proposal · {p['status']} · {cname.get(p['circle_id'], '')}", matched, score, f"/governance/proposals/{p['id']}"))
    if wanted("project"):
        for p in await q(db, "SELECT id, name, description, status FROM projects WHERE organization_id = :o AND deleted_at IS NULL", o=org_id):
            score, matched = _score(stems_, [("name", p["name"], 8), ("description", p["description"], 3)])
            if score > 0:
                results.append(_hit("project", p["id"], p["name"], f"Project · {p['status']}", matched, score, f"/work?tab=projects&project={p['id']}"))
    if wanted("task"):
        for t in await q(db, "SELECT id, title, description, status FROM tasks WHERE organization_id = :o AND deleted_at IS NULL", o=org_id):
            score, matched = _score(stems_, [("title", t["title"], 8), ("description", t["description"], 3)])
            if score > 0:
                results.append(_hit("task", t["id"], t["title"], f"Task · {t['status']}", matched, score, f"/work?task={t['id']}"))
    if wanted("meeting"):
        for m in await q(db, "SELECT id, title, notes, meeting_type FROM meetings WHERE organization_id = :o AND deleted_at IS NULL", o=org_id):
            score, matched = _score(stems_, [("title", m["title"], 8), ("notes", m["notes"], 2)])
            if score > 0:
                results.append(_hit("meeting", m["id"], m["title"], f"Meeting · {m['meeting_type']}", matched, score, f"/meetings/{m['id']}"))
    if wanted("tension"):
        for t in await q(db, "SELECT id, title, description, status FROM tensions WHERE organization_id = :o AND deleted_at IS NULL", o=org_id):
            score, matched = _score(stems_, [("title", t["title"], 8), ("description", t["description"], 3)])
            if score > 0:
                results.append(_hit("tension", t["id"], t["title"], f"Tension · {t['status']}", matched, score, "/governance?tab=tensions"))
    results.sort(key=lambda r: -r["score"])
    return results[:limit]


def _hit(kind: str, ident: UUID, title: str, subtitle: str, matched: list[dict], score: float, link: str) -> dict[str, Any]:
    snippet = next((m for m in matched if m["field"] not in ("name", "title")), matched[0] if matched else None)
    return {
        "type": kind,
        "id": ident,
        "title": title,
        "subtitle": subtitle,
        "snippet": snippet,
        "score": round(score, 1),
        "link": link,
    }
