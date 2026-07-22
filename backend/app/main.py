"""
THINK OS — 사고 성장 운영체제 (FastAPI)

한 서비스로 배포: 백엔드가 API + 프론트(index.html)를 함께 서빙한다.
프론트는 백엔드가 서빙하면 same-origin 프록시를 자동 사용하므로,
GEMINI_API_KEY는 서버에만 두면 되고 브라우저에 노출되지 않는다.

로컬 실행:
  pip install -r requirements.txt
  export GEMINI_API_KEY=AIza...           # (선택) 없으면 규칙 기반으로 동작
  uvicorn app.main:app --host 0.0.0.0 --port 8000
  # → http://localhost:8000  (앱)  ·  /docs (API)

배포: Dockerfile / docker-compose.yml 참고.
"""
from __future__ import annotations

import os
from pathlib import Path

import time
from collections import deque

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from . import agents, auth, db, llm, scoring
from .schemas import (AnalyzeIn, AnalyzeOut, AiIn, CoachIn, GrowthOut,
                      LoginIn, RegisterIn, StateIn)

# 프론트(index.html) 위치 — 기본은 레포 루트, 배포 시 THINKOS_FRONTEND로 지정
FRONTEND = Path(os.getenv("THINKOS_FRONTEND",
                          str(Path(__file__).resolve().parents[2] / "index.html")))
# 허용 오리진 — 프로덕션에선 실제 도메인만. 기본 '*'(개발용)
_ORIGINS = [o.strip() for o in os.getenv("THINKOS_ALLOWED_ORIGINS", "*").split(",") if o.strip()]

app = FastAPI(title="THINK OS", version="1.0.0",
              description="사고 성장 운영체제 — Agent Orchestrator + 성장 데이터 플랫폼")
app.add_middleware(CORSMiddleware, allow_origins=_ORIGINS, allow_methods=["*"],
                   allow_headers=["*"])


@app.on_event("startup")
def _startup():
    db.init()


@app.get("/healthz")
def healthz():
    return {"ok": True, "ai_mode": llm.provider() or "rule-based-fallback"}


@app.get("/api")
def api_status():
    return {
        "service": "THINK OS API", "version": "1.0.0",
        "ai_mode": llm.provider() or "rule-based-fallback",
        "agents": [{"key": a.key, "name": a.name, "role": a.role}
                   for a in agents.AGENTS.values()],
        "docs": "/docs",
    }


@app.get("/", response_class=HTMLResponse)
def serve_app():
    """프론트 서빙 + same-origin 프록시 플래그 주입."""
    if not FRONTEND.exists():
        return HTMLResponse("<h1>THINK OS API</h1><p>프론트 파일이 없습니다. /docs 참고.</p>")
    html = FRONTEND.read_text(encoding="utf-8")
    # 백엔드가 서빙했음을 프론트에 알림 → 브라우저가 same-origin 프록시를 자동 사용
    inject = "<script>window.THINKOS_API=location.origin;</script>"
    return HTMLResponse(html.replace("</head>", inject + "</head>", 1)
                        if "</head>" in html else inject + html)


# --- 1. 사고 분석: 문제+답변 → 비판 질문 + 8축 점수 + 기록 ---
@app.post("/thinking/analyze", response_model=AnalyzeOut)
async def analyze(body: AnalyzeIn):
    if not body.answer.strip():
        raise HTTPException(400, "answer is empty")

    # Critic Agent — 사용자의 생각을 공격
    critic = await agents.run_agent(
        "critic",
        f"문제: {body.question}\n문제 재정의: {body.frame}\n답변: {body.answer}",
    )
    critique = [ln.strip("-• ").strip()
                for ln in critic["output"].splitlines() if ln.strip()][:4]

    # Evaluation Engine — 점수화
    ev = await scoring.score_answer(body.question, body.answer, body.frame, body.action)

    surface = ev["scores"].get("essence", 50) < 45

    sid = db.save_session(
        body.user_id, question=body.question, frame=body.frame, answer=body.answer,
        framework=body.framework, action=body.action,
        scores=ev["scores"], feedback=ev["feedback"],
    )
    if body.principle.strip():
        db.add_principle(body.user_id, body.principle.strip(), body.question)
    # 실행 약속을 피드백 루프에 등록 (pending)
    if body.action.strip():
        db.add_action(body.user_id, body.question, body.action.strip())

    return AnalyzeOut(session_id=sid, surface=surface, critique=critique,
                      scores=ev["scores"], feedback=ev["feedback"], source=ev["source"])


# --- Feedback loop: 실행 약속 조회 & 결과 회고(Reflection Agent) → 원칙 축적 ---
@app.get("/actions/{user_id}")
def list_actions(user_id: int, status: str | None = None):
    return {"actions": db.actions(user_id, status)}


@app.post("/actions/{action_id}/resolve")
async def resolve_action(action_id: int, status: str, result: str = ""):
    if status not in ("done", "skipped"):
        raise HTTPException(400, "status must be 'done' or 'skipped'")
    # Reflection Agent가 결과에서 '나만의 원칙' 한 줄을 추출
    ref = await agents.run_agent(
        "reflection", f"실행 상태: {status}\n결과: {result}")
    lesson = ref["output"].splitlines()[0].strip("-• ").strip() if ref["output"] else ""
    row = db.resolve_action(action_id, status, result, lesson)
    if not row:
        raise HTTPException(404, "action not found")
    if lesson:
        db.add_principle(row["user_id"], lesson, "🔁 " + (row.get("problem") or ""))
    return {"action": row, "lesson": lesson, "source": ref["source"]}


# ==========================================================================
#  계정 (이메일+비밀번호) · 서버 저장 (멀티기기 동기화)
# ==========================================================================
def current_user(authorization: str = Header(default="")) -> int:
    tok = authorization[7:].strip() if authorization[:7].lower() == "bearer " else ""
    uid = auth.verify_token(tok)
    if not uid or not db.user_by_id(uid):
        raise HTTPException(401, "unauthorized")
    return uid


@app.post("/auth/register")
def register(body: RegisterIn):
    email = body.email.strip().lower()
    if "@" not in email or "." not in email:
        raise HTTPException(400, "invalid_email")
    if len(body.password) < 6:
        raise HTTPException(400, "weak_password")
    if db.user_by_email(email):
        raise HTTPException(409, "email_taken")
    uid = db.create_user(body.name.strip() or email.split("@")[0], email,
                         auth.hash_password(body.password))
    return {"token": auth.make_token(uid), "user": db.user_by_id(uid)}


@app.post("/auth/login")
def login(body: LoginIn):
    u = db.user_by_email(body.email.strip())
    if not u or not u.get("password_hash") or not auth.verify_password(body.password, u["password_hash"]):
        raise HTTPException(401, "bad_credentials")
    return {"token": auth.make_token(u["id"]), "user": db.user_by_id(u["id"])}


@app.get("/me")
def me(uid: int = Depends(current_user)):
    return {"user": db.user_by_id(uid)}


@app.get("/me/state")
def get_my_state(uid: int = Depends(current_user)):
    return {"state": db.get_state(uid)}


@app.put("/me/state")
def put_my_state(body: StateIn, uid: int = Depends(current_user)):
    db.put_state(uid, body.state)
    return {"ok": True}


# --- 검증: 코호트 지표 집계 (관리자 전용 · THINKOS_ADMIN_SECRET) ---
def _user_metrics(state: dict) -> dict:
    H = [h for h in (state.get("history") or []) if h.get("metrics")]
    n = len(H)
    rate = lambda f: (sum(1 for h in H if f(h)) / n) if n else None
    win = max(1, n // 2)
    early, recent = H[:win], H[win:] or H[-win:]
    er = lambda arr: (sum(1 for h in arr if h["metrics"].get("essence")) / len(arr)) if arr else 0
    acts = [a for a in (state.get("actions") or []) if a.get("status") != "pending"]
    done = sum(1 for a in acts if a.get("status") == "done")
    return {
        "sessions": state.get("sessions", 0),
        "essence_rate": rate(lambda h: h["metrics"].get("essence")),
        "counter_rate": rate(lambda h: h["metrics"].get("counter")),
        "leap_rate": rate(lambda h: h["metrics"].get("leap")),
        "avg_depth": (sum(h["metrics"].get("depth", 0) for h in H) / n) if n else None,
        "exec_rate": (done / len(acts)) if acts else None,
        "essence_early": round(er(early), 3), "essence_recent": round(er(recent), 3),
    }


@app.get("/admin/cohort")
def cohort(x_admin_secret: str = Header(default="")):
    secret = os.getenv("THINKOS_ADMIN_SECRET", "")
    if not secret or x_admin_secret != secret:
        raise HTTPException(403, "forbidden")
    states = db.all_states()
    per = [{"uid": s["uid"], "email": s["email"], "updated_at": s["updated_at"],
            **_user_metrics(s["state"])} for s in states]
    active = [p for p in per if (p["sessions"] or 0) > 0]

    def avg(key):
        vals = [p[key] for p in active if p.get(key) is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    improved = sum(1 for p in active if p["essence_recent"] > p["essence_early"])
    return {
        "users": len(per), "active": len(active),
        "avg_sessions": avg("sessions"),
        "avg_essence_rate": avg("essence_rate"), "avg_counter_rate": avg("counter_rate"),
        "avg_leap_rate": avg("leap_rate"), "avg_exec_rate": avg("exec_rate"),
        "essence_improved_users": improved,   # 본질 도달률이 오른 사용자 수 (검증 핵심)
        "per_user": per,
    }


# --- 간단한 IP 레이트 리밋 (오픈 프록시 남용·쿼터 소진 방지) ---
_RL: dict[str, deque] = {}
_RL_MAX = int(os.getenv("THINKOS_RL_PER_MIN", "30"))


def _rate_ok(ip: str) -> bool:
    now = time.time()
    dq = _RL.setdefault(ip, deque())
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= _RL_MAX:
        return False
    dq.append(now)
    return True


# --- 범용 LLM 프록시: 프론트가 키 없이 서버를 거쳐 호출 (키 노출·CORS 해결) ---
@app.post("/ai/complete")
async def ai_complete(body: AiIn, request: Request):
    ip = request.client.host if request.client else "?"
    if not _rate_ok(ip):
        raise HTTPException(429, "rate_limited")
    if not llm.has_key():
        raise HTTPException(503, "no_provider")  # 프론트는 규칙 기반으로 폴백
    if not body.user.strip():
        raise HTTPException(400, "user is empty")
    try:
        text = await llm.complete(body.system, body.user, max_tokens=body.max_tokens)
    except Exception:
        raise HTTPException(502, "llm_error")
    return {"text": text, "provider": llm.provider()}


# --- 2. AI 코치: 소크라테스 / 논쟁 / 멀티에이전트 오케스트레이션 ---
@app.post("/coach")
async def coach(body: CoachIn):
    if not body.text.strip():
        raise HTTPException(400, "text is empty")

    if body.mode == "orchestrate":
        return await agents.orchestrate(body.text)

    # socratic/debate: Critic 또는 Strategy 단일 Agent로 질문 생성
    key = "critic" if body.mode == "socratic" else "strategy"
    result = await agents.run_agent(key, f"사용자 입력: {body.text}")
    questions = [ln.strip("-• ").strip()
                 for ln in result["output"].splitlines() if ln.strip()]
    return {"mode": body.mode, "text": body.text, "questions": questions,
            "note": "AI는 답을 주지 않는다. 각 질문에 스스로 답하라.",
            "source": result["source"]}


# --- 3. 성장: 능력치 추세 + 축적된 원칙 (Feedback Loop 가시화) ---
@app.get("/growth/{user_id}", response_model=GrowthOut)
def growth(user_id: int):
    hist = db.sessions(user_id)
    latest = hist[0]["scores"] if hist else {}
    trend = {}
    if len(hist) >= 2:
        first = hist[-1]["scores"]
        for d in scoring.DIMENSIONS:
            a, b = first.get(d), latest.get(d)
            if a and b:
                trend[d] = round((b - a) / max(1, a) * 100)
    return GrowthOut(sessions=len(hist), latest_scores=latest, trend=trend,
                     principles=db.principles(user_id))


# --- 4. Thinking DNA: 사고 데이터를 성장 리포트로 (앱의 가장 큰 자산) ---
@app.get("/dna/{user_id}")
def thinking_dna(user_id: int):
    hist = list(reversed(db.sessions(user_id)))  # 시간 오름차순
    n = len(hist)
    if n == 0:
        return {"sessions": 0, "message": "아직 사고 지문이 없습니다. 훈련을 쌓으세요."}

    latest = hist[-1]["scores"]
    ranked = sorted(scoring.DIMENSIONS, key=lambda d: latest.get(d, 0), reverse=True)
    strengths = [{"key": k, "name": scoring.DIM_KR[k], "score": latest.get(k)} for k in ranked[:3]]

    # 약점 신호 (측정 가능한 것만)
    weak = [{"signal": f"{scoring.DIM_KR[ranked[-1]]}이(가) 가장 낮은 축"}]
    think = [d for d in scoring.DIMENSIONS if d != "exec"]
    think_avg = sum(latest.get(d, 0) for d in think) / len(think)
    if latest.get("exec", 0) < think_avg - 6:
        weak.append({"signal": "실행력이 사고력보다 낮음 — 생각을 검증 행동으로 옮겨라"})
    framed = sum(1 for h in hist if (h.get("frame") or "").strip())
    if framed / n < 0.5:
        weak.append({"signal": f"문제 정의를 자주 건너뜀 ({round(framed/n*100)}%만 재정의)"})

    # 사고방식 사용 빈도
    from collections import Counter
    fw = Counter(h.get("framework") for h in hist if h.get("framework"))
    total = sum(fw.values())
    frequency = [{"framework": k, "count": c, "pct": round(c / total * 100)}
                 for k, c in fw.most_common()] if total else []

    # 능력치 변화 (첫→최근)
    trend = {}
    if n >= 2:
        first = hist[0]["scores"]
        for d in scoring.DIMENSIONS:
            a, b = first.get(d), latest.get(d)
            if a is not None and b is not None:
                trend[d] = {"name": scoring.DIM_KR[d], "from": a, "to": b, "delta": b - a}

    return {"sessions": n, "strengths": strengths, "weaknesses": weak,
            "frequency": frequency, "trend": trend,
            "principles": db.principles(user_id)}


# --- 5. 지식 그래프 (2차 기능 스텁) ---
@app.post("/knowledge")
def add_knowledge(user_id: int, concept: str, relation: str = "", note: str = ""):
    db.add_knowledge(user_id, concept, relation, note)
    return {"ok": True}


@app.get("/knowledge/{user_id}")
def get_knowledge(user_id: int):
    return {"nodes": db.knowledge(user_id)}
