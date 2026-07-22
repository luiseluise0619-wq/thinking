"""
Vercel Serverless Function — 키를 숨기는 stateless Gemini 프록시.
프론트의 /ai/complete → (vercel.json rewrite) → /api/ai/complete.
환경변수: GEMINI_API_KEY (Vercel 대시보드에서 설정). 없으면 503 → 프론트는 규칙 기반.
"""
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler


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
        model = os.environ.get("THINKOS_GEMINI_MODEL", "gemini-2.5-flash")
        payload = {
            "systemInstruction": {"parts": [{"text": body.get("system", "")}]},
            "contents": [{"role": "user", "parts": [{"text": body.get("user", "")}]}],
            "generationConfig": {"maxOutputTokens": int(body.get("max_tokens", 800)),
                                 "temperature": 0.7},
        }
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={key}")
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
            parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts).strip()
            return self._send(200, {"text": text, "provider": "gemini"})
        except Exception:
            return self._send(502, {"error": "llm_error"})
