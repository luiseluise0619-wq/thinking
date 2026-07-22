# THINK OS — 아키텍처

> 개인의 **사고력·판단력·실행력**을 성장시키는 AI OS.
> ChatGPT(답을 주는 AI) · Notion(기록) · Duolingo(훈련) 사이에서,
> **AI가 답을 주지 않고 사용자의 사고 과정을 축적·성장시키는** 장기 플랫폼.

핵심 명제: **좋은 질문을 던지고 본질을 파악하는 능력**이 AI 시대의 해자다.
따라서 THINK OS의 해자는 기능이 아니라 **개인 사고 데이터의 선순환(Data Flywheel)** 이다.

---

## 1. 시스템 개요

```
                    Client (Flutter / 본 레포의 index.html 프로토타입)
                          |
                     API Gateway
                          |
                  Backend (FastAPI)
                          |
   ┌──────────────────────┼──────────────────────┐
   |                      |                      |
User System         Growth System           AI System
   |                      |                      |
 Auth               Evaluation Engine      Agent Orchestrator
 Profile            Analytics / Report      ├─ Problem Agent
 Goals                                      ├─ First Principles Agent
                                            ├─ Critic Agent
                                            ├─ Strategy Agent
                                            ├─ Execution Agent
                                            └─ Reflection Agent
                          |
              ┌───────────┴───────────┐
              |                       |
        PostgreSQL               Vector DB
      (구조 데이터)          (생각/지식 기억, pgvector·Qdrant)
              |
            Redis
      (캐시 · 세션 · Queue)
              |
        AI Model Layer  —  Claude / Gemini (멀티 프로바이더, 런타임 선택)
```

이 레포는 위 구조의 **MVP 슬라이스**를 실제로 구현한다: `index.html`(Client) + `backend/`(FastAPI + Agent Orchestrator + Evaluation + SQLite).

---

## 2. AI Agent Layer — 차별점

하나의 LLM 호출이 아니라 **역할별 Agent를 Orchestrator가 조합**한다.

```
User Input
    ↓
Planner Agent        상황 분석 → "어떤 사고법이 필요한가?"
    ↓
┌───────────────────────────────┐
│ Problem  → 문제를 진짜 문제로 재정의 │
│ First    → 본질까지 분해            │
│ Critic   → 생각을 공격(오류·편향·근거) │
│ Strategy → 선택지·리스크·기회비용 설계 │
│ Execution→ 검증 가능한 최소 행동 생성  │
│ Reflection→ 결과에서 원칙 추출        │
└───────────────────────────────┘
    ↓
Final Insight (통합) — 단, 결론은 사용자가 내린다
```

구현: [`backend/app/agents.py`](backend/app/agents.py)

- **Planner**: Claude가 있으면 LLM이 Agent 조합을 고르고, 없으면 키워드 규칙으로 골격
  (`problem → critic → execution`)을 항상 보장한 뒤 매칭된 전문 Agent를 끼워 넣는다.
- **각 Agent**: Claude 호출 실패/무키 시 의미 있는 규칙 기반 결과로 폴백한다.

> 설계 원칙: **API 키가 없어도 전체 시스템이 동작한다.** 키가 있으면 진짜 추론으로 업그레이드될 뿐.

---

## 3. Memory System — "개인 AI"의 조건

| 계층 | 저장소 | 내용 | 본 MVP |
|---|---|---|---|
| Short Memory | Redis | 최근 대화/세션 | (프로덕션) |
| Long Memory | PostgreSQL | 가치관·강점·약점·반복 오류·관심 분야 (Personal Intelligence Profile) | `profiles` 테이블 |
| Knowledge Memory | Vector DB | 읽은 책·논문·생각 기록 → 의미 검색 | `knowledge_nodes` (텍스트, embedding 업그레이드 경로) |

**Personal Intelligence Profile** 예시:
```
강점: 아이디어 생성, 빠른 학습
약점: 실행 지속성, 검증 단계 생략
편향: 새 기술 선호
목표: Medical AI Founder
```
→ 이것이 쌓이면 AI 멘토가 진화한다:
> "좋은 아이디어지만, 이전에도 비슷한 패턴으로 3번 검증 전에 넘어갔습니다. 이번엔 고객 인터뷰부터."

---

## 4. 데이터 모델 (PostgreSQL 설계 → MVP는 SQLite)

구현: [`backend/app/db.py`](backend/app/db.py)

```
users(id, name, created_at)

thinking_sessions(id, user_id, question, frame, answer,
                  framework, action, scores(JSON 8축), feedback, created_at)

profiles(user_id, strengths, weaknesses, biases, interests, goal)

knowledge_nodes(id, user_id, concept, relation, note)   -- 지식 그래프

principles(id, user_id, principle, source)              -- Wisdom Engine
```

> **업그레이드 경로**: SQLite → PostgreSQL(구조 데이터) + pgvector/Qdrant(지식 기억) + Redis(세션·큐).
> 스키마는 그대로 이식 가능하도록 설계했다.

---

## 5. Evaluation Engine — 진짜 성장 측정

"오늘 생각했다"가 아니라 **실제 능력 변화**를 측정한다. 두 층으로 나뉜다.

**(a) 8축 능력치** (0~100) — [`backend/app/scoring.py`](backend/app/scoring.py)
```
본질 파악력 · 논리력 · 분석력 · 창의력 · 판단력 · 메타인지 · 학습력 · 실행력
```
채점은 **답변 길이가 아니라 사고 신호**로 한다: 근거 제시(왜냐·따라서), 근본 원인 도달(근본·본질·인센티브),
반례 고려(반례·그러나·반증), 검증 행동의 구체성. Claude가 있으면 LLM 채점, 없으면 동일 신호 기반 휴리스틱.

**(b) 6대 신뢰 지표 (Thinking DNA/Genome 근거)** — 프론트 `sessionMetrics()`/`genome()`
| 지표 | 측정 방식 |
|---|---|
| 질문의 깊이 | 문제 재정의·프레임 적용·최종 생각 심화·인과 표현의 결합(0~100 → Lv1~5) |
| 본질 도달률 | 표면어 없이 근본 원인/재정의에 닿은 세션 비율 |
| 논리적 비약 | 근거·증거 표현이 전무한 세션 비율(낮을수록 좋음) |
| 반례 고려율 | 반례/반증 표현 또는 역발상·확률 프레임 사용 비율 |
| 실행 완료율 | 피드백 루프에서 done/(done+skipped) 실측 |
| 원칙 재사용률 | Wisdom 원칙 중 적용 사례·재수정 이력이 있는 비율 |

각 지표는 **분모(N회/건/개)를 함께 노출**해 신뢰성을 드러낸다. 표본이 적으면 그렇게 보이게 둔다.

## 5-1. Thinking Genome — 장기 사고 프로필

위 지표를 시간축으로 집계해 **사람마다 다른 사고 유전자**를 만든다:
사고 성향(★ 5축), 의사결정 스타일(구조·데이터 vs 발상·직관), 평균 사고 깊이 Lv 추이(early→recent),
본질 도달률 추이(34%→81% 형태). 단순 점수보다 의미 있고, 장기 사용의 이유가 된다.
`GET /dna/{user_id}` 가 서버측 동등 리포트를 반환한다.

---

## 6. Data Flywheel — 가장 큰 해자

```
사용자 생각 기록
      ↓
AI 분석 · 점수화
      ↓
사고 패턴 데이터 축적 (Profile)
      ↓
개인 맞춤 코칭 정확도 ↑
      ↓
더 좋은 사고 기록
      ↓  ↺
AI 멘토가 더 똑똑해짐 → 다른 앱으로 갈 이유가 사라짐
```

성장 루프(사용자 경험):
```
경험 → 문제 정의 → 사고 → AI 검증 → 실행 → 결과 → 피드백 → 더 나은 사고 → …
```

---

## 7. MVP 로드맵

**1차 (본 레포 구현 범위)** — 핵심 가치 검증
- Client(프로토타입) + FastAPI + LLM(Claude) + DB
- ① 문제 입력 ② AI 질문(Critic) ③ 사고 분석·점수 ④ 성장 기록 ⑤ Agent Orchestration

**2차** — 개인화
- Personal Intelligence Profile · Knowledge Graph · Mental Model 자동 추천 · Memory(Redis/Vector)

**3차** — 진화/확장
- AI Twin(개인 AI 진화) · Goal/Energy/Environment(Life OS) · 커뮤니티 · B2B 교육

---

## 8. 보안 / 프라이버시

생각 데이터는 극도로 개인적이다. 필수 요건:
데이터 암호화 · 사용자 데이터 격리 · 완전 삭제 · **개인 기억 ON/OFF 토글**.

## 9. Monetization

| Tier | 내용 |
|---|---|
| Free | 하루 사고 훈련 1회 · 기본 AI 분석 |
| Pro | 무제한 코칭 · 개인 AI 기억 · 성장 리포트 · 고급 Agent |
| Premium | AI 멘토 모드 · 목표/커리어/창업 코칭 |

---

## 10. 한 줄 요약

```
THINK OS = 사고 훈련 엔진 + 개인 지식 저장소 + AI 멘토
         + 의사결정 시스템 + 실행 관리 + 성장 분석 + 개인 AI 진화
```
"앱 하나"가 아니라 **개인의 두 번째 두뇌 시스템**.
