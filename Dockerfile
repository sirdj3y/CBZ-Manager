# ── Stage 1: Build frontend ────────────────────────────────────────────────────
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY VERSION ../VERSION
COPY frontend/ ./
# Infos de build affichées dans l'app (fournies par GitHub Actions, vides en build local).
ARG APP_CHANNEL=local
ARG APP_GIT_SHA=
ARG APP_BUILD_DATE=
ENV APP_CHANNEL=$APP_CHANNEL APP_GIT_SHA=$APP_GIT_SHA APP_BUILD_DATE=$APP_BUILD_DATE
RUN npm run build
# Output: /app/backend/static/ (configured in vite.config.js)

# ── Stage 2: Python runtime ────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# unrar (non-free) for full CBR/RAR5 support
# gosu: drops root privileges cleanly after the entrypoint fixes ownership (see below)
RUN echo "deb http://deb.debian.org/debian bookworm non-free" >> /etc/apt/sources.list.d/non-free.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    unrar \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Non-root app user — real UID/GID are set at container start from PUID/PGID (default
# 1000:1000) by docker-entrypoint.sh, matching the linuxserver.io convention so NAS users
# can align it with their own account and keep bind-mounted files readable outside Docker.
RUN groupadd -g 1000 appuser && useradd -u 1000 -g appuser -M -d /app appuser

WORKDIR /app

# Copy backend source + version
COPY backend/ ./backend/
COPY VERSION ./VERSION

# Install Python dependencies
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy built frontend (Vite outputs to ../backend/static relative to frontend/)
COPY --from=frontend-builder /app/backend/static/ ./backend/static/

COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Default environment variables (can be overridden at runtime)
ENV MEDIA_ROOT=/media \
    DB_PATH=/data/cbzmanager.db \
    COVER_CACHE_DIR=/data/covers \
    PORT=32123

# Data volume
VOLUME ["/data"]

EXPOSE 32123

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:32123/api/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "32123"]
