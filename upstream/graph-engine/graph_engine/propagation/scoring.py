"""Explainable propagation scoring helpers."""

from __future__ import annotations


def compute_path_score(
    relation_weight: float,
    evidence_confidence: float,
    channel_multiplier: float,
    regime_multiplier: float,
    recency_decay: float,
) -> float:
    """Compute the documented five-factor propagation path score."""

    return (
        relation_weight
        * evidence_confidence
        * channel_multiplier
        * regime_multiplier
        * recency_decay
    )


def build_score_explanation(
    *,
    relation_weight: float,
    evidence_confidence: float,
    channel_multiplier: float,
    regime_multiplier: float,
    recency_decay: float,
) -> dict[str, float]:
    """Return the serializable scoring inputs and computed path score."""

    return {
        "relation_weight": relation_weight,
        "evidence_confidence": evidence_confidence,
        "channel_multiplier": channel_multiplier,
        "regime_multiplier": regime_multiplier,
        "recency_decay": recency_decay,
        "score": compute_path_score(
            relation_weight,
            evidence_confidence,
            channel_multiplier,
            regime_multiplier,
            recency_decay,
        ),
    }
