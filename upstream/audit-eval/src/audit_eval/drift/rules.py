"""Versioned structural drift warning rules."""

from __future__ import annotations

from dataclasses import dataclass

from audit_eval.drift.schema import (
    DriftedFeature,
    EvidentlyRunResult,
    RegimeWarningLevel,
)

ALERT_RULES_VERSION = "drift-regime-v1"


@dataclass(frozen=True)
class DriftRuleConfig:
    """Thresholds for structural drift warning classification."""

    warning_drifted_feature_count: int = 1
    critical_drifted_feature_count: int = 3
    warning_drifted_feature_ratio: float = 0.25
    critical_drifted_feature_ratio: float = 0.6
    warning_feature_score: float = 0.2
    critical_feature_score: float = 0.8
    version: str = ALERT_RULES_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.version, str):
            raise ValueError("version must be a string")
        stripped_version = self.version.strip()
        if not stripped_version:
            raise ValueError("version must not be empty")
        object.__setattr__(self, "version", stripped_version)
        if self.warning_drifted_feature_count < 0:
            raise ValueError("warning_drifted_feature_count must be non-negative")
        if self.critical_drifted_feature_count < self.warning_drifted_feature_count:
            raise ValueError(
                "critical_drifted_feature_count must be >= warning threshold"
            )
        if not 0 <= self.warning_drifted_feature_ratio <= 1:
            raise ValueError("warning_drifted_feature_ratio must be between 0 and 1")
        if not 0 <= self.critical_drifted_feature_ratio <= 1:
            raise ValueError("critical_drifted_feature_ratio must be between 0 and 1")
        if self.critical_drifted_feature_ratio < self.warning_drifted_feature_ratio:
            raise ValueError(
                "critical_drifted_feature_ratio must be >= warning threshold"
            )
        if self.warning_feature_score < 0:
            raise ValueError("warning_feature_score must be non-negative")
        if self.critical_feature_score < self.warning_feature_score:
            raise ValueError("critical_feature_score must be >= warning threshold")


@dataclass(frozen=True)
class DriftRuleDecision:
    """Versioned structural drift rule decision."""

    regime_warning_level: RegimeWarningLevel
    drifted_features: tuple[DriftedFeature, ...]
    alert_rules_version: str
    reason: str


DEFAULT_DRIFT_RULE_CONFIG = DriftRuleConfig()


def classify_regime_warning(
    result: EvidentlyRunResult,
    *,
    rules: DriftRuleConfig = DEFAULT_DRIFT_RULE_CONFIG,
) -> DriftRuleDecision:
    """Classify an Evidently result into a structural warning level."""

    drifted_features = result.drifted_features
    drifted_count = len(drifted_features)
    total_feature_count = result.total_feature_count
    if total_feature_count is None:
        total_feature_count = len(result.features)

    drifted_ratio = (
        drifted_count / total_feature_count if total_feature_count else 0.0
    )
    max_feature_score = max(
        (_feature_strength(feature) for feature in drifted_features),
        default=0.0,
    )

    if drifted_count == 0:
        return DriftRuleDecision(
            regime_warning_level="none",
            drifted_features=drifted_features,
            alert_rules_version=rules.version,
            reason="within_thresholds",
        )

    if (
        drifted_count >= rules.critical_drifted_feature_count
        or drifted_ratio >= rules.critical_drifted_feature_ratio
        or max_feature_score >= rules.critical_feature_score
    ):
        return DriftRuleDecision(
            regime_warning_level="critical",
            drifted_features=drifted_features,
            alert_rules_version=rules.version,
            reason="critical_threshold_exceeded",
        )

    if (
        drifted_count >= rules.warning_drifted_feature_count
        or drifted_ratio >= rules.warning_drifted_feature_ratio
        or max_feature_score >= rules.warning_feature_score
    ):
        return DriftRuleDecision(
            regime_warning_level="warning",
            drifted_features=drifted_features,
            alert_rules_version=rules.version,
            reason="warning_threshold_exceeded",
        )

    return DriftRuleDecision(
        regime_warning_level="none",
        drifted_features=drifted_features,
        alert_rules_version=rules.version,
        reason="within_thresholds",
    )


def _feature_strength(feature: DriftedFeature) -> float:
    if feature.score is not None:
        return feature.score
    if feature.statistic is not None:
        return feature.statistic
    return 0.0


__all__ = [
    "ALERT_RULES_VERSION",
    "DEFAULT_DRIFT_RULE_CONFIG",
    "DriftRuleConfig",
    "DriftRuleDecision",
    "classify_regime_warning",
]
