"""Reader cutover tests for canonical_v2 / canonical_lineage namespace.

These tests assert that the `DP_CANONICAL_USE_V2` env flag swaps the dataset
table mapping to the canonical_v2 namespace AND that the alias-column helper
returns the canonical (provider-neutral) identifier name. event_timeline routes
to `canonical_v2.fact_event` with 8 source interfaces after M1.8.

Per ult_milestone.md M1.4 + M1-G2. No source code in current_cycle_inputs.py
is exercised here — that path uses the same helpers and is unit-tested in
`tests/cycle/test_current_cycle_inputs*.py`.
"""

from __future__ import annotations

import pytest

from data_platform.serving.canonical_datasets import (
    CANONICAL_DATASET_TABLE_MAPPINGS,
    CANONICAL_DATASET_TABLE_MAPPINGS_V2,
    USE_CANONICAL_V2_ENV_VAR,
    canonical_alias_column_for_dataset,
    canonical_table_identifier_for_dataset,
    canonical_table_mapping_for_dataset,
    use_canonical_v2,
)


def test_default_mapping_remains_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(USE_CANONICAL_V2_ENV_VAR, raising=False)
    assert use_canonical_v2() is False
    assert (
        canonical_table_identifier_for_dataset("security_master")
        == "canonical.dim_security"
    )
    assert canonical_alias_column_for_dataset("security_master") == "ts_code"
    assert canonical_alias_column_for_dataset("index_master") == "index_code"


@pytest.mark.parametrize("flag_value", ["1", "true", "yes", "on", "TRUE"])
def test_v2_flag_switches_mapping(
    monkeypatch: pytest.MonkeyPatch, flag_value: str
) -> None:
    monkeypatch.setenv(USE_CANONICAL_V2_ENV_VAR, flag_value)
    assert use_canonical_v2() is True
    assert (
        canonical_table_identifier_for_dataset("security_master")
        == "canonical_v2.dim_security"
    )
    assert (
        canonical_table_identifier_for_dataset("price_bar")
        == "canonical_v2.fact_price_bar"
    )
    assert (
        canonical_table_identifier_for_dataset("index_master")
        == "canonical_v2.dim_index"
    )


# Pinned dataset_id -> canonical_v2 table identifier mapping.
# Lock-step with `CANONICAL_DATASET_TABLE_MAPPINGS_V2` in canonical_datasets.py.
# Every dataset_id present in the legacy mapping MUST be present here after
# M1.8 (event_timeline now resolves to canonical_v2.fact_event for 8 sources).
_EXPECTED_V2_MAPPING: tuple[tuple[str, str], ...] = (
    ("security_master", "canonical_v2.dim_security"),
    ("security_profile", "canonical_v2.dim_security"),
    ("price_bar", "canonical_v2.fact_price_bar"),
    ("adjustment_factor", "canonical_v2.fact_price_bar"),
    ("market_daily_feature", "canonical_v2.fact_market_daily_feature"),
    ("index_master", "canonical_v2.dim_index"),
    ("index_price_bar", "canonical_v2.fact_index_price_bar"),
    ("event_timeline", "canonical_v2.fact_event"),
    ("financial_indicator", "canonical_v2.fact_financial_indicator"),
    ("financial_forecast_event", "canonical_v2.fact_forecast_event"),
    ("holding_position", "canonical_v2.fact_holding_position"),
    ("northbound_turnover_daily", "canonical_v2.fact_northbound_turnover"),
)


@pytest.mark.parametrize(("dataset_id", "expected_identifier"), _EXPECTED_V2_MAPPING)
def test_v2_flag_routes_every_dataset_to_canonical_v2(
    monkeypatch: pytest.MonkeyPatch,
    dataset_id: str,
    expected_identifier: str,
) -> None:
    """All v2-mapped canonical dataset_ids resolve to a canonical_v2 table under flag.

    M1-G2 closed the last gap (event_timeline). M1.5-2 pins the full table
    so any future cutover regression — e.g., a dataset_id silently falling
    back to the legacy namespace — fails at this guard.
    """

    monkeypatch.setenv(USE_CANONICAL_V2_ENV_VAR, "1")
    assert (
        canonical_table_identifier_for_dataset(dataset_id) == expected_identifier
    )


_EXPECTED_LEGACY_MAPPING: tuple[tuple[str, str], ...] = (
    ("security_master", "canonical.dim_security"),
    ("security_profile", "canonical.dim_security"),
    ("price_bar", "canonical.fact_price_bar"),
    ("adjustment_factor", "canonical.fact_price_bar"),
    ("market_daily_feature", "canonical.fact_market_daily_feature"),
    ("index_master", "canonical.dim_index"),
    ("index_price_bar", "canonical.fact_index_price_bar"),
    ("event_timeline", "canonical.fact_event"),
    ("financial_indicator", "canonical.fact_financial_indicator"),
    ("financial_forecast_event", "canonical.fact_forecast_event"),
)


@pytest.mark.parametrize(("dataset_id", "expected_identifier"), _EXPECTED_LEGACY_MAPPING)
def test_default_routes_every_dataset_to_legacy(
    monkeypatch: pytest.MonkeyPatch,
    dataset_id: str,
    expected_identifier: str,
) -> None:
    """Without the v2 flag, all 10 datasets resolve to legacy `canonical.*`."""

    monkeypatch.delenv(USE_CANONICAL_V2_ENV_VAR, raising=False)
    assert (
        canonical_table_identifier_for_dataset(dataset_id) == expected_identifier
    )


_EXPECTED_DEFAULT_ALIAS: tuple[tuple[str, str], ...] = (
    ("security_master", "ts_code"),
    ("security_profile", "ts_code"),
    ("price_bar", "ts_code"),
    ("adjustment_factor", "ts_code"),
    ("market_daily_feature", "ts_code"),
    ("index_master", "index_code"),
    ("index_price_bar", "index_code"),
    ("event_timeline", "ts_code"),
    ("financial_indicator", "ts_code"),
    ("financial_forecast_event", "ts_code"),
)


@pytest.mark.parametrize(("dataset_id", "expected_alias"), _EXPECTED_DEFAULT_ALIAS)
def test_default_alias_columns_for_all_datasets(
    monkeypatch: pytest.MonkeyPatch,
    dataset_id: str,
    expected_alias: str,
) -> None:
    """Without the v2 flag, every dataset's alias column is the legacy
    provider-shaped name. Locks the surface area against accidental flips."""

    monkeypatch.delenv(USE_CANONICAL_V2_ENV_VAR, raising=False)
    assert canonical_alias_column_for_dataset(dataset_id) == expected_alias


def test_v2_flag_uses_canonical_alias_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(USE_CANONICAL_V2_ENV_VAR, "1")
    assert canonical_alias_column_for_dataset("security_master") == "security_id"
    assert canonical_alias_column_for_dataset("security_profile") == "security_id"
    assert canonical_alias_column_for_dataset("price_bar") == "security_id"
    assert canonical_alias_column_for_dataset("market_daily_feature") == "security_id"
    assert canonical_alias_column_for_dataset("index_master") == "index_id"
    assert canonical_alias_column_for_dataset("index_price_bar") == "index_id"
    assert canonical_alias_column_for_dataset("event_timeline") == "entity_id"
    assert canonical_alias_column_for_dataset("financial_indicator") == "security_id"
    assert (
        canonical_alias_column_for_dataset("financial_forecast_event") == "security_id"
    )
    assert canonical_alias_column_for_dataset("holding_position") == "security_id"
    assert canonical_alias_column_for_dataset("northbound_turnover_daily") == "security_id"


def test_event_timeline_routes_to_canonical_v2_fact_event_under_v2_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """event_timeline reads from canonical_v2.fact_event
    when DP_CANONICAL_USE_V2=1. The 8 candidate sources (pledge_*, repurchase,
    stk_holdertrade, limit_list_*, hm_detail, stk_surv) remain
    BLOCKED_NO_STAGING.
    """

    monkeypatch.setenv(USE_CANONICAL_V2_ENV_VAR, "1")
    mapping = canonical_table_mapping_for_dataset("event_timeline")
    assert mapping.table_identifier == "canonical_v2.fact_event"
    assert canonical_alias_column_for_dataset("event_timeline") == "entity_id"


def test_event_timeline_remains_legacy_without_v2_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default (no v2 flag) routes event_timeline to legacy canonical.fact_event."""

    monkeypatch.delenv(USE_CANONICAL_V2_ENV_VAR, raising=False)
    mapping = canonical_table_mapping_for_dataset("event_timeline")
    assert mapping.table_identifier == "canonical.fact_event"
    assert canonical_alias_column_for_dataset("event_timeline") == "ts_code"


def test_falsy_env_values_keep_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ["", "0", "false", "no", "off", "anything-else"]:
        monkeypatch.setenv(USE_CANONICAL_V2_ENV_VAR, value)
        assert use_canonical_v2() is False, f"value={value!r} should not enable v2"
        assert (
            canonical_table_identifier_for_dataset("security_master")
            == "canonical.dim_security"
        )


def test_v2_mapping_set_covers_legacy_plus_promoted_holdings() -> None:
    """The v2 map covers every legacy dataset plus v2-only holdings marts."""

    legacy_dataset_ids = {m.dataset_id for m in CANONICAL_DATASET_TABLE_MAPPINGS}
    v2_dataset_ids = {m.dataset_id for m in CANONICAL_DATASET_TABLE_MAPPINGS_V2}

    assert "event_timeline" in legacy_dataset_ids
    assert "event_timeline" in v2_dataset_ids
    assert legacy_dataset_ids < v2_dataset_ids
    assert v2_dataset_ids - legacy_dataset_ids == {
        "holding_position",
        "northbound_turnover_daily",
    }
