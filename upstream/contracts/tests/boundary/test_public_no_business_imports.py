"""Boundary tests for the contracts public entrypoints.

Two boundaries to enforce per ``contracts/CLAUDE.md``:

1. ``contracts.public`` must not depend on any business module — public.py
   is the high-traffic integration glue, the most likely place to
   accidentally pull one in.
2. ``contracts.public`` must not pull in heavy runtime libraries
   (PostgreSQL/Iceberg/Neo4j/LLM/dagster). These would defeat the cheap
   importable-namespace promise downstream modules rely on.

**Subprocess-isolated** (codex review #2, lesson recorded in plan stage 2.1
followups): a previous version scanned ``sys.modules`` of the live pytest
session, which gave false negatives — if any earlier test or pytest plugin
already imported ``dagster`` or ``assembly``, the deny scan caught those
*even though* ``contracts.public`` did not pull them in. We now spawn a
clean Python subprocess that imports only ``contracts.public`` and dumps
its post-import ``sys.modules`` to JSON; the boundary scan runs against
that pristine snapshot.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


_BUSINESS_MODULES = (
    "data_platform",
    "main_core",
    "graph_engine",
    "audit_eval",        # consumer-direction only — contracts must not import it
    "entity_registry",
    "reasoner_runtime",
    "subsystem_sdk",
    "subsystem_announcement",
    "subsystem_news",
    "orchestrator",
    "assembly",
    "feature_store",
    "stream_layer",
)
_HEAVY_RUNTIME_PREFIXES = (
    "psycopg",
    "pyiceberg",
    "neo4j",
    "litellm",
    "openai",
    "anthropic",
    "torch",
    "tensorflow",
    "dagster",
)

# Subprocess script: imports contracts.public in a clean interpreter and
# prints the resulting ``sys.modules`` keys as JSON to stdout. Path setup
# matches the project's src layout.
_PROBE_SCRIPT = textwrap.dedent(
    """
    import json
    import sys
    sys.path.insert(0, {src_dir!r})
    import contracts.public  # noqa: F401
    print(json.dumps(sorted(sys.modules.keys())))
    """
).strip()


@pytest.fixture(scope="module")
def loaded_modules_in_clean_subprocess() -> frozenset[str]:
    src_dir = str(Path(__file__).resolve().parents[2] / "src")
    result = subprocess.run(
        [sys.executable, "-c", _PROBE_SCRIPT.format(src_dir=src_dir)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            "subprocess probe failed; stderr:\n" + result.stderr
        )
    return frozenset(json.loads(result.stdout))


class TestNoBusinessModuleImports:
    def test_contracts_public_pulls_in_no_business_module(
        self, loaded_modules_in_clean_subprocess: frozenset[str]
    ) -> None:
        offenders = sorted(
            mod
            for mod in loaded_modules_in_clean_subprocess
            if any(mod == p or mod.startswith(p + ".") for p in _BUSINESS_MODULES)
        )

        assert not offenders, (
            f"contracts.public pulled in business module(s): {offenders}"
        )


class TestNoHeavyRuntimeImports:
    def test_contracts_public_pulls_in_no_heavy_runtime(
        self, loaded_modules_in_clean_subprocess: frozenset[str]
    ) -> None:
        offenders = sorted(
            mod
            for mod in loaded_modules_in_clean_subprocess
            if any(
                mod == p or mod.startswith(p + ".") for p in _HEAVY_RUNTIME_PREFIXES
            )
        )

        assert not offenders, (
            f"contracts.public pulled in heavy runtime module(s): {offenders}"
        )


class TestSmokeHookContractCoverage:
    """smoke_hook must continue to cover all four Ex payload families.

    If a future refactor drops one of Ex0/Ex1/Ex2/Ex3 from the smoke
    coverage, this test fails — guards against silent regression of the
    smoke contract. Runs in-process (no subprocess needed; just exercises
    the entrypoint and inspects the structured result).
    """

    def test_smoke_covers_four_ex_payload_models(self) -> None:
        from contracts import public

        result = public.smoke_hook.run(profile_id="lite-local")

        assert result["passed"], result.get("failure_reason")
        details = result.get("details", {})
        assert details.get("ex_models_checked") == 4, details
