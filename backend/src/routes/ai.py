"""Circle Intelligence: grounded Q&A, role suggestions, provider configuration.

The assistant NEVER writes governance records. It returns drafts which a user can turn into
a normal governance proposal.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from limiter import limiter
from pydantic import BaseModel, Field
from services.assistant import answer_question, build_role_template, detect_lang, tr
from services.ctx import CtxDep, require_admin
from services.dbx import DbDep, err, q1, x
from services.events import audit
from services.llm import LlmProvider, chat, load_provider, parse_json_block
from services.orgdata import load_structure
from services.secrets import decrypt, encrypt

router = APIRouter(prefix="/api", tags=["ai"])


class AskBody(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    lang: str | None = Field(default=None, max_length=2)


class SuggestBody(BaseModel):
    brief: str = Field(min_length=5, max_length=1000)
    lang: str | None = Field(default=None, max_length=2)


class ProviderBody(BaseModel):
    name: str = Field(default="Custom provider", max_length=80)
    base_url: str = Field(default="", max_length=300)
    model: str = Field(default="", max_length=120)
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool = False


def _compact_context(structure: dict[str, list[dict]], limit: int = 14000) -> str:
    cname = {c["id"]: c["name"] for c in structure["circles"]}
    lines: list[str] = []
    for c in structure["circles"]:
        lines.append(f"CIRCLE {c['name']} | purpose: {c['purpose']}")
    for r in structure["roles"]:
        holders = ", ".join(h["name"] for h in r["holders"]) or "UNFILLED"
        acc = "; ".join(i["text"] for i in r["accountabilities"])
        dom = "; ".join(i["text"] for i in r["domains"])
        aut = "; ".join(i["text"] for i in r["authorities"])
        lines.append(f"ROLE {r['name']} (circle {cname.get(r['circle_id'])}) holders: {holders} | purpose: {r['purpose']} | accountabilities: {acc} | domains: {dom} | decision authorities: {aut}")
    return "\n".join(lines)[:limit]


@router.post("/ai/ask", summary="Ask Circle Intelligence a question about the organization")
@limiter.limit("30/minute")
async def ask(request: Request, body: AskBody, ctx: CtxDep, db: DbDep) -> dict:
    result = await answer_question(db, ctx, body.question, body.lang)
    provider = await load_provider(db, ctx.org_id)
    result["llm_available"] = provider is not None
    if provider is not None and result["intent"] != "suggest_role":
        structure = await load_structure(db, ctx.org_id)
        lang = result["lang"]
        system = (
            "You are Circle Intelligence, an assistant for a self-organizing organization. Answer ONLY using the organization data and verified facts "
            "provided. Never invent roles, responsibilities or decision authorities. Distinguish accountability, domain ownership and decision authority. "
            "If authority is ambiguous or data is missing, say so explicitly. Separate verified facts from recommendations. "
            f"Answer in {'German' if lang == 'de' else 'English'}, concisely, in plain text."
        )
        user = (
            f"Organization data:\n{_compact_context(structure)}\n\nVerified facts from records:\n" + "\n".join(f"- {f}" for f in result["facts"])
            + f"\n\nQuestion: {body.question}"
        )
        try:
            text = await chat(provider, [{"role": "system", "content": system}, {"role": "user", "content": user}])
            result["answer"] = text
            result["mode"] = "llm"
        except RuntimeError as exc:
            result["llm_error"] = str(exc)
    await audit(db, ctx, "ai.ask", "ai", None, body.question[:200], {"intent": result["intent"], "mode": result["mode"]})
    await db.commit()
    return result


@router.post("/ai/suggest-role", summary="Generate a structured role proposal draft (never applied automatically)")
@limiter.limit("20/minute")
async def suggest_role(request: Request, body: SuggestBody, ctx: CtxDep, db: DbDep) -> dict:
    structure = await load_structure(db, ctx.org_id)
    lang = detect_lang(body.brief, body.lang)
    suggestion = build_role_template(structure, body.brief, lang)
    provider = await load_provider(db, ctx.org_id)
    note: str | None = None
    if provider is not None:
        try:
            suggestion = await _llm_role(provider, structure, body.brief, lang, suggestion)
        except RuntimeError as exc:
            note = str(exc)
    await audit(db, ctx, "ai.suggest_role", "ai", None, body.brief[:200], {"generated_by": suggestion["generated_by"]})
    await db.commit()
    return {
        "suggestion": suggestion,
        "disclaimer": tr(lang, "AI-generated draft. It has not been applied; submit it as a governance proposal to make it effective.", "KI-generierter Entwurf. Er wurde nicht angewendet; reichen Sie ihn als Governance-Antrag ein, damit er wirksam wird."),
        "llm_error": note,
        "lang": lang,
    }


async def _llm_role(provider: LlmProvider, structure: dict, brief: str, lang: str, base: dict[str, Any]) -> dict[str, Any]:
    system = (
        "You design roles for self-organizing organizations (Holacracy/Sociocracy style). Reply ONLY with a JSON object: "
        '{"name": str, "purpose": str, "accountabilities": [str], "domains": [str]}. Accountabilities are ongoing activities starting with a gerund. '
        f"Write in {'German' if lang == 'de' else 'English'}. Avoid duplicating the existing roles listed."
    )
    text = await chat(provider, [{"role": "system", "content": system}, {"role": "user", "content": f"Existing organization:\n{_compact_context(structure, 9000)}\n\nRequest: {brief}"}], temperature=0.4)
    data = parse_json_block(text)
    if not data or not isinstance(data.get("name"), str):
        raise RuntimeError("The AI provider did not return a usable role draft; showing the template draft instead.")
    merged = dict(base)
    merged.update(
        name=str(data["name"])[:120],
        purpose=str(data.get("purpose", base["purpose"]))[:2000],
        accountabilities=[str(a)[:600] for a in (data.get("accountabilities") or base["accountabilities"])][:12],
        domains=[str(d)[:600] for d in (data.get("domains") or [])][:8],
        generated_by="llm",
    )
    return merged


# ------------------------------------------------------------ provider settings


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise err(422, "URL_INVALID", "The API endpoint must be an http(s) URL such as https://api.openai.com/v1.", "base_url")


@router.get("/admin/ai", summary="AI provider configuration (credential is never returned)")
async def get_ai_config(ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    row = await q1(db, "SELECT name, base_url, model, enabled, api_key_encrypted FROM ai_provider_configs WHERE organization_id = :o", o=ctx.org_id)
    if row is None:
        return {"name": "", "base_url": "", "model": "", "enabled": False, "has_key": False}
    return {"name": row["name"], "base_url": row["base_url"], "model": row["model"], "enabled": row["enabled"], "has_key": bool(row["api_key_encrypted"])}


@router.put("/admin/ai", summary="Configure the OpenAI-compatible LLM provider")
async def put_ai_config(body: ProviderBody, ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    if body.base_url:
        _validate_url(body.base_url)
    if body.enabled and not (body.base_url and body.model):
        raise err(422, "PROVIDER_INCOMPLETE", "Endpoint and model are required to enable the provider.")
    existing = await q1(db, "SELECT api_key_encrypted FROM ai_provider_configs WHERE organization_id = :o", o=ctx.org_id)
    key_enc = encrypt(body.api_key) if body.api_key else (existing["api_key_encrypted"] if existing else None)
    await x(
        db,
        """INSERT INTO ai_provider_configs (organization_id, name, base_url, model, api_key_encrypted, enabled, created_by, updated_by)
           VALUES (:o, :n, :b, :m, :k, :e, :u, :u)
           ON CONFLICT (organization_id) DO UPDATE SET name = :n, base_url = :b, model = :m, api_key_encrypted = :k, enabled = :e,
             updated_at = NOW(), updated_by = :u""",
        o=ctx.org_id, n=body.name, b=body.base_url.rstrip("/"), m=body.model, k=key_enc, e=body.enabled, u=ctx.user_id,
    )
    await audit(db, ctx, "ai.configured", "ai", None, f"AI provider {'enabled' if body.enabled else 'disabled'}: {body.model or '-'}")
    await db.commit()
    return {"ok": True}


@router.post("/admin/ai/test", summary="Send a test prompt to the configured provider")
async def test_ai(ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    row = await q1(db, "SELECT name, base_url, model, api_key_encrypted FROM ai_provider_configs WHERE organization_id = :o", o=ctx.org_id)
    if not row or not row["base_url"] or not row["model"]:
        raise err(409, "PROVIDER_NOT_CONFIGURED", "Configure endpoint and model first.")
    provider = LlmProvider(row["name"], row["base_url"].rstrip("/"), row["model"], decrypt(row["api_key_encrypted"]))
    try:
        reply = await chat(provider, [{"role": "user", "content": "Reply with the single word: ready"}], temperature=0)
    except RuntimeError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": reply[:200]}


@router.get("/ai/capabilities", summary="What the assistant can do right now (MCP-ready metadata)")
async def capabilities(ctx: CtxDep, db: DbDep) -> dict:
    provider = await load_provider(db, ctx.org_id)
    tools = [
        {"name": "search_organization", "description": "Ranked search across circles, roles, people, responsibilities", "writes": False},
        {"name": "find_responsible_roles", "description": "Separates accountability, domain and decision authority", "writes": False},
        {"name": "list_unfilled_roles", "description": "Roles without role holders", "writes": False},
        {"name": "suggest_role", "description": "Draft role proposal (user must submit it)", "writes": False},
    ]
    return {"llm_configured": provider is not None, "deterministic": True, "tools": tools, "mcp": "planned", "agents": "planned", "semantic_search": "planned"}

