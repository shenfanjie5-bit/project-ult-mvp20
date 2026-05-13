"""Public integration entrypoints for assembly compatibility checks.

Mirrors the audit-eval / contracts public.py templates (see
project-ult test rollout plan stage 2). Five module-level singletons
referenced by ``assembly/module-registry.yaml`` ``module_id:
reasoner-runtime``:

- ``health_probe`` — verifies the reasoner_runtime package boundary loads
  and the LLM provider config namespace is non-empty
- ``smoke_hook`` — runs an in-memory ``build_replay_bundle`` exercise to
  catch the five-field replay invariant breaking before any LLM call is
  attempted
- ``init_hook`` — no-op (reasoner-runtime owns no PostgreSQL/Iceberg/
  Neo4j connection; instructor + litellm are pip packages, no init)
- ``version_declaration`` — returns the reasoner_runtime module + contract
  version
- ``cli`` — argparse-based dispatcher with a ``version`` subcommand

Boundary (reasoner-runtime CLAUDE.md):
- This module does NOT make any live LLM call at import or during smoke.
  smoke_hook only exercises the replay-bundle constructor with synthetic
  inputs, so it stays under the 1-second smoke budget.
- This module does NOT bypass scrub_input on PII paths — the smoke hook
  does not feed real prompts; the scrub boundary tests live separately.
"""

from __future__ import annotations

import argparse
import time
from typing import Any

from reasoner_runtime import __version__ as _MODULE_VERSION

_MODULE_ID = "reasoner-runtime"
# Stage 4 §4.1.5: contract_version is the canonical contracts schema version
# this module is bound against (NOT this module's own package version, which
# stays in module_version). Harmonized to v0.1.3 across all 11 active
# subsystem modules so assembly's ContractsVersionCheck (strict equality vs
# matrix.contract_version) succeeds at the cross-project compat audit
# (assembly/scripts/stage_3_compat_audit.py + Stage 4 §4.1 registry).
_CONTRACT_VERSION = "v0.1.3"
_COMPATIBLE_CONTRACT_RANGE = ">=0.1.0,<0.2.0"


class _HealthProbe:
    """Health probe — confirms the reasoner_runtime package is importable
    and the provider/scrub config surface is non-empty.

    Never raises on infrastructure unavailability; degrades to ``status=
    "degraded"`` so ``make smoke`` can run without an LLM provider key.
    """

    _PROBE_NAME = "reasoner-runtime.import"

    def check(self, *, timeout_sec: float) -> dict[str, Any]:
        start = time.monotonic()
        details: dict[str, Any] = {"timeout_sec": timeout_sec}
        try:
            from reasoner_runtime.config import (  # noqa: F401
                ProviderProfile,
                ScrubRuleSet,
            )

            details["config_namespace"] = "loaded"
            status = "healthy"
            message = "reasoner-runtime package import healthy"
        except Exception as exc:  # pragma: no cover - degraded path
            status = "degraded"
            message = f"reasoner-runtime import degraded: {exc!s}"
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
    """Smoke hook — exercises the replay-bundle five-field invariant.

    No live LLM call. Builds a synthetic ``ReplayBundle`` with all five
    required fields populated to verify the model definition has not
    drifted (``extra="forbid"`` would reject any spurious field; missing
    fields would raise ValidationError on construction).

    Profile-aware: ``lite-local`` and ``full-dev`` both run identically.
    """

    _HOOK_NAME = "reasoner-runtime.replay-bundle-smoke"

    def run(self, *, profile_id: str) -> dict[str, Any]:
        start = time.monotonic()
        try:
            from reasoner_runtime.replay.models import ReplayBundle

            from contracts.schemas.reasoner import (  # noqa: F401
                ReasonerRequest as ContractRequest,
                ReasonerResult as ContractResult,
            )

            # Construct a contract-shaped request/result pair for the
            # bundle's request_id identity check, then assemble a bundle
            # with all five replay fields present.
            request = _make_synthetic_contract_request()
            result = _make_synthetic_contract_result(request_id=request.request_id)
            bundle = ReplayBundle(
                sanitized_input="<smoke sanitized>",
                input_hash="0" * 64,
                raw_output='{"smoke": true}',
                parsed_result={"smoke": True},
                output_hash="1" * 64,
                request=request,
                result=result,
            )

            five_fields = {
                "sanitized_input": bundle.sanitized_input,
                "input_hash": bundle.input_hash,
                "raw_output": bundle.raw_output,
                "parsed_result": bundle.parsed_result,
                "output_hash": bundle.output_hash,
            }
            assert all(v is not None for v in five_fields.values()), five_fields

            duration_ms = (time.monotonic() - start) * 1000.0
            return {
                "module_id": _MODULE_ID,
                "hook_name": self._HOOK_NAME,
                "passed": True,
                "duration_ms": duration_ms,
                "failure_reason": None,
                "details": {
                    "profile_id": profile_id,
                    "five_replay_fields_present": True,
                },
            }
        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000.0
            return {
                "module_id": _MODULE_ID,
                "hook_name": self._HOOK_NAME,
                "passed": False,
                "duration_ms": duration_ms,
                "failure_reason": f"reasoner-runtime smoke failed: {exc!s}",
                "details": {"profile_id": profile_id},
            }


def _make_synthetic_contract_request() -> Any:
    """Build a contract-shaped ReasonerRequest with all required fields
    populated. We pay the full Pydantic validation cost so smoke also
    catches drift in the contract schema itself.
    """
    from datetime import UTC, datetime
    from contracts.schemas.reasoner import ReasonerRequest as ContractRequest

    return ContractRequest(
        request_id="smoke-req-000",
        cycle_id="smoke-cycle-000",
        reasoner_name="smoke-reasoner",
        reasoner_version="0.0.0",
        prompt="smoke",
        context={},
        requested_at=datetime.now(UTC),
    )


def _make_synthetic_contract_result(*, request_id: str) -> Any:
    """Build a contract-shaped ReasonerResult (status=COMPLETED, no error
    classification — error_classification_must_match_status validator
    requires None when status != FAILED).
    """
    from datetime import UTC, datetime
    from contracts.schemas.reasoner import (
        ReasonerResult as ContractResult,
        ReasonerStatus,
    )

    return ContractResult(
        result_id=f"smoke-res-{request_id}",
        request_id=request_id,
        status=ReasonerStatus.COMPLETED,
        reasoner_name="smoke-reasoner",
        reasoner_version="0.0.0",
        output={"smoke": True},
        completed_at=datetime.now(UTC),
    )


class _InitHook:
    """Init hook — no-op.

    reasoner-runtime owns no DB connection, no model weights to load. The
    LLM provider clients (instructor + litellm) are constructed lazily
    inside ``build_client`` only when an LLM call is actually invoked.
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

    _PROG = "reasoner-runtime"

    def invoke(self, argv: list[str]) -> int:
        parser = argparse.ArgumentParser(
            prog=self._PROG,
            description="reasoner-runtime public CLI",
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
# assembly/module-registry.yaml ("reasoner_runtime.public:health_probe", etc.).
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
