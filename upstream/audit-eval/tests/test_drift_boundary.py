from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from audit_eval._boundary import BoundaryViolationError
from audit_eval.contracts import DriftReport
from audit_eval.drift import (
    DriftedFeature,
    EvidentlyRunResult,
    InMemoryDriftInputGateway,
    InMemoryDriftReportJsonWriter,
    InMemoryDriftReportStorage,
    InMemoryEvidentlyRunner,
    run_drift_report,
)


def _valid_payload() -> dict[str, Any]:
    return {
        "report_id": "drift-report-1",
        "cycle_id": "cycle_20260418",
        "baseline_ref": "feature-window://baseline",
        "target_ref": "feature-window://target",
        "evidently_json_ref": "s3://reports/drift-report-1.json",
        "drifted_features": {
            "features": [
                {
                    "name": "spread",
                    "score": 0.7,
                    "statistic": None,
                    "threshold": 0.2,
                    "drifted": True,
                }
            ]
        },
        "regime_warning_level": "warning",
        "alert_rules_version": "drift-regime-v1",
        "created_at": datetime(2026, 4, 18, tzinfo=timezone.utc),
    }


def test_drift_report_fields_match_project_contract() -> None:
    assert tuple(DriftReport.model_fields) == (
        "report_id",
        "cycle_id",
        "baseline_ref",
        "target_ref",
        "evidently_json_ref",
        "drifted_features",
        "regime_warning_level",
        "alert_rules_version",
        "created_at",
    )


def test_drift_report_accepts_valid_payload() -> None:
    report = DriftReport.model_validate(_valid_payload())

    assert report.regime_warning_level == "warning"
    assert report.drifted_features.features[0].name == "spread"


@pytest.mark.parametrize(
    "field_name",
    [
        "report_id",
        "cycle_id",
        "baseline_ref",
        "target_ref",
        "evidently_json_ref",
        "alert_rules_version",
    ],
)
def test_drift_report_rejects_whitespace_identifier_refs(
    field_name: str,
) -> None:
    payload = _valid_payload()
    payload[field_name] = "   "

    with pytest.raises(ValidationError, match=f"{field_name} must not be empty"):
        DriftReport.model_validate(payload)


def test_drift_report_strips_identifier_refs() -> None:
    payload = _valid_payload()
    payload["report_id"] = " drift-report-1 "
    payload["cycle_id"] = "\tcycle_20260418\n"
    payload["baseline_ref"] = " feature-window://baseline "
    payload["target_ref"] = " feature-window://target "
    payload["evidently_json_ref"] = " s3://reports/drift-report-1.json "
    payload["alert_rules_version"] = " drift-regime-v1 "

    report = DriftReport.model_validate(payload)

    assert report.report_id == "drift-report-1"
    assert report.cycle_id == "cycle_20260418"
    assert report.baseline_ref == "feature-window://baseline"
    assert report.target_ref == "feature-window://target"
    assert report.evidently_json_ref == "s3://reports/drift-report-1.json"
    assert report.alert_rules_version == "drift-regime-v1"


def test_drift_report_rejects_extra_fields() -> None:
    payload = _valid_payload()
    payload["extra"] = "forbidden"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DriftReport.model_validate(payload)


def test_drift_report_rejects_unknown_warning_level() -> None:
    payload = _valid_payload()
    payload["regime_warning_level"] = "gate"

    with pytest.raises(ValidationError, match="none"):
        DriftReport.model_validate(payload)


def test_drift_report_rejects_nested_forbidden_field() -> None:
    payload = _valid_payload()
    payload["drifted_features"]["features"][0]["metadata"] = {
        "feature_weight_multiplier": 1.2
    }

    with pytest.raises(
        BoundaryViolationError,
        match=r"\$\.drifted_features\.features\[0\]\.metadata"
        r"\.feature_weight_multiplier",
    ):
        DriftReport.model_validate(payload)


def test_drift_report_rejects_warning_without_feature_evidence() -> None:
    payload = _valid_payload()
    payload["drifted_features"] = {"features": []}

    with pytest.raises(ValidationError, match="feature evidence"):
        DriftReport.model_validate(payload)


def test_drift_report_rejects_malformed_feature_evidence() -> None:
    payload = _valid_payload()
    payload["drifted_features"]["features"][0].pop("score")
    payload["drifted_features"]["features"][0]["statistic"] = None

    with pytest.raises(ValidationError, match="score or statistic"):
        DriftReport.model_validate(payload)


@pytest.mark.parametrize("field_name", ["score", "statistic", "threshold"])
def test_drift_report_rejects_bool_numeric_evidence(field_name: str) -> None:
    payload = _valid_payload()
    payload["drifted_features"]["features"][0][field_name] = True

    with pytest.raises(ValidationError, match="real numbers"):
        DriftReport.model_validate(payload)


@pytest.mark.parametrize("field_name", ["score", "statistic", "threshold"])
def test_drift_report_rejects_string_numeric_evidence(field_name: str) -> None:
    payload = _valid_payload()
    payload["drifted_features"]["features"][0][field_name] = "0.7"

    with pytest.raises(ValidationError, match="real numbers"):
        DriftReport.model_validate(payload)


def test_run_drift_report_rejects_forbidden_input_before_runner_or_writes() -> None:
    input_gateway = InMemoryDriftInputGateway(
        {
            "baseline": {"nested": {"feature_weight_multiplier": 1.2}},
            "target": {"x": [2]},
        }
    )
    evidently_runner = InMemoryEvidentlyRunner(
        EvidentlyRunResult(evidently_json={}, features=())
    )
    json_writer = InMemoryDriftReportJsonWriter()
    storage = InMemoryDriftReportStorage()

    with pytest.raises(
        BoundaryViolationError,
        match=r"\$\.reference_data\.nested\.feature_weight_multiplier",
    ):
        run_drift_report(
            "baseline",
            "target",
            input_gateway=input_gateway,
            evidently_runner=evidently_runner,
            json_writer=json_writer,
            storage=storage,
        )

    assert input_gateway.loaded_refs == ["baseline"]
    assert evidently_runner.calls == []
    assert json_writer.write_calls == []
    assert storage.append_calls == 0


def test_run_drift_report_rejects_forbidden_evidently_json_before_writes() -> None:
    input_gateway = InMemoryDriftInputGateway(
        {"baseline": {"x": [1]}, "target": {"x": [2]}}
    )
    evidently_runner = InMemoryEvidentlyRunner(
        EvidentlyRunResult(
            evidently_json={"nested": {"feature_weight_multiplier": 1.2}},
            features=(DriftedFeature("spread", 0.7, None, 0.2, True),),
            total_feature_count=1,
        )
    )
    json_writer = InMemoryDriftReportJsonWriter()
    storage = InMemoryDriftReportStorage()

    with pytest.raises(
        BoundaryViolationError,
        match=r"\$\.evidently_json\.nested\.feature_weight_multiplier",
    ):
        run_drift_report(
            "baseline",
            "target",
            input_gateway=input_gateway,
            evidently_runner=evidently_runner,
            json_writer=json_writer,
            storage=storage,
        )

    assert len(evidently_runner.calls) == 1
    assert json_writer.write_calls == []
    assert storage.append_calls == 0
