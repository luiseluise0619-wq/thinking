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
MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_GEMINI = os.getenv("THINKOS_GEMINI_MODEL", "gemini-flash-latest")
_RESOLVED: dict = {}   # 마지막으로 성공한 모델 캐시


def _best_model(models: list[str]) -> str | None:
    bad = ("vision", "image", "tts", "embedding", "aqa", "thinking", "live")
    flash = [m for m in models if "flash" in m and not any(b in m for b in bad)]
    pool = flash or [m for m in models if not any(b in m for b in bad)] or models
    latest = [m for m in pool if m.endswith("-latest")]
    return (latest or pool)[0] if pool else None


async def _list_models(client, key: str) -> list[str]:
    r = await client.get(MODELS_URL, params={"key": key})
    r.raise_for_status()
    return [m["name"].split("/")[-1] for m in r.json().get("models", [])
            if "generateContent" in (m.get("supportedGenerationMethods") or [])]


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
    body = {
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7},
    }
    if (system or "").strip():   # 빈 systemInstruction은 Gemini가 거부할 수 있어 생략
        body["systemInstruction"] = {"parts": [{"text": system}]}
    chosen = _RESOLVED.get("m") or model or DEFAULT_GEMINI
    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(2):
            r = await client.post(GEMINI_URL.format(model=chosen), params={"key": key},
                                  headers={"content-type": "application/json"}, json=body)
            if r.status_code == 404 and attempt == 0:   # 모델 지원 종료 → 자동 탐색 후 재시도
                try:
                    pick = _best_model(await _list_models(client, key))
                    if pick and pick != chosen:
                        chosen = pick
                        continue
                except Exception:
                    pass
            if r.status_code >= 400:
                raise RuntimeError(f"gemini {r.status_code} (model={chosen}): {r.text[:300]}")
            data = r.json()
            _RESOLVED["m"] = chosen
            cands = data.get("candidates", [])
            parts = cands[0]["content"]["parts"] if cands else []
            return "".join(x.get("text", "") for x in parts).strip()
    raise RuntimeError("gemini: no usable model")


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
