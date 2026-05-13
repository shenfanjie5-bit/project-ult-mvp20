import pytest

from audit_eval.drift import (
    ALERT_RULES_VERSION,
    DEFAULT_DRIFT_RULE_CONFIG,
    DriftRuleConfig,
    DriftedFeature,
    EvidentlyRunResult,
    classify_regime_warning,
)


def _feature(
    name: str,
    *,
    score: float = 0.1,
    drifted: bool = True,
) -> DriftedFeature:
    return DriftedFeature(
        name=name,
        score=score,
        statistic=None,
        threshold=0.05,
        drifted=drifted,
    )


def _result(
    features: tuple[DriftedFeature, ...],
    *,
    total_feature_count: int | None = None,
) -> EvidentlyRunResult:
    return EvidentlyRunResult(
        evidently_json={"metrics": []},
        features=features,
        total_feature_count=total_feature_count,
    )


def test_classify_regime_warning_returns_none_without_drift() -> None:
    decision = classify_regime_warning(
        _result((_feature("stable", drifted=False),), total_feature_count=4)
    )

    assert decision.regime_warning_level == "none"
    assert decision.drifted_features == ()
    assert decision.alert_rules_version == ALERT_RULES_VERSION
    assert decision.alert_rules_version == DEFAULT_DRIFT_RULE_CONFIG.version


def test_drift_rule_config_strips_version() -> None:
    config = DriftRuleConfig(version=" drift-regime-v2 ")

    assert config.version == "drift-regime-v2"


@pytest.mark.parametrize("version", ["", "   ", 123])
def test_drift_rule_config_rejects_invalid_version(version: object) -> None:
    with pytest.raises(ValueError, match="version"):
        DriftRuleConfig(version=version)  # type: ignore[arg-type]


def test_classify_regime_warning_does_not_warn_without_feature_evidence() -> None:
    rules = DriftRuleConfig(
        warning_drifted_feature_count=0,
        critical_drifted_feature_count=0,
        warning_drifted_feature_ratio=0,
        critical_drifted_feature_ratio=0,
        warning_feature_score=0,
        critical_feature_score=0,
    )

    decision = classify_regime_warning(_result((), total_feature_count=0), rules=rules)

    assert decision.regime_warning_level == "none"
    assert decision.drifted_features == ()


def test_classify_regime_warning_reaches_warning_on_threshold_boundary() -> None:
    rules = DriftRuleConfig(
        warning_drifted_feature_count=2,
        critical_drifted_feature_count=4,
        warning_drifted_feature_ratio=0.25,
        critical_drifted_feature_ratio=0.75,
        warning_feature_score=0.5,
        critical_feature_score=0.9,
    )
    decision = classify_regime_warning(
        _result((_feature("spread", score=0.1),), total_feature_count=4),
        rules=rules,
    )

    assert decision.regime_warning_level == "warning"
    assert [feature.name for feature in decision.drifted_features] == ["spread"]
    assert decision.alert_rules_version == ALERT_RULES_VERSION


def test_classify_regime_warning_reaches_critical_on_ratio_boundary() -> None:
    rules = DriftRuleConfig(
        warning_drifted_feature_count=3,
        critical_drifted_feature_count=4,
        warning_drifted_feature_ratio=0.25,
        critical_drifted_feature_ratio=0.5,
        warning_feature_score=0.5,
        critical_feature_score=0.9,
    )
    decision = classify_regime_warning(
        _result(
            (
                _feature("spread", score=0.1),
                _feature("volume", score=0.1),
            ),
            total_feature_count=4,
        ),
        rules=rules,
    )

    assert decision.regime_warning_level == "critical"
    assert [feature.name for feature in decision.drifted_features] == [
        "spread",
        "volume",
    ]


def test_classify_regime_warning_reaches_critical_on_score_boundary() -> None:
    decision = classify_regime_warning(
        _result((_feature("spread", score=0.8),), total_feature_count=10)
    )

    assert decision.regime_warning_level == "critical"
