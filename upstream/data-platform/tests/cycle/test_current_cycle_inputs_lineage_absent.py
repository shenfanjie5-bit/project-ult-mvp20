"""Boundary schema test: `current_cycle_inputs()` output rows must not surface
raw-zone lineage fields or provider-shaped identifiers.

Today the OUTPUT row schema (the dict returned by `_current_cycle_row`) is
already provider-neutral — it uses canonical names (`entity_id`, `market`,
`industry`, `trade_date`, ...) and does not include `source_run_id`,
`raw_loaded_at`, or `ts_code`. This test pins that contract by inspecting
the current-cycle row dataclass-equivalent literal keys directly, so a future
silent regression that re-introduces lineage at the output boundary would
fail loudly.

Per ult_milestone.md M1-E. Plan-only test addition; no source code change.
"""

from __future__ import annotations

import inspect
import re
from typing import Final

from data_platform.cycle import current_cycle_inputs as cci_module  # noqa: F401  # for re-export sanity
from data_platform.cycle.current_cycle_inputs import _current_cycle_row, __all__ as cci_all


FORBIDDEN_OUTPUT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "source_run_id",
        "raw_loaded_at",
        "ts_code",
        "index_code",
        "submitted_at",
        "ingest_seq",
    }
)


def test_current_cycle_row_factory_does_not_emit_lineage_fields() -> None:
    """`_current_cycle_row` literal keys must not include lineage / provider-shaped names."""

    source = inspect.getsource(_current_cycle_row)
    # Extract dict literal key names from the return value: keys appear as
    # quoted string literals on lines that look like `        "<name>": ...`.
    key_pattern = re.compile(r'^\s*"([A-Za-z_][A-Za-z0-9_]*)":', re.MULTILINE)
    keys = set(key_pattern.findall(source))

    leaks = sorted(keys & FORBIDDEN_OUTPUT_FIELDS)
    assert not leaks, (
        "current_cycle_inputs._current_cycle_row emits forbidden output fields "
        f"{leaks}; the output contract must remain provider-neutral and "
        "lineage-free per M1-A design"
    )


def test_current_cycle_row_factory_emits_canonical_identifier_only() -> None:
    """The current-cycle row must surface `entity_id`, not `ts_code`."""

    source = inspect.getsource(_current_cycle_row)
    assert '"entity_id":' in source, (
        "current_cycle_inputs._current_cycle_row must surface entity_id as the "
        "canonical identifier in its output"
    )
    assert '"ts_code":' not in source, (
        "current_cycle_inputs._current_cycle_row must NOT surface ts_code in its "
        "output (provider-shaped identifier — use entity_id instead)"
    )


def test_current_cycle_inputs_module_does_not_re_export_lineage_constants() -> None:
    """The module's __all__ must not advertise lineage/provider-shaped symbols."""

    public_names = set(cci_all)
    leaks = sorted(public_names & FORBIDDEN_OUTPUT_FIELDS)
    assert not leaks, (
        f"current_cycle_inputs.__all__ must not advertise {leaks}"
    )


def test_security_rows_by_alias_supports_canonical_security_id_column() -> None:
    """`_security_rows_by_alias` indexes rows by the requested alias_column.

    Confirms the canonical_v2 reader cutover works: when current_cycle_inputs
    is run with `DP_CANONICAL_USE_V2=1`, the security_master columns request
    `security_id` instead of `ts_code` and the alias index keys on
    `security_id` rows.
    """

    from data_platform.cycle.current_cycle_inputs import _security_rows_by_alias

    rows = [
        {"security_id": "ENT_AAA", "market": "Main", "industry": "Tech"},
        {"security_id": "ENT_BBB", "market": "Main", "industry": "Bank"},
    ]
    indexed = _security_rows_by_alias(rows, alias_column="security_id")

    assert set(indexed) == {"ENT_AAA", "ENT_BBB"}
    assert indexed["ENT_AAA"]["market"] == "Main"
    # Confirm the same helper still works for legacy ts_code shape.
    legacy_rows = [
        {"ts_code": "000001.SZ", "market": "Main", "industry": "Bank"},
    ]
    legacy_indexed = _security_rows_by_alias(legacy_rows, alias_column="ts_code")
    assert legacy_indexed["000001.SZ"]["industry"] == "Bank"


def test_price_rows_by_alias_supports_canonical_security_id_column() -> None:
    """`_price_rows_by_alias` filters by daily freq + trade_date + alias."""

    from datetime import date as _date

    from data_platform.cycle.current_cycle_inputs import _price_rows_by_alias

    target_trade_date = _date(2026, 4, 15)
    rows = [
        {
            "security_id": "ENT_AAA",
            "trade_date": target_trade_date,
            "freq": "daily",
            "close": 1.5,
            "pre_close": 1.4,
            "pct_chg": 0.07,
            "vol": 1000,
            "amount": 1500,
        },
        # Wrong freq — must be excluded.
        {
            "security_id": "ENT_AAA",
            "trade_date": target_trade_date,
            "freq": "weekly",
            "close": 1.5,
            "pre_close": 1.4,
            "pct_chg": 0.07,
            "vol": 1000,
            "amount": 1500,
        },
    ]
    indexed = _price_rows_by_alias(
        rows,
        trade_date=target_trade_date,
        alias_column="security_id",
    )
    assert set(indexed) == {"ENT_AAA"}
    assert indexed["ENT_AAA"]["close"] == 1.5
