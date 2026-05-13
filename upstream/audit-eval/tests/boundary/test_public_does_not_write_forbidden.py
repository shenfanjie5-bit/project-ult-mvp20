"""Boundary tests for audit-eval public entrypoints.

audit-eval's CLAUDE.md C3 forbids writing ``feature_weight_multiplier``.
The public entrypoints must not, even by accident, surface a payload
containing this field — they are the integration boundary that assembly
will exercise on every Lite/Full bootstrap.
"""

from __future__ import annotations

from audit_eval import public
from audit_eval._boundary import (
    BoundaryViolationError,
    assert_no_forbidden_write,
)


class TestHealthProbeBoundary:
    def test_health_dict_contains_no_forbidden_field(self) -> None:
        result = public.health_probe.check(timeout_sec=1.0)

        # Must not raise — assert_no_forbidden_write scans nested dict/list.
        assert_no_forbidden_write(result)

    def test_boundary_does_detect_forbidden_in_polluted_payload(self) -> None:
        # Self-test: confirm the boundary check would catch a violation.
        polluted = dict(public.health_probe.check(timeout_sec=1.0))
        polluted["feature_weight_multiplier"] = 1.5

        try:
            assert_no_forbidden_write(polluted)
        except BoundaryViolationError as exc:
            assert "feature_weight_multiplier" in str(exc)
        else:
            raise AssertionError("expected BoundaryViolationError")


class TestSmokeHookBoundary:
    def test_smoke_dict_contains_no_forbidden_field(self) -> None:
        result = public.smoke_hook.run(profile_id="lite-local")

        assert_no_forbidden_write(result)


class TestVersionDeclarationBoundary:
    def test_version_dict_contains_no_forbidden_field(self) -> None:
        result = public.version_declaration.declare()

        assert_no_forbidden_write(result)


class TestPublicModuleHasNoLLMOrInfraImports:
    """audit-eval public.py must not pull in heavy infra at import time.

    Importing public should never:
      - require a live PostgreSQL/Iceberg/Neo4j connection
      - instantiate any LLM client
      - load model weights or large fixtures

    We assert this indirectly by checking that no module in
    ``sys.modules`` after importing public matches a denylist of heavy
    runtime modules.
    """

    DENY_PREFIXES = (
        "psycopg",          # PostgreSQL driver
        "pyiceberg",        # Iceberg client
        "neo4j",            # Neo4j driver
        "litellm",          # LLM gateway
        "openai",           # LLM client
        "anthropic",        # LLM client
        "torch",            # ML
        "tensorflow",       # ML
    )

    def test_no_heavy_runtime_modules_loaded(self) -> None:
        import importlib
        import sys

        # Force a fresh import of public so we observe its transitive imports.
        if "audit_eval.public" in sys.modules:
            del sys.modules["audit_eval.public"]
        importlib.import_module("audit_eval.public")

        offenders = sorted(
            mod
            for mod in sys.modules
            if any(mod == p or mod.startswith(p + ".") for p in self.DENY_PREFIXES)
        )

        assert not offenders, (
            f"public.py pulled in heavy runtime modules at import: {offenders}"
        )
