VENV ?= $(HOME)/.venvs/codectx
PYTHON := $(VENV)/bin/python

SRC_DIR := src
TEST_DIR := tests
PACKAGE := codectx
PYTEST_FLAGS ?= -s
ARTIFACT := dist/codectx.pex
ARTIFACT_PLATFORMS ?= \
	--platform manylinux2014_x86_64-cp-311-cp311 \
	--platform manylinux2014_x86_64-cp-312-cp312 \
	--platform win_amd64-cp-311-cp311 \
	--platform win_amd64-cp-312-cp312
PEX_FLAGS ?= --venv --python-shebang "/usr/bin/env python3"
PEX_RESOLVE_FLAGS ?= \
	--only-binary tree-sitter \
	--only-binary tree-sitter-cpp \
	--only-binary tree-sitter-go \
	--only-binary tree-sitter-java \
	--only-binary tree-sitter-matlab \
	--only-binary tree-sitter-python \
	--only-binary tree-sitter-rust

.PHONY: \
	help setup-venv install-dev \
	format format-check \
	lint typecheck dead-code reachability \
	test architecture coverage coverage-report \
	package package-smoke artifact artifact-smoke release-ci clean ci

help:
	@echo "codectx Makefile targets:"
	@echo "  make setup-venv     - Create shared virtual environment at $(VENV)"
	@echo "  make install-dev    - Install current checkout with dev dependencies"
	@echo "  make format         - Run Ruff formatting"
	@echo "  make format-check   - Check Ruff formatting"
	@echo "  make lint           - Run Ruff linting"
	@echo "  make typecheck      - Run mypy static checks"
	@echo "  make dead-code      - Run Vulture dead-code checks"
	@echo "  make reachability   - Run mypy and Vulture reachability checks"
	@echo "  make test           - Run the test suite"
	@echo "  make architecture   - Run architecture-focused tests"
	@echo "  make coverage       - Run tests and enforce 90% per-file coverage"
	@echo "  make coverage-report - Run tests with terminal and JSON coverage reporting"
	@echo "  make package        - Build source and wheel distributions"
	@echo "  make package-smoke  - Build and smoke-test installed source/wheel artifacts"
	@echo "  make artifact       - Build one Linux/Windows runnable PEX artifact at $(ARTIFACT)"
	@echo "  make artifact-smoke - Build and smoke-test the PEX artifact"
	@echo "  make release-ci     - Run CI gates and smoke-test release artifacts"
	@echo "  make clean          - Remove local build and test artifacts"
	@echo "  make ci             - Run format-check, lint, reachability, architecture, and coverage gates"

$(PYTHON):
	mkdir -p "$(dir $(VENV))"
	python3 -m venv "$(VENV)"

setup-venv: $(PYTHON)

install-dev: $(PYTHON)
	"$(PYTHON)" -m pip install --upgrade pip
	"$(PYTHON)" -m pip install -e .[dev]

format:
	"$(PYTHON)" -m ruff format $(SRC_DIR) $(TEST_DIR) scripts

format-check:
	"$(PYTHON)" -m ruff format --check $(SRC_DIR) $(TEST_DIR) scripts

lint:
	"$(PYTHON)" -m ruff check $(SRC_DIR) $(TEST_DIR) scripts

typecheck:
	"$(PYTHON)" -m mypy $(SRC_DIR)

dead-code:
	"$(PYTHON)" -m vulture

reachability: typecheck dead-code

test:
	"$(PYTHON)" -m pytest $(PYTEST_FLAGS)

architecture:
	"$(PYTHON)" -m pytest $(PYTEST_FLAGS) tests/architecture

coverage-report:
	"$(PYTHON)" -m pytest $(PYTEST_FLAGS) --cov=$(PACKAGE) --cov-report=term-missing --cov-report=json:coverage.json

coverage: coverage-report
	"$(PYTHON)" scripts/check_coverage.py --input coverage.json --threshold 90

package:
	"$(PYTHON)" -m build --no-isolation

package-smoke: package
	"$(PYTHON)" scripts/smoke_release_artifacts.py

artifact:
	mkdir -p "$(dir $(ARTIFACT))"
	"$(PYTHON)" -m pex --project . -c codectx -o "$(ARTIFACT)" $(ARTIFACT_PLATFORMS) $(PEX_FLAGS) $(PEX_RESOLVE_FLAGS)

artifact-smoke: artifact
	"$(PYTHON)" "$(ARTIFACT)" --version
	"$(PYTHON)" "$(ARTIFACT)" --help >/dev/null
	tmp_dir="$$(mktemp -d)"; \
	trap 'rm -rf "$$tmp_dir"' EXIT; \
	set -e; \
	"$(PYTHON)" "$(ARTIFACT)" index tests/fixtures/java_basic --db "$$tmp_dir/graph.sqlite" --rebuild >/dev/null; \
	"$(PYTHON)" "$(ARTIFACT)" context --repo tests/fixtures/java_basic --db "$$tmp_dir/graph.sqlite" --file src/main/java/acme/PaymentService.java --goal explain --budget 1000 --format json >/dev/null; \
	"$(PYTHON)" "$(ARTIFACT)" index tests/fixtures/python_basic --db "$$tmp_dir/python.sqlite" --rebuild >/dev/null; \
	"$(PYTHON)" "$(ARTIFACT)" context --repo tests/fixtures/python_basic --db "$$tmp_dir/python.sqlite" --file src/payments/service.py --goal explain --budget 1000 --format json >/dev/null; \
	"$(PYTHON)" "$(ARTIFACT)" index tests/fixtures/matlab_basic --db "$$tmp_dir/matlab.sqlite" --rebuild >/dev/null; \
	"$(PYTHON)" "$(ARTIFACT)" context --repo tests/fixtures/matlab_basic --db "$$tmp_dir/matlab.sqlite" --file src/PaymentService.m --goal explain --budget 1000 --format json >/dev/null; \
	"$(PYTHON)" "$(ARTIFACT)" index tests/fixtures/go_basic --db "$$tmp_dir/go.sqlite" --rebuild >/dev/null; \
	"$(PYTHON)" "$(ARTIFACT)" context --repo tests/fixtures/go_basic --db "$$tmp_dir/go.sqlite" --file service.go --goal explain --budget 1000 --format json >/dev/null; \
	"$(PYTHON)" "$(ARTIFACT)" index tests/fixtures/rust_basic --db "$$tmp_dir/rust.sqlite" --rebuild >/dev/null; \
	"$(PYTHON)" "$(ARTIFACT)" context --repo tests/fixtures/rust_basic --db "$$tmp_dir/rust.sqlite" --file src/lib.rs --goal explain --budget 1000 --format json >/dev/null

release-ci: ci package-smoke artifact-smoke

clean:
	rm -rf build dist .coverage .mypy_cache .pytest_cache .ruff_cache *.egg-info src/*.egg-info coverage.json htmlcov coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

ci: format-check lint reachability architecture coverage
