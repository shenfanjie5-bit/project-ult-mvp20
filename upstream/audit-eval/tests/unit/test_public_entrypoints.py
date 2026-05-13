"""Unit tests for the audit-eval public entrypoints (assembly integration).

These verify the *shape* of the dict each public entrypoint returns matches
the field names in ``assembly.contracts.models.{HealthResult,SmokeResult,
VersionInfo}`` so that downstream typed construction stays drift-free.

Signature compliance against assembly Protocols is covered by the assembly
side ``public_api_boundary`` compatibility check; see also
``tests/smoke/test_public_smoke.py`` for an end-to-end import smoke.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from audit_eval import public


class TestHealthProbeDictShape:
    def test_required_fields_present(self) -> None:
        result = public.health_probe.check(timeout_sec=1.0)

        assert set(result.keys()) >= {
            "module_id",
            "probe_name",
            "status",
            "latency_ms",
            "message",
            "details",
        }

    def test_status_in_allowed_values(self) -> None:
        result = public.health_probe.check(timeout_sec=1.0)

        assert result["status"] in {"healthy", "degraded", "blocked"}

    def test_module_id_is_audit_eval(self) -> None:
        result = public.health_probe.check(timeout_sec=1.0)

        assert result["module_id"] == "audit-eval"


class TestSmokeHookDictShape:
    def test_required_fields_present(self) -> None:
        result = public.smoke_hook.run(profile_id="lite-local")

        assert set(result.keys()) >= {
            "module_id",
            "hook_name",
            "passed",
            "duration_ms",
            "failure_reason",
        }

    def test_passed_is_bool(self) -> None:
        result = public.smoke_hook.run(profile_id="lite-local")

        assert isinstance(result["passed"], bool)

    def test_failure_reason_none_when_passed(self) -> None:
        result = public.smoke_hook.run(profile_id="lite-local")

        if result["passed"]:
            assert result["failure_reason"] is None


class TestVersionDeclarationDictShape:
    def test_required_fields_present(self) -> None:
        result = public.version_declaration.declare()

        assert set(result.keys()) == {
            "module_id",
            "module_version",
            "contract_version",
            "compatible_contract_range",
        }

    def test_module_version_is_semver(self) -> None:
        import re

        result = public.version_declaration.declare()

        assert re.match(r"^\d+\.\d+\.\d+$", result["module_version"]), result

    def test_contract_version_has_v_prefix(self) -> None:
        import re

        result = public.version_declaration.declare()

        assert re.match(r"^v\d+\.\d+\.\d+$", result["contract_version"]), result


class TestInitHookIsNoOp:
    def test_returns_none(self) -> None:
        initialize = cast(Callable[..., object], public.init_hook.initialize)

        assert initialize(resolved_env={}) is None

    def test_accepts_arbitrary_env(self) -> None:
        initialize = cast(Callable[..., object], public.init_hook.initialize)

        assert (
            initialize(resolved_env={"PG_HOST": "localhost", "PG_PORT": "5432"})
            is None
        )


class TestCliInvokeReturnsExitCode:
    def test_version_subcommand_succeeds(self, capsys) -> None:
        rc = public.cli.invoke(["version"])

        assert rc == 0
        captured = capsys.readouterr()
        assert "audit-eval" in captured.out

    def test_unknown_subcommand_fails(self) -> None:
        rc = public.cli.invoke(["nonsense-subcommand"])

        assert rc != 0
