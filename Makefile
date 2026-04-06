.PHONY: help install install-dev dev-client dev-server \
        clean test lint format docker-build docker-run-server

PYTHON := python
PIP    := pip
IMAGE_PREFIX := rgcc

help:
	@echo "RGCC - Remote GCC Compiler System"
	@echo ""
	@echo "Installation:"
	@echo "  install           Install the unified package locally (-e .)"
	@echo "  install-dev       Install both + dev tools (-e \".[dev]\")"
	@echo ""
	@echo "Development:"
	@echo "  dev-client        Run client dry-run (sample/main.cpp)"
	@echo "  dev-server        Run server on 127.0.0.1:4444 (reload mode)"
	@echo ""
	@echo "Docker:"
	@echo "  docker-build      Build server image"
	@echo "  docker-run-server Run server container"
	@echo ""
	@echo "Quality & Cleanup:"
	@echo "  test              Run tests"
	@echo "  lint              Run ruff + black check"
	@echo "  format            Run ruff format + fix"
	@echo "  clean             Remove build artifacts and caches (deep clean)"

install:
	$(PIP) install -e .

install-dev:
	$(PIP) install -e ".[dev]"

dev-client:
	rgcc compile sample/main.cpp --dry-run

dev-server:
	rgccd --host 127.0.0.1 --port 4444 --reload

test:
	pytest tests/ -v --tb=short

lint:
	$(PYTHON) -m ruff check rgcc/ tests/
	$(PYTHON) -m black --check rgcc/ tests/

format:
	$(PYTHON) -m ruff format rgcc/ tests/
	$(PYTHON) -m ruff check --fix rgcc/ tests/

docker-build:
	docker build -f Dockerfile.server -t $(IMAGE_PREFIX)-server:latest .

docker-run-server:
	docker run -p 4444:4444 \
		-v $(PWD)/rgccd.yaml:/app/rgccd.yaml \
		$(IMAGE_PREFIX)-server:latest

clean:
	$(PYTHON) clean.py