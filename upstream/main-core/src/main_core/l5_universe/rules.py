"""Deterministic L5 scoring and ranking rules."""

from __future__ import annotations

from collections.abc import Sequence

from main_core.common.schemas.feature_bundle import FeatureSignalBundle
from main_core.common.schemas.world_state import WorldStateSnapshot
from main_core.l5_universe.types import PoolSelectionConfig


def score_candidate(
    bundle: FeatureSignalBundle,
    world_state: WorldStateSnapshot,
) -> float:
    """Score one candidate using already-finalized L3 feature semantics."""

    del world_state

    if "candidate_score" in bundle.signal_values:
        return float(bundle.signal_values["candidate_score"])
    if "alpha_score" in bundle.feature_values:
        return float(bundle.feature_values["alpha_score"])
    if "momentum" in bundle.feature_values:
        return float(bundle.feature_values["momentum"])
    return 0.0


def rank_candidates(
    world_state: WorldStateSnapshot,
    bundles: Sequence[FeatureSignalBundle],
    config: PoolSelectionConfig,
) -> list[FeatureSignalBundle]:
    """Rank observation candidates by score descending and entity_id ascending."""

    scored_candidates = [
        (score_candidate(bundle, world_state), bundle)
        for bundle in bundles
    ]
    if config.min_candidate_score is not None:
        scored_candidates = [
            (score, bundle)
            for score, bundle in scored_candidates
            if score >= config.min_candidate_score
        ]

    ranked_candidates = [
        bundle
        for _score, bundle in sorted(
            scored_candidates,
            key=lambda scored: (-scored[0], str(scored[1].entity_id)),
        )
    ]
    if config.observation_limit is None:
        return ranked_candidates
    return ranked_candidates[: config.observation_limit]


__all__ = ["rank_candidates", "score_candidate"]
