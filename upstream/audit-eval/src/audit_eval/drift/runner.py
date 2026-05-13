"""Drift report orchestration entrypoints."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import datetime, timezone

from pydantic import ValidationError

from audit_eval._boundary import assert_no_forbidden_write
from audit_eval.contracts.drift_report import DriftedFeaturesPayload, DriftReport
from audit_eval.drift.rules import (
    DEFAULT_DRIFT_RULE_CONFIG,
    DriftRuleConfig,
    classify_regime_warning,
)
from audit_eval.drift.schema import (
    DriftAlertPayload,
    DriftedFeature,
    RegimeWarningLevel,
)
from audit_eval.drift.storage import (
    DriftInputError,
    DriftInputGateway,
    DriftReportJsonWriter,
    DriftReportStorage,
    DriftRunnerError,
    DriftStorageError,
    EvidentlyRunner,
    get_default_evidently_runner,
    get_default_input_gateway,
    get_default_json_writer,
    get_default_report_storage,
)


def run_drift_report(
    reference_ref: str,
    target_ref: str,
    *,
    cycle_id: str | None = None,
    input_gateway: DriftInputGateway | None = None,
    evidently_runner: EvidentlyRunner | None = None,
    json_writer: DriftReportJsonWriter | None = None,
    storage: DriftReportStorage | None = None,
    rules: DriftRuleConfig | None = None,
    created_at: datetime | None = None,
) -> DriftReport:
    """Generate, persist, and return one analytical drift report."""

    try:
        reference_ref, target_ref = _validate_request_refs(
            reference_ref=reference_ref,
            target_ref=target_ref,
        )
        cycle_id = _normalize_optional_request_ref("cycle_id", cycle_id)
    except DriftInputError:
        raise
    except Exception as exc:
        raise DriftInputError(str(exc)) from exc

    gateway = input_gateway or get_default_input_gateway()
    runner = evidently_runner or get_default_evidently_runner()
    writer = json_writer or get_default_json_writer()
    report_storage = storage or get_default_report_storage()

    reference_data = gateway.load_feature_window(reference_ref)
    assert_no_forbidden_write(reference_data, path="$.reference_data")
    target_data = gateway.load_feature_window(target_ref)
    assert_no_forbidden_write(target_data, path="$.target_data")

    try:
        result = runner.run(reference_data, target_data)
    except DriftRunnerError:
        raise
    except Exception as exc:
        raise DriftRunnerError(f"Evidently runner failed: {exc}") from exc
    assert_no_forbidden_write(result.evidently_json, path="$.evidently_json")

    rule_decision = classify_regime_warning(
        result,
        rules=rules or DEFAULT_DRIFT_RULE_CONFIG,
    )
    drifted_features_payload = _drifted_features_payload(
        rule_decision.drifted_features,
    )
    assert_no_forbidden_write(
        drifted_features_payload.model_dump(),
        path="$.drifted_features",
    )

    effective_created_at = created_at or datetime.now(timezone.utc)
    report_id = _report_id(
        reference_ref=reference_ref,
        target_ref=target_ref,
        cycle_id=cycle_id,
        created_at=effective_created_at,
    )

    _build_report(
        report_id=report_id,
        cycle_id=cycle_id,
        reference_ref=reference_ref,
        target_ref=target_ref,
        evidently_json_ref="pending://validated-before-write",
        drifted_features_payload=drifted_features_payload,
        regime_warning_level=rule_decision.regime_warning_level,
        alert_rules_version=rule_decision.alert_rules_version,
        created_at=effective_created_at,
    )
    evidently_json_ref = _write_report_json(
        writer,
        report_id,
        result.evidently_json,
    )
    report = _build_report(
        report_id=report_id,
        cycle_id=cycle_id,
        reference_ref=reference_ref,
        target_ref=target_ref,
        evidently_json_ref=evidently_json_ref,
        drifted_features_payload=drifted_features_payload,
        regime_warning_level=rule_decision.regime_warning_level,
        alert_rules_version=rule_decision.alert_rules_version,
        created_at=effective_created_at,
    )
    try:
        persisted_id = report_storage.append_drift_report(report)
    except DriftStorageError:
        raise
    except Exception as exc:
        raise DriftStorageError(f"append_drift_report failed: {exc}") from exc
    if persisted_id != report.report_id:
        raise DriftStorageError(
            "Drift report storage returned mismatched report_id: "
            f"{persisted_id!r} != {report.report_id!r}"
        )
    return report


def build_drift_alert_payload(report: DriftReport) -> DriftAlertPayload:
    """Build the third-layer structural alert payload for a drift report."""

    payload = DriftAlertPayload(
        report_id=report.report_id,
        regime_warning_level=report.regime_warning_level,
        drifted_features=tuple(
            feature.name
            for feature in report.drifted_features.features
            if feature.drifted
        ),
        evidently_json_ref=report.evidently_json_ref,
    )
    assert_no_forbidden_write(asdict(payload), path="$.drift_alert_payload")
    return payload


def _validate_request_refs(
    *,
    reference_ref: object,
    target_ref: object,
) -> tuple[str, str]:
    return (
        _normalize_required_request_ref("reference_ref", reference_ref),
        _normalize_required_request_ref("target_ref", target_ref),
    )


def _normalize_required_request_ref(field_name: str, value: object) -> str:
    if not isinstance(value, str):
        raise DriftInputError(f"{field_name} must be a string")
    stripped = value.strip()
    if not stripped:
        raise DriftInputError(f"{field_name} must not be empty")
    return stripped


def _normalize_optional_request_ref(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    return _normalize_required_request_ref(field_name, value)


def _drifted_features_payload(
    features: tuple[DriftedFeature, ...],
) -> DriftedFeaturesPayload:
    try:
        return DriftedFeaturesPayload.model_validate(
            {"features": [feature.to_payload() for feature in features]}
        )
    except ValidationError as exc:
        raise DriftRunnerError("Drifted feature evidence is invalid") from exc


def _write_report_json(
    writer: DriftReportJsonWriter,
    report_id: str,
    evidently_json: dict[str, object],
) -> str:
    try:
        ref = writer.write_report_json(report_id, evidently_json)
    except DriftStorageError:
        raise
    except Exception as exc:
        raise DriftStorageError(f"write_report_json failed: {exc}") from exc
    try:
        return _normalize_required_request_ref("evidently_json_ref", ref)
    except DriftInputError as exc:
        _cleanup_report_json(writer, report_id)
        raise DriftStorageError(str(exc)) from exc


def _build_report(
    *,
    report_id: str,
    cycle_id: str | None,
    reference_ref: str,
    target_ref: str,
    evidently_json_ref: str,
    drifted_features_payload: DriftedFeaturesPayload,
    regime_warning_level: RegimeWarningLevel,
    alert_rules_version: str,
    created_at: datetime,
) -> DriftReport:
    try:
        return DriftReport(
            report_id=report_id,
            cycle_id=cycle_id,
            baseline_ref=reference_ref,
            target_ref=target_ref,
            evidently_json_ref=evidently_json_ref,
            drifted_features=drifted_features_payload,
            regime_warning_level=regime_warning_level,
            alert_rules_version=alert_rules_version,
            created_at=created_at,
        )
    except ValidationError as exc:
        raise DriftInputError("Drift report contract validation failed") from exc


def _cleanup_report_json(writer: DriftReportJsonWriter, report_id: str) -> None:
    cleanup = getattr(writer, "delete_report_json", None)
    if cleanup is None:
        return
    try:
        cleanup(report_id)
    except Exception:
        return


def _report_id(
    *,
    reference_ref: str,
    target_ref: str,
    cycle_id: str | None,
    created_at: datetime,
) -> str:
    digest = hashlib.sha256(
        "\0".join(
            (
                cycle_id or "",
                reference_ref,
                target_ref,
                created_at.isoformat(),
            )
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"drift-{digest}"


__all__ = [
    "build_drift_alert_payload",
    "run_drift_report",
]
