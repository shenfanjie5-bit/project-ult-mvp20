"""Unit tests for ``contracts.public`` (assembly integration).

Mirrors the same checks ``audit_eval/tests/unit/test_public_entrypoints.py``
applies to its public surface, adjusted for ``contracts``-specific facts:
the contract_version equals the module_version (contracts is its own
contract source).
"""

from __future__ import annotations

from contracts import public


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

    def test_module_id_is_contracts(self) -> None:
        result = public.health_probe.check(timeout_sec=1.0)

        assert result["module_id"] == "contracts"


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

    def test_passed_for_both_profiles(self) -> None:
        for profile_id in ("lite-local", "full-dev"):
            assert public.smoke_hook.run(profile_id=profile_id)["passed"], profile_id


class TestVersionDeclarationShape:
    def test_required_fields_present(self) -> None:
        info = public.version_declaration.declare()

        assert set(info.keys()) == {
            "module_id",
            "module_version",
            "contract_version",
            "compatible_contract_range",
        }

    def test_contract_version_starts_with_v(self) -> None:
        import re

        info = public.version_declaration.declare()
        assert re.match(r"^v\d+\.\d+\.\d+$", info["contract_version"]), info

    def test_contracts_is_its_own_contract_source(self) -> None:
        # contracts module: module_version == contract_version (sans 'v').
        info = public.version_declaration.declare()
        assert info["contract_version"] == f"v{info['module_version']}"


class TestInitHookIsNoOp:
    def test_returns_none(self) -> None:
        assert public.init_hook.initialize(resolved_env={}) is None


class TestCliInvokeReturnsExitCode:
    def test_version_subcommand_succeeds(self, capsys) -> None:
        rc = public.cli.invoke(["version"])

        assert rc == 0
        captured = capsys.readouterr()
        assert "contracts" in captured.out

    def test_unknown_subcommand_fails(self) -> None:
        rc = public.cli.invoke(["nonsense"])

        assert rc != 0
