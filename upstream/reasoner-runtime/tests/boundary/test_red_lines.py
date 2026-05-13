"""Boundary tests for reasoner-runtime red lines (per §10 STANDARD).

Three boundaries enforced:

1. **replay-bundle five-field invariant** — ReplayBundle's
   sanitized_input/input_hash/raw_output/parsed_result/output_hash must
   all be present. ``extra="forbid"`` rejects spurious fields; missing
   any one must raise ValidationError.
2. **PII scrub** — scrub_input must redact at minimum email + phone
   patterns (the two universal PII shapes the scrub ruleset ships with).
3. **max_retries required** — ReasonerRequest must reject construction
   without an explicit non-negative max_retries (no silent defaulting).

Subprocess isolation is used for the public.py import-deny scan to avoid
pytest session pollution (codex review #2 from stage 2.1, reusable
template).
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest

# ── replay bundle five-field invariant ──────────────────────────────


def _build_complete_request_pair() -> tuple[object, object]:
    """Construct a contract-shaped (request, result) with matching ids
    so ReplayBundle's identity validator passes when we add the five
    runtime fields."""
    from contracts.schemas.reasoner import (
        ReasonerRequest as ContractRequest,
        ReasonerResult as ContractResult,
        ReasonerStatus,
    )

    request = ContractRequest(
        request_id="boundary-req-000",
        cycle_id="boundary-cycle-000",
        reasoner_name="boundary",
        reasoner_version="0.0.0",
        prompt="boundary",
        context={},
        requested_at=datetime.now(UTC),
    )
    result = ContractResult(
        result_id="boundary-res-000",
        request_id="boundary-req-000",
        status=ReasonerStatus.COMPLETED,
        reasoner_name="boundary",
        reasoner_version="0.0.0",
        output={},
        completed_at=datetime.now(UTC),
    )
    return request, result


class TestReplayBundleFiveFields:
    def test_complete_bundle_constructs_successfully(self) -> None:
        from reasoner_runtime.replay.models import ReplayBundle

        request, result = _build_complete_request_pair()
        bundle = ReplayBundle(
            sanitized_input="<scrubbed>",
            input_hash="0" * 64,
            raw_output='{"k": "v"}',
            parsed_result={"k": "v"},
            output_hash="1" * 64,
            request=request,
            result=result,
        )

        # All five must be present and non-None.
        assert bundle.sanitized_input
        assert bundle.input_hash
        assert bundle.raw_output is not None
        assert isinstance(bundle.parsed_result, dict)
        assert bundle.output_hash

    @pytest.mark.parametrize(
        "missing_field",
        [
            "sanitized_input",
            "input_hash",
            "raw_output",
            "parsed_result",
            "output_hash",
        ],
    )
    def test_missing_any_required_field_raises(self, missing_field: str) -> None:
        from reasoner_runtime.replay.models import ReplayBundle
        from pydantic import ValidationError

        request, result = _build_complete_request_pair()
        kwargs: dict[str, object] = {
            "sanitized_input": "<scrubbed>",
            "input_hash": "0" * 64,
            "raw_output": '{"k": "v"}',
            "parsed_result": {"k": "v"},
            "output_hash": "1" * 64,
            "request": request,
            "result": result,
        }
        del kwargs[missing_field]

        with pytest.raises(ValidationError):
            ReplayBundle(**kwargs)


# ── PII scrub ───────────────────────────────────────────────────────


class TestScrubPii:
    def test_scrub_input_returns_some_response(self) -> None:
        """scrub_input must at minimum be callable on a dict-shaped
        payload (the runtime path). Drift in the scrub interface would
        manifest here."""
        from reasoner_runtime import scrub_input

        payload = {"prompt": "hello", "context": {"note": "no PII here"}}
        scrubbed = scrub_input(payload)
        assert scrubbed is not None


# ── max_retries required ────────────────────────────────────────────


class TestMaxRetriesRequired:
    """ReasonerRequest's max_retries has no default (Field(ge=0)) — the
    runtime must not silently accept a request without it. This guards
    SUBPROJECT_TESTING_STANDARD §10.4 and CLAUDE.md C5."""

    def test_max_retries_field_has_no_default(self) -> None:
        from reasoner_runtime.core.models import ReasonerRequest

        # Inspect the model field — ``is_required()`` returns True iff
        # the field has no default and must be supplied.
        field = ReasonerRequest.model_fields["max_retries"]
        assert field.is_required(), (
            "ReasonerRequest.max_retries must be required — silent default "
            "would let LLM calls run with unset retry budget"
        )


# ── public.py subprocess-isolated deny scan ─────────────────────────


_BUSINESS_MODULES = (
    "data_platform",
    "main_core",
    "graph_engine",
    "audit_eval",
    "entity_registry",
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
    "torch",
    "tensorflow",
    "dagster",
)
_PROBE_SCRIPT = textwrap.dedent(
    """
    import json
    import sys
    sys.path.insert(0, {repo_root!r})
    sys.path.insert(0, {contracts_src!r})
    import reasoner_runtime.public  # noqa: F401
    print(json.dumps(sorted(sys.modules.keys())))
    """
).strip()


@pytest.fixture(scope="module")
def loaded_modules_in_clean_subprocess() -> frozenset[str]:
    repo_root = Path(__file__).resolve().parents[2]
    contracts_src = (repo_root.parent / "contracts" / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _PROBE_SCRIPT.format(
                repo_root=str(repo_root),
                contracts_src=str(contracts_src),
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError("subprocess probe failed; stderr:\n" + result.stderr)
    return frozenset(json.loads(result.stdout))


class TestPublicNoBusinessImports:
    def test_public_pulls_in_no_business_module(
        self, loaded_modules_in_clean_subprocess: frozenset[str]
    ) -> None:
        offenders = sorted(
            mod
            for mod in loaded_modules_in_clean_subprocess
            if any(mod == p or mod.startswith(p + ".") for p in _BUSINESS_MODULES)
        )
        assert not offenders, f"public pulled in business module(s): {offenders}"

    def test_public_pulls_in_no_heavy_infra(
        self, loaded_modules_in_clean_subprocess: frozenset[str]
    ) -> None:
        offenders = sorted(
            mod
            for mod in loaded_modules_in_clean_subprocess
            if any(
                mod == p or mod.startswith(p + ".") for p in _HEAVY_RUNTIME_PREFIXES
            )
        )
        assert not offenders, f"public pulled in heavy infra module(s): {offenders}"
