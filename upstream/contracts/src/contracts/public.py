"""Public integration entrypoints for assembly compatibility checks.

Mirrors ``audit_eval.public`` template (see audit-eval v0.2.0). Five
module-level singletons referenced by ``assembly/module-registry.yaml``
``module_id: contracts``:

- ``health_probe`` — verifies the contracts package boundary loads and
  the canonical schema namespace is non-empty
- ``smoke_hook`` — exercises the Pydantic models for the four Ex payload
  families to catch model-definition drift before assembly e2e even runs
- ``init_hook`` — no-op (contracts is pure schema, no IO/connections to
  initialize)
- ``version_declaration`` — returns the contracts module + contract
  version pulled from ``contracts.core.version``
- ``cli`` — argparse-based dispatcher to the existing ``contracts-export``
  and ``contracts-compat`` subcommands, plus a ``version`` subcommand

Boundary (contracts CLAUDE.md):
- This module does NOT import any business module (data-platform,
  main-core, etc.). Public-facing integration glue, schema-only.
- This module is NOT the source of truth for any field — Pydantic models
  in ``contracts.schemas`` and ``contracts.core`` remain the only schema
  source. ``public.py`` only exposes presence/version metadata.
"""

from __future__ import annotations

import argparse
import time
from typing import Any

from contracts.core.version import __version__ as _MODULE_VERSION

_MODULE_ID = "contracts"
_CONTRACT_VERSION = f"v{_MODULE_VERSION}"  # contracts is its own contract source
_COMPATIBLE_CONTRACT_RANGE = ">=0.1.0,<0.2.0"


class _HealthProbe:
    """Health probe — confirms the contracts package is importable and the
    schema namespace has well-formed Pydantic models.
    """

    _PROBE_NAME = "contracts.import"

    def check(self, *, timeout_sec: float) -> dict[str, Any]:
        start = time.monotonic()
        details: dict[str, Any] = {"timeout_sec": timeout_sec}
        try:
            from contracts import schemas as _schemas  # noqa: F401
            from contracts.schemas.ex_payloads import Ex0Metadata  # noqa: F401

            # Touch the model class to verify Pydantic model definitions
            # are well-formed.
            assert Ex0Metadata.model_fields, "Ex0Metadata has no fields"
            details["schema_namespace"] = "loaded"
            status = "healthy"
            message = "contracts package import healthy"
        except Exception as exc:  # pragma: no cover - degraded path
            status = "degraded"
            message = f"contracts import degraded: {exc!s}"
            details["error_type"] = type(exc).__name__
        latency_ms = (time.monotonic() - start) * 1000.0
        return {
            "module_id": _MODULE_ID,
            "probe_name": self._PROBE_NAME,
            "status": status,
            "latency_ms": latency_ms,
            "message": message,
            "details": details,
        }


class _SmokeHook:
    """Smoke hook — exercises the Ex0~Ex3 Pydantic models in-memory.

    Catches Pydantic model definition drift (e.g. wrong default factory,
    missing required field) before assembly e2e even tries to bootstrap.
    No IO, no infra dependencies — runs identically under lite-local and
    full-dev profiles.
    """

    _HOOK_NAME = "contracts.ex-payload-smoke"

    def run(self, *, profile_id: str) -> dict[str, Any]:
        start = time.monotonic()
        try:
            from contracts.schemas.ex_payloads import (  # noqa: F401
                Ex0Metadata,
                Ex1CandidateFact,
                Ex2CandidateSignal,
                Ex3CandidateGraphDelta,
            )

            # Each model must declare at least one field — guards against
            # accidental empty-model regressions.
            for model in (
                Ex0Metadata,
                Ex1CandidateFact,
                Ex2CandidateSignal,
                Ex3CandidateGraphDelta,
            ):
                assert model.model_fields, f"{model.__name__} has no fields"

            duration_ms = (time.monotonic() - start) * 1000.0
            return {
                "module_id": _MODULE_ID,
                "hook_name": self._HOOK_NAME,
                "passed": True,
                "duration_ms": duration_ms,
                "failure_reason": None,
                "details": {"profile_id": profile_id, "ex_models_checked": 4},
            }
        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000.0
            return {
                "module_id": _MODULE_ID,
                "hook_name": self._HOOK_NAME,
                "passed": False,
                "duration_ms": duration_ms,
                "failure_reason": f"contracts smoke failed: {exc!s}",
                "details": {"profile_id": profile_id},
            }


class _InitHook:
    """Init hook — no-op.

    contracts is pure schema; there is no PostgreSQL/Iceberg/Neo4j to
    initialize, no LLM client to construct. Kept here to satisfy the
    assembly Protocol contract.
    """

    def initialize(self, *, resolved_env: dict[str, str]) -> None:
        _ = resolved_env  # explicit unused-binding to silence linters
        return None


class _VersionDeclaration:
    """Version declaration — single source of truth for module + contract version."""

    def declare(self) -> dict[str, Any]:
        return {
            "module_id": _MODULE_ID,
            "module_version": _MODULE_VERSION,
            "contract_version": _CONTRACT_VERSION,
            "compatible_contract_range": _COMPATIBLE_CONTRACT_RANGE,
        }


class _Cli:
    """CLI entrypoint — minimal argparse dispatcher.

    Currently supports:
        version  — print module + contract version
        export   — forward to ``contracts.export.__main__:main``
        compat   — forward to ``contracts.compat.__main__:main``

    Returns POSIX exit codes (0 ok, 2 invalid usage). The argv parameter
    is positional-or-keyword to match the ``CliEntrypoint`` protocol.
    """

    _PROG = "contracts"

    def invoke(self, argv: list[str]) -> int:
        parser = argparse.ArgumentParser(
            prog=self._PROG,
            description="contracts public CLI",
        )
        parser.add_argument(
            "subcommand",
            nargs="?",
            default="version",
            choices=("version", "export", "compat"),
            help="subcommand to run (default: version)",
        )
        try:
            # Parse only the leading subcommand; the rest is forwarded.
            args, remaining = parser.parse_known_args(argv)
        except SystemExit as exc:
            return int(exc.code) if exc.code is not None else 2

        if args.subcommand == "version":
            info = _VersionDeclaration().declare()
            print(
                f"{info['module_id']} {info['module_version']} "
                f"(contract {info['contract_version']})"
            )
            return 0
        if args.subcommand == "export":
            from contracts.export.__main__ import main as export_main

            return int(export_main(remaining) or 0)
        if args.subcommand == "compat":
            from contracts.compat.__main__ import main as compat_main

            return int(compat_main(remaining) or 0)
        return 2


# Module-level singletons — these are the names referenced by
# assembly/module-registry.yaml ("contracts.public:health_probe", etc.).
health_probe: _HealthProbe = _HealthProbe()
smoke_hook: _SmokeHook = _SmokeHook()
init_hook: _InitHook = _InitHook()
version_declaration: _VersionDeclaration = _VersionDeclaration()
cli: _Cli = _Cli()


__all__ = [
    "cli",
    "health_probe",
    "init_hook",
    "smoke_hook",
    "version_declaration",
]
