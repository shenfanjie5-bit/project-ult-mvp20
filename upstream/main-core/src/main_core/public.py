"""Public integration entrypoints for assembly compatibility checks.

Mirrors the audit-eval / contracts / reasoner-runtime public.py templates
(see project-ult test rollout plan stage 2). Five module-level singletons
referenced by ``assembly/module-registry.yaml`` ``module_id: main-core``:

- ``health_probe`` — verifies the main_core package boundary loads and
  the formal object schema namespace is non-empty
- ``smoke_hook`` — exercises the L4 / L5 / L6 / L7 formal object Pydantic
  models in-memory to catch model-definition drift before assembly e2e
  even bootstraps (no LLM call, no DB)
- ``init_hook`` — no-op (main-core owns no DB connection; PostgreSQL /
  Iceberg / Neo4j are owned by data-platform / graph-engine respectively)
- ``version_declaration`` — returns the main_core module + contract
  version
- ``cli`` — argparse-based dispatcher with a ``version`` subcommand

Boundary (main-core CLAUDE.md):
- This module does NOT make any live LLM call (LLM runtime owned by
  reasoner-runtime per BAN list)
- This module does NOT touch the database (raw data ingestion owned by
  data-platform per BAN list)
- This module does NOT write audit_record / replay_record (owned by
  audit-eval per BAN list)
"""

from __future__ import annotations

import argparse
import time
from typing import Any

from main_core import __version__ as _MODULE_VERSION_RAW

_MODULE_ID = "main-core"
# main_core/__init__.py declares __version__ already; fall back if absent.
_MODULE_VERSION = _MODULE_VERSION_RAW if isinstance(_MODULE_VERSION_RAW, str) else "0.1.1"
# Stage 4 §4.1.5: contract_version is the canonical contracts schema version
# this module is bound against (NOT this module's own package version, which
# stays in module_version). Harmonized to v0.1.3 across all 11 active
# subsystem modules so assembly's ContractsVersionCheck (strict equality vs
# matrix.contract_version) succeeds at the cross-project compat audit
# (assembly/scripts/stage_3_compat_audit.py + Stage 4 §4.1 registry).
_CONTRACT_VERSION = "v0.1.3"
_COMPATIBLE_CONTRACT_RANGE = ">=0.1.3,<0.2.0"


class _HealthProbe:
    """Health probe — confirms the main_core package is importable and
    the formal-object schema namespace has well-formed Pydantic models.

    Never raises; degrades to ``status="degraded"`` so ``make smoke`` can
    run without any infra.
    """

    _PROBE_NAME = "main-core.import"

    def check(self, *, timeout_sec: float) -> dict[str, Any]:
        start = time.monotonic()
        details: dict[str, Any] = {"timeout_sec": timeout_sec}
        try:
            from main_core.common import schemas as _schemas  # noqa: F401
            from main_core.common.schemas.world_state import (  # noqa: F401
                WorldStateSnapshot,
            )

            assert WorldStateSnapshot.model_fields, "WorldStateSnapshot has no fields"
            details["schema_namespace"] = "loaded"
            status = "healthy"
            message = "main-core package import healthy"
        except Exception as exc:  # pragma: no cover - degraded path
            status = "degraded"
            message = f"main-core import degraded: {exc!s}"
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
    """Smoke hook — exercises the four critical formal-object Pydantic
    models in-memory.

    Per main-core §10 重点 / §16.3 the four formal objects whose schema
    drift would break downstream consumers (assembly, audit-eval, dashboard)
    are: WorldStateSnapshot, OfficialAlphaPool, AlphaResultSnapshot,
    RecommendationSnapshot. Smoke checks they import and declare ≥1 field
    each.

    Profile-aware: ``lite-local`` and ``full-dev`` both run identically.
    """

    _HOOK_NAME = "main-core.formal-object-smoke"

    def run(self, *, profile_id: str) -> dict[str, Any]:
        start = time.monotonic()
        try:
            from main_core.common.schemas.world_state import WorldStateSnapshot
            from main_core.common.schemas.pool import OfficialAlphaPool
            from main_core.common.schemas.alpha import AlphaResultSnapshot
            from main_core.common.schemas.recommendation import RecommendationSnapshot

            for model in (
                WorldStateSnapshot,
                OfficialAlphaPool,
                AlphaResultSnapshot,
                RecommendationSnapshot,
            ):
                assert model.model_fields, f"{model.__name__} has no fields"

            duration_ms = (time.monotonic() - start) * 1000.0
            return {
                "module_id": _MODULE_ID,
                "hook_name": self._HOOK_NAME,
                "passed": True,
                "duration_ms": duration_ms,
                "failure_reason": None,
            }
        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000.0
            return {
                "module_id": _MODULE_ID,
                "hook_name": self._HOOK_NAME,
                "passed": False,
                "duration_ms": duration_ms,
                "failure_reason": f"main-core smoke failed: {exc!s}",
            }


class _InitHook:
    """Init hook — no-op.

    main-core owns no DB connection (data-platform owns PG/Iceberg;
    graph-engine owns Neo4j). The L1-L8 chain reads from data-platform
    canonical tables on demand inside Phase 0/1/2/3 dispatch — there is
    nothing to initialize at bootstrap time.
    """

    def initialize(self, *, resolved_env: dict[str, str]) -> None:
        _ = resolved_env  # explicit unused-binding to silence linters


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

    Currently supports ``version``. Returns POSIX exit codes (0 ok, 2
    invalid usage). The argv parameter is positional-or-keyword to match
    the assembly ``CliEntrypoint`` protocol.
    """

    _PROG = "main-core"

    def invoke(self, argv: list[str]) -> int:
        parser = argparse.ArgumentParser(
            prog=self._PROG,
            description="main-core public CLI",
        )
        parser.add_argument(
            "subcommand",
            nargs="?",
            default="version",
            choices=("version",),
            help="subcommand to run (default: version)",
        )
        try:
            args = parser.parse_args(argv)
        except SystemExit as exc:
            return int(exc.code) if exc.code is not None else 2

        if args.subcommand == "version":
            info = _VersionDeclaration().declare()
            print(
                f"{info['module_id']} {info['module_version']} "
                f"(contract {info['contract_version']})"
            )
            return 0
        return 2


# Module-level singletons — names referenced by
# assembly/module-registry.yaml ("main_core.public:health_probe", etc.).
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
