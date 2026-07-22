"""
AI Agent Layer — THINK OS의 차별점.

하나의 LLM 호출이 아니라 역할별 Agent를 Orchestrator(Planner)가 조합한다.

    User Input
        ↓
    Planner Agent      (상황 분석 → 어떤 Agent가 필요한가?)
        ↓
    ┌─────────────────────────────┐
    │ Problem / FirstPrinciples   │
    │ Critic / Strategy           │
    │ Execution / Reflection      │
    └─────────────────────────────┘
        ↓
    Final Insight  (통합)

각 Agent는 Claude가 있으면 진짜 추론을, 없으면 규칙 기반 결과를 낸다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from . import llm


# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------
@dataclass
class Agent:
    key: str
    name: str
    role: str            # 한 줄 설명 (UI 노출용)
    system: str          # LLM system prompt
    triggers: list[str] = field(default_factory=list)  # planner 키워드


PROBLEM = Agent(
    "problem", "Problem Agent", "문제를 진짜 문제로 다시 정의한다",
    "너는 문제 정의 전문가다. 사용자가 말한 표면 문제 뒤의 근본 문제를 찾아라. "
    "'표면 문제'와 '근본 문제'를 각각 한 문장으로, 그리고 '진짜 답해야 할 질문' 하나를 제시하라. 답은 주지 마라.",
    ["문제", "정의", "무엇", "왜"],
)
FIRST = Agent(
    "first", "First Principles Agent", "본질까지 분해한다",
    "너는 1원칙 사고 전문가다. 통념을 걷어내고 더 못 쪼개는 근본 요소로 분해하라. "
    "근본 요소 3~5개와, 그로부터 다시 세운 한 문장의 재구성을 제시하라.",
    ["본질", "창업", "기술", "아이디어", "원리"],
)
CRITIC = Agent(
    "critic", "Critic Agent", "사고 상태에 맞춰 검증한다",
    "너는 적응형 비판자다. 규칙: (1) 절대 칭찬·요약·답을 하지 마라. "
    "(2) 먼저 사용자의 사고 상태를 판단하라 — 개념을 '배우는 중'이면 공격 대신 핵심 구조·작동 원리·적용 경계를 세우는 질문을, "
    "'결정/고민'이면 반증 조건·가역성·비대칭 선택지를, '주장/확신'이면 반증부터('틀렸다면 어떤 증거가?')와 감지된 약한 고리"
    "(근거 부족/숨은 가정/반례 미고려)를 물어라. (3) 사용자의 실제 표현을 인용해 구체적으로. "
    "질문 3개, 각 한 줄, 번호 없이 줄바꿈 구분.",
    ["검증", "반박", "비판", "오류", "편향"],
)
STRATEGY = Agent(
    "strategy", "Strategy Agent", "해결책·선택지를 설계한다",
    "너는 전략가다. 80/20·역발상·2차 사고를 활용해 선택지 2~3개를 만들고 각각의 리스크와 기회비용, "
    "장기(2차) 결과를 한 줄씩 제시하라.",
    ["전략", "선택", "결정", "해결", "이직", "투자"],
)
EXECUTION = Agent(
    "execution", "Execution Agent", "검증 가능한 실행 계획을 만든다",
    "너는 실행 코치다. 생각을 행동으로 바꿔라. 7일 내 검증 가능한 최소 행동 3개를 제시하되 "
    "실패 비용이 낮은 순으로 정렬하라. 추상적 조언 금지, 구체적 행동만.",
    ["실행", "행동", "계획", "실험", "시작"],
)
REFLECTION = Agent(
    "reflection", "Reflection Agent", "결과에서 원칙을 추출한다",
    "너는 회고 코치다. 사용자가 입력한 경험/결과에서 반복 패턴과 배운 점을 찾고, "
    "다음에 쓸 수 있는 '나만의 원칙' 한 문장을 뽑아라.",
    ["결과", "회고", "돌아보", "원칙", "배운"],
)

AGENTS: dict[str, Agent] = {
    a.key: a for a in (PROBLEM, FIRST, CRITIC, STRATEGY, EXECUTION, REFLECTION)
}


# ---------------------------------------------------------------------------
# Planner — 어떤 Agent를 부를지 결정 (뇌의 뇌)
# ---------------------------------------------------------------------------
async def plan(user_input: str) -> list[str]:
    """상황을 분석해 실행할 Agent 순서를 반환한다."""
    if llm.has_key():
        try:
            keys = ", ".join(AGENTS)
            out = await llm.complete_json(
                "너는 THINK OS의 Orchestrator다. 사용자의 입력을 보고 어떤 사고 Agent들이 "
                f"필요한지 고른다. 사용 가능한 agent key: [{keys}]. "
                'JSON {"agents": ["problem", ...]} 형식으로, 논리적 순서대로 3~5개 반환하라.',
                f"사용자 입력: {user_input}",
                max_tokens=200,
            )
            picked = [k for k in out.get("agents", []) if k in AGENTS]
            if picked:
                return picked
        except Exception:
            pass
    # --- 규칙 기반 planner ---
    picked = {k for k, a in AGENTS.items() if any(t in user_input for t in a.triggers)}
    # 문제 정의로 시작 → 비판으로 검증 → 실행으로 끝맺는 골격은 항상 보장,
    # 매칭된 전문 Agent(first/strategy/reflection)를 정규 순서에 끼워 넣는다.
    backbone = {"problem", "critic", "execution"}
    canonical = ["problem", "first", "critic", "strategy", "execution", "reflection"]
    return [k for k in canonical if k in picked or k in backbone]


# ---------------------------------------------------------------------------
# Specialist agent execution
# ---------------------------------------------------------------------------
async def run_agent(key: str, context: str) -> dict:
    agent = AGENTS[key]
    if llm.has_key():
        try:
            text = await llm.complete(agent.system, context, max_tokens=500)
            return {"agent": key, "name": agent.name, "role": agent.role,
                    "output": text, "source": "claude"}
        except Exception:
            pass
    return {"agent": key, "name": agent.name, "role": agent.role,
            "output": _fallback(key, context), "source": "rules"}


async def orchestrate(user_input: str) -> dict:
    """Planner → agents → 통합. 코칭 엔드포인트의 핵심."""
    order = await plan(user_input)
    steps = []
    context = f"사용자 입력: {user_input}"
    for key in order:
        result = await run_agent(key, context)
        steps.append(result)
        context += f"\n[{result['name']}] {result['output']}"
    return {"input": user_input, "plan": order, "steps": steps,
            "final": _synthesize(steps)}


# ---------------------------------------------------------------------------
# Rule-based fallbacks (키 없이도 의미 있는 결과)
# ---------------------------------------------------------------------------
def _topic(t: str) -> str:
    return re.sub(r"(왜|할까|하고 싶다|입니다|\?|\.)", "", t).strip() or "이 문제"


def _fallback(key: str, ctx: str) -> str:
    t = _topic(ctx.splitlines()[0].replace("사용자 입력:", ""))
    return {
        "problem": f"표면 문제: '{t}' 자체.\n근본 문제: '{t}'이(가) 해결하려는 진짜 가치는 무엇인가?\n"
                   f"진짜 질문: 이 문제가 사라지면 나에게 무엇이 해결되는가?",
        "first": f"'{t}'을(를) 더 못 쪼갤 때까지 분해하라: (1) 관련된 사람 (2) 그들의 동기 "
                 f"(3) 제약 조건. 통념을 걷어내면 남는 근본 사실은?",
        "critic": "이 생각이 틀렸다면 어떤 증거를 보게 될까? (반증 조건)\n"
                  "그 주장은 근거인가 느낌인가 — 뒷받침하는 사실 하나는?\n"
                  "이 설명으로 설명되지 않는 반례를 하나 대라.",
        "strategy": f"선택지 A(현상 유지)·B(정면 돌파)·C(작게 실험) 중 각각의 리스크와 기회비용, "
                    f"그리고 1년 뒤 2차 결과를 비교하라. '{t}'의 핵심 20% 변수는?",
        "execution": "7일 내 최소 행동: (1) 관련 자료 1개 정독 (2) 이해관계자 1명 인터뷰 "
                     "(3) 가장 싼 실험 1개 실행. 실패 비용이 낮은 순.",
        "reflection": "이번 경험의 반복 패턴은? 다음에 쓸 원칙 한 줄로: '____보다 ____이(가) 먼저다.'",
    }[key]


def _synthesize(steps: list[dict]) -> str:
    names = " → ".join(s["name"] for s in steps)
    return (f"[{names}] 순서로 사고를 통과시켰다. AI는 결론을 대신 내리지 않는다 — "
            "각 Agent의 질문에 스스로 답하며 너의 판단을 세워라.")
