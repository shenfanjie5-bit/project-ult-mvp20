"""L3 package: feature and signal bundle assembly."""

from main_core.common.protocols import (
    GraphEnginePort,
    GraphImpactRecord,
    GraphRegimeContext,
    GraphSnapshotError,
)
from main_core.l3_features.builder import build_feature_signal_bundle, build_feature_signal_bundles
from main_core.l3_features.candidate_signals import (
    CandidateSignalError,
    CandidateSignalPort,
    CandidateSignalRecord,
    candidate_signal_multiplier,
    merge_candidate_signals,
    normalize_candidate_signals,
)
from main_core.l3_features.errors import InvalidMultiplierError, L3FeatureError
from main_core.l3_features.graph_adapter import load_graph_features, merge_graph_features
from main_core.l3_features.multiplier_store import InMemoryMultiplierStore, MultiplierStore
from main_core.l3_features.weight_api import (
    apply_weight_multiplier,
    get_feature_weight_multiplier,
)

__all__ = [
    "GraphEnginePort",
    "GraphImpactRecord",
    "GraphRegimeContext",
    "GraphSnapshotError",
    "InMemoryMultiplierStore",
    "InvalidMultiplierError",
    "L3FeatureError",
    "MultiplierStore",
    "CandidateSignalError",
    "CandidateSignalPort",
    "CandidateSignalRecord",
    "apply_weight_multiplier",
    "build_feature_signal_bundle",
    "build_feature_signal_bundles",
    "candidate_signal_multiplier",
    "get_feature_weight_multiplier",
    "load_graph_features",
    "merge_candidate_signals",
    "merge_graph_features",
    "normalize_candidate_signals",
]
