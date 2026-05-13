PYTHON ?= python3
PYTHONPATH ?= src:../contracts/src
export PYTHONPATH

.PHONY: install install-shared install-contracts-schemas install-all \
        test test-fast smoke contract regression \
        lint typecheck

install:
	$(PYTHON) -m pip install -e ".[dev]"

install-shared:
	$(PYTHON) -m pip install -e ".[dev,shared-fixtures]"

install-contracts-schemas:
	$(PYTHON) -m pip install -e ".[dev,contracts-schemas]"

install-all:
	$(PYTHON) -m pip install -e ".[dev,contracts-schemas,shared-fixtures]"

test:
	$(PYTHON) -m pytest

test-fast:
	$(PYTHON) -m pytest tests/unit tests/boundary -q

smoke:
	$(PYTHON) -m pytest tests/smoke -q

contract:
	$(PYTHON) -m pytest tests/contract -q

regression:
	$(PYTHON) -m pytest tests/regression -q

lint:
	$(PYTHON) -m ruff check . || true

typecheck:
	$(PYTHON) -m mypy src tests || true
