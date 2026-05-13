from __future__ import annotations

import pytest

from data_platform.provider_catalog import CANONICAL_DATASETS
from data_platform.serving.canonical_datasets import (
    CANONICAL_DATASET_TABLE_MAPPINGS,
    USE_CANONICAL_V2_ENV_VAR,
    UnsupportedCanonicalDataset,
    canonical_datasets_for_table,
    canonical_table_for_dataset,
    canonical_table_identifier_for_dataset,
)


def test_canonical_dataset_ids_map_explicitly_to_iceberg_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy-mode mapping pin. The v2-flag-on equivalent is parametrized in
    `tests/serving/test_canonical_datasets_v2_cutover.py`."""

    monkeypatch.delenv(USE_CANONICAL_V2_ENV_VAR, raising=False)
    assert canonical_table_identifier_for_dataset("security_master") == "canonical.dim_security"
    assert canonical_table_for_dataset("price_bar") == "fact_price_bar"
    assert canonical_table_for_dataset("market_daily_feature") == "fact_market_daily_feature"
    assert canonical_table_for_dataset("index_price_bar") == "fact_index_price_bar"
    assert canonical_table_for_dataset("financial_forecast_event") == "fact_forecast_event"


def test_canonical_dataset_mapping_does_not_assume_dataset_id_is_table_name() -> None:
    non_identity_mappings = {
        mapping.dataset_id: mapping.table_name
        for mapping in CANONICAL_DATASET_TABLE_MAPPINGS
        if mapping.dataset_id != mapping.table_name
    }

    assert non_identity_mappings["price_bar"] == "fact_price_bar"
    assert non_identity_mappings["security_master"] == "dim_security"
    assert non_identity_mappings["market_daily_feature"] == "fact_market_daily_feature"


def test_canonical_dataset_mapping_rejects_unimplemented_dataset() -> None:
    assert "trading_calendar" in CANONICAL_DATASETS

    with pytest.raises(UnsupportedCanonicalDataset):
        canonical_table_for_dataset("trading_calendar")


def test_table_to_dataset_mapping_handles_shared_tables() -> None:
    assert canonical_datasets_for_table("canonical.fact_price_bar") == (
        "price_bar",
        "adjustment_factor",
    )
    assert canonical_datasets_for_table("dim_security") == (
        "security_master",
        "security_profile",
    )
