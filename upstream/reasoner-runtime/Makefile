PYTHON ?= python3
PYTHONPATH ?= .:../contracts/src
export PYTHONPATH

.PHONY: install install-shared test test-fast smoke regression lint typecheck ci

# Pure-pip dev install — offline-first per SUBPROJECT_TESTING_STANDARD.md §2.2.
# Used by test-fast / smoke lanes.
install:
	$(PYTHON) -m pip install -e ".[dev]"

# install-shared adds the shared-fixtures git extra needed by tests/regression.
install-shared:
	$(PYTHON) -m pip install -e ".[dev,shared-fixtures]"

# Full suite — legacy tests/unit + tests/integration + new canonical tier
# dirs (tests/{boundary,smoke,regression,contract}). pytest collects all.
test:
	$(PYTHON) -m pytest

# Fast lane for PR CI and local pre-commit. unit + boundary only.
test-fast:
	$(PYTHON) -m pytest tests/unit tests/boundary -q

# Minimal smoke — exercises public entrypoints. Infra-free.
smoke:
	$(PYTHON) -m pytest tests/smoke -q

# Regression tier — explicit entry. Hard-fails when audit_eval_fixtures
# is not installed (no silent skip).
regression:
	$(PYTHON) -m pytest tests/regression -q

lint:
	$(PYTHON) -m ruff check . || true

typecheck:
	$(PYTHON) -m mypy reasoner_runtime tests || true

ci: test
