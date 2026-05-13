PYTHON ?= python3
PYTHONPATH ?= src
PYTHONDONTWRITEBYTECODE ?= 1
export PYTHONPATH
export PYTHONDONTWRITEBYTECODE

.PHONY: install install-backtest test test-fast smoke lint typecheck bytecode-clean backtest-smoke ci

install:
	$(PYTHON) -m pip install -e ".[dev]"

install-backtest:
	$(PYTHON) -m pip install -e ".[dev,backtest]"

# Full test suite — legacy tests remain in tests/ root, new canonical-tier
# tests live under tests/{unit,boundary,smoke,...}. pytest collects both.
test:
	$(PYTHON) -m pytest

# Fast lane for PR CI and local pre-commit. unit + boundary only — no smoke
# (smoke can hit infra-touching hooks even if currently no-op).
test-fast:
	$(PYTHON) -m pytest tests/unit tests/boundary -q

# Minimal smoke — exercises public entrypoints. Must stay infra-free.
smoke:
	$(PYTHON) -m pytest tests/smoke -q

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy src tests

bytecode-clean:
	test -z "$$(find . -path './.venv' -prune -o \( -path '*/__pycache__/*' -o -name '*.pyc' -o -name '*.pyo' \) -print -quit)"

backtest-smoke:
	AUDIT_EVAL_REQUIRE_ALPHALENS_SMOKE=1 $(PYTHON) -m pytest tests/test_alphalens_adapter.py::test_alphalens_adapter_smoke_with_installed_dependency

ci: lint typecheck test bytecode-clean
