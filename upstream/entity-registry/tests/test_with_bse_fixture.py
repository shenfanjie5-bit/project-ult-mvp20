"""Tushare Phase B — bse_mapping_snapshot consumer regression.

Plan: ~/.claude/plans/wise-cooking-wolf.md §6.3.2.

Drives the real entity-registry initialization pipeline against the
tushare-derived BSE (北交所) new-code projection at
``tests/fixtures/bse_mapping_snapshot.json``. Guards that:

1. ``.BJ`` ts_codes map to ``exchange == "BSE"`` via the
   ``_exchange_from_ts_code`` helper (entity-registry init.py:598-609).
2. Generated ``canonical_entity_id`` follows ``ENT_STOCK_*.BJ`` shape
   (``generate_stock_entity_id`` preserves the dot).
3. Fixture rows all carry ``is_hs = null`` — BSE stocks are NOT in
   the northbound HSGT universe, so accidentally setting ``is_hs``
   to H/S here would cross-contaminate the HSGT semantics.

Sibling ``bse_mapping_snapshot.source.json`` carries Phase B §7
traceability.
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


FIXTURE_PATH = Path("tests/fixtures/bse_mapping_snapshot.json")
SOURCE_PATH = Path("tests/fixtures/bse_mapping_snapshot.source.json")


@pytest.fixture(autouse=True)
def reset_public_repositories() -> Iterator[None]:
    entity_registry.reset_default_repositories()
    yield
    entity_registry.reset_default_repositories()


def test_bse_source_json_has_all_traceability_keys() -> None:
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
    assert not missing, f"bse_mapping source missing keys: {missing}"
    assert source["completeness_status"] == "未见明显遗漏"


def test_bse_fixture_loads_via_file_snapshot_reader() -> None:
    records = FileStockBasicSnapshotReader().read(str(FIXTURE_PATH))
    assert len(records) >= 5, (
        f"bse_mapping_snapshot must carry 5-8 rows per plan §6.3.2; "
        f"got {len(records)}"
    )
    for record in records:
        assert isinstance(record, StockBasicRecord)


def test_every_bse_row_has_exchange_bse_and_bj_ts_code() -> None:
    """Core invariant: BSE rows MUST carry ts_code ending in .BJ AND
    exchange='BSE'. The plan explicitly pins the exchange pinning rule
    here so the fixture itself doesn't drift."""

    records = FileStockBasicSnapshotReader().read(str(FIXTURE_PATH))
    for record in records:
        assert record.ts_code.endswith(".BJ"), (
            f"{record.ts_code}: must end with .BJ for BSE"
        )
        assert record.exchange == "BSE", (
            f"{record.ts_code}: exchange must be BSE; got {record.exchange!r}"
        )


def test_bse_rows_do_not_carry_is_hs() -> None:
    """Zero-contamination invariant: BSE stocks are NOT in the northbound
    HSGT universe, so is_hs MUST be null. Accidentally setting is_hs
    here would blur the HSGT semantic for downstream consumers."""

    records = FileStockBasicSnapshotReader().read(str(FIXTURE_PATH))
    for record in records:
        assert record.is_hs is None, (
            f"{record.ts_code}: is_hs must be null for BSE stocks; "
            f"got {record.is_hs!r}"
        )


def test_bse_initialization_generates_ent_stock_bj_canonical_ids() -> None:
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
    for record in records:
        expected_id = f"ENT_STOCK_{record.ts_code}"
        assert expected_id.endswith(".BJ"), (
            f"{expected_id}: canonical id must end with .BJ suffix "
            f"so BSE stocks are distinguishable by id alone"
        )
        assert entity_repo.get(expected_id) is not None, (
            f"canonical entity {expected_id} not persisted"
        )
