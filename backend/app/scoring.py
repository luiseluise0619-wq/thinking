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


async def score_answer(problem: str, answer: str, frame: str = "",
                       action: str = "") -> dict:
    """사고 기록 → 8개 능력치 점수(0~100) + 한 줄 피드백."""
    if llm.has_key():
        try:
            out = await llm.complete_json(
                "너는 THINK OS의 평가 엔진이다. 사용자의 사고 기록을 8개 축으로 0~100 점수화하라. "
                "축 key: essence, logic, analysis, creative, judge, meta, learning, exec. "
                '엄격하게, 근거 없는 표면 답변엔 낮은 점수를. '
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
    words = len(a.split())
    depth = min(100, 30 + words * 2)                    # 길이 = 근사 깊이
    surface = any(w in a for w in _SURFACE) and len(a) < 40
    has_why = "왜" in a or "때문" in a or "근거" in a
    has_frame = len(frame.strip()) > 5
    has_action = len(action.strip()) > 3

    base = 20 if surface else 55
    scores = {
        "essence": min(100, base + (20 if has_frame else 0) + words),
        "logic": min(100, base + (15 if has_why else 0) + words // 2),
        "analysis": min(100, depth),
        "creative": min(100, 40 + words // 2),
        "judge": min(100, base + (10 if has_action else 0)),
        "meta": min(100, 45 + (15 if has_frame else 0)),
        "learning": min(100, 40 + words // 2),
        "exec": 75 if has_action else 30,
    }
    fb = ("표면적 답변이다 — 근거와 '왜'를 더 파고들어라." if surface
          else "방향은 있다. 반례와 2차 결과까지 검증하면 더 단단해진다.")
    return {"scores": scores, "feedback": fb, "source": "rules"}
