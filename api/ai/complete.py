"""
Vercel Serverless Function — 키를 숨기는 stateless Gemini 프록시.
프론트의 /ai/complete → (vercel.json rewrite) → /api/ai/complete.
환경변수: GEMINI_API_KEY (필수), THINKOS_GEMINI_MODEL (선택).

모델이 지원 종료돼도 안 깨지도록: 지정 모델이 404면 키가 실제 쓸 수 있는
모델 목록을 조회해 flash 계열을 자동 선택하고 재시도한다(웜 인스턴스에 캐시).
"""
import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

_RESOLVED = {}   # 웜 인스턴스 캐시: 마지막으로 성공한 모델


def _list_models(key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.loads(r.read())
    out = []
    for m in data.get("models", []):
        if "generateContent" in (m.get("supportedGenerationMethods") or []):
            out.append(m["name"].split("/")[-1])
    return out


def _best_model(models):
    bad = ("vision", "image", "tts", "embedding", "aqa", "thinking", "live")
    flash = [m for m in models if "flash" in m and not any(b in m for b in bad)]
    pool = flash or [m for m in models if not any(b in m for b in bad)] or models
    latest = [m for m in pool if m.endswith("-latest")]
    return (latest or pool)[0] if pool else None


def _generate(key, model, payload):
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def do_POST(self):
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            return self._send(503, {"error": "no_provider"})
        try:
            length = int(self.headers.get("content-length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._send(400, {"error": "bad_request"})
        if not (body.get("user") or "").strip():
            return self._send(400, {"error": "user is empty"})

        payload = {
            "contents": [{"role": "user", "parts": [{"text": body.get("user", "")}]}],
            # thinkingBudget:0 → flash가 답변 대신 '사고'에 예산을 쓰다 답이 잘리는 것 방지
            "generationConfig": {"maxOutputTokens": int(body.get("max_tokens", 2048)),
                                 "temperature": 0.7,
                                 "thinkingConfig": {"thinkingBudget": 0}},
        }
        sys_prompt = (body.get("system") or "").strip()
        if sys_prompt:   # 빈 systemInstruction은 Gemini가 거부할 수 있어 생략
            payload["systemInstruction"] = {"parts": [{"text": sys_prompt}]}

        model = _RESOLVED.get("m") or os.environ.get("THINKOS_GEMINI_MODEL", "gemini-flash-latest")
        last, tried_discovery, stripped_thinking = "", False, False
        for _ in range(4):
            try:
                data = _generate(key, model, payload)
                _RESOLVED["m"] = model
                parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts).strip()
                return self._send(200, {"text": text, "provider": "gemini", "model": model})
            except urllib.error.HTTPError as e:
                try:
                    last = e.read().decode()[:500]
                except Exception:
                    last = ""
                if e.code == 404 and not tried_discovery:   # 모델 지원 종료 → 자동 탐색 후 재시도
                    tried_discovery = True
                    try:
                        pick = _best_model(_list_models(key))
                        if pick and pick != model:
                            model = pick
                            continue
                    except Exception:
                        pass
                # pro 등 thinking 필수 모델은 thinkingBudget:0을 400으로 거부 → 떼고 재시도
                if e.code == 400 and not stripped_thinking and \
                        "thinkingConfig" in payload["generationConfig"]:
                    stripped_thinking = True
                    payload["generationConfig"].pop("thinkingConfig", None)
                    continue
                return self._send(502, {"error": "llm_error", "status": e.code,
                                        "model": model, "detail": last})
            except Exception as e:
                return self._send(502, {"error": "llm_error", "detail": str(e)[:300]})
        return self._send(502, {"error": "llm_error", "detail": "no usable model"})
