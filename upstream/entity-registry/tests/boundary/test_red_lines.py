"""Boundary tests for entity-registry red lines (per §10 + CLAUDE.md).

Three red-line checks:

1. **A+H dual-listing 零容忍** — CLAUDE.md: A+H 双上市分别有独立 canonical
   ID，通过 cross_listing_group 关联，绝不合并。Construct two
   CanonicalEntity instances simulating A-share + H-share for the same
   issuer; assert they have different canonical_entity_id values.
2. **unresolved 显式记录** — CLAUDE.md "未解析 mention 是否有显式
   unresolved 路径，不静默丢弃". The runtime resolution paths must
   surface unresolved cases as explicit decision_type, never None /
   silent drop.
3. **public.py 边界** — subprocess-isolated import deny scan
   (iron rule #2): no LLM provider direct import, no business module.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


# ── #1 A+H dual-listing 零容忍 ───────────────────────────────


class TestAHDualListingNotMerged:
    """Construct two distinct CanonicalEntity-shaped runtime payloads
    for A-share (300750.SZ) and a hypothetical H-share for the same
    issuer (e.g. 03750.HK). The runtime CanonicalEntity model must NOT
    silently merge them by canonical_entity_id collision; their IDs
    must differ.
    """

    def test_a_share_and_h_share_have_distinct_canonical_ids(self) -> None:
        from entity_registry.core import CanonicalEntity, EntityType, EntityStatus
        from datetime import UTC, datetime

        a_share = CanonicalEntity(
            canonical_entity_id="ENT_STOCK_300750.SZ",
            entity_type=EntityType.STOCK,
            display_name="宁德时代-A",
            status=EntityStatus.ACTIVE,
            anchor_code="300750.SZ",
            cross_listing_group="catl-cross-listing",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        h_share = CanonicalEntity(
            canonical_entity_id="ENT_STOCK_03750.HK",
            entity_type=EntityType.STOCK,
            display_name="宁德时代-H",
            status=EntityStatus.ACTIVE,
            anchor_code="03750.HK",
            cross_listing_group="catl-cross-listing",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        # Iron rule: different canonical IDs even within the same
        # cross_listing_group.
        assert a_share.canonical_entity_id != h_share.canonical_entity_id, (
            "A+H dual-listing must keep distinct canonical_entity_id "
            "(CLAUDE.md zero-tolerance invariant)"
        )
        # Cross-listing group is the bridge — same value links them
        # without merging the IDs.
        assert a_share.cross_listing_group == h_share.cross_listing_group


# ── #2 unresolved 显式记录 ───────────────────────────────────


class TestUnresolvedExplicit:
    """Per CLAUDE.md "未解析 mention 是否有显式 unresolved 路径，不静默
    丢弃": both ``ResolutionMethod`` and ``FinalStatus`` enums must
    carry a ``UNRESOLVED`` member so the runtime can label any failed
    resolution explicitly. Drift here would let a refactor silently
    swallow unresolved cases.
    """

    def test_resolution_method_enum_has_unresolved(self) -> None:
        from entity_registry.core import ResolutionMethod

        values = {member.value for member in ResolutionMethod}
        assert "unresolved" in values, (
            f"ResolutionMethod must include 'unresolved'; got {values}"
        )

    def test_final_status_enum_has_unresolved(self) -> None:
        from entity_registry.core import FinalStatus

        values = {member.value for member in FinalStatus}
        assert "unresolved" in values, (
            f"FinalStatus must include 'unresolved'; got {values}"
        )


# ── #3 public.py 边界（subprocess-isolated）─────────────────

_BUSINESS_DOWNSTREAMS = (
    "main_core", "data_platform", "graph_engine", "audit_eval",
    "reasoner_runtime",
    "subsystem_sdk", "subsystem_announcement", "subsystem_news",
    "orchestrator", "assembly", "feature_store", "stream_layer",
)
_HEAVY_RUNTIME_PREFIXES = (
    "psycopg", "pyiceberg", "neo4j",
    "litellm", "openai", "anthropic",
    "torch", "tensorflow",
    "dagster",
    "hanlp", "splink",  # entity-registry's own NER/fuzzy heavy deps
)
_PROBE_SCRIPT = textwrap.dedent(
    """
    import json, sys
    sys.path.insert(0, {src_dir!r})
    sys.path.insert(0, {contracts_src!r})
    import entity_registry.public  # noqa: F401
    print(json.dumps(sorted(sys.modules.keys())))
    """
).strip()


@pytest.fixture(scope="module")
def loaded_modules_in_clean_subprocess() -> frozenset[str]:
    repo_root = Path(__file__).resolve().parents[2]
    contracts_src = repo_root.parent / "contracts" / "src"
    src_dir = repo_root / "src"
    result = subprocess.run(
        [
            sys.executable, "-c",
            _PROBE_SCRIPT.format(
                src_dir=str(src_dir),
                contracts_src=str(contracts_src),
            ),
        ],
        check=False, capture_output=True, text=True,
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

    def test_public_pulls_in_no_heavy_infra(
        self, loaded_modules_in_clean_subprocess: frozenset[str]
    ) -> None:
        offenders = sorted(
            mod for mod in loaded_modules_in_clean_subprocess
            if any(mod == p or mod.startswith(p + ".") for p in _HEAVY_RUNTIME_PREFIXES)
        )
        assert not offenders, f"public pulled in heavy infra module(s): {offenders}"
