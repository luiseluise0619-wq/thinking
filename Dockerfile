# THINK OS — 단일 컨테이너 (API + 프론트 서빙)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    THINKOS_FRONTEND=/app/index.html \
    THINKOS_DB=/data/thinkos.db

WORKDIR /app

# 의존성 먼저 (레이어 캐시)
COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# 앱 코드 + 프론트
COPY backend/app ./app
COPY index.html ./index.html

# 사고 데이터(SQLite) 볼륨
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000
# Render·Railway·Fly는 $PORT를 주입한다 → 있으면 그 포트, 없으면 8000
HEALTHCHECK --interval=30s --timeout=4s --retries=3 \
  CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/healthz'%os.getenv('PORT','8000')).status==200 else 1)"

# 프로덕션 서버 (gunicorn + uvicorn worker). exec로 PID1 → SIGTERM 정상 수신
CMD ["sh","-c","exec gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:${PORT:-8000} --timeout 90"]
