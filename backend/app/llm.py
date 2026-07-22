"""
LLM layer — Claude Messages API with a graceful rule-based fallback.

핵심 원칙: API 키가 없어도 전체 시스템이 동작해야 한다.
키가 있으면 진짜 추론(Claude), 없으면 규칙 기반 엔진으로 대체한다.
"""
from __future__ import annotations

import os
import json
import httpx

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = os.getenv("THINKOS_MODEL", "claude-sonnet-5")


def has_key() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


async def complete(system: str, user: str, *, max_tokens: int = 900,
                   model: str | None = None) -> str:
    """Call Claude. Raises on transport/API error so callers can fall back."""
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("no_api_key")
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": model or DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(ANTHROPIC_URL, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    return "".join(b.get("text", "") for b in data.get("content", [])).strip()


async def complete_json(system: str, user: str, *, max_tokens: int = 900,
                        model: str | None = None) -> dict:
    """Call Claude and parse a JSON object out of the reply."""
    raw = await complete(system + "\n\n반드시 유효한 JSON 객체만 출력하라.",
                         user, max_tokens=max_tokens, model=model)
    # tolerate ```json fences
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    return json.loads(raw)
