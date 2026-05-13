from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from audit_eval._boundary import BoundaryViolationError
from audit_eval.backtest import BacktestInputError, BacktestJob, FeatureAvailability
from audit_eval.contracts import BacktestResult


def _valid_payload() -> dict[str, Any]:
    return {
        "backtest_id": "backtest-1",
        "job_ref": "job://alphalens-1",
        "engine": "alphalens",
        "feature_ref": "feature://momentum/v1",
        "formal_snapshot_range": {
            "manifest_cycle_id": "cycle_20260418",
            "manifest_snapshot_refs": ["snapshot://features/20260418"],
        },
        "metrics": {"ic": 0.12, "decay": {"T+5": 0.08}},
        "pit_check_passed": True,
        "created_at": datetime(2026, 4, 18, tzinfo=timezone.utc),
    }


def test_backtest_result_fields_match_project_contract() -> None:
    assert tuple(BacktestResult.model_fields) == (
        "backtest_id",
        "job_ref",
        "engine",
        "feature_ref",
        "formal_snapshot_range",
        "metrics",
        "pit_check_passed",
        "created_at",
    )


def test_backtest_result_accepts_valid_payload() -> None:
    result = BacktestResult.model_validate(_valid_payload())

    assert result.backtest_id == "backtest-1"
    assert result.engine == "alphalens"
    assert result.pit_check_passed is True


def test_backtest_result_strips_identifier_refs() -> None:
    payload = _valid_payload()
    payload["backtest_id"] = " backtest-1 "
    payload["job_ref"] = "\tjob://alphalens-1\n"
    payload["feature_ref"] = " feature://momentum/v1 "

    result = BacktestResult.model_validate(payload)

    assert result.backtest_id == "backtest-1"
    assert result.job_ref == "job://alphalens-1"
    assert result.feature_ref == "feature://momentum/v1"


@pytest.mark.parametrize("field_name", ["backtest_id", "job_ref", "feature_ref"])
def test_backtest_result_rejects_whitespace_identifier_refs(
    field_name: str,
) -> None:
    payload = _valid_payload()
    payload[field_name] = "   "

    with pytest.raises(ValidationError, match=f"{field_name} must not be empty"):
        BacktestResult.model_validate(payload)


def test_backtest_result_rejects_extra_fields() -> None:
    payload = _valid_payload()
    payload["extra"] = "forbidden"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BacktestResult.model_validate(payload)


def test_backtest_result_rejects_unknown_engine() -> None:
    payload = _valid_payload()
    payload["engine"] = "nautilus"

    with pytest.raises(ValidationError, match="alphalens"):
        BacktestResult.model_validate(payload)


def test_backtest_result_rejects_failed_pit_gate() -> None:
    payload = _valid_payload()
    payload["pit_check_passed"] = False

    with pytest.raises(ValidationError, match="pit_check_passed must be True"):
        BacktestResult.model_validate(payload)


@pytest.mark.parametrize("value", [1, "true", "yes"])
def test_backtest_result_rejects_coerced_truthy_pit_gate(value: object) -> None:
    payload = _valid_payload()
    payload["pit_check_passed"] = value

    with pytest.raises(ValidationError, match="pit_check_passed"):
        BacktestResult.model_validate(payload)


@pytest.mark.parametrize("field_name", ["formal_snapshot_range", "metrics"])
def test_backtest_result_rejects_forbidden_field_in_json_payloads(
    field_name: str,
) -> None:
    payload = _valid_payload()
    payload[field_name] = {"nested": {"feature_weight_multiplier": 1.2}}

    with pytest.raises(
        BoundaryViolationError,
        match=rf"\$\.{field_name}\.nested\.feature_weight_multiplier",
    ):
        BacktestResult.model_validate(payload)


def test_backtest_result_exported_from_contracts_package() -> None:
    from audit_eval.contracts import BacktestResult as ExportedBacktestResult

    assert ExportedBacktestResult is BacktestResult


def test_backtest_job_normalizes_and_copies_inputs() -> None:
    formal_snapshot_range = {
        "manifest_snapshot_refs": ["snapshot://features/20260418"]
    }
    metrics_config = {"quantiles": 5}

    job = BacktestJob(
        job_ref=" job://alphalens-1 ",
        feature_ref="\tfeature://momentum/v1\n",
        formal_snapshot_range=formal_snapshot_range,
        metrics_config=metrics_config,
    )
    formal_snapshot_range["manifest_snapshot_refs"].append("mutated")
    metrics_config["quantiles"] = 10

    assert job.job_ref == "job://alphalens-1"
    assert job.feature_ref == "feature://momentum/v1"
    assert job.engine == "alphalens"
    assert job.run_mode == "offline_research"
    assert job.formal_snapshot_range == {
        "manifest_snapshot_refs": ["snapshot://features/20260418"]
    }
    assert job.metrics_config == {"quantiles": 5}


@pytest.mark.parametrize("field_name", ["job_ref", "feature_ref"])
def test_backtest_job_rejects_blank_refs(field_name: str) -> None:
    kwargs: dict[str, Any] = {
        "job_ref": "job://alphalens-1",
        "feature_ref": "feature://momentum/v1",
        "formal_snapshot_range": {
            "manifest_snapshot_refs": ["snapshot://features/20260418"]
        },
    }
    kwargs[field_name] = "   "

    with pytest.raises(BacktestInputError, match=f"{field_name} must not be empty"):
        BacktestJob(**kwargs)


def test_backtest_job_rejects_unknown_engine() -> None:
    with pytest.raises(BacktestInputError, match="engine"):
        BacktestJob(
            job_ref="job://alphalens-1",
            feature_ref="feature://momentum/v1",
            formal_snapshot_range={
                "manifest_snapshot_refs": ["snapshot://features/20260418"]
            },
            engine="nautilus",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("run_mode", ["daily_cycle", "online", "read_head"])
def test_backtest_job_rejects_daily_cycle_and_online_modes(run_mode: str) -> None:
    with pytest.raises(BacktestInputError, match="offline_research"):
        BacktestJob(
            job_ref="job://alphalens-1",
            feature_ref="feature://momentum/v1",
            formal_snapshot_range={
                "manifest_snapshot_refs": ["snapshot://features/20260418"]
            },
            run_mode=run_mode,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("field_name", ["formal_snapshot_range", "metrics_config"])
def test_backtest_job_rejects_forbidden_fields(field_name: str) -> None:
    kwargs: dict[str, Any] = {
        "job_ref": "job://alphalens-1",
        "feature_ref": "feature://momentum/v1",
        "formal_snapshot_range": {
            "manifest_snapshot_refs": ["snapshot://features/20260418"]
        },
        "metrics_config": {},
    }
    kwargs[field_name] = {"nested": {"feature_weight_multiplier": 1.2}}

    with pytest.raises(BoundaryViolationError, match="feature_weight_multiplier"):
        BacktestJob(**kwargs)


def test_feature_availability_rejects_forbidden_metadata() -> None:
    with pytest.raises(
        BoundaryViolationError,
        match=r"\$\.metadata\.feature_weight_multiplier",
    ):
        FeatureAvailability(
            feature_ref="feature://momentum/v1",
            as_of=datetime(2026, 4, 18, tzinfo=timezone.utc),
            available_at=datetime(2026, 4, 17, tzinfo=timezone.utc),
            snapshot_ref="snapshot://features/20260418",
            metadata={"feature_weight_multiplier": 1.2},
        )
