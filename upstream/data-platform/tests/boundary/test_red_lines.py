"""Boundary tests for data-platform red lines (per §10 STANDARD + CLAUDE.md).

Three red-line checks:

1. **Raw / Canonical / Formal 分层不混**：data_platform.raw must not
   import from data_platform.serving.formal (Raw and Formal are different
   zones per CLAUDE.md §"架构核心决策" point 1).
2. **ingest_metadata 不在 producer Ex payload**：CLAUDE.md BAN list and
   §"架构核心决策" point 5: submitted_at / ingest_seq must not appear as
   producer-side fields on ExPayload — they are written by Layer B at
   ingest time.
3. **public.py 不引入业务依赖 / LLM**：subprocess-isolated import deny
   scan (iron rule #2).
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


# ── #1 Raw / Canonical / Formal 分层不混 ─────────────────────────


class TestRawCanonicalFormalZoneBoundary:
    """data_platform.raw is the Raw Zone (Parquet/JSON, no Iceberg).
    data_platform.serving.formal is the Formal Zone (Iceberg + manifest).
    Per CLAUDE.md these are separate zones; raw must not depend on formal.
    """

    SRC_DIR = Path(__file__).resolve().parents[2] / "src" / "data_platform"
    FORBIDDEN_FROM_RAW = (
        "data_platform.serving.formal",
        "data_platform.cycle.manifest",
    )

    def test_raw_does_not_import_formal_serving(self) -> None:
        violations: list[str] = []
        raw_dir = self.SRC_DIR / "raw"
        for py_path in raw_dir.rglob("*.py"):
            tree = ast.parse(py_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if any(module == p or module.startswith(p + ".") for p in self.FORBIDDEN_FROM_RAW):
                        violations.append(
                            f"{py_path.relative_to(self.SRC_DIR.parents[1])}:"
                            f"{node.lineno}: from {module}"
                        )
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if any(alias.name == p or alias.name.startswith(p + ".")
                               for p in self.FORBIDDEN_FROM_RAW):
                            violations.append(
                                f"{py_path.relative_to(self.SRC_DIR.parents[1])}:"
                                f"{node.lineno}: import {alias.name}"
                            )
        assert not violations, (
            "Raw Zone must not depend on Formal Zone serving (CLAUDE.md "
            "decision #1):\n" + "\n".join(violations)
        )


# ── #2 ingest_metadata 不在 producer ExPayload ──────────────────


class TestIngestMetadataNotInProducerPayload:
    """CLAUDE.md BAN: submitted_at / ingest_seq must not be exposed as
    producer-side ExPayload fields. They are Layer B's ingest metadata
    written on insert. If they leak into the producer schema, downstream
    contracts test will accept producer payloads carrying them — and
    the subsystem-sdk side will start setting them, breaking the
    invariant.
    """

    FORBIDDEN_PRODUCER_FIELDS = ("submitted_at", "ingest_seq")

    def test_ex_payload_does_not_declare_ingest_metadata(self) -> None:
        from data_platform.queue.validation import ExPayload

        # ExPayload is a Pydantic model or TypedDict. Inspect declared
        # fields and check none of the forbidden ingest-metadata names
        # appear at the top level.
        if hasattr(ExPayload, "model_fields"):
            declared_fields = set(ExPayload.model_fields.keys())
        else:
            # TypedDict / dataclass / plain class fallback.
            declared_fields = set(getattr(ExPayload, "__annotations__", {}).keys())

        offenders = [
            f for f in self.FORBIDDEN_PRODUCER_FIELDS if f in declared_fields
        ]
        assert not offenders, (
            f"ExPayload must NOT declare ingest-metadata fields: {offenders} "
            "(CLAUDE.md BAN: submitted_at / ingest_seq are Layer B-side)"
        )


# ── #3 public.py 边界扫描（subprocess-isolated）──────────────────

_BUSINESS_DOWNSTREAMS = (
    "main_core",
    "graph_engine",
    "audit_eval",
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
    "litellm",
    "openai",
    "anthropic",
    "torch",
    "tensorflow",
    "dagster",
)
_PROBE_SCRIPT = textwrap.dedent(
    """
    import json
    import sys
    sys.path.insert(0, {src_dir!r})
    import data_platform.public  # noqa: F401
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
        raise AssertionError("subprocess probe failed; stderr:\n" + result.stderr)
    return frozenset(json.loads(result.stdout))


class TestPublicNoBusinessImports:
    def test_public_pulls_in_no_business_module(
        self, loaded_modules_in_clean_subprocess: frozenset[str]
    ) -> None:
        offenders = sorted(
            mod for mod in loaded_modules_in_clean_subprocess
            if any(mod == p or mod.startswith(p + ".") for p in _BUSINESS_DOWNSTREAMS)
        )
        assert not offenders, f"public pulled in business module(s): {offenders}"

    def test_public_pulls_in_no_llm_or_dagster(
        self, loaded_modules_in_clean_subprocess: frozenset[str]
    ) -> None:
        offenders = sorted(
            mod for mod in loaded_modules_in_clean_subprocess
            if any(mod == p or mod.startswith(p + ".") for p in _HEAVY_RUNTIME_PREFIXES)
        )
        assert not offenders, f"public pulled in LLM/dagster module(s): {offenders}"
