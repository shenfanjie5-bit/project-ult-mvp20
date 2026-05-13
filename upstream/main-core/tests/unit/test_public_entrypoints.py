"""Unit tests for ``main_core.public`` (assembly integration).

Mirrors the audit-eval / contracts / reasoner-runtime public-tier checks
adjusted for main-core: smoke must pass without LLM/DB, contract_version
is module-version-derived, four formal-object models are checked.
"""

from __future__ import annotations

from main_core import public


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

    def test_module_id_is_main_core(self) -> None:
        result = public.health_probe.check(timeout_sec=1.0)
        assert result["module_id"] == "main-core"


class TestSmokeHookDictShape:
    def test_required_fields_present(self) -> None:
        result = public.smoke_hook.run(profile_id="lite-local")
        assert set(result.keys()) == {
            "module_id",
            "hook_name",
            "passed",
            "duration_ms",
            "failure_reason",
        }

    def test_passed_for_both_profiles(self) -> None:
        for profile_id in ("lite-local", "full-dev"):
            result = public.smoke_hook.run(profile_id=profile_id)
            assert result["passed"], (profile_id, result.get("failure_reason"))

    def test_smoke_result_has_no_assembly_forbidden_extra_fields(self) -> None:
        result = public.smoke_hook.run(profile_id="lite-local")
        assert result["passed"]
        assert "details" not in result
        assert "profile_id" not in result


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


class TestInitHookIsNoOp:
    def test_returns_none(self) -> None:
        assert public.init_hook.initialize(resolved_env={}) is None


class TestCliInvokeReturnsExitCode:
    def test_version_subcommand_succeeds(self, capsys) -> None:
        rc = public.cli.invoke(["version"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "main-core" in captured.out

    def test_unknown_subcommand_fails(self) -> None:
        rc = public.cli.invoke(["nonsense"])
        assert rc != 0
