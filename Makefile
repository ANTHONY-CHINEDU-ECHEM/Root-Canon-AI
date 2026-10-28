# Root Canon AI: every common task. Run `make help` for the list.
PY ?= python
NPM ?= npm
COMPOSE ?= docker compose

.DEFAULT_GOAL := help
.PHONY: help install install_dev seed serve frontend up down logs ingest ingest_quick reindex stats \
        test lint format typecheck eval eval_gate eval_live check demo_build readme diagram ask clean

help: ## Show this list
	@grep -E '^[a-z_]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[1m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Python (all extras) and frontend dependencies
	$(PY) -m pip install -e ".[all,dev]"
	cd frontend && $(NPM) ci

install_dev: ## Lightweight install for offline development and CI (no model weights)
	$(PY) -m pip install -e ".[dev]"

seed: ## Index the bundled UK guidance seed set in seconds
	$(PY) -m ingestion.cli seed

serve: ## API on port 8000 with reload
	$(PY) -m uvicorn backend.app.main:app --reload --port 8000

frontend: ## Clinician interface on port 5173
	cd frontend && $(NPM) run dev

up: ## Full stack in containers: API, Qdrant, Redis, interface, Prometheus, Grafana
	$(COMPOSE) up -d --build

down: ## Stop the stack
	$(COMPOSE) down

logs: ## Follow API logs
	$(COMPOSE) logs -f api

ingest: ## Harvest every source into the index (several hours)
	$(PY) -m ingestion.cli ingest --sources all

ingest_quick: ## Capped harvest for development
	$(PY) -m ingestion.cli ingest --sources all --limit 200

reindex: ## Rebuild the indexes from data/raw without calling any API
	$(PY) -m ingestion.cli ingest --from-raw

stats: ## Print the current index manifest
	$(PY) -m ingestion.cli stats

test: ## Unit, pipeline and API tests with coverage
	$(PY) -m pytest --cov --cov-report=term --cov-report=xml

lint: ## Ruff lint and README style gate
	$(PY) -m ruff check backend ingestion evaluation scripts tests
	$(PY) -m scripts.build_readme --check

format: ## Apply safe lint fixes
	$(PY) -m ruff check --fix backend ingestion evaluation scripts tests

typecheck: ## Mypy over the Python packages, tsc over the interface
	$(PY) -m mypy
	cd frontend && $(NPM) run typecheck

eval: ## Offline evaluation report (seed index, extractive generator)
	$(PY) -m evaluation.run_eval --markdown evaluation/results/latest.md

eval_gate: ## Offline evaluation that fails on any threshold in evaluation/thresholds.yaml
	$(PY) -m evaluation.run_eval --gate --markdown evaluation/results/latest.md

eval_live: ## Evaluation against the live index and Claude, with a model judge
	$(PY) -m evaluation.run_eval --provider anthropic --judge anthropic --out evaluation/results/live.json \
		--markdown evaluation/results/live.md

check: lint typecheck test eval_gate ## Everything CI runs

demo_build: ## Rebuild the standalone demo page from the seed corpus
	$(PY) -m scripts.build_demo

readme: ## Rebuild README.md from docs/README.template.md, keeping the diagram in sync
	$(PY) -m scripts.build_readme

diagram: ## Regenerate docs/architecture.svg
	$(PY) -m scripts.draw_architecture

ask: ## Ask from the terminal, e.g. make ask Q="amoxicillin dose for a 3 year old"
	$(PY) -m backend.app.cli ask "$(Q)"

clean: ## Remove caches and build output
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml frontend/dist
