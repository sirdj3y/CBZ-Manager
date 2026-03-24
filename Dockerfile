# ── Stage 1: Build frontend ────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY VERSION ../VERSION
COPY frontend/ ./
RUN npm run build
# Output: /app/backend/static/ (configured in vite.config.js)

# ── Stage 2: Python runtime ────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# unrar-free for CBR support
RUN apt-get update && apt-get install -y --no-install-recommends \
    unrar-free \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy backend source + version
COPY backend/ ./backend/
COPY VERSION ./VERSION

# Install Python dependencies
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy built frontend (Vite outputs to ../backend/static relative to frontend/)
COPY --from=frontend-builder /app/backend/static/ ./backend/static/

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

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "32123"]
