.PHONY: help install install-dev dev-client dev-server \
	clean test lint format docker-build docker-run-server

PYTHON := python
PIP := pip
IMAGE_PREFIX := rgcc

help:
	@echo "RGCC - Remote GCC System"
	@echo ""
	@echo "Installation:"
	@echo "  install           Install the unified package (-e ., requires a venv)"
	@echo "  install-dev       Install + dev tools (-e \".[dev]\", requires a venv)"
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

# Guard for pip targets: refuses to run outside a virtual environment.
# The check is done by the interpreter itself (sys.prefix vs sys.base_prefix),
# not by shell syntax, so it behaves identically on Linux, macOS and Windows -
# under sh, Git Bash, WSL, and even cmd.exe with mingw32-make.
check-venv:
	@$(PYTHON) -c "import sys; sys.exit(0) if sys.prefix != sys.base_prefix else sys.exit('ERROR: this target runs pip and needs a virtual environment.\n\nCreate and activate one first:\n  python -m venv .venv\n  source .venv/bin/activate         (bash, zsh)\n  source .venv/bin/activate.fish    (fish)\n  .venv/Scripts/Activate.ps1        (Windows PowerShell)\n  .venv/Scripts/activate.bat        (Windows cmd)\n\nThen re-run: make $(MAKECMDGOALS)\n\nEveryday use without development: install with pipx or uv - see README.md, Installation.')"

install: check-venv
	$(PIP) install -e .

install-dev: check-venv
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
	-v $(CURDIR)/rgccd.yaml:/app/rgccd.yaml \
        $(IMAGE_PREFIX)-server:latest

clean:
	$(PYTHON) clean.py