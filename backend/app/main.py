"""
THINK OS — Backend MVP (FastAPI)

MVP 범위 (사용자 1차 정의):
  문제 입력 → AI 질문(Critic) → 사고 분석(점수) → 성장 기록
핵심 차별점: AI Agent Orchestrator + Feedback/Growth 데이터 축적.

실행:
  pip install -r requirements.txt
  uvicorn app.main:app --reload
  # (선택) export ANTHROPIC_API_KEY=sk-ant-...  → 진짜 Claude 추론
  # 키가 없으면 규칙 기반 엔진으로 동일하게 동작한다.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import agents, db, llm, scoring
from .schemas import AnalyzeIn, AnalyzeOut, CoachIn, GrowthOut

app = FastAPI(title="THINK OS API", version="0.1.0",
              description="사고 성장 운영체제 — Agent Orchestrator + 성장 데이터 플랫폼")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


@app.on_event("startup")
def _startup():
    db.init()


@app.get("/")
def root():
    return {
        "service": "THINK OS API",
        "ai_mode": "claude" if llm.has_key() else "rule-based-fallback",
        "agents": [{"key": a.key, "name": a.name, "role": a.role}
                   for a in agents.AGENTS.values()],
        "docs": "/docs",
    }


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

    return AnalyzeOut(session_id=sid, surface=surface, critique=critique,
                      scores=ev["scores"], feedback=ev["feedback"], source=ev["source"])


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
