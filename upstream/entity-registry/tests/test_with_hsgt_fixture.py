"""Tushare Phase B — stock_hsgt_snapshot consumer regression.

Plan: ~/.claude/plans/wise-cooking-wolf.md §6.3.1.

Drives the real entity-registry initialization pipeline against the
tushare-derived HSGT constituent projection at
``tests/fixtures/stock_hsgt_snapshot.json``. Guards that:

1. Every fixture row validates as ``StockBasicRecord``.
2. ``FileStockBasicSnapshotReader`` can materialize all rows.
3. ``initialize_from_stock_basic_into`` creates the expected
   canonical entities + at least one alias per entity.
4. Every fixture row has ``is_hs`` populated (H or S) — the northbound
   HSGT constituency is the whole point of the fixture, so a row
   without ``is_hs`` means the fixture drifted.

The sibling ``stock_hsgt_snapshot.source.json`` documents source-to-case
traceability per Phase B §7 traceability contract.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

import entity_registry
from entity_registry.init import (
    FileStockBasicSnapshotReader,
    StockBasicRecord,
    initialize_from_stock_basic_into,
)
from entity_registry.storage import (
    InMemoryAliasRepository,
    InMemoryEntityRepository,
)


FIXTURE_PATH = Path("tests/fixtures/stock_hsgt_snapshot.json")
SOURCE_PATH = Path("tests/fixtures/stock_hsgt_snapshot.source.json")


@pytest.fixture(autouse=True)
def reset_public_repositories() -> Iterator[None]:
    entity_registry.reset_default_repositories()
    yield
    entity_registry.reset_default_repositories()


def test_hsgt_source_json_has_all_traceability_keys() -> None:
    """Phase B §7: traceability sidecar must carry the 8-key contract."""

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
    assert not missing, f"stock_hsgt source missing keys: {missing}"
    assert source["completeness_status"] == "未见明显遗漏"


def test_hsgt_fixture_loads_via_file_snapshot_reader() -> None:
    records = FileStockBasicSnapshotReader().read(str(FIXTURE_PATH))
    assert len(records) >= 5, (
        f"stock_hsgt_snapshot must carry 5-8 rows per plan §6.3.1; "
        f"got {len(records)}"
    )
    for record in records:
        assert isinstance(record, StockBasicRecord)


def test_every_hsgt_row_has_is_hs_populated() -> None:
    """Core invariant: northbound HSGT membership is the whole fixture
    purpose, so every row MUST carry ``is_hs`` (H for 沪股通, S for
    深股通). A row with ``is_hs`` absent would mean the fixture has
    drifted and no longer serves as an HSGT snapshot."""

    records = FileStockBasicSnapshotReader().read(str(FIXTURE_PATH))
    for record in records:
        assert record.is_hs is not None and record.is_hs.upper() in {"H", "S"}, (
            f"{record.ts_code}: is_hs must be 'H' or 'S'; "
            f"got {record.is_hs!r}"
        )


def test_hsgt_initialization_creates_all_entities_and_aliases() -> None:
    """Drive the real initialization pipeline + assert entity + alias
    presence. ``initialize_from_stock_basic_into`` is the production
    entry point so this test also guards the initialization path."""

    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()

    result = initialize_from_stock_basic_into(
        str(FIXTURE_PATH),
        entity_repo,
        alias_repo,
        stock_basic_reader=FileStockBasicSnapshotReader(),
    )

    assert not result.errors, f"unexpected initialization errors: {result.errors}"

    records = FileStockBasicSnapshotReader().read(str(FIXTURE_PATH))
    # ``generate_stock_entity_id`` (entity_registry/core.py:77) preserves
    # the dot in ts_code — the canonical id is ``ENT_STOCK_<ts_code>``
    # verbatim (e.g. ENT_STOCK_600084.SH), not an underscored form.
    expected_canonical_ids = {
        f"ENT_STOCK_{record.ts_code}" for record in records
    }
    assert result.entities_created == len(expected_canonical_ids)

    for canonical_id in expected_canonical_ids:
        assert entity_repo.get(canonical_id) is not None, (
            f"canonical entity {canonical_id} not persisted"
        )
        aliases = alias_repo.find_by_entity(canonical_id)
        assert len(aliases) >= 1, (
            f"canonical entity {canonical_id} has no aliases; "
            f"initialize_from_stock_basic_into is expected to register "
            f"at least one alias per stock_basic row"
        )
