# graph-engine Makefile — stage-2.10 plan canonical lane targets.
#
# Per stage-2 plan iron rules:
# - test-fast / smoke run only against [dev] (offline-first per
#   SUBPROJECT_TESTING_STANDARD §2.2).
# - contract: also installs [contracts-schemas] for cross-repo align.
# - regression: installs [shared-fixtures] for real audit_eval_fixtures.
# - full(ci): installs all extras, runs the entire test suite.
#
# **2-step install order** (NOT 3-step like announcement / news —
# graph-engine does NOT depend on subsystem-sdk; it CONSUMES Ex-3 from
# contracts directly). This matches entity-registry's pattern:
#   1. pip install contracts@v0.1.3
#   2. pip install -e ".[<lane extras>]"
# The 2-step preinstall pattern is wired into EVERY install target so
# callers can't accidentally skip step 1.

PYTHON ?= python3.12
PIP    := $(PYTHON) -m pip
PYTEST := $(PYTHON) -m pytest

CONTRACTS_PIN := git+https://github.com/shenfanjie5-bit/project-ult-contracts.git@v0.1.3

.PHONY: help \
        install-dev install-contracts-schemas install-shared install-all \
        test-fast smoke contract regression test ci clean

help:
	@echo "Targets (all install targets are 2-step: contracts -> repo;"
	@echo " no subsystem-sdk dependency — graph-engine consumes Ex-3 directly):"
	@echo "  install-dev               — preinstall pinned contracts + pip install -e .[dev]"
	@echo "  install-contracts-schemas — preinstall pinned contracts + pip install -e .[dev,contracts-schemas]"
	@echo "  install-shared            — preinstall pinned contracts + pip install -e .[dev,shared-fixtures]"
	@echo "  install-all               — preinstall pinned contracts + pip install -e .[dev,contracts-schemas,shared-fixtures]"
	@echo "  test-fast                 — tests/unit + tests/boundary"
	@echo "  smoke                     — tests/smoke"
	@echo "  contract                  — tests/contract (incl. cross-repo align)"
	@echo "  regression                — tests/regression (real audit_eval_fixtures + case_ex3_negative)"
	@echo "  test                      — full pytest collection"
	@echo "  ci                        — install-all + test (used by CI full(ci))"

install-dev:
	$(PIP) install "$(CONTRACTS_PIN)"
	$(PIP) install -e ".[dev]"

install-contracts-schemas:
	$(PIP) install "$(CONTRACTS_PIN)"
	$(PIP) install -e ".[dev,contracts-schemas]"

install-shared:
	$(PIP) install "$(CONTRACTS_PIN)"
	$(PIP) install -e ".[dev,shared-fixtures]"

install-all:
	$(PIP) install "$(CONTRACTS_PIN)"
	$(PIP) install -e ".[dev,contracts-schemas,shared-fixtures]"

test-fast:
	$(PYTEST) tests/unit tests/boundary -q

smoke:
	$(PYTEST) tests/smoke -q

contract:
	$(PYTEST) tests/contract -q

regression:
	$(PYTEST) tests/regression -q

test:
	$(PYTEST)

ci: install-all test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
