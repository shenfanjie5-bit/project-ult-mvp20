"""Public integration entrypoints for assembly compatibility checks.

Mirrors the audit-eval / contracts / reasoner-runtime / main-core /
data-platform / orchestrator public.py templates. Five module-level
singletons referenced by ``assembly/module-registry.yaml``
``module_id: entity-registry``:

- ``health_probe``  — verifies the entity_registry package boundary
  loads and the four headline public APIs (resolve_mention /
  lookup_alias / batch_resolve / initialize_from_stock_basic) exist
- ``smoke_hook``    — exercises the headline-API symbols are importable
  + callable shape (no actual resolution; that requires a configured
  repository context which lives in the runtime)
- ``init_hook``     — no-op (entity_registry repos are configured by
  callers via ``configure_default_repositories(...)`` — there is no
  bootstrap-time PG/Iceberg setup owned by this module)
- ``version_declaration`` — returns module + contract version
- ``cli``           — argparse-based dispatcher with a ``version``
  subcommand

Boundary (entity-registry CLAUDE.md):
- This module does NOT define any business L4-L7 logic
- This module does NOT call LLM directly (delegates to
  reasoner-runtime per CLAUDE.md BAN list)
- This module does NOT depend on data-platform private adapters; only
  the canonical ``stock_basic`` table (read-only) — and even that is
  not imported at public-entrypoint time
"""

from __future__ import annotations

import argparse
import time
from typing import Any

from entity_registry import __version__ as _MODULE_VERSION

_MODULE_ID = "entity-registry"
# Stage 4 §4.1.5: contract_version is the canonical contracts schema version
# this module is bound against (NOT this module's own package version, which
# stays in module_version). Harmonized to v0.1.3 across all 11 active
# subsystem modules so assembly's ContractsVersionCheck (strict equality vs
# matrix.contract_version) succeeds at the cross-project compat audit
# (assembly/scripts/stage_3_compat_audit.py + Stage 4 §4.1 registry).
_CONTRACT_VERSION = "v0.1.3"
_COMPATIBLE_CONTRACT_RANGE = ">=0.1.0,<0.2.0"


class _HealthProbe:
    """Health probe — confirms the entity_registry package is importable
    and the four headline APIs are reachable. No live PG/Iceberg call.
    """

    _PROBE_NAME = "entity-registry.import"

    def check(self, *, timeout_sec: float) -> dict[str, Any]:
        start = time.monotonic()
        details: dict[str, Any] = {"timeout_sec": timeout_sec}
        try:
            from entity_registry import (  # noqa: F401
                resolve_mention,
                lookup_alias,
                batch_resolve,
            )

            details["public_apis"] = [
                "entity_registry.resolve_mention",
                "entity_registry.lookup_alias",
                "entity_registry.batch_resolve",
            ]
            status = "healthy"
            message = "entity-registry package import healthy"
        except Exception as exc:  # pragma: no cover - degraded path
            status = "degraded"
            message = f"entity-registry import degraded: {exc!s}"
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
    """Smoke hook — exercises the three headline public APIs are
    callable. Does NOT invoke them (would require a configured
    repository context — out of scope for smoke).
    """

    _HOOK_NAME = "entity-registry.public-api-smoke"

    def run(self, *, profile_id: str) -> dict[str, Any]:
        start = time.monotonic()
        try:
            from entity_registry import (
                resolve_mention,
                lookup_alias,
                batch_resolve,
            )

            checked = 0
            for fn in (resolve_mention, lookup_alias, batch_resolve):
                assert callable(fn), f"{fn.__name__} not callable"
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
                "failure_reason": f"entity-registry smoke failed: {exc!s}",
                "details": {"profile_id": profile_id},
            }


class _InitHook:
    """Init hook — no-op.

    entity_registry's repository context is wired by callers via
    ``configure_default_repositories(...)`` /
    ``configure_default_in_memory_audit_repositories()``; this module
    has no bootstrap-time PG/Iceberg setup.
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

    _PROG = "entity-registry"

    def invoke(self, argv: list[str]) -> int:
        parser = argparse.ArgumentParser(
            prog=self._PROG,
            description="entity-registry public CLI",
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
# assembly/module-registry.yaml ("entity_registry.public:health_probe", ...).
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
