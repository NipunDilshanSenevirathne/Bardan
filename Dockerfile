# Bardan prototype: one container serves the API (/v1) and the built web app (Google Cloud Run).
# Multi-stage: Node builds the web app; a slim Python image runs it as a non-root user.

# ---------- 1. Web app ----------
FROM node:22-bookworm-slim AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY shared/ /src/shared/
COPY frontend/ ./
RUN npm run build

# ---------- 2. Runtime ----------
FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BARDAN_WEB_DIST=/app/frontend/dist \
    BARDAN_SHARED_DIR=/app/shared \
    BARDAN_DATA_CLASS=synthetic \
    BARDAN_AI_TIER=free \
    PORT=8080
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/app ./app
COPY backend/reports ./reports
COPY shared /app/shared
COPY --from=web /src/frontend/dist /app/frontend/dist
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin bardan \
    && chown -R bardan /app/backend/reports
USER bardan
EXPOSE 8080
# One worker by design: the judge sandboxes live in memory (Cloud Run max-instances=1).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*' --no-access-log --log-level info"]
