# 🧠 THINK OS — 사고 성장 운영체제

> AI 시대엔 답을 찾는 능력보다 **좋은 질문을 던지고 본질을 파악하는 능력**이 중요하다.
> THINK OS는 답을 주는 앱이 아니다. **사용자의 사고 과정을 강제로 기록하고 성장시키는** AI 코치다.

포지션: `ChatGPT(답) · Notion(기록) · Duolingo(언어 근육)` 사이의 **사고 근육 훈련 OS**.

---

## 무엇이 들어있나

| 부분 | 파일 | 설명 |
|---|---|---|
| **① 인터랙티브 프로토타입** | [`index.html`](index.html) | 설치 없이 브라우저로 여는 완성형 데모. 코어 UX 루프를 끝까지 체험 |
| **② 백엔드 MVP** | [`backend/`](backend/) | FastAPI + AI Agent Orchestrator + Evaluation Engine + SQLite |
| **③ 시스템 설계** | [`ARCHITECTURE.md`](ARCHITECTURE.md) | 전체 아키텍처·에이전트·메모리·데이터 플라이휠·MVP 로드맵 |
| **④ 북극성 비전** | [`HUMAN_OS.md`](HUMAN_OS.md) | HUMAN OS 성장 모델 · 7대 영역 매핑 · 검증 지표 (구현 vs 로드맵) |
| **⑤ 검증 계획** | [`PILOT.md`](PILOT.md) · [`docs/pilot-invite.html`](docs/pilot-invite.html) | 30일 파일럿 — 가설·성공 지표·Go/Kill 게이트 + 참가자 모집 1페이지 |

두 구현 모두 **Gemini API 키가 없어도 규칙 기반 엔진으로 완전히 동작**한다.
키를 넣으면 진짜 추론으로 업그레이드된다.

---

## 코어 루프 (10-step 사고 파이프라인)

```
① 문제 정의  → ② 1원칙  → ③ 5 Whys → ④ 멘탈 모델 → ⑤ 시스템 사고
→ ⑥ 80/20 → ⑦ 역발상 → ⑧ 2차 사고 → ⑨ 확률 사고 → ⑩ 실행
```

매일의 훈련은 이 파이프라인을 6단계로 압축해 **강제 기록**한다:
**문제 정의 → 내 생각 → AI 반박 → 사고 프레임 적용 → 실행 약속 → 결론 & 원칙**

능력치 8축(본질·논리·분석·창의·판단·메타인지·학습·실행)으로 성장을 게임처럼 측정한다.

---

## ① 프로토타입 실행

```bash
# 그냥 브라우저로 열면 된다
open index.html            # macOS
# 또는
python3 -m http.server 8080   # → http://localhost:8080
```
- 오늘의 훈련 · 사고 프레임(10) · 멘탈 모델 라이브러리 · AI 코치(소크라테스/논쟁) · 성장 대시보드
- 진행 상황은 브라우저 `localStorage`에 저장된다.
- 설정(⚙️)에서 AI를 켜는 두 가지 방법:
  - **백엔드 프록시(권장)** — 아래 FastAPI를 띄우고 설정에 그 URL을 넣으면, 키가 **서버에만** 있고 브라우저에 노출되지 않는다. CORS·키 노출을 동시에 해결.
  - **직접 Gemini 키** — 프록시 없이 브라우저에서 직접 호출(개인 실험용, 키가 브라우저에 노출).
- 어느 쪽이든 실패하면 규칙 기반 엔진으로 자동 폴백한다.

## ② 백엔드 MVP 실행

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
# (선택) 진짜 추론:
export GEMINI_API_KEY=AIza...           # Gemini
# (선택) 모델 지정: export THINKOS_GEMINI_MODEL=gemini-2.5-pro
```
→ `http://localhost:8000/docs` (Swagger)

### 주요 엔드포인트
| Method | Path | 설명 |
|---|---|---|
| `GET` | `/` | 서비스 상태 · AI 모드 · 에이전트 목록 |
| `POST` | `/ai/complete` | **프론트 프록시** — {system,user} → {text}. 키를 서버에 숨긴다 |
| `POST` | `/thinking/analyze` | 문제+답변 → Critic 질문 + 8축 점수 + 세션 기록 |
| `POST` | `/coach` | `socratic` / `debate` / `orchestrate`(멀티 에이전트) |
| `GET` | `/growth/{user_id}` | 능력치 추세(첫→최근 %) + 축적된 원칙 |
| `POST`/`GET` | `/knowledge` | 지식 그래프 노드(2차 기능 스텁) |

예시:
```bash
curl -X POST localhost:8000/thinking/analyze -H 'content-type: application/json' \
  -d '{"question":"왜 사람들은 명품을 살까?","answer":"그냥 비싸서","action":"경쟁 브랜드 3개 조사"}'
```

---

## 품질 원칙 (기능보다 질)

이 앱의 가치는 UI가 아니라 **질문의 질**과 **지표의 신뢰성**이다.

1. **질문은 적응형.** 사용자의 사고 상태를 감지해 질문 전략을 바꾼다 —
   **배우는 중(learn)**엔 핵심 구조부터, **결정/고민(decide)**엔 가역성·비대칭 선택지, **주장/확신(assert)**엔
   반증부터("그 생각이 틀렸다면 어떤 증거가?") + 감지된 약한 고리(근거·가정·반례). 항상 반증부터가 아니다.
   *(습관 형성을 위한 **⚡ 빠른 판단 5분** 모드로 매일 루프를 최소화, 깊은 훈련은 선택.)*
2. **지표는 길이가 아니라 사고에서 측정.** 본질 도달률·논리적 비약·반례 고려율·사고 깊이·실행 완료율·원칙 재사용률을
   실제 사고 신호로 측정하고 **분모를 함께 노출**한다.
3. **Wisdom Log는 살아있다.** 원칙에 적용 사례가 쌓이고 검증되면 재수정된다 — 메모가 아니라 개인 사고 체계.
4. **Thinking Genome.** 이 지표들을 장기 집계해 사람마다 다른 사고 프로필(성향·의사결정 스타일·깊이 추이)을 만든다.

### 핵심 루프 (닫힘)
```
문제 정의 → 질문 → 사고 → AI 반박 → 실행 약속 → 결과 되먹임 → 원칙 축적 → 성장 분석(Genome)
```

## 설계 철학 3가지

1. **AI는 답을 주지 않는다.** Critic Agent는 칭찬 없이 오류·숨은 가정·근거 부족을 찌른다.
2. **사고 과정을 강제로 남긴다.** 매 단계가 기록되고 점수화되어 데이터로 축적된다.
3. **성장은 데이터 플라이휠이다.** 기록이 쌓일수록 코칭이 정교해지고, 떠날 이유가 사라진다.

자세한 내용은 [`ARCHITECTURE.md`](ARCHITECTURE.md) 참고.

---

> 이 레포는 컨셉을 검증 가능한 MVP로 구현한 것이다. 프로덕션 경로(PostgreSQL/pgvector/Redis,
> Flutter 클라이언트, 멀티 프로바이더 라우팅, AI Twin)는 아키텍처 문서에 정리되어 있다.
