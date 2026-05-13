from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from data_platform.cycle import (
    current_cycle_inputs as package_current_cycle_inputs,
    load_current_cycle_inputs,
)
from data_platform.cycle.current_cycle_inputs import (
    CurrentCycleInputsUnavailable,
    canonical_reader,
    current_cycle_inputs,
    load_current_cycle_inputs as module_load_current_cycle_inputs,
)


FORBIDDEN_OUTPUT_TOKENS = ("stg_", "tushare", "doc_api", "raw")


def test_current_cycle_inputs_loads_provider_neutral_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _CanonicalReaderFixture()
    fixture.install(monkeypatch)

    rows = current_cycle_inputs(
        "CYCLE_20260416",
        "cycle_candidate_selection:CYCLE_20260416",
        ["600519.SH", "ENT_STOCK_000001.SZ"],
    )

    assert [row["entity_id"] for row in rows] == [
        "ENT_STOCK_600519.SH",
        "ENT_STOCK_000001.SZ",
    ]
    assert rows[0]["trade_date"] == "2026-04-16"
    assert rows[0]["close"] == 1700.0
    assert rows[0]["pre_close"] == 1680.0
    assert rows[0]["return_1d"] == 0.012
    assert rows[0]["volume"] == 100.0
    assert rows[0]["amount"] == 170000.0
    assert rows[0]["market"] == "Main"
    assert rows[0]["industry"] == "Liquor"
    assert rows[0]["canonical_dataset_refs"] == ["price_bar", "security_master"]
    assert rows[0]["canonical_snapshot_ids"] == {
        "price_bar": 1001,
        "security_master": 1002,
    }
    assert rows[0]["lineage_refs"] == [
        "cycle:CYCLE_20260416",
        "selection:cycle_candidate_selection:CYCLE_20260416",
        "candidate:600519.SH",
        "canonical:price_bar@1001",
        "canonical:security_master@1002",
    ]
    assert fixture.dataset_reads == ["security_master", "price_bar"]
    assert fixture.table_reads == ["canonical_entity", "entity_alias"]


def test_current_cycle_inputs_output_does_not_leak_source_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _CanonicalReaderFixture()
    fixture.install(monkeypatch)

    rows = current_cycle_inputs(
        "CYCLE_20260416",
        "cycle_candidate_selection:CYCLE_20260416",
        ["600519.SH"],
    )

    payload = json.dumps(rows, sort_keys=True, default=str).lower()
    for token in FORBIDDEN_OUTPUT_TOKENS:
        assert token not in payload


def test_current_cycle_inputs_can_read_explicit_snapshot_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy-mode snapshot-set key resolution.

    The `as_of_snapshot` dict here keys by the LEGACY table identifier
    (`canonical.dim_security`). Under `DP_CANONICAL_USE_V2=1` the production
    code queries the v2 identifier (`canonical_v2.dim_security`) and the
    legacy key would be silently ignored — that's intentional v2 routing,
    not a regression. M1.5-3 pins this test to legacy mode; the v2 mode is
    exercised via test_canonical_datasets_v2_cutover.py and the dataset_id
    form is tested by test_current_cycle_inputs_loads_provider_neutral_rows
    above.
    """

    monkeypatch.delenv("DP_CANONICAL_USE_V2", raising=False)
    fixture = _CanonicalReaderFixture()
    fixture.install(monkeypatch)

    rows = current_cycle_inputs(
        "CYCLE_20260416",
        "cycle_candidate_selection:CYCLE_20260416",
        ["600519.SH"],
        as_of_snapshot={
            "price_bar": 3001,
            "canonical.dim_security": 3002,
        },
    )

    assert rows[0]["canonical_snapshot_ids"] == {
        "price_bar": 3001,
        "security_master": 3002,
    }
    assert fixture.dataset_snapshot_reads == [
        ("security_master", 3002),
        ("price_bar", 3001),
    ]


def test_current_cycle_inputs_fails_closed_when_snapshot_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _CanonicalReaderFixture()
    fixture.install(monkeypatch)

    with pytest.raises(CurrentCycleInputsUnavailable) as exc_info:
        current_cycle_inputs(
            "CYCLE_20260416",
            "cycle_candidate_selection:CYCLE_20260416",
            ["600519.SH"],
            as_of_snapshot={"price_bar": 3001},
        )

    assert exc_info.value.code == "canonical_snapshot_missing"
    assert exc_info.value.evidence == {"missing_datasets": ["security_master"]}


def test_current_cycle_inputs_fails_closed_when_entity_row_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _CanonicalReaderFixture()
    fixture.tables["canonical_entity"] = pa.table({"canonical_entity_id": []})
    fixture.install(monkeypatch)

    with pytest.raises(CurrentCycleInputsUnavailable) as exc_info:
        current_cycle_inputs(
            "CYCLE_20260416",
            "cycle_candidate_selection:CYCLE_20260416",
            ["600519.SH"],
        )

    assert exc_info.value.code == "canonical_entity_missing"


def test_current_cycle_inputs_fails_closed_when_candidate_price_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _CanonicalReaderFixture()
    # Provide BOTH legacy and v2 alias columns so the fixture works under
    # either DP_CANONICAL_USE_V2 state. Production code in current_cycle_inputs
    # picks the right one via canonical_alias_column_for_dataset().
    fixture.datasets["price_bar"] = pa.table(
        {
            "ts_code": ["000001.SZ"],
            "security_id": ["000001.SZ"],
            "trade_date": [date(2026, 4, 16)],
            "freq": ["daily"],
            "close": [Decimal("10.5")],
            "pre_close": [Decimal("10.0")],
            "pct_chg": [Decimal("5.0")],
            "vol": [Decimal("10")],
            "amount": [Decimal("105")],
        }
    )
    fixture.install(monkeypatch)

    with pytest.raises(CurrentCycleInputsUnavailable) as exc_info:
        current_cycle_inputs(
            "CYCLE_20260416",
            "cycle_candidate_selection:CYCLE_20260416",
            ["600519.SH"],
        )

    assert exc_info.value.code == "canonical_candidate_rows_missing"
    assert exc_info.value.evidence["missing_rows"] == [
        {
            "candidate_id": "600519.SH",
            "entity_id": "ENT_STOCK_600519.SH",
            "reason": "missing canonical candidate row",
        }
    ]


def test_current_cycle_inputs_public_aliases_export_same_loader() -> None:
    assert package_current_cycle_inputs is current_cycle_inputs
    assert load_current_cycle_inputs is module_load_current_cycle_inputs


class _CanonicalReaderFixture:
    def __init__(self) -> None:
        self.tables: dict[str, pa.Table] = {
            "canonical_entity": pa.table(
                {
                    "canonical_entity_id": [
                        "ENT_STOCK_600519.SH",
                        "ENT_STOCK_000001.SZ",
                    ]
                }
            ),
            "entity_alias": pa.table(
                {
                    "alias": ["600519.SH", "000001.SZ"],
                    "canonical_entity_id": [
                        "ENT_STOCK_600519.SH",
                        "ENT_STOCK_000001.SZ",
                    ],
                }
            ),
        }
        # Provide BOTH legacy `ts_code` and v2 `security_id` alias columns so
        # the fixture works under either DP_CANONICAL_USE_V2 state. Production
        # current_cycle_inputs picks the right one via
        # canonical_alias_column_for_dataset(). M1.5-3 v2-default-on test lane
        # uses this for fixture flag-agnosticism.
        self.datasets: dict[str, pa.Table] = {
            "security_master": pa.table(
                {
                    "ts_code": ["600519.SH", "000001.SZ"],
                    "security_id": ["600519.SH", "000001.SZ"],
                    "market": ["Main", "Main"],
                    "industry": ["Liquor", "Bank"],
                }
            ),
            "price_bar": pa.table(
                {
                    "ts_code": ["600519.SH", "000001.SZ"],
                    "security_id": ["600519.SH", "000001.SZ"],
                    "trade_date": [date(2026, 4, 16), date(2026, 4, 16)],
                    "freq": ["daily", "daily"],
                    "close": [Decimal("1700.0"), Decimal("10.5")],
                    "pre_close": [Decimal("1680.0"), Decimal("10.0")],
                    "pct_chg": [Decimal("1.2"), Decimal("5.0")],
                    "vol": [Decimal("100"), Decimal("10")],
                    "amount": [Decimal("170000"), Decimal("105")],
                }
            ),
        }
        self.snapshots = {"price_bar": 1001, "security_master": 1002}
        self.table_reads: list[str] = []
        self.dataset_reads: list[str] = []
        self.dataset_snapshot_reads: list[tuple[str, int]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(canonical_reader, "read_canonical", self.read_canonical)
        monkeypatch.setattr(
            canonical_reader,
            "read_canonical_dataset",
            self.read_canonical_dataset,
        )
        monkeypatch.setattr(
            canonical_reader,
            "read_canonical_dataset_snapshot",
            self.read_canonical_dataset_snapshot,
        )
        monkeypatch.setattr(
            canonical_reader,
            "canonical_snapshot_id_for_dataset",
            self.canonical_snapshot_id_for_dataset,
        )

    def read_canonical(
        self,
        table: str,
        columns: list[str] | None = None,
        filters: list[tuple[str, str, Any]] | None = None,
    ) -> pa.Table:
        assert filters is None
        self.table_reads.append(table)
        payload = self.tables[table]
        return payload.select(columns or payload.schema.names)

    def read_canonical_dataset(
        self,
        dataset_id: str,
        columns: list[str] | None = None,
        filters: list[tuple[str, str, Any]] | None = None,
    ) -> pa.Table:
        assert filters is None
        self.dataset_reads.append(dataset_id)
        payload = self.datasets[dataset_id]
        return payload.select(columns or payload.schema.names)

    def read_canonical_dataset_snapshot(
        self,
        dataset_id: str,
        snapshot_id: int,
    ) -> pa.Table:
        self.dataset_snapshot_reads.append((dataset_id, snapshot_id))
        return self.datasets[dataset_id]

    def canonical_snapshot_id_for_dataset(self, dataset_id: str) -> int:
        return self.snapshots[dataset_id]
