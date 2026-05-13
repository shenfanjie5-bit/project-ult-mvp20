"""Smoke tests — minimal end-to-end exercise of public entrypoints.

The path ``make smoke`` runs and assembly hits during stage
public_smoke_probes of bootstrap. Stays infra-free.
"""

from __future__ import annotations

import time

from reasoner_runtime import public


class TestSmokeFastPath:
    def test_health_probe_under_1s(self) -> None:
        start = time.monotonic()
        result = public.health_probe.check(timeout_sec=1.0)
        elapsed = time.monotonic() - start

        assert result["status"] in {"healthy", "degraded"}
        assert elapsed < 1.0, f"health_probe took {elapsed:.3f}s"

    def test_smoke_hook_passes_for_lite_local(self) -> None:
        result = public.smoke_hook.run(profile_id="lite-local")
        assert result["passed"], result.get("failure_reason")

    def test_smoke_hook_passes_for_full_dev(self) -> None:
        result = public.smoke_hook.run(profile_id="full-dev")
        assert result["passed"], result.get("failure_reason")

    def test_cli_version_under_1s(self) -> None:
        start = time.monotonic()
        rc = public.cli.invoke(["version"])
        elapsed = time.monotonic() - start

        assert rc == 0
        assert elapsed < 1.0, f"cli version took {elapsed:.3f}s"
