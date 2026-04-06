.PHONY: help install-client install-server install-dev dev-client dev-server \
        clean test lint format docker-build build-client build-server integration-local

PYTHON := python3
PIP    := pip
IMAGE_PREFIX := rgcc

help:
	@echo "RGCC - Remote GCC Compiler System"
	@echo ""
	@echo "Installation:"
	@echo "  Client:  pip install \"rgcc-client @ git+https://github.com/whaiman/remote-compiler.git#subdirectory=packages/rgcc-client\""
	@echo "  Server:  pip install \"rgcc-server @ git+https://github.com/whaiman/remote-compiler.git#subdirectory=packages/rgcc-server\""
	@echo ""
	@echo "Development:"
	@echo "  install-client   Install client locally (-e)"
	@echo "  install-server   Install server locally (-e)"
	@echo "  install-dev      Install both + dev tools"
	@echo "  dev-client       Run client dry-run"
	@echo "  dev-server       Run server in reload mode"
	@echo ""
	@echo "Quality:"
	@echo "  test             Run tests"
	@echo "  lint             Run linters"
	@echo "  format           Format code"
	@echo ""
	@echo "Docker:"
	@echo "  docker-build        Build server image"
	@echo "  docker-run-server   Run server container"
	@echo "  clean               Remove artifacts"

install-client:
	$(PIP) install -e packages/rgcc-client

install-server:
	$(PIP) install -e packages/rgcc-server

install-dev:
	$(PIP) install -e ".[dev]"

dev-client:
	rgcc compile sample/main.cpp --dry-run

dev-server:
	rgccd --host 127.0.0.1 --port 4444 --reload

test:
	pytest tests/ -v --tb=short

lint:
	ruff check rgcc/ tests/
	black --check rgcc/ tests/

format:
	ruff format rgcc/ tests/
	ruff check --fix rgcc/ tests/

docker-build:
	docker build -f Dockerfile.server -t $(IMAGE_PREFIX)-server:latest .

docker-run-server:
	docker run -p 4444:4444 \
		-v $(PWD)/.rgcc/server.config.yaml:/app/.rgcc/server.config.yaml \
		$(IMAGE_PREFIX)-server:latest

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete