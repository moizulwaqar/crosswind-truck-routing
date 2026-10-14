# Local commands. Production still builds from the Dockerfile.
.PHONY: setup test backend frontend demo

setup:
	cd backend && uv sync
	cd frontend && npm ci

test:
	cd backend && uv run pytest

backend:
	cd backend && uv run python manage.py runserver 127.0.0.1:8000

frontend:
	cd frontend && npm run dev

demo:
	cd backend && FAKE_PROVIDERS=1 uv run python manage.py runserver 127.0.0.1:8000
