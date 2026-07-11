.PHONY: dev test seed migrate lint clean docker-up docker-down create-user install-web dev-web build-web eval eval-seed eval-report

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

eval: ## 对本地栈跑离线评估套件（需先 make eval-seed）
	$(PYTHON) -m eval.harness.run_eval --suite all

eval-seed: ## （重）播种评估语料文档并写出 corpus_map.json
	$(PYTHON) -m eval.harness.seed_corpus

eval-report: ## 查看最近若干轮评估的质量趋势（回归时非零退出）
	$(PYTHON) -m eval.harness.report --last 10

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
