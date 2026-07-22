"""
LLM layer — Gemini + 규칙 기반 폴백.

핵심 원칙: API 키가 없어도 전체 시스템이 동작한다.
GEMINI_API_KEY가 있으면 진짜 추론(Gemini), 없으면 규칙 기반 엔진으로 대체한다.
"""
from __future__ import annotations

import os
import json
import httpx

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_GEMINI = os.getenv("THINKOS_GEMINI_MODEL", "gemini-2.5-flash")


def provider() -> str | None:
    return "gemini" if os.getenv("GEMINI_API_KEY") else None


def has_key() -> bool:
    return provider() is not None


async def complete(system: str, user: str, *, max_tokens: int = 900,
                   model: str | None = None) -> str:
    """Gemini 호출. 오류는 그대로 raise해 상위에서 규칙 기반으로 폴백하게 한다."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("no_api_key")
    url = GEMINI_URL.format(model=model or DEFAULT_GEMINI)
    body = {
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7},
    }
    if (system or "").strip():   # 빈 systemInstruction은 Gemini가 거부할 수 있어 생략
        body["systemInstruction"] = {"parts": [{"text": system}]}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, params={"key": key},
                              headers={"content-type": "application/json"}, json=body)
        if r.status_code >= 400:  # 업스트림 오류를 그대로 드러냄
            raise RuntimeError(f"gemini {r.status_code}: {r.text[:300]}")
        data = r.json()
    cands = data.get("candidates", [])
    parts = cands[0]["content"]["parts"] if cands else []
    return "".join(x.get("text", "") for x in parts).strip()


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
