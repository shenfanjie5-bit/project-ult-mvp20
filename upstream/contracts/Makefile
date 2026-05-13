PYTHON ?= python3
PYTHONPATH ?= src
export PYTHONPATH

.PHONY: install install-shared test test-fast smoke regression lint typecheck ci

install:
	$(PYTHON) -m pip install -e ".[dev]"

# install-shared: pulls in the shared-fixtures extra (git+URL) needed by
# the regression tier. Use this for `make test` / `make regression`.
install-shared:
	$(PYTHON) -m pip install -e ".[dev,shared-fixtures]"

# regression tier — explicit entry so dev runs the real fixture-backed
# regression after `make install-shared`. Will hard-fail if
# audit_eval_fixtures is missing (no silent skip).
regression:
	$(PYTHON) -m pytest tests/regression -q

# Full test suite — legacy tests at tests/*.py + new canonical tier dirs
# (tests/unit, tests/boundary, tests/smoke, tests/regression).
test:
	$(PYTHON) -m pytest

# Fast lane for PR CI and local pre-commit. unit + boundary only.
test-fast:
	$(PYTHON) -m pytest tests/unit tests/boundary -q

# Minimal smoke — exercises public entrypoints. Infra-free.
smoke:
	$(PYTHON) -m pytest tests/smoke -q

lint:
	$(PYTHON) -m ruff check . || true

typecheck:
	$(PYTHON) -m mypy src tests || true

ci: test
