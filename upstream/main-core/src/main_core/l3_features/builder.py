"""Feature signal bundle builder for the L3 layer."""

from __future__ import annotations

from collections.abc import Mapping
from importlib import import_module
from os import environ
from typing import Any

from main_core.common.protocols import GraphEnginePort
from main_core.common.schemas.feature_bundle import FeatureSignalBundle
from main_core.common.types import CycleId, EntityId
from main_core.l1_l2_basis.models import MarketBar
from main_core.l1_l2_basis.ports import DataPlatformPort
from main_core.l1_l2_basis.readers import read_entity_master, read_market_bars
from main_core.l3_features.candidate_signals import (
    CandidateSignalPort,
    CandidateSignalRecord,
    merge_candidate_signals,
    normalize_candidate_signals,
)
from main_core.l3_features.errors import L3FeatureError
from main_core.l3_features.feature_math import (
    apply_feature_weight_multiplier,
    market_bar_feature_values,
)
from main_core.l3_features.graph_adapter import load_graph_features, merge_graph_features
from main_core.l3_features.multiplier_store import MultiplierStore
from main_core.l3_features.weight_api import get_feature_weight_multiplier

_DATA_PLATFORM_PORT_ENV = "MAIN_CORE_DATA_PLATFORM_PORT"


def build_feature_signal_bundle(  # noqa: PLR0913
    cycle_id: CycleId | str,
    *,
    data_port: DataPlatformPort | None = None,
    multiplier_store: MultiplierStore | None = None,
    graph_engine_port: GraphEnginePort | None = None,
    graph_impact: Mapping[str, Mapping[str, Any]] | None = None,
    candidate_signals: Mapping[str, Mapping[str, Any]] | None = None,
    candidate_signal_port: CandidateSignalPort | None = None,
) -> FeatureSignalBundle:
    """Build the documented single L3 feature signal bundle for a cycle.

    The default data-platform port is resolved from
    ``MAIN_CORE_DATA_PLATFORM_PORT=module:attribute``. The attribute may be either a
    ``DataPlatformPort`` instance or a zero-argument factory returning one.
    """

    bundles = build_feature_signal_bundles(
        cycle_id,
        data_port=data_port,
        multiplier_store=multiplier_store,
        graph_engine_port=graph_engine_port,
        graph_impact=graph_impact,
        candidate_signals=candidate_signals,
        candidate_signal_port=candidate_signal_port,
    )
    if len(bundles) == 1:
        return bundles[0]
    if not bundles:
        raise L3FeatureError("cycle produced no FeatureSignalBundle records")
    raise L3FeatureError(
        "cycle produced multiple FeatureSignalBundle records; "
        "call build_feature_signal_bundles for per-entity output"
    )


def build_feature_signal_bundles(  # noqa: PLR0913
    cycle_id: CycleId | str,
    *,
    data_port: DataPlatformPort | None = None,
    multiplier_store: MultiplierStore | None = None,
    graph_engine_port: GraphEnginePort | None = None,
    graph_impact: Mapping[str, Mapping[str, Any]] | None = None,
    candidate_signals: Mapping[str, Mapping[str, Any]] | None = None,
    candidate_signal_port: CandidateSignalPort | None = None,
) -> list[FeatureSignalBundle]:
    """Build one feature signal bundle per active entity with market data."""

    resolved_data_port = _resolve_data_platform_port(data_port)
    entity_master = read_entity_master(cycle_id, port=resolved_data_port)
    market_bars = read_market_bars(cycle_id, port=resolved_data_port)
    active_entity_ids = {
        str(entity.entity_id)
        for entity in entity_master
        if entity.is_active
    }
    latest_bars = _latest_market_bars_by_entity(market_bars)
    multipliers = get_feature_weight_multiplier(cycle_id, store=multiplier_store)
    normalized_cycle_id = CycleId(str(cycle_id))
    candidate_signal_records = [
        *_candidate_signal_records_from_mapping(normalized_cycle_id, candidate_signals),
        *_read_candidate_signal_records(normalized_cycle_id, candidate_signal_port),
    ]

    bundles: list[FeatureSignalBundle] = []
    for entity_id in sorted(active_entity_ids):
        market_bar = latest_bars.get(entity_id)
        if market_bar is None:
            continue

        base_feature_values = market_bar_feature_values(market_bar)
        feature_values, effective_multipliers = apply_feature_weight_multiplier(
            base_feature_values,
            multipliers,
        )
        bundle = FeatureSignalBundle(
            cycle_id=cycle_id,
            entity_id=EntityId(entity_id),
            feature_values=feature_values,
            signal_values={},
            graph_features=dict((graph_impact or {}).get(entity_id, {})),
            feature_weight_multiplier=effective_multipliers,
        )
        graph_features = load_graph_features(
            CycleId(str(cycle_id)),
            EntityId(entity_id),
            graph_engine_port,
        )
        if graph_features:
            bundle = merge_graph_features(
                bundle,
                {**dict(bundle.graph_features), **graph_features},
            )
        normalized_candidate_signals = normalize_candidate_signals(
            candidate_signal_records,
            cycle_id=normalized_cycle_id,
            entity_id=EntityId(entity_id),
            multipliers=multipliers,
        )
        if normalized_candidate_signals:
            bundle = merge_candidate_signals(bundle, normalized_candidate_signals)
        bundles.append(bundle)

    return bundles


def _resolve_data_platform_port(data_port: DataPlatformPort | None) -> DataPlatformPort:
    if data_port is not None:
        return data_port

    port_path = environ.get(_DATA_PLATFORM_PORT_ENV)
    if not port_path:
        raise L3FeatureError(
            "data_port is required unless MAIN_CORE_DATA_PLATFORM_PORT is configured"
        )

    module_name, separator, attribute_name = port_path.partition(":")
    if not separator or not module_name or not attribute_name:
        raise L3FeatureError(
            "MAIN_CORE_DATA_PLATFORM_PORT must use module:attribute format"
        )

    try:
        candidate = getattr(import_module(module_name), attribute_name)
        resolved_port = candidate() if callable(candidate) else candidate
    except Exception as exc:
        raise L3FeatureError("failed to resolve default data-platform port") from exc

    if not isinstance(resolved_port, DataPlatformPort):
        raise L3FeatureError(
            "resolved default data-platform port does not implement DataPlatformPort"
        )
    return resolved_port


def _latest_market_bars_by_entity(market_bars: list[MarketBar]) -> dict[str, MarketBar]:
    latest_bars: dict[str, MarketBar] = {}
    for market_bar in market_bars:
        entity_id = str(market_bar.entity_id)
        previous_bar = latest_bars.get(entity_id)
        if previous_bar is None or market_bar.as_of_date > previous_bar.as_of_date:
            latest_bars[entity_id] = market_bar
    return latest_bars


def _candidate_signal_records_from_mapping(
    cycle_id: CycleId,
    candidate_signals: Mapping[str, Mapping[str, Any]] | None,
) -> list[CandidateSignalRecord]:
    if not candidate_signals:
        return []

    records: list[CandidateSignalRecord] = []
    for entity_id, entity_signals in candidate_signals.items():
        for signal_name, value in entity_signals.items():
            records.append(
                CandidateSignalRecord(
                    cycle_id=cycle_id,
                    entity_id=EntityId(str(entity_id)),
                    signal_name=str(signal_name),
                    value=value,
                )
            )
    return records


def _read_candidate_signal_records(
    cycle_id: CycleId,
    candidate_signal_port: CandidateSignalPort | None,
) -> list[CandidateSignalRecord]:
    if candidate_signal_port is None:
        return []
    return list(candidate_signal_port.read_candidate_signals(cycle_id))


__all__ = ["build_feature_signal_bundle", "build_feature_signal_bundles"]
