# ---- 1. Build the React app -------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Django API + built SPA in one image ----------------------------------
FROM python:3.12-slim
# One malloc arena. The default (one per thread) reserves ~64 MiB each and
# blows the 128 MiB host limit as soon as a forecast runs.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_DEBUG=0 PORT=8000 MALLOC_ARENA_MAX=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
# Present in the image so a read-only runtime does not try to create it.
RUN mkdir -p /app/backend/staticfiles
COPY --from=frontend /app/frontend/dist /app/frontend/dist
EXPOSE 8000
# One worker, two threads: a forecast can run while a health check still gets through.
CMD sh -c "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT} --workers 1 --threads 2 --timeout 90 --no-control-socket"
