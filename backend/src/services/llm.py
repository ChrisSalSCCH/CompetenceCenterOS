"""Provider-independent LLM access.

Any OpenAI-compatible `/chat/completions` endpoint works: hosted providers, vLLM/Ollama/LiteLLM
gateways or internal on-premise services. Calls happen server-side only; the API key is stored
encrypted and never returned to the browser. When no provider is configured the application
falls back to deterministic answers (see services/assistant.py).

Future: MCP tools and governed AI agents can plug in behind `LlmProvider`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from services.dbx import q1
from services.secrets import decrypt


@dataclass(frozen=True)
class LlmProvider:
    name: str
    base_url: str
    model: str
    api_key: str | None


async def load_provider(db, org_id: UUID) -> LlmProvider | None:
    row = await q1(db, "SELECT * FROM ai_provider_configs WHERE organization_id = :o", o=org_id)
    if not row or not row["enabled"] or not row["base_url"] or not row["model"]:
        return None
    return LlmProvider(row["name"], row["base_url"].rstrip("/"), row["model"], decrypt(row["api_key_encrypted"]))


async def chat(provider: LlmProvider, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
    headers = {"Content-Type": "application/json"}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"
    payload: dict[str, Any] = {"model": provider.model, "messages": messages, "temperature": temperature}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
            res = await client.post(f"{provider.base_url}/chat/completions", headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"The AI provider could not be reached ({type(exc).__name__}).") from exc
    if res.status_code >= 400:
        raise RuntimeError(f"The AI provider answered with HTTP {res.status_code}.")
    try:
        return str(res.json()["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, ValueError) as exc:
        raise RuntimeError("The AI provider returned an unexpected response format.") from exc


def parse_json_block(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from an LLM reply (tolerates code fences)."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None
