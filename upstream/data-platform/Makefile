PYTHON ?= python3
PYTHONPATH ?= src
export PYTHONPATH

.PHONY: install install-shared install-contracts-schemas install-all \
        test test-fast smoke contract regression \
        smoke-p1a smoke-p1c

# Pure-pip dev install — offline-first per SUBPROJECT_TESTING_STANDARD.md §2.2.
install:
	$(PYTHON) -m pip install -e ".[dev]"

# install-shared adds the shared-fixtures git extra needed by tests/regression.
install-shared:
	$(PYTHON) -m pip install -e ".[dev,shared-fixtures]"

# install-contracts-schemas adds the contracts git extra needed by the
# cross-repo alignment block in tests/contract/test_contracts_alignment.py.
install-contracts-schemas:
	$(PYTHON) -m pip install -e ".[dev,contracts-schemas]"

# install-all gives the full offline+online dev environment (used by
# the `ci` lane): dev + contracts-schemas + shared-fixtures.
install-all:
	$(PYTHON) -m pip install -e ".[dev,contracts-schemas,shared-fixtures]"

# Full suite — legacy tests/* + new canonical tier dirs.
test:
	$(PYTHON) -m pytest

# Fast lane for PR CI and local pre-commit. unit + boundary only.
test-fast:
	$(PYTHON) -m pytest tests/unit tests/boundary -q

# Minimal smoke — exercises public entrypoints. Infra-free.
smoke:
	$(PYTHON) -m pytest tests/smoke -q

# Contract tier — runs both self-check and cross-repo alignment
# (latter requires `make install-contracts-schemas` to fully exercise).
contract:
	$(PYTHON) -m pytest tests/contract -q

# Regression tier — explicit entry. Hard-fails when audit_eval_fixtures
# is not installed (no silent skip per iron rule #1).
regression:
	$(PYTHON) -m pytest tests/regression -q

# Existing repo-specific smoke scripts kept (P1a / P1c data layer probes).
smoke-p1a:
	@scripts/smoke_p1a.sh

smoke-p1c:
	@./scripts/smoke_p1c.sh
