"""
LLM layer — 멀티 프로바이더(Claude / Gemini) + 규칙 기반 폴백.

핵심 원칙: API 키가 없어도 전체 시스템이 동작한다.
키가 있으면 진짜 추론, 없으면 규칙 기반 엔진으로 대체한다.

프로바이더 선택:
  ANTHROPIC_API_KEY → Claude,  GEMINI_API_KEY → Gemini.
  둘 다 있으면 THINKOS_PROVIDER(claude|gemini)로 결정, 없으면 Claude 우선.
"""
from __future__ import annotations

import os
import json
import httpx

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_CLAUDE = os.getenv("THINKOS_MODEL", "claude-sonnet-5")
DEFAULT_GEMINI = os.getenv("THINKOS_GEMINI_MODEL", "gemini-2.5-flash")


def provider() -> str | None:
    """활성 프로바이더 결정 (키 존재 + THINKOS_PROVIDER)."""
    a, g = os.getenv("ANTHROPIC_API_KEY"), os.getenv("GEMINI_API_KEY")
    pref = os.getenv("THINKOS_PROVIDER", "").lower()
    if pref == "gemini" and g:
        return "gemini"
    if pref == "claude" and a:
        return "claude"
    if a:
        return "claude"
    if g:
        return "gemini"
    return None


def has_key() -> bool:
    return provider() is not None


async def complete(system: str, user: str, *, max_tokens: int = 900,
                   model: str | None = None) -> str:
    """활성 프로바이더로 호출. 오류는 그대로 raise해 상위에서 폴백하게 한다."""
    p = provider()
    if p is None:
        raise RuntimeError("no_api_key")
    async with httpx.AsyncClient(timeout=60) as client:
        if p == "gemini":
            key = os.getenv("GEMINI_API_KEY")
            url = GEMINI_URL.format(model=model or DEFAULT_GEMINI)
            body = {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7},
            }
            r = await client.post(url, params={"key": key},
                                  headers={"content-type": "application/json"}, json=body)
            r.raise_for_status()
            data = r.json()
            cands = data.get("candidates", [])
            parts = cands[0]["content"]["parts"] if cands else []
            return "".join(x.get("text", "") for x in parts).strip()
        # claude
        key = os.getenv("ANTHROPIC_API_KEY")
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        body = {"model": model or DEFAULT_CLAUDE, "max_tokens": max_tokens,
                "system": system, "messages": [{"role": "user", "content": user}]}
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
