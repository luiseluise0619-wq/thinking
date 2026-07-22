"""
인증 — 외부 의존성 없이 stdlib만 사용.
- 비밀번호: PBKDF2-HMAC-SHA256 (salt 포함)
- 토큰: HMAC-SHA256 서명(JWT 유사, 자체 포맷)  payload.signature

프로덕션에선 THINKOS_SECRET 환경변수를 반드시 설정할 것.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

_SECRET = os.getenv("THINKOS_SECRET", "dev-insecure-secret-change-me").encode()
_TTL = int(os.getenv("THINKOS_TOKEN_TTL_DAYS", "30")) * 86400
_ITER = 120_000


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ---- 비밀번호 ----
def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, _ITER)
    return f"{salt.hex()}:{dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split(":")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), _ITER)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ---- 토큰 ----
def make_token(uid: int) -> str:
    payload = _b64e(json.dumps({"uid": uid, "exp": int(time.time()) + _TTL}).encode())
    sig = _b64e(hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify_token(token: str) -> int | None:
    """유효하면 uid, 아니면 None."""
    try:
        payload, sig = token.split(".")
        expected = _b64e(hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_b64d(payload))
        if int(data.get("exp", 0)) < time.time():
            return None
        return int(data["uid"])
    except Exception:
        return None
