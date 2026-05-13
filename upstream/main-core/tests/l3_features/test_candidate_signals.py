"""Tests for Layer B candidate signal consumption in L3."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from main_core.common.schemas.feature_bundle import FeatureSignalBundle
from main_core.common.types import CycleId, EntityId
from main_core.l3_features import (
    CandidateSignalError,
    CandidateSignalPort,
    CandidateSignalRecord,
    build_feature_signal_bundles,
    candidate_signal_multiplier,
    merge_candidate_signals,
    normalize_candidate_signals,
)

from .conftest import FakeDataPlatformPort

SCOPED_MULTIPLIER = 1.5
UNSCOPED_MULTIPLIER = 0.75


@dataclass
class FakeCandidateSignalPort:
    records: Sequence[CandidateSignalRecord] = field(default_factory=tuple)
    calls: list[CycleId] = field(default_factory=list)

    def read_candidate_signals(
        self,
        cycle_id: CycleId,
    ) -> Sequence[CandidateSignalRecord]:
        self.calls.append(cycle_id)
        return self.records


def test_candidate_signal_port_is_runtime_checkable_and_read_only() -> None:
    port = FakeCandidateSignalPort()

    protocol_methods = {
        name
        for name, value in CandidateSignalPort.__dict__.items()
        if callable(value) and not name.startswith("_")
    }

    assert isinstance(port, CandidateSignalPort)
    assert protocol_methods == {"read_candidate_signals"}
    assert not {
        name
        for name in dir(CandidateSignalPort)
        if name.startswith(("write_", "ack_", "commit_", "mutate_"))
    }
    assert not {
        name
        for name in dir(port)
        if name.startswith(("write_", "ack_", "commit_", "mutate_"))
    }


def test_empty_candidate_signal_port_preserves_market_only_bundle(
    cycle_id: CycleId,
    active_entity,
    market_bar,
) -> None:
    data_port = FakeDataPlatformPort(
        market_bars=(market_bar,),
        entity_master=(active_entity,),
    )
    empty_candidate_port = FakeCandidateSignalPort()

    market_only = build_feature_signal_bundles(cycle_id, data_port=data_port)
    with_empty_layer_b = build_feature_signal_bundles(
        cycle_id,
        data_port=data_port,
        candidate_signal_port=empty_candidate_port,
    )

    assert _stable_bundle_payload(with_empty_layer_b[0]) == _stable_bundle_payload(
        market_only[0]
    )
    assert empty_candidate_port.calls == [cycle_id]


def test_normalize_candidate_signals_filters_entity_and_applies_multipliers() -> None:
    cycle_id = CycleId("cycle-layer-b")
    records = (
        CandidateSignalRecord(
            cycle_id=cycle_id,
            entity_id=EntityId("ENT_A"),
            signal_name="layer_b_score",
            value=2.0,
            confidence=0.8,
            metadata={"window": "5d"},
        ),
        CandidateSignalRecord(
            cycle_id=cycle_id,
            entity_id=EntityId("ENT_A"),
            signal_name="regime_hint",
            value="risk_on",
            metadata={"reason": "news"},
        ),
        CandidateSignalRecord(
            cycle_id=cycle_id,
            entity_id=EntityId("ENT_B"),
            signal_name="layer_b_score",
            value=99.0,
        ),
    )

    normalized = normalize_candidate_signals(
        records,
        cycle_id=cycle_id,
        entity_id=EntityId("ENT_A"),
        multipliers={"candidate_signals.layer_b_score": 1.5},
    )

    assert normalized == {
        "layer_b_score": {
            "raw_value": 2.0,
            "adjusted_value": 3.0,
            "source": "layer_b",
            "confidence": 0.8,
            "metadata": {"window": "5d"},
        },
        "regime_hint": {
            "raw_value": "risk_on",
            "adjusted_value": "risk_on",
            "source": "layer_b",
            "confidence": None,
            "metadata": {"reason": "news"},
        },
    }


def test_candidate_signal_multiplier_prefers_scoped_name() -> None:
    multipliers = {
        "layer_b_score": 2.0,
        "candidate_signals.layer_b_score": SCOPED_MULTIPLIER,
    }

    assert candidate_signal_multiplier("layer_b_score", multipliers) == SCOPED_MULTIPLIER
    assert (
        candidate_signal_multiplier(
            "other_signal",
            {"other_signal": UNSCOPED_MULTIPLIER},
        )
        == UNSCOPED_MULTIPLIER
    )
    assert candidate_signal_multiplier("missing_signal", {}) == 1.0


def test_normalize_candidate_signals_rejects_duplicate_signal_records() -> None:
    cycle_id = CycleId("cycle-layer-b")
    records = (
        CandidateSignalRecord(
            cycle_id=cycle_id,
            entity_id=EntityId("ENT_A"),
            signal_name="layer_b_score",
            value=1.0,
        ),
        CandidateSignalRecord(
            cycle_id=cycle_id,
            entity_id=EntityId("ENT_A"),
            signal_name="layer_b_score",
            value=2.0,
        ),
    )

    with pytest.raises(CandidateSignalError, match="duplicate"):
        normalize_candidate_signals(
            records,
            cycle_id=cycle_id,
            entity_id=EntityId("ENT_A"),
            multipliers={},
        )


def test_normalize_candidate_signals_rejects_cycle_mismatch() -> None:
    with pytest.raises(CandidateSignalError, match="cycle_id"):
        normalize_candidate_signals(
            (
                CandidateSignalRecord(
                    cycle_id=CycleId("cycle-other"),
                    entity_id=EntityId("ENT_A"),
                    signal_name="layer_b_score",
                    value=1.0,
                ),
            ),
            cycle_id=CycleId("cycle-current"),
            entity_id=EntityId("ENT_A"),
            multipliers={},
        )


def test_normalize_candidate_signals_omits_other_entities() -> None:
    cycle_id = CycleId("cycle-layer-b")

    assert normalize_candidate_signals(
        (
            CandidateSignalRecord(
                cycle_id=cycle_id,
                entity_id=EntityId("ENT_B"),
                signal_name="layer_b_score",
                value=1.0,
            ),
        ),
        cycle_id=cycle_id,
        entity_id=EntityId("ENT_A"),
        multipliers={},
    ) == {}


def test_merge_candidate_signals_preserves_bundle_payload_without_mutating() -> None:
    bundle = FeatureSignalBundle(
        cycle_id="cycle-layer-b",
        entity_id="ENT_A",
        feature_values={"close_price": 100.0},
        signal_values={"direction": "positive"},
        graph_features={"snapshot_id": "graph-001", "features": {"centrality": 0.7}},
        feature_weight_multiplier={"close_price": 1.0},
    )
    before_json = bundle.to_json()

    merged = merge_candidate_signals(
        bundle,
        {
            "layer_b_score": {
                "raw_value": 2.0,
                "adjusted_value": 3.0,
                "source": "layer_b",
                "confidence": 0.8,
                "metadata": {},
            },
        },
    )

    assert bundle.to_json() == before_json
    assert merged is not bundle
    assert merged.generated_at == bundle.generated_at
    assert merged.signal_values == {
        "direction": "positive",
        "candidate_signals": {
            "layer_b_score": {
                "raw_value": 2.0,
                "adjusted_value": 3.0,
                "source": "layer_b",
                "confidence": 0.8,
                "metadata": {},
            },
        },
    }
    assert merged.graph_features == bundle.graph_features


def _stable_bundle_payload(bundle: FeatureSignalBundle) -> dict:
    payload = bundle.model_dump(mode="python")
    payload.pop("generated_at")
    return payload
