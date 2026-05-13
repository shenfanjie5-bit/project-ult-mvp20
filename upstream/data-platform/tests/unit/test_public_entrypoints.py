"""Unit tests for ``data_platform.public`` (assembly integration)."""

from __future__ import annotations

from data_platform import public


class TestHealthProbeDictShape:
    def test_required_fields_present(self) -> None:
        result = public.health_probe.check(timeout_sec=1.0)
        assert set(result.keys()) >= {
            "module_id", "probe_name", "status", "latency_ms", "message", "details",
        }

    def test_status_in_allowed_values(self) -> None:
        result = public.health_probe.check(timeout_sec=1.0)
        assert result["status"] in {"healthy", "degraded", "blocked"}

    def test_module_id_is_data_platform(self) -> None:
        result = public.health_probe.check(timeout_sec=1.0)
        assert result["module_id"] == "data-platform"


class TestSmokeHookDictShape:
    def test_required_fields_present(self) -> None:
        result = public.smoke_hook.run(profile_id="lite-local")
        assert set(result.keys()) >= {
            "module_id", "hook_name", "passed", "duration_ms", "failure_reason",
        }


class TestVersionDeclarationShape:
    def test_required_fields_present(self) -> None:
        info = public.version_declaration.declare()
        assert set(info.keys()) == {
            "module_id", "module_version", "contract_version",
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
        assert "data-platform" in captured.out

    def test_unknown_subcommand_fails(self) -> None:
        rc = public.cli.invoke(["nonsense"])
        assert rc != 0
