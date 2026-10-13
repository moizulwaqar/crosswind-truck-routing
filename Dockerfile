# ---- 1. Build the React app -------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Django API + built SPA in one image ----------------------------------
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_DEBUG=0 PORT=8000 \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    PATH="/app/backend/.venv/bin:$PATH"
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/ ./
# Present in the image so a read-only runtime does not try to create it.
RUN mkdir -p /app/backend/staticfiles
COPY --from=frontend /app/frontend/dist /app/frontend/dist
EXPOSE 8000
# Threads let one worker overlap the slow third-party HTTP calls.
CMD sh -c "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 90"
