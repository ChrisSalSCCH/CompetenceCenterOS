"""Pure, dependency-free text helpers shared by search, AI and conflict detection."""

from __future__ import annotations

import re
from typing import Any

STOP_WORDS = {
    # English
    "a", "an", "the", "of", "to", "for", "and", "or", "in", "on", "at", "is", "are", "be", "we",
    "who", "what", "which", "whether", "how", "do", "does", "our", "my", "by", "with", "that", "this",
    "new", "can", "should", "has", "have", "it", "if", "from", "as", "responsible", "decides",
    "deciding", "decide", "currently", "there", "any", "all", "me", "i", "you", "roles", "role",
    "ask", "about", "tell", "show", "list",
    # German
    "der", "die", "das", "den", "dem", "ein", "eine", "einen", "und", "oder", "von", "zu", "für",
    "ist", "sind", "wer", "was", "welche", "wie", "wir", "unsere", "ob", "mit", "im", "in", "auf",
    "neue", "neuen", "neues", "entscheidet", "zuständig", "verantwortlich", "rolle", "rollen", "gibt",
    "es", "hat", "haben", "zeige", "zeig", "mir", "meine", "mein",
}

_WORD = re.compile(r"[A-Za-zÄÖÜäöüß0-9]+")


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for w in _WORD.findall(text or ""):
        lw = w.lower()
        if len(lw) > 1 and lw not in STOP_WORDS:
            out.append(lw)
    return out


def stem(word: str) -> str:
    """Cheap prefix stemmer: good enough to match acquire/acquiring/acquisition."""
    n = len(word)
    if n <= 4:
        return word
    if n <= 6:
        return word[: n - 1]
    return word[:5]


def stems(text: str) -> set[str]:
    return {stem(t) for t in tokenize(text)}


def match_count(query_stems: list[str], text: str | None) -> int:
    """How many query stems occur (as substrings) in the text."""
    if not text:
        return 0
    low = text.lower()
    return sum(1 for s in query_stems if s in low)


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_overlaps(items: list[dict[str, Any]], threshold: float = 0.5) -> list[dict[str, Any]]:
    """Detect overlapping responsibilities between DIFFERENT roles.

    items: dicts with role_id, role_name, kind, text. Domains are compared case-insensitively
    for exact equality (two roles owning the same domain is a hard conflict); accountabilities
    and decision authorities use token-overlap similarity.
    """
    found: list[dict[str, Any]] = []
    comparable = [i for i in items if i["kind"] in ("accountability", "domain", "decision_authority")]
    prepared = [(i, stems(i["text"]), i["text"].strip().lower()) for i in comparable]
    for idx, (a, sa, ta) in enumerate(prepared):
        for b, sb, tb in prepared[idx + 1 :]:
            if a["role_id"] == b["role_id"] or a["kind"] != b["kind"]:
                continue
            if a["kind"] == "domain":
                if ta == tb:
                    found.append(_overlap(a, b, 1.0, "conflict"))
                continue
            shared = sa & sb
            sim = jaccard(sa, sb)
            if len(shared) >= 2 and sim >= threshold:
                severity = "conflict" if a["kind"] == "decision_authority" else "overlap"
                found.append(_overlap(a, b, sim, severity))
    return found


def _overlap(a: dict[str, Any], b: dict[str, Any], sim: float, severity: str) -> dict[str, Any]:
    return {
        "kind": a["kind"],
        "severity": severity,
        "similarity": round(sim, 2),
        "a": {"role_id": a["role_id"], "role_name": a["role_name"], "text": a["text"]},
        "b": {"role_id": b["role_id"], "role_name": b["role_name"], "text": b["text"]},
    }
