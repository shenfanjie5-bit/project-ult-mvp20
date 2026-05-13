"""Tushare Phase B — ah_pair_snapshot consumer regression.

Plan: ~/.claude/plans/wise-cooking-wolf.md §6.3.3.

Drives the real entity-registry initialization pipeline against the
tushare-derived A+H cross-listing projection at
``tests/fixtures/ah_pair_snapshot.json``. The fixture guards the
zero-tolerance invariant from ``entity-registry/CLAUDE.md``: "A+H 错误
合并率 = 0" — A and H sides of the same company MUST retain two
distinct canonical_entity_id values AND both MUST carry the SAME
``cross_listing_group``.

Assertions:

1. ``detect_cross_listing_groups(records)`` returns ≥ 1 group.
2. For each pair, A-side and H-side produce two DIFFERENT canonical ids.
3. For each pair, A-side and H-side share the SAME cross_listing_group.
4. The initialization pipeline (end-to-end) persists these semantics
   into the entity repository.

Sibling ``ah_pair_snapshot.source.json`` carries Phase B §7 traceability.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

import entity_registry
from entity_registry.core import generate_stock_entity_id
from entity_registry.init import (
    FileStockBasicSnapshotReader,
    StockBasicRecord,
    detect_cross_listing_groups,
    initialize_from_stock_basic_into,
)
from entity_registry.storage import (
    InMemoryAliasRepository,
    InMemoryEntityRepository,
)


FIXTURE_PATH = Path("tests/fixtures/ah_pair_snapshot.json")
SOURCE_PATH = Path("tests/fixtures/ah_pair_snapshot.source.json")

#: The 3 pairs the fixture encodes. Used for cross-side assertions.
EXPECTED_PAIRS: tuple[tuple[str, str], ...] = (
    ("000063.SZ", "00763.HK"),
    ("000039.SZ", "02039.HK"),
    ("000002.SZ", "02202.HK"),
)


@pytest.fixture(autouse=True)
def reset_public_repositories() -> Iterator[None]:
    entity_registry.reset_default_repositories()
    yield
    entity_registry.reset_default_repositories()


def test_ah_source_json_has_all_traceability_keys() -> None:
    assert SOURCE_PATH.is_file(), f"missing traceability sidecar: {SOURCE_PATH}"
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))

    required = {
        "corpus_root",
        "dataset_path",
        "datasets",
        "selected_ts_codes",
        "date_window",
        "audit_timestamp",
        "completeness_status",
        "coverage_note",
    }
    missing = required - set(source.keys())
    assert not missing, f"ah_pair source missing keys: {missing}"
    assert source["completeness_status"] == "未见明显遗漏"


def test_ah_fixture_carries_three_pairs_six_rows() -> None:
    records = FileStockBasicSnapshotReader().read(str(FIXTURE_PATH))
    assert len(records) == 6, (
        f"ah_pair_snapshot must carry exactly 6 rows (3 pairs × 2 sides); "
        f"got {len(records)}"
    )
    ts_codes = [r.ts_code for r in records]
    for a_side, h_side in EXPECTED_PAIRS:
        assert a_side in ts_codes, f"A-side {a_side} missing from fixture"
        assert h_side in ts_codes, f"H-side {h_side} missing from fixture"


def test_detect_cross_listing_groups_finds_three_groups() -> None:
    """``detect_cross_listing_groups`` is the public API that
    ``initialize_from_stock_basic_into`` calls; we assert it classifies
    the 6 rows into exactly 3 groups (one per pair)."""

    records = FileStockBasicSnapshotReader().read(str(FIXTURE_PATH))
    groups = detect_cross_listing_groups(records)

    # All 6 ts_codes should appear in the group mapping (no pair loses a side).
    for record in records:
        assert record.ts_code in groups, (
            f"{record.ts_code} not classified into any cross-listing group"
        )

    distinct_group_ids = set(groups.values())
    assert len(distinct_group_ids) == 3, (
        f"expected 3 cross-listing groups (one per pair); "
        f"got {len(distinct_group_ids)}: {distinct_group_ids}"
    )


@pytest.mark.parametrize("a_side, h_side", EXPECTED_PAIRS)
def test_pair_shares_same_cross_listing_group(
    a_side: str, h_side: str
) -> None:
    """Zero-tolerance invariant #1 (pair identity preserved): A-side
    and H-side of the same company must share the SAME cross_listing_group."""

    records = FileStockBasicSnapshotReader().read(str(FIXTURE_PATH))
    groups = detect_cross_listing_groups(records)

    assert groups[a_side] == groups[h_side], (
        f"A-side {a_side} and H-side {h_side} must share the same "
        f"cross_listing_group; got {groups[a_side]!r} vs {groups[h_side]!r}"
    )


@pytest.mark.parametrize("a_side, h_side", EXPECTED_PAIRS)
def test_pair_produces_distinct_canonical_entity_ids(
    a_side: str, h_side: str
) -> None:
    """Zero-tolerance invariant #2 (no A+H merge): A-side and H-side
    MUST receive two DIFFERENT canonical_entity_id values. Merging
    them would re-introduce the exact bug entity-registry CLAUDE.md
    bans at zero tolerance."""

    a_canonical = generate_stock_entity_id(a_side)
    h_canonical = generate_stock_entity_id(h_side)
    assert a_canonical != h_canonical, (
        f"A-side {a_side} and H-side {h_side} must produce two distinct "
        f"canonical ids; got the same id {a_canonical!r} — this is the "
        f"exact regression CLAUDE.md forbids"
    )


def test_ah_initialization_persists_distinct_entities_sharing_group() -> None:
    """End-to-end: drive the production ``initialize_from_stock_basic_into``
    pipeline and assert persisted entities honor both invariants
    simultaneously."""

    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()

    result = initialize_from_stock_basic_into(
        str(FIXTURE_PATH),
        entity_repo,
        alias_repo,
        stock_basic_reader=FileStockBasicSnapshotReader(),
    )
    assert not result.errors, f"unexpected initialization errors: {result.errors}"
    assert result.cross_listing_groups == 3

    for a_side, h_side in EXPECTED_PAIRS:
        a_entity = entity_repo.get(generate_stock_entity_id(a_side))
        h_entity = entity_repo.get(generate_stock_entity_id(h_side))
        assert a_entity is not None and h_entity is not None, (
            f"missing A or H canonical entity for pair {a_side}/{h_side}"
        )
        assert a_entity.canonical_entity_id != h_entity.canonical_entity_id
        assert a_entity.cross_listing_group is not None
        assert a_entity.cross_listing_group == h_entity.cross_listing_group, (
            f"A-side {a_side} cross_listing_group "
            f"{a_entity.cross_listing_group!r} ≠ H-side {h_side} "
            f"{h_entity.cross_listing_group!r}"
        )
