# ═══════════════════════════════════════════════════════════════════
# TalentIQ - Single Dockerfile for Northflank deployment
# Stage 1: Build React frontend
# Stage 2: Python backend + serve built frontend via FastAPI static
# ═══════════════════════════════════════════════════════════════════

# ── Stage 1: Build frontend ──────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm install --no-fund --no-audit

COPY frontend/ ./
RUN npm run build
# Output: /app/frontend/dist


# ── Stage 2: Production image ────────────────────────────────────
FROM python:3.11-slim

# System deps for Playwright + PDF libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget gnupg ca-certificates \
    libglib2.0-0 libnss3 libnspr4 libdbus-1-3 \
    libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 \
    libpangocairo-1.0-0 libpango-1.0-0 libcairo2 \
    libatspi2.0-0 libx11-6 libxcb1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium --with-deps || true

# Copy backend source
COPY backend/ ./backend/

# Copy built frontend into backend/static so FastAPI can serve it
COPY --from=frontend-build /app/frontend/dist ./backend/static/

# Copy data directory (LinkedIn session, location.json)
COPY backend/data/ ./backend/data/

# Update main.py to serve frontend static files
WORKDIR /app/backend

# Environment defaults (override in Northflank)
ENV PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
