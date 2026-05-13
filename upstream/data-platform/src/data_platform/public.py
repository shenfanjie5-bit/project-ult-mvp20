"""Public integration entrypoints for assembly compatibility checks.

Mirrors the audit-eval / contracts / reasoner-runtime / main-core public.py
templates (see project-ult test rollout plan stage 2). Five module-level
singletons referenced by ``assembly/module-registry.yaml``
``module_id: data-platform``:

- ``health_probe`` — verifies the data_platform package boundary loads
  and the key API namespace packages are discoverable without importing
  heavy runtime dependencies. Never tries a real PostgreSQL or Iceberg
  connection — that is left to runtime / orchestrator.
- ``smoke_hook`` — verifies the five headline public API functions
  (list_cycles, get_formal_latest, get_formal_by_id, submit_candidate,
  freeze_cycle_candidates) are importable + callable shape, without
  invoking them
- ``init_hook`` — no-op (PostgreSQL / Iceberg / DuckDB are owned by the
  infra/orchestrator side; data_platform does not initialize them at
  bootstrap)
- ``version_declaration`` — returns the data_platform module + contract
  version
- ``cli`` — argparse-based dispatcher with a ``version`` subcommand

Boundary (data-platform CLAUDE.md):
- This module does NOT make any live PG/Iceberg/DuckDB call at import
  time (would defeat the cheap importable-namespace promise that
  downstream modules rely on)
- This module does NOT touch the LLM runtime (per CLAUDE.md BAN list)
- This module does NOT define any L4-L7 business logic
"""

from __future__ import annotations

import argparse
import importlib.util
import time
from typing import Any

from data_platform import __version__ as _MODULE_VERSION

_MODULE_ID = "data-platform"
# Stage 4 §4.1.5: contract_version is the canonical contracts schema version
# this module is bound against (NOT this module's own package version, which
# stays in module_version). Harmonized to v0.1.3 across all 11 active
# subsystem modules so assembly's ContractsVersionCheck (strict equality vs
# matrix.contract_version) succeeds at the cross-project compat audit
# (assembly/scripts/stage_3_compat_audit.py + Stage 4 §4.1 registry).
_CONTRACT_VERSION = "v0.1.3"
_COMPATIBLE_CONTRACT_RANGE = ">=0.1.0,<0.2.0"
_PUBLIC_NAMESPACE_SPECS = (
    "data_platform.serving",
    "data_platform.queue",
    "data_platform.cycle",
    "data_platform.raw",
)


class _HealthProbe:
    """Health probe — confirms the data_platform package is importable
    and the key public-API namespaces (serving, queue, cycle, raw) are
    discoverable.

    Never attempts a real PG/Iceberg/DuckDB connection; degrades to
    ``status="degraded"`` so ``make smoke`` can run without infra.
    The smoke hook below imports the headline callables; keeping this
    probe at namespace-spec resolution avoids cold-loading PyArrow and
    other runtime dependencies inside the 1-second health budget.
    """

    _PROBE_NAME = "data-platform.import"

    def check(self, *, timeout_sec: float) -> dict[str, Any]:
        start = time.monotonic()
        details: dict[str, Any] = {"timeout_sec": timeout_sec}
        try:
            missing_namespaces = [
                name
                for name in _PUBLIC_NAMESPACE_SPECS
                if importlib.util.find_spec(name) is None
            ]

            details["public_namespaces"] = list(_PUBLIC_NAMESPACE_SPECS)
            details["namespace_check"] = "module_spec"
            if missing_namespaces:
                status = "degraded"
                message = "data-platform public namespace missing"
                details["missing_public_namespaces"] = missing_namespaces
            else:
                status = "healthy"
                message = "data-platform package boundary healthy"
        except Exception as exc:  # pragma: no cover - degraded path
            status = "degraded"
            message = f"data-platform import degraded: {exc!s}"
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
    """Smoke hook — exercises the five headline public-API callables
    are importable + carry the expected callable shape.

    No live PG/Iceberg call — this stays under the 1-second smoke
    budget and works in lite-local without infra. Real integration
    tests live in tests/integration where a PG service is provisioned.
    """

    _HOOK_NAME = "data-platform.public-api-smoke"

    def run(self, *, profile_id: str) -> dict[str, Any]:
        start = time.monotonic()
        try:
            from data_platform.serving.formal import (
                get_formal_latest,
                get_formal_by_id,
            )
            from data_platform.cycle import list_cycles
            from data_platform.queue.api import submit_candidate
            from data_platform.cycle.freeze import freeze_cycle_candidates

            # Confirm each is callable; do NOT invoke (would need a live
            # PostgreSQL connection — out of scope for smoke).
            checked = 0
            for fn in (
                list_cycles,
                get_formal_latest,
                get_formal_by_id,
                submit_candidate,
                freeze_cycle_candidates,
            ):
                assert callable(fn), f"{fn.__name__} is not callable"
                checked += 1

            duration_ms = (time.monotonic() - start) * 1000.0
            return {
                "module_id": _MODULE_ID,
                "hook_name": self._HOOK_NAME,
                "passed": True,
                "duration_ms": duration_ms,
                "failure_reason": None,
                "details": {
                    "profile_id": profile_id,
                    "public_apis_checked": checked,
                },
            }
        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000.0
            return {
                "module_id": _MODULE_ID,
                "hook_name": self._HOOK_NAME,
                "passed": False,
                "duration_ms": duration_ms,
                "failure_reason": f"data-platform smoke failed: {exc!s}",
                "details": {"profile_id": profile_id},
            }


class _InitHook:
    """Init hook — no-op.

    PostgreSQL / Iceberg / DuckDB are managed by the infra layer
    (assembly bootstrap orchestrates docker compose; orchestrator
    Dagster resources own DB sessions). data_platform's runtime
    functions open connections lazily on first call — there is nothing
    to initialize at bootstrap.
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

    Currently supports ``version``. Returns POSIX exit codes (0 ok, 2
    invalid usage). The argv parameter is positional-or-keyword to match
    the assembly ``CliEntrypoint`` protocol.
    """

    _PROG = "data-platform"

    def invoke(self, argv: list[str]) -> int:
        parser = argparse.ArgumentParser(
            prog=self._PROG,
            description="data-platform public CLI",
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
# assembly/module-registry.yaml ("data_platform.public:health_probe", etc.).
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
