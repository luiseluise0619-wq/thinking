# THINK OS — 배포 (계정 · 서버 동기화 · 코호트 켜기)

정적 배포(Vercel/Cloudflare)는 **AI 프록시만** 켠다. 로그인·멀티기기 동기화·
파일럿 코호트 집계(`/admin/cohort`)를 쓰려면 **컨테이너(백엔드)** 를 띄워야 한다.
한 컨테이너가 API와 프론트(`index.html`)를 함께 서빙하므로 배포는 하나로 끝난다.

---

## 무엇이 켜지나

| 기능 | 정적(Vercel) | 컨테이너(아래) |
|---|---|---|
| AI 코치/반박 (Gemini 프록시) | ✅ | ✅ |
| 규칙 기반 폴백 (키 없어도 동작) | ✅ | ✅ |
| **계정 로그인 · 서버 저장 · 멀티기기 동기화** | ❌ | ✅ |
| **파일럿 코호트 집계(사전/사후 효과)** | ❌ | ✅ |

---

## A. Render — 원클릭 (권장, 가장 쉬움)

1. 이 리포를 GitHub에 올린다.
2. render.com → **New → Blueprint** → 이 리포 선택 → **Apply**.
   `render.yaml`이 서비스·비밀키(자동 생성)·헬스체크를 알아서 설정한다.
3. 배포 후 서비스 **Environment** 에서 `GEMINI_API_KEY` 입력(선택 — 없으면 규칙 기반).
4. 끝. `https://<서비스>.onrender.com` 에서 앱이 뜨고, 로그인/동기화가 동작한다.

> **파일럿 데이터 보존:** free 플랜은 재배포 시 SQLite가 초기화된다(테스트엔 OK).
> 30일 파일럿이면 `render.yaml`의 `disk:` 블록 주석을 풀고 유료 플랜으로(영구 저장),
> 또는 외부 DB로 교체.

## B. Railway

1. railway.app → **New Project → Deploy from GitHub** → 이 리포.
2. Railway가 `Dockerfile`을 감지해 빌드. `$PORT`는 자동 주입된다(대응됨).
3. **Variables** 에 아래 표대로 입력. **Volume** 을 `/data`에 붙이면 데이터 영구 보존.

## C. Fly.io

```bash
fly launch --dockerfile Dockerfile   # 앱 이름·리전 선택
fly volumes create data --size 1     # /data 영구 볼륨
fly secrets set GEMINI_API_KEY=... THINKOS_SECRET=... THINKOS_ADMIN_SECRET=...
fly deploy
```
`fly.toml`에 `[mounts] source="data" destination="/data"` 추가.

## D. 직접(도커)

```bash
cp .env.example .env    # 값 채우기
docker compose up -d    # docker-compose.yml 사용
```

---

## 환경변수

| 변수 | 필수 | 설명 |
|---|---|---|
| `GEMINI_API_KEY` | 선택 | 없으면 규칙 기반으로 동작(앱 안 깨짐) |
| `THINKOS_SECRET` | **권장** | 로그인 토큰 서명 키. 프로덕션은 반드시 랜덤(자동 생성 권장) |
| `THINKOS_ADMIN_SECRET` | 파일럿 | `/admin/cohort` 접근용. 비우면 대시보드 비활성 |
| `THINKOS_ALLOWED_ORIGINS` | 선택 | CORS 허용 오리진(쉼표 구분). 프로덕션은 실제 도메인만 |
| `THINKOS_GEMINI_MODEL` | 선택 | 기본 `gemini-flash-latest`. 더 날카로운 질문은 `gemini-pro-latest` |
| `THINKOS_DB` | 선택 | SQLite 경로(기본 `/data/thinkos.db`) |
| `PORT` | 자동 | 플랫폼이 주입. 없으면 8000 |

---

## 파일럿 켜는 법 (배포 후)

1. 참가자에게 배포 URL 공유 → 각자 **계정 가입**(설정에서).
2. 참가자는 **Day 0에 사전 진단**, 매일 훈련, **Day 30에 사후 진단**(PILOT.md 참고).
3. 진행자는 코호트 집계를 조회:
   ```bash
   curl -H "x-admin-secret: $THINKOS_ADMIN_SECRET" https://<배포URL>/admin/cohort
   ```
   응답의 **`pre_post`** 블록이 곧 효과 검증 결과다:
   - `avg_baseline_index → avg_latest_index`, `avg_index_delta` (평균 사고력 지수 변화)
   - `improved_users / users` (향상자 비율), `dim_deltas` (6축별 평균 변화)

> 개인 사고 데이터는 민감정보다. 익명 ID로만 취합하고, 원문은 참가자 소유로 둔다.
