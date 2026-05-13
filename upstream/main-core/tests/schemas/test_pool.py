"""Tests for the L5 official alpha pool schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from main_core.common.schemas import OfficialAlphaPool


def _pool_payload() -> dict[str, object]:
    return {
        "cycle_id": "cycle_001",
        "observation_pool_size": 12,
        "official_alpha_pool_capacity": 2,
        "selected_entities": ["ENT_001", "ENT_002"],
        "added_entities": ["ENT_002"],
        "removed_entities": [],
        "freeze_reason_map": {"ENT_001": "existing core holding"},
    }


def test_official_alpha_pool_happy_path_round_trips_json() -> None:
    pool = OfficialAlphaPool(**_pool_payload())

    assert OfficialAlphaPool.from_json(pool.to_json()) == pool


def test_official_alpha_pool_missing_field_fails() -> None:
    payload = _pool_payload()
    payload.pop("selected_entities")

    with pytest.raises(ValidationError):
        OfficialAlphaPool(**payload)


def test_official_alpha_pool_rejects_selected_entities_over_capacity() -> None:
    payload = _pool_payload()
    payload["official_alpha_pool_capacity"] = 1

    with pytest.raises(ValidationError, match="selected_entities length"):
        OfficialAlphaPool(**payload)


def test_official_alpha_pool_selected_entities_cannot_mutate_past_capacity() -> None:
    payload = _pool_payload()
    payload["official_alpha_pool_capacity"] = 1
    payload["selected_entities"] = ["ENT_001"]
    pool = OfficialAlphaPool(**payload)
    before_json = pool.to_json()

    with pytest.raises(AttributeError):
        pool.selected_entities.append("ENT_002")

    assert len(pool.selected_entities) == 1
    assert pool.to_json() == before_json


def test_official_alpha_pool_freeze_reason_map_is_immutable() -> None:
    pool = OfficialAlphaPool(**_pool_payload())
    before_json = pool.to_json()

    with pytest.raises(TypeError):
        pool.freeze_reason_map["ENT_002"] = "late mutation"

    assert pool.to_json() == before_json


def test_official_alpha_pool_model_copy_revalidates_capacity_updates() -> None:
    payload = _pool_payload()
    payload["official_alpha_pool_capacity"] = 1
    payload["selected_entities"] = ["ENT_001"]
    pool = OfficialAlphaPool(**payload)

    with pytest.raises(ValidationError, match="selected_entities length"):
        pool.model_copy(update={"selected_entities": ["ENT_001", "ENT_002"]})


def test_official_alpha_pool_model_copy_freezes_valid_update_values() -> None:
    payload = _pool_payload()
    payload["official_alpha_pool_capacity"] = 2
    payload["selected_entities"] = ["ENT_001"]
    pool = OfficialAlphaPool(**payload)

    copied = pool.model_copy(
        update={
            "selected_entities": ["ENT_001", "ENT_002"],
            "freeze_reason_map": {"ENT_002": "new frozen entity"},
        }
    )
    before_json = copied.to_json()

    with pytest.raises(AttributeError):
        copied.selected_entities.append("ENT_003")
    with pytest.raises(TypeError):
        copied.freeze_reason_map["ENT_003"] = "late mutation"

    assert copied.to_json() == before_json


@pytest.mark.parametrize(
    "capacity",
    [0, 101],
)
def test_official_alpha_pool_rejects_capacity_outside_hard_bounds(capacity: int) -> None:
    payload = _pool_payload()
    payload["official_alpha_pool_capacity"] = capacity

    with pytest.raises(ValidationError):
        OfficialAlphaPool(**payload)


def test_official_alpha_pool_rejects_negative_observation_pool_size() -> None:
    payload = _pool_payload()
    payload["observation_pool_size"] = -1

    with pytest.raises(ValidationError):
        OfficialAlphaPool(**payload)


def test_official_alpha_pool_rejects_selected_exceeding_observation_pool() -> None:
    payload = _pool_payload()
    payload["observation_pool_size"] = 1
    payload["official_alpha_pool_capacity"] = 5
    payload["selected_entities"] = ["ENT_001", "ENT_002"]
    payload["freeze_reason_map"] = {}

    with pytest.raises(ValidationError, match="observation_pool_size"):
        OfficialAlphaPool(**payload)


def test_official_alpha_pool_allows_selected_frozen_entities_with_eligible_count() -> None:
    payload = _pool_payload()
    payload["observation_pool_size"] = 2
    payload["official_alpha_pool_capacity"] = 5
    payload["selected_entities"] = ["ENT_001", "ENT_002"]
    payload["freeze_reason_map"] = {"ENT_001": "existing core freeze"}

    pool = OfficialAlphaPool(**payload)

    assert pool.selected_entities == ("ENT_001", "ENT_002")


def test_official_alpha_pool_rejects_freeze_reason_map_as_eligibility_proof() -> None:
    payload = _pool_payload()
    payload["observation_pool_size"] = 0
    payload["official_alpha_pool_capacity"] = 5
    payload["selected_entities"] = ["ENT_001", "ENT_002"]
    payload["freeze_reason_map"] = {
        "ENT_001": "forged freeze",
        "ENT_002": "forged freeze",
    }

    with pytest.raises(ValidationError, match="observation_pool_size"):
        OfficialAlphaPool(**payload)


def test_official_alpha_pool_rejects_freeze_reason_for_unselected_entity() -> None:
    payload = _pool_payload()
    payload["freeze_reason_map"] = {"ENT_003": "unselected freeze"}

    with pytest.raises(ValidationError, match="freeze_reason_map keys"):
        OfficialAlphaPool(**payload)
