"""
Evaluation Engine — 사고 기록을 점수화한다.

"오늘 생각했다"가 아니라 실제 능력 변화를 측정하는 것이 성장 OS의 핵심.
Claude가 있으면 LLM 평가, 없으면 휴리스틱으로 점수를 낸다.
"""
from __future__ import annotations

from . import llm

DIMENSIONS = ["essence", "logic", "analysis", "creative", "judge", "meta", "learning", "exec"]
DIM_KR = {
    "essence": "본질 파악력", "logic": "논리력", "analysis": "분석력",
    "creative": "창의력", "judge": "판단력", "meta": "메타인지",
    "learning": "학습력", "exec": "실행력",
}

_SURFACE = ["많아서", "때문에", "좋아서", "그냥", "원해서", "비싸서", "필요해서", "유행", "돈"]
_BECAUSE = ["왜냐", "때문", "근거", "이유는", "따라서", "그래서"]
_CAUSAL = ["근본", "본질", "구조", "뿌리", "메커니즘", "인센티브", "원인", "동인"]
_COUNTER = ["반례", "예외", "반증", "그러나", "하지만", "반대로", "틀릴", "한계", "다만", "반면"]


async def score_answer(problem: str, answer: str, frame: str = "",
                       action: str = "") -> dict:
    """사고 기록 → 8개 능력치 점수(0~100) + 한 줄 피드백."""
    if llm.has_key():
        try:
            out = await llm.complete_json(
                "너는 THINK OS의 엄격한 평가 엔진이다. 사용자의 사고 기록을 8개 축으로 0~100 점수화하라. "
                "축 key: essence, logic, analysis, creative, judge, meta, learning, exec. "
                "채점 기준: 근거 없는 표면 답변은 20점대. 근본 원인·숨은 가정까지 내려가면 essence↑, "
                "반례/반증을 스스로 고려하면 logic·meta↑, 검증 행동이 구체적이면 exec↑. "
                'JSON {"scores": {...}, "feedback": "한 줄 피드백"} 형식.',
                f"문제: {problem}\n문제 재정의: {frame}\n답변: {answer}\n실행 계획: {action}",
                max_tokens=300,
            )
            scores = {d: int(out["scores"].get(d, 50)) for d in DIMENSIONS}
            return {"scores": scores, "feedback": out.get("feedback", ""),
                    "source": "claude"}
        except Exception:
            pass
    return _heuristic(problem, answer, frame, action)


def _heuristic(problem: str, answer: str, frame: str, action: str) -> dict:
    a = answer.strip()
    both = a + " " + frame
    words = len(a.split())
    surface = (any(w in a for w in _SURFACE) and len(a) < 40) or words < 4
    has_because = any(w in both for w in _BECAUSE)   # 근거 제시 여부
    has_causal = any(w in both for w in _CAUSAL)     # 근본 원인 도달
    has_counter = any(w in a for w in _COUNTER)      # 반례 고려
    has_frame = len(frame.strip()) > 5
    has_action = len(action.strip()) > 3

    base = 20 if surface else 52
    scores = {
        "essence": min(100, base + (20 if has_causal else 0) + (12 if has_frame else 0) + words // 2),
        "logic": min(100, base + (18 if has_because else 0) + (12 if has_counter else 0)),
        "analysis": min(100, base + (15 if has_causal else 0) + words),
        "creative": min(100, 40 + words // 2),
        "judge": min(100, base + (10 if has_action else 0) + (10 if has_counter else 0)),
        "meta": min(100, 42 + (15 if has_counter else 0) + (10 if has_frame else 0)),
        "learning": min(100, 40 + words // 2),
        "exec": 75 if has_action else 28,
    }
    if surface:
        fb = "표면적 답변이다 — 그 생각이 틀렸다면 어떤 증거가 필요한지부터 물어라."
    elif not has_counter:
        fb = "방향은 있다. 하지만 반례를 스스로 찾지 않았다 — 설명 안 되는 사례를 하나 떠올려라."
    else:
        fb = "근거와 반례를 함께 다뤘다. 2차 결과까지 밀어붙이면 더 단단해진다."
    return {"scores": scores, "feedback": fb, "source": "rules"}
