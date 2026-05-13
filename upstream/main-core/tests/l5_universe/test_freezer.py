"""Tests for L5 frozen entity merge helpers."""

from __future__ import annotations

import pytest

from main_core.common.errors import MainCoreError
from main_core.common.schemas import OfficialAlphaPool
from main_core.l5_universe.freezer import (
    ensure_frozen_entities_fit_capacity,
    merge_frozen_entities,
)


def _previous_pool() -> OfficialAlphaPool:
    return OfficialAlphaPool(
        cycle_id="cycle_l5",
        observation_pool_size=3,
        official_alpha_pool_capacity=3,
        selected_entities=["ENT_B", "ENT_A", "ENT_D"],
        added_entities=[],
        removed_entities=[],
        freeze_reason_map={
            "ENT_A": "prior freeze A",
            "ENT_B": "prior freeze B",
        },
    )


def test_merge_frozen_entities_preserves_previous_reasons_and_adds_explicit() -> None:
    frozen = merge_frozen_entities(
        _previous_pool(),
        {
            "ENT_A": "explicit reason should not replace prior reason",
            "ENT_C": "manual freeze C",
        },
    )

    assert list(frozen) == ["ENT_B", "ENT_A", "ENT_C"]
    assert frozen == {
        "ENT_B": "prior freeze B",
        "ENT_A": "prior freeze A",
        "ENT_C": "manual freeze C",
    }


def test_merge_frozen_entities_accepts_explicit_without_previous_pool() -> None:
    frozen = merge_frozen_entities(
        None,
        {
            "ENT_Z": "manual freeze Z",
            "ENT_A": "manual freeze A",
        },
    )

    assert list(frozen) == ["ENT_Z", "ENT_A"]
    assert frozen == {
        "ENT_Z": "manual freeze Z",
        "ENT_A": "manual freeze A",
    }


def test_ensure_frozen_entities_fit_capacity_rejects_overflow() -> None:
    with pytest.raises(MainCoreError, match="frozen entity count"):
        ensure_frozen_entities_fit_capacity(
            {"ENT_A": "freeze", "ENT_B": "freeze"},
            capacity=1,
        )
