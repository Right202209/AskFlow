.PHONY: dev test seed migrate lint clean docker-up docker-down create-user install-web dev-web build-web

PYTHON ?= python
PIP ?= pip

ifneq ("$(wildcard .venv/bin/python)","")
PYTHON := .venv/bin/python
PIP := .venv/bin/pip
endif

dev:
	uvicorn askflow.main:create_app --factory --reload --host 0.0.0.0 --port 8000

docker-up:
	docker compose up -d

docker-down:
	docker compose down

migrate:
	alembic upgrade head

migrate-create:
	alembic revision --autogenerate -m "$(msg)"

seed:
	$(PYTHON) scripts/seed_data.py

create-user:
	$(PYTHON) scripts/create_user.py --username $(username) --email $(email) --password $(password) --role $(role)

test:
	$(PYTHON) -m pytest tests/ -v --cov=src/askflow --cov-report=term-missing

lint:
	$(PYTHON) -m ruff check src/ tests/
	$(PYTHON) -m ruff format --check src/ tests/

format:
	$(PYTHON) -m ruff format src/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage dist build *.egg-info

install:
	$(PIP) install -e ".[dev]"

install-web:
	cd web && npm install

dev-web:
	cd web && npm run dev

build-web:
	cd web && npm run build
