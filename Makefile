PYTHON ?= python3.12
API_DIR := apps/api
WEB_DIR := apps/web
VENV := $(API_DIR)/.venv
VBIN := $(VENV)/bin

.DEFAULT_GOAL := help
.PHONY: help install install-api install-web dev dev-api dev-web test test-api test-web e2e lint lint-api lint-web fmt

help: ## Show available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: install-api install-web ## Install all dependencies

install-api: ## Create backend venv and install deps
	$(PYTHON) -m venv $(VENV)
	$(VBIN)/pip install -q --upgrade pip
	$(VBIN)/pip install -q -e "$(API_DIR)[dev]"

install-web: ## Install frontend deps
	@if [ -f $(WEB_DIR)/package.json ]; then cd $(WEB_DIR) && pnpm install; else echo "web app not scaffolded yet"; fi

dev-api: ## Run FastAPI with reload on :8000
	cd $(API_DIR) && .venv/bin/uvicorn app.main:app --reload --port 8000

dev-web: ## Run Next.js dev server on :3000
	cd $(WEB_DIR) && pnpm dev

dev: ## Run backend and frontend together
	$(MAKE) -j2 dev-api dev-web

test: test-api test-web ## Run all tests

test-api: ## Run backend tests
	cd $(API_DIR) && .venv/bin/pytest

test-web: ## Run frontend tests
	@if [ -f $(WEB_DIR)/package.json ]; then cd $(WEB_DIR) && pnpm test; else echo "web app not scaffolded yet"; fi

e2e: ## Playwright end-to-end run (mock mode; uses local Chrome; stop `make dev` first)
	cd $(WEB_DIR) && pnpm e2e

lint: lint-api lint-web ## Lint everything

lint-api: ## Ruff + mypy
	cd $(API_DIR) && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy app

lint-web: ## ESLint
	@if [ -f $(WEB_DIR)/package.json ]; then cd $(WEB_DIR) && pnpm lint; else echo "web app not scaffolded yet"; fi

fmt: ## Auto-format backend
	cd $(API_DIR) && .venv/bin/ruff format . && .venv/bin/ruff check --fix .
