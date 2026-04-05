.PHONY: help install install-client install-server install-dev dev clean test lint format docker-build docker-run

PYTHON := python3
PIP := pip
IMAGE_PREFIX := rgcc

help:
	@echo "RGCC - Remote GCC Compiler System (GitHub-only distribution)"
	@echo ""
	@echo "Installation (for users):"
	@echo "  pip install \"git+https://github.com/whaiman/remote-compiler.git#egg=remote-compiler[client]\""
	@echo "  pip install \"git+https://github.com/whaiman/remote-compiler.git#egg=remote-compiler[server]\""
	@echo ""
	@echo "Development:"
	@echo "  install-client  Install client locally (-e .[client])"
	@echo "  install-server  Install server locally (-e .[server])"
	@echo "  install-dev     Install all dev dependencies"
	@echo "  dev-client      Run client in dev mode"
	@echo "  dev-server      Run server in dev mode"
	@echo ""
	@echo "Quality:"
	@echo "  test            Run tests"
	@echo "  lint            Run linters"
	@echo "  format          Format code"
	@echo ""
	@echo "Docker:"
	@echo "  docker-build    Build images locally"
	@echo "  docker-run-server  Run server container"
	@echo "  clean           Remove artifacts"

# Local installation for dev
install-client:
	$(PIP) install -e ".[client]"

install-server:
	$(PIP) install -e ".[server]"

install-dev:
	$(PIP) install -e ".[dev]"

# Development
dev-client:
	rgcc compile sample/main.cpp --dry-run

dev-server:
	rgccd --host 127.0.0.1 --port 4444 --reload

# Test
test:
	pytest tests/ -v --tb=short
	python -c "import sys; from rgcc import client_main; assert 'starlette' not in sys.modules"
	python -c "import sys; from rgcc import server_main; assert 'rich' not in sys.modules"

lint:
	ruff check rgcc/ tests/
	black --check rgcc/ tests/

format:
	ruff format rgcc/ tests/
	ruff check --fix rgcc/ tests/

# Docker
docker-build:
	docker build -f Dockerfile.server -t $(IMAGE_PREFIX)-server:latest .
	docker build -f Dockerfile.client -t $(IMAGE_PREFIX)-client:latest .

docker-run-server:
	docker run -p 4444:4444 -v $(PWD)/config/server.config.yaml:/app/config/server.config.yaml $(IMAGE_PREFIX)-server:latest

docker-run-client:
	docker run --rm -it -v $(PWD):/workspace $(IMAGE_PREFIX)-client:latest compile /workspace/sample/main.cpp

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
