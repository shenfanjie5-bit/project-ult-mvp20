"""Unit tests for ``reasoner_runtime.public`` (assembly integration).

Mirrors the audit-eval / contracts public-tier checks adjusted for
reasoner-runtime: smoke must pass without a real LLM provider key, and
the version_declaration's contract_version is module-version-derived
(reasoner-runtime is its own contract source for the public surface).
"""

from __future__ import annotations

from reasoner_runtime import public


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

    def test_module_id_is_reasoner_runtime(self) -> None:
        result = public.health_probe.check(timeout_sec=1.0)
        assert result["module_id"] == "reasoner-runtime"


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
            result = public.smoke_hook.run(profile_id=profile_id)
            assert result["passed"], (profile_id, result.get("failure_reason"))

    def test_smoke_confirms_five_replay_fields(self) -> None:
        result = public.smoke_hook.run(profile_id="lite-local")
        assert result["passed"]
        assert result["details"].get("five_replay_fields_present") is True


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
        assert "reasoner-runtime" in captured.out

    def test_unknown_subcommand_fails(self) -> None:
        rc = public.cli.invoke(["nonsense"])
        assert rc != 0
