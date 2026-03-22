.PHONY: install dev test lint format

install:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	cd frontend && npm install

dev:
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	pytest -v --cov=backend

lint:
	ruff check backend/
	mypy backend/

format:
	ruff format backend/
