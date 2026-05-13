"""Public integration entrypoints for assembly compatibility checks.

This module exposes the five public entrypoints declared in
``assembly/module-registry.yaml`` for ``module_id: audit-eval``:

- ``health_probe``  — assembly.contracts.protocols.HealthProbe
- ``smoke_hook``    — assembly.contracts.protocols.SmokeHook
- ``init_hook``     — assembly.contracts.protocols.InitHook
- ``version_declaration`` — assembly.contracts.protocols.VersionDeclaration
- ``cli``           — assembly.contracts.protocols.CliEntrypoint

Design notes:

- Each entrypoint is a *module-level instance* (lowercase snake_case) so that
  ``assembly.compat.checks.public_api_boundary`` can ``importlib.import_module``
  + ``getattr`` the reference and pass ``isinstance(loaded, protocol)``.
- Method signatures match the assembly Protocols exactly (parameter name +
  keyword-only / positional kind), validated by
  ``_validate_entrypoint_signature`` in
  ``assembly/src/assembly/compat/checks/public_api_boundary.py``.
- This module **does not import assembly**. Returning ``dict[str, Any]`` keeps
  the integration boundary one-way (audit-eval is the producer, assembly is
  the consumer). Field names match
  ``assembly.contracts.models.{HealthResult,SmokeResult,VersionInfo}`` so
  downstream code can construct the typed model from this dict.
- Health/smoke deliberately stay lightweight — they only verify package import
  paths, not external infrastructure. PostgreSQL/Iceberg connectivity belongs
  in a richer probe wired via ``init_hook`` once a real ``resolved_env`` is
  available.

This file also serves as the **template** for the other 11 project-ult modules
(see ``docs/lessons-learned`` and the workspace-level test rollout plan).
"""

from __future__ import annotations

import argparse
import time
from typing import Any

from audit_eval._boundary import FORBIDDEN_WRITE_FIELDS

_MODULE_ID = "audit-eval"
_MODULE_VERSION = "0.2.5"
_CONTRACT_VERSION = "v0.1.3"
_COMPATIBLE_CONTRACT_RANGE = ">=0.1.0,<0.2.0"


class _HealthProbe:
    """Health probe — confirms the audit_eval package is importable.

    Never raises on infrastructure unavailability; degrades to ``status=
    "degraded"`` instead so ``make smoke`` can run without PostgreSQL etc.
    """

    _PROBE_NAME = "audit-eval.import"

    def check(self, *, timeout_sec: float) -> dict[str, Any]:
        start = time.monotonic()
        details: dict[str, Any] = {"timeout_sec": timeout_sec}
        try:
            # Lightweight import probe — verifies the package boundary loads
            # and the contract namespace has a non-empty schema set.
            from audit_eval import contracts as _contracts  # noqa: F401
            from audit_eval.contracts.audit_record import AuditRecord  # noqa: F401

            details["forbidden_write_fields"] = sorted(FORBIDDEN_WRITE_FIELDS)
            status = "healthy"
            message = "audit-eval package import healthy"
        except Exception as exc:  # pragma: no cover - degraded path
            status = "degraded"
            message = f"audit-eval import degraded: {exc!s}"
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
    """Smoke hook — exercises the contract Pydantic models without side effects.

    Profile-aware: ``lite-local`` and ``full-dev`` both run the same in-memory
    smoke; only the ``profile_id`` is recorded in the result for traceability.
    """

    _HOOK_NAME = "audit-eval.contract-smoke"

    def run(self, *, profile_id: str) -> dict[str, Any]:
        start = time.monotonic()
        try:
            from audit_eval.contracts.audit_record import AuditRecord
            from audit_eval.contracts.replay_record import ReplayRecord  # noqa: F401

            # Touch the model class to verify Pydantic model definitions
            # are well-formed (would raise PydanticUserError otherwise).
            assert AuditRecord.model_fields, "AuditRecord has no fields"
            duration_ms = (time.monotonic() - start) * 1000.0
            return {
                "module_id": _MODULE_ID,
                "hook_name": self._HOOK_NAME,
                "passed": True,
                "duration_ms": duration_ms,
                "failure_reason": None,
                "details": {"profile_id": profile_id},
            }
        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000.0
            return {
                "module_id": _MODULE_ID,
                "hook_name": self._HOOK_NAME,
                "passed": False,
                "duration_ms": duration_ms,
                "failure_reason": f"smoke contract import failed: {exc!s}",
                "details": {"profile_id": profile_id},
            }


class _InitHook:
    """Init hook — placeholder for future audit/replay table provisioning.

    Until P5 wires real PostgreSQL/Iceberg setup, this is a structural no-op
    so ``assembly.bootstrap`` can call it without touching infra. Once the
    real init lands, it will validate (or create) the ``audit_record`` /
    ``replay_record`` tables based on ``resolved_env`` connection settings.
    """

    def initialize(self, *, resolved_env: dict[str, str]) -> None:
        # No-op until real audit/replay table provisioning lands.
        # The keyword-only resolved_env param is required by the protocol.
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
    """CLI entrypoint — minimal argparse-based subcommand dispatcher.

    Currently supports ``version`` only. Returns POSIX exit codes (0 ok, 2
    invalid usage). The argv parameter is positional-or-keyword to match the
    ``CliEntrypoint`` protocol exactly.
    """

    _PROG = "audit-eval"

    def invoke(self, argv: list[str]) -> int:
        parser = argparse.ArgumentParser(
            prog=self._PROG,
            description="audit-eval public CLI",
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
        except SystemExit as exc:  # argparse exits non-zero on bad input
            return int(exc.code) if exc.code is not None else 2

        if args.subcommand == "version":
            info = _VersionDeclaration().declare()
            print(
                f"{info['module_id']} {info['module_version']} "
                f"(contract {info['contract_version']})"
            )
            return 0
        return 2


# Module-level singletons — these are the names referenced by
# assembly/module-registry.yaml (e.g. "audit_eval.public:health_probe").
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
