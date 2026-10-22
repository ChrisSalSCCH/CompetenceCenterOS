"""Circle Intelligence - deterministic core.

Every answer is derived from the organization's real data. Facts (verified from records) are
kept apart from recommendations (suggestions). Authority is never inferred: accountability,
domain ownership and decision authority are reported separately and ambiguity is stated.
"""

from __future__ import annotations

import re
from typing import Any

from services.analysis import STOP_WORDS, find_overlaps, tokenize
from services.ctx import Ctx
from services.dbx import q
from services.orgdata import history_rows, load_structure
from services.search import rank_roles, search_all

GERMAN_HINT = re.compile(
    r"[äöüß]|\b(wer|welche|welcher|welches|wie|und|für|zuständig|rolle|rollen|aufgaben|unbesetzt|überfällig|verändert|geändert|anträge|kunden|projekt|entscheidet|meine|gibt|nicht)\b",
    re.IGNORECASE,
)

GENERIC_ROLE_WORDS = {
    "coordinate", "coordinates", "coordinating", "coordination", "activities", "activity", "across", "multiple", "circles",
    "circle", "role", "suggest", "manages", "manage", "ensures", "ensure", "helps", "organization", "organisation",
    "company", "teams", "team", "between", "within", "propose", "create", "koordiniert", "aktivitäten", "mehrere",
    "kreise", "schlage", "vor", "rolle", "die", "der", "das",
}


def detect_lang(text: str, hint: str | None) -> str:
    if GERMAN_HINT.search(text):
        return "de"
    return hint if hint in ("de", "en") else "en"


def tr(lang: str, en: str, de: str) -> str:
    return de if lang == "de" else en


def ref(kind: str, ident: Any, label: str, link: str) -> dict[str, Any]:
    return {"type": kind, "id": ident, "label": label, "link": link}


def role_ref(role_id: Any, name: str) -> dict[str, Any]:
    return ref("role", role_id, name, f"/organization/roles/{role_id}")


def circle_ref(circle_id: Any, name: str) -> dict[str, Any]:
    return ref("circle", circle_id, name, f"/organization/circles/{circle_id}")


def _result(intent: str, answer: str, facts: list[str] | None = None, recs: list[str] | None = None,
            refs: list[dict] | None = None, uncertainty: str | None = None, suggestion: dict | None = None) -> dict[str, Any]:
    return {
        "intent": intent,
        "answer": answer,
        "facts": facts or [],
        "recommendations": recs or [],
        "references": refs or [],
        "uncertainty": uncertainty,
        "suggestion": suggestion,
        "mode": "deterministic",
    }


def classify(question: str) -> str:
    s = question.lower()
    if re.search(r"suggest (a |an )?(new )?role|propose (a |an )?(new )?role|schlag\w* .*rolle|neue rolle vor|design a role", s):
        return "suggest_role"
    if re.search(r"overdue|überfällig|ueberfällig|past due|verspätet", s):
        return "overdue"
    if re.search(r"(unfilled|vacant|unassigned|unbesetzt|no (assigned )?(person|holder|one)|without (a )?(person|holder)|ohne (person|besetzung|rolleninhaber)|nicht besetzt)", s) and re.search(r"role|rolle", s):
        return "unfilled"
    if re.search(r"(proposal|anträge|antrag|vorschläge)", s) and re.search(r"(await|pending|waiting|open|offen|entscheid|decision|ausstehend)", s):
        return "proposals"
    if re.search(r"(what|was).*(changed|veränder|geändert)|last (month|week)|letzten? (monat|woche)|recent changes|änderungen", s):
        return "changes"
    if re.search(r"overlap|überschneid|conflict|konflikt|duplicate|doppel", s):
        return "overlaps"
    if re.search(r"\b(my roles|meine rollen|welche rollen habe ich|roles do i)\b", s):
        return "my_roles"
    return "responsibility"


async def answer_question(db, ctx: Ctx, question: str, lang_hint: str | None) -> dict[str, Any]:
    lang = detect_lang(question, lang_hint)
    intent = classify(question)
    structure = await load_structure(db, ctx.org_id)
    handler = {
        "unfilled": _unfilled,
        "overdue": _overdue,
        "proposals": _proposals,
        "changes": _changes,
        "overlaps": _overlaps,
        "my_roles": _my_roles,
        "suggest_role": _suggest_role_answer,
        "responsibility": _responsibility,
    }[intent]
    res = await handler(db, ctx, question, lang, structure)
    res["lang"] = lang
    return res


async def _unfilled(db, ctx, question, lang, structure):
    cname = {c["id"]: c["name"] for c in structure["circles"]}
    empty = [r for r in structure["roles"] if not r["holders"]]
    if not empty:
        return _result("unfilled", tr(lang, "Every role currently has at least one assigned person.", "Jede Rolle hat aktuell mindestens eine zugewiesene Person."))
    facts = [tr(lang, f"{r['name']} ({cname.get(r['circle_id'])}) has no assigned person.", f"{r['name']} ({cname.get(r['circle_id'])}) hat keine zugewiesene Person.") for r in empty]
    return _result(
        "unfilled",
        tr(lang, f"{len(empty)} role(s) have no assigned person.", f"{len(empty)} Rolle(n) haben keine zugewiesene Person."),
        facts,
        [tr(lang, "Check whether the open accountabilities are covered elsewhere, then assign someone or raise a tension.", "Prüfen Sie, ob die offenen Verantwortlichkeiten anderweitig abgedeckt sind, und weisen Sie dann jemanden zu oder erfassen Sie eine Spannung.")],
        [role_ref(r["id"], r["name"]) for r in empty],
    )


async def _overdue(db, ctx, question, lang, structure):
    rows = await q(
        db,
        """SELECT t.id, t.title, t.due_date, u.display_name AS assignee, c.name AS circle_name
           FROM tasks t LEFT JOIN projects p ON p.id = t.project_id LEFT JOIN users u ON u.id = t.assignee_id
           LEFT JOIN circles c ON c.id = COALESCE(t.circle_id, p.circle_id)
           WHERE t.organization_id = :o AND t.deleted_at IS NULL AND t.status <> 'done' AND t.due_date < CURRENT_DATE
             AND (t.assignee_id = :u OR COALESCE(t.circle_id, p.circle_id) IN (
                  SELECT r.circle_id FROM role_assignments ra JOIN roles r ON r.id = ra.role_id WHERE ra.user_id = :u AND ra.deleted_at IS NULL))
           ORDER BY t.due_date""",
        o=ctx.org_id, u=ctx.user_id,
    )
    if not rows:
        return _result("overdue", tr(lang, "No tasks are overdue in your circles.", "In Ihren Kreisen sind keine Aufgaben überfällig."))
    facts = [f"{r['title']} – {r['assignee'] or tr(lang, 'unassigned', 'nicht zugewiesen')} – {tr(lang, 'due', 'fällig')} {r['due_date']} ({r['circle_name'] or '-'})" for r in rows]
    return _result(
        "overdue",
        tr(lang, f"{len(rows)} task(s) are overdue in your circles.", f"{len(rows)} Aufgabe(n) sind in Ihren Kreisen überfällig."),
        facts,
        [tr(lang, "Review them in the next tactical meeting; re-plan or close tasks that are no longer relevant.", "Besprechen Sie sie im nächsten taktischen Meeting; planen Sie neu oder schließen Sie nicht mehr relevante Aufgaben.")],
        [ref("task", r["id"], r["title"], f"/work?task={r['id']}") for r in rows[:10]],
    )


async def _proposals(db, ctx, question, lang, structure):
    rows = await q(
        db,
        """SELECT gp.id, gp.title, gp.status, gp.workflow, c.name AS circle_name FROM governance_proposals gp JOIN circles c ON c.id = gp.circle_id
           WHERE gp.organization_id = :o AND gp.deleted_at IS NULL AND gp.status NOT IN ('draft','accepted','rejected','withdrawn') ORDER BY gp.created_at""",
        o=ctx.org_id,
    )
    if not rows:
        return _result("proposals", tr(lang, "No governance proposals are awaiting a decision.", "Aktuell warten keine Governance-Anträge auf eine Entscheidung."))
    facts = [f"{r['title']} – {r['circle_name']} – {r['workflow']} / {r['status']}" for r in rows]
    return _result(
        "proposals",
        tr(lang, f"{len(rows)} governance proposal(s) are awaiting a decision.", f"{len(rows)} Governance-Anträge warten auf eine Entscheidung."),
        facts,
        refs=[ref("proposal", r["id"], r["title"], f"/governance/proposals/{r['id']}") for r in rows],
    )


async def _changes(db, ctx, question, lang, structure):
    days = 7 if re.search(r"week|woche", question.lower()) else 30
    rows = await history_rows(db, ctx.org_id, "gc.source <> 'seed' AND gc.created_at > NOW() - make_interval(days => :d)", 40, d=days)
    label = tr(lang, "last week", "in der letzten Woche") if days == 7 else tr(lang, "last month", "im letzten Monat")
    if not rows:
        return _result("changes", tr(lang, f"No structural changes were recorded {label}.", f"Es wurden {label} keine Strukturänderungen erfasst."))
    facts = [f"{r['created_at']:%Y-%m-%d}: {r['summary']} ({tr(lang, 'by', 'von')} {r['actor_name'] or '?'}{', ' + r['proposal_title'] if r['proposal_title'] else ''})" for r in rows]
    refs = [ref(r["entity_type"], r["entity_id"], r["summary"], f"/organization/{'roles' if r['entity_type'] == 'role' else 'circles'}/{r['entity_id']}") for r in rows[:10]]
    return _result("changes", tr(lang, f"{len(rows)} governance change(s) {label}.", f"{len(rows)} Governance-Änderung(en) {label}."), facts, refs=refs)


async def _overlaps(db, ctx, question, lang, structure):
    flat = []
    for r in structure["roles"]:
        for key, kind in (("accountabilities", "accountability"), ("domains", "domain"), ("authorities", "decision_authority")):
            for it in r[key]:
                flat.append({"role_id": r["id"], "role_name": r["name"], "kind": kind, "text": it["text"]})
    found = find_overlaps(flat)
    if not found:
        return _result("overlaps", tr(lang, "No overlapping responsibilities were detected by the text analysis.", "Die Textanalyse hat keine überlappenden Verantwortlichkeiten gefunden."),
                       uncertainty=tr(lang, "The check compares wording; semantically similar duties with different words may be missed.", "Die Prüfung vergleicht Formulierungen; inhaltlich ähnliche Aufgaben mit anderen Worten können unentdeckt bleiben."))
    facts = [f"[{o['severity']}] {o['kind']}: {o['a']['role_name']} ↔ {o['b']['role_name']} – “{o['a']['text']}” / “{o['b']['text']}”" for o in found]
    refs: list[dict] = []
    for o in found:
        for side in (o["a"], o["b"]):
            if not any(r["id"] == side["role_id"] for r in refs):
                refs.append(role_ref(side["role_id"], side["role_name"]))
    return _result(
        "overlaps",
        tr(lang, f"{len(found)} possible overlap(s) between roles were found.", f"{len(found)} mögliche Überschneidung(en) zwischen Rollen gefunden."),
        facts,
        [tr(lang, "Clarify ownership in a governance proposal: move or reword one of the accountabilities.", "Klären Sie die Zuständigkeit in einem Governance-Antrag: verschieben oder formulieren Sie eine der Verantwortlichkeiten um.")],
        refs,
        tr(lang, "Similarity is detected from wording only; whether it is a real conflict is a governance decision.", "Ähnlichkeit wird nur aus der Formulierung erkannt; ob ein echter Konflikt vorliegt, ist eine Governance-Entscheidung."),
    )


async def _my_roles(db, ctx, question, lang, structure):
    cname = {c["id"]: c["name"] for c in structure["circles"]}
    mine = [r for r in structure["roles"] if any(h["user_id"] == ctx.user_id for h in r["holders"])]
    if not mine:
        return _result("my_roles", tr(lang, "You do not currently hold any role.", "Sie haben aktuell keine Rolle."))
    return _result(
        "my_roles",
        tr(lang, f"You hold {len(mine)} role(s).", f"Sie haben {len(mine)} Rolle(n)."),
        [f"{r['name']} ({cname.get(r['circle_id'])}): {r['purpose']}" for r in mine],
        refs=[role_ref(r["id"], r["name"]) for r in mine],
    )


async def _responsibility(db, ctx, question, lang, structure):
    roles = rank_roles(structure, question, limit=5)
    others = [h for h in await search_all(db, ctx.org_id, question, {"circle", "project", "proposal"}, 5)]
    if not roles and not others:
        return _result(
            "responsibility",
            tr(lang, "I found nothing in the organization's records that matches this question.", "In den Organisationsdaten wurde nichts gefunden, das zu dieser Frage passt."),
            uncertainty=tr(lang, "No role, accountability, domain or policy matches. Nobody is explicitly responsible according to the records - consider raising a tension.", "Keine Rolle, Verantwortlichkeit, Domäne oder Richtlinie passt. Laut Datenlage ist niemand ausdrücklich zuständig – erwägen Sie eine Spannung."),
        )
    facts: list[str] = []
    refs: list[dict] = []
    authority_roles = [r for r in roles if r["decision_authorities"]]
    for r in roles:
        holders = ", ".join(h["name"] for h in r["holders"]) or tr(lang, "unfilled", "unbesetzt")
        parts = [f"{r['role_name']} ({r['circle_name']}; {holders})"]
        if r["accountabilities"]:
            parts.append(tr(lang, "Accountable for: ", "Verantwortlich für: ") + "; ".join(r["accountabilities"]))
        if r["domains"]:
            parts.append(tr(lang, "Owns domain: ", "Besitzt Domäne: ") + "; ".join(r["domains"]))
        if r["decision_authorities"]:
            parts.append(tr(lang, "Explicit decision authority: ", "Explizite Entscheidungsbefugnis: ") + "; ".join(r["decision_authorities"]))
        facts.append(" – ".join(parts))
        refs.append(role_ref(r["role_id"], r["role_name"]))
    for h in others:
        refs.append(ref(h["type"], h["id"], h["title"], h["link"]))
    uncertainty = None
    decision_q = re.search(r"decid|entscheid|approve|genehmig|accept|annehmen|authority|befugnis", question.lower())
    if decision_q and not authority_roles:
        uncertainty = tr(lang, "No role has an explicit decision authority matching this question. The roles above are accountable or related, but accountability is not decision authority - the decision right is ambiguous. Raise a tension or governance proposal to define it.", "Keine Rolle hat eine ausdrückliche passende Entscheidungsbefugnis. Die genannten Rollen sind verantwortlich oder verwandt, aber Verantwortung ist keine Entscheidungsbefugnis – das Entscheidungsrecht ist unklar. Erfassen Sie eine Spannung oder einen Governance-Antrag, um es zu definieren.")
    elif len(authority_roles) > 1:
        uncertainty = tr(lang, "More than one role has a matching decision authority; the records do not say which one prevails.", "Mehr als eine Rolle hat eine passende Entscheidungsbefugnis; die Daten sagen nicht, welche Vorrang hat.")
    elif not decision_q and len(roles) > 1:
        uncertainty = tr(lang, "Several roles are related to this topic; check their accountabilities for the exact scope.", "Mehrere Rollen haben mit diesem Thema zu tun; prüfen Sie deren Verantwortlichkeiten für den genauen Umfang.")
    top = roles[0] if roles else None
    if top:
        answer = tr(lang, f"Most relevant: {top['role_name']} in {top['circle_name']}. Matches are listed separately as accountability, domain and decision authority.", f"Am relevantesten: {top['role_name']} in {top['circle_name']}. Treffer sind getrennt nach Verantwortlichkeit, Domäne und Entscheidungsbefugnis aufgeführt.")
    else:
        answer = tr(lang, "No role matches, but related records were found.", "Keine Rolle passt, aber verwandte Einträge wurden gefunden.")
    return _result("responsibility", answer, facts, refs=refs, uncertainty=uncertainty)


# ---------------------------------------------------------------- role suggestion


def build_role_template(structure: dict[str, list[dict]], text: str, lang: str) -> dict[str, Any]:
    tokens = [t for t in tokenize(text) if t not in GENERIC_ROLE_WORDS and t not in STOP_WORDS]
    key = tokens[:2]
    base = " ".join(w.capitalize() for w in key) or tr(lang, "Coordination", "Koordination")
    topic = " ".join(key) or tr(lang, "cross-circle topics", "kreisübergreifende Themen")
    cross = bool(re.search(r"across|multiple|several|cross|mehrere|übergreifend|über .*kreise", text.lower()))
    overlaps = rank_roles(structure, " ".join(key), limit=4) if key else []
    circles = {c["id"]: c for c in structure["circles"]}
    root = next((c for c in structure["circles"] if c["parent_id"] is None), None)
    parent = root
    if not cross and overlaps:
        parent = circles.get(overlaps[0]["circle_id"], root)
    return {
        "name": f"{base} {tr(lang, 'Catalyst' if 'innov' in topic else 'Coordinator', 'Katalysator' if 'innov' in topic else 'Koordination')}",
        "purpose": tr(lang, f"{base.capitalize()} efforts are visible, connected and moving forward across the organization.", f"{base}-Aktivitäten sind sichtbar, vernetzt und kommen organisationsweit voran."),
        "accountabilities": [
            tr(lang, f"Maintaining an overview of {topic} activities across circles", f"Pflegen einer Übersicht über {topic}-Aktivitäten über Kreise hinweg"),
            tr(lang, f"Connecting people and roles who work on {topic}", f"Vernetzen von Personen und Rollen, die an {topic} arbeiten"),
            tr(lang, f"Facilitating regular exchange and surfacing shared opportunities for {topic}", f"Moderieren des regelmäßigen Austauschs und Aufzeigen gemeinsamer Chancen für {topic}"),
        ],
        "domains": [tr(lang, f"{base} coordination backlog", f"{base}-Koordinationsbacklog")],
        "parent_circle_id": parent["id"] if parent else None,
        "parent_circle_name": parent["name"] if parent else None,
        "overlaps": [{"role_id": o["role_id"], "role_name": o["role_name"], "circle_name": o["circle_name"], "matching": (o["accountabilities"] + o["domains"])[:3]} for o in overlaps],
        "generated_by": "template",
    }


async def _suggest_role_answer(db, ctx, question, lang, structure):
    s = build_role_template(structure, question, lang)
    facts = [tr(lang, f"Existing related role: {o['role_name']} ({o['circle_name']})", f"Bestehende verwandte Rolle: {o['role_name']} ({o['circle_name']})") for o in s["overlaps"]]
    refs = [role_ref(o["role_id"], o["role_name"]) for o in s["overlaps"]]
    return _result(
        "suggest_role",
        tr(lang, f"Draft role proposal: “{s['name']}”. This is a recommendation only - nothing has been changed.", f"Entwurf für eine Rolle: „{s['name']}“. Das ist nur eine Empfehlung – es wurde nichts verändert."),
        facts,
        [tr(lang, "Review the draft, check the overlaps and submit it as a governance proposal.", "Prüfen Sie den Entwurf und die Überschneidungen und reichen Sie ihn als Governance-Antrag ein.")],
        refs,
        tr(lang, "Names, accountabilities and domains are generated from templates and your wording; they are suggestions, not verified facts.", "Namen, Verantwortlichkeiten und Domänen werden aus Vorlagen und Ihrer Formulierung erzeugt; sie sind Vorschläge, keine geprüften Fakten."),
        s,
    )
