import importlib.util
import re
import socket
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from audit_eval.drift import (
    DriftInputError,
    DriftRuleConfig,
    DriftRunnerError,
    DriftStorageError,
    DriftedFeature,
    EvidentlyDataDriftRunner,
    EvidentlyRunResult,
    InMemoryDriftInputGateway,
    InMemoryDriftReportJsonWriter,
    InMemoryDriftReportStorage,
    InMemoryEvidentlyRunner,
    build_drift_alert_payload,
    get_default_evidently_runner,
    get_default_input_gateway,
    get_default_json_writer,
    get_default_report_storage,
    run_drift_report,
)


class _BlankRefJsonWriter:
    def __init__(self, returned_ref: str) -> None:
        self.returned_ref = returned_ref
        self.write_calls: list[tuple[str, dict[str, Any]]] = []

    def write_report_json(self, report_id: str, payload: dict[str, Any]) -> str:
        self.write_calls.append((report_id, payload))
        return self.returned_ref


class _AppendingStorage:
    def __init__(
        self,
        *,
        exc: Exception | None = None,
        report_id: str | None = None,
    ) -> None:
        self.exc = exc
        self.report_id = report_id
        self.append_calls = 0
        self.rows: list[dict[str, Any]] = []

    def append_drift_report(self, report: Any) -> str:
        self.append_calls += 1
        self.rows.append(report.model_dump(mode="json"))
        if self.exc is not None:
            raise self.exc
        return self.report_id or report.report_id


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    real_socket = socket.socket

    def fail_network_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Drift reporting must not call network")

    def guarded_socket(
        family: int = socket.AF_INET,
        *args: Any,
        **kwargs: Any,
    ) -> socket.socket:
        if family == socket.AF_UNIX:
            return real_socket(family, *args, **kwargs)
        raise AssertionError("Drift reporting must not call network")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network_call)
    monkeypatch.setattr(socket, "socket", guarded_socket)


def _runner_result() -> EvidentlyRunResult:
    return EvidentlyRunResult(
        evidently_json={"metrics": [{"metric_name": "fake"}]},
        features=(
            DriftedFeature("spread", 0.7, None, 0.2, True),
            DriftedFeature("sector", 0.1, None, 0.2, False),
        ),
        total_feature_count=2,
    )


def test_run_drift_report_uses_all_boundaries_and_appends_once() -> None:
    created_at = datetime(2026, 4, 18, 9, 30, tzinfo=timezone.utc)
    input_gateway = InMemoryDriftInputGateway(
        {
            "feature-window://baseline": {"rows": [{"spread": 1.0}]},
            "feature-window://target": {"rows": [{"spread": 9.0}]},
        }
    )
    evidently_runner = InMemoryEvidentlyRunner(_runner_result())
    json_writer = InMemoryDriftReportJsonWriter("memory://reports")
    storage = InMemoryDriftReportStorage()

    report = run_drift_report(
        "feature-window://baseline",
        "feature-window://target",
        cycle_id="cycle_20260418",
        input_gateway=input_gateway,
        evidently_runner=evidently_runner,
        json_writer=json_writer,
        storage=storage,
        created_at=created_at,
    )

    assert input_gateway.loaded_refs == [
        "feature-window://baseline",
        "feature-window://target",
    ]
    assert evidently_runner.calls == [
        ({"rows": [{"spread": 1.0}]}, {"rows": [{"spread": 9.0}]})
    ]
    assert len(json_writer.write_calls) == 1
    assert json_writer.write_calls[0] == (
        report.report_id,
        {"metrics": [{"metric_name": "fake"}]},
    )
    assert report.evidently_json_ref == f"memory://reports/{report.report_id}.json"
    assert storage.append_calls == 1
    assert storage.rows[0]["report_id"] == report.report_id
    assert report.cycle_id == "cycle_20260418"
    assert report.baseline_ref == "feature-window://baseline"
    assert report.target_ref == "feature-window://target"
    assert report.regime_warning_level == "warning"
    assert report.drifted_features.model_dump(mode="json") == {
        "features": [
            {
                "name": "spread",
                "score": 0.7,
                "statistic": None,
                "threshold": 0.2,
                "drifted": True,
            }
        ]
    }


@pytest.mark.parametrize(
    ("reference_ref", "target_ref", "match"),
    [
        ("", "target", "reference_ref must not be empty"),
        ("   ", "target", "reference_ref must not be empty"),
        ("baseline", "", "target_ref must not be empty"),
        ("baseline", " \t ", "target_ref must not be empty"),
        (123, "target", "reference_ref must be a string"),
        ("baseline", object(), "target_ref must be a string"),
    ],
)
def test_run_drift_report_rejects_invalid_request_refs_before_adapters(
    reference_ref: object,
    target_ref: object,
    match: str,
) -> None:
    input_gateway = InMemoryDriftInputGateway(
        {"baseline": {"x": [1]}, "target": {"x": [2]}}
    )
    evidently_runner = InMemoryEvidentlyRunner(_runner_result())
    json_writer = InMemoryDriftReportJsonWriter()
    storage = InMemoryDriftReportStorage()

    with pytest.raises(DriftInputError, match=match):
        run_drift_report(
            reference_ref,  # type: ignore[arg-type]
            target_ref,  # type: ignore[arg-type]
            input_gateway=input_gateway,
            evidently_runner=evidently_runner,
            json_writer=json_writer,
            storage=storage,
        )

    assert input_gateway.loaded_refs == []
    assert evidently_runner.calls == []
    assert json_writer.write_calls == []
    assert storage.append_calls == 0


def test_run_drift_report_rejects_blank_cycle_id_before_adapters() -> None:
    input_gateway = InMemoryDriftInputGateway(
        {"baseline": {"x": [1]}, "target": {"x": [2]}}
    )
    evidently_runner = InMemoryEvidentlyRunner(_runner_result())
    json_writer = InMemoryDriftReportJsonWriter()
    storage = InMemoryDriftReportStorage()

    with pytest.raises(DriftInputError, match="cycle_id must not be empty"):
        run_drift_report(
            "baseline",
            "target",
            cycle_id="   ",
            input_gateway=input_gateway,
            evidently_runner=evidently_runner,
            json_writer=json_writer,
            storage=storage,
        )

    assert input_gateway.loaded_refs == []
    assert evidently_runner.calls == []
    assert json_writer.write_calls == []
    assert storage.append_calls == 0


def test_run_drift_report_strips_request_refs_before_loading() -> None:
    input_gateway = InMemoryDriftInputGateway(
        {"baseline": {"x": [1]}, "target": {"x": [2]}}
    )
    storage = InMemoryDriftReportStorage()

    report = run_drift_report(
        " baseline ",
        "\ttarget\n",
        cycle_id=" cycle_20260418 ",
        input_gateway=input_gateway,
        evidently_runner=InMemoryEvidentlyRunner(_runner_result()),
        json_writer=InMemoryDriftReportJsonWriter(),
        storage=storage,
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    assert input_gateway.loaded_refs == ["baseline", "target"]
    assert report.cycle_id == "cycle_20260418"
    assert report.baseline_ref == "baseline"
    assert report.target_ref == "target"


@pytest.mark.parametrize("returned_ref", ["", "   "])
def test_run_drift_report_rejects_blank_writer_ref_before_storage(
    returned_ref: str,
) -> None:
    json_writer = _BlankRefJsonWriter(returned_ref)
    storage = InMemoryDriftReportStorage()

    with pytest.raises(DriftStorageError, match="evidently_json_ref"):
        run_drift_report(
            "baseline",
            "target",
            input_gateway=InMemoryDriftInputGateway(
                {"baseline": {"x": [1]}, "target": {"x": [2]}}
            ),
            evidently_runner=InMemoryEvidentlyRunner(_runner_result()),
            json_writer=json_writer,
            storage=storage,
            created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        )

    assert len(json_writer.write_calls) == 1
    assert storage.append_calls == 0


def test_run_drift_report_retains_json_when_storage_fails_after_append() -> None:
    json_writer = InMemoryDriftReportJsonWriter()
    storage = _AppendingStorage(
        exc=DriftStorageError("warehouse unavailable after append")
    )

    with pytest.raises(DriftStorageError, match="warehouse unavailable after append"):
        run_drift_report(
            "baseline",
            "target",
            input_gateway=InMemoryDriftInputGateway(
                {"baseline": {"x": [1]}, "target": {"x": [2]}}
            ),
            evidently_runner=InMemoryEvidentlyRunner(_runner_result()),
            json_writer=json_writer,
            storage=storage,  # type: ignore[arg-type]
            created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        )

    assert storage.append_calls == 1
    report_id = storage.rows[0]["report_id"]
    assert set(json_writer.payloads_by_report_id) == {report_id}
    assert storage.rows[0]["evidently_json_ref"] == (
        f"memory://drift-report-json/{report_id}.json"
    )


def test_run_drift_report_rejects_storage_report_id_mismatch_without_deleting_json() -> None:
    json_writer = InMemoryDriftReportJsonWriter()
    storage = _AppendingStorage(report_id="drift-other")

    with pytest.raises(DriftStorageError, match="mismatched report_id"):
        run_drift_report(
            "baseline",
            "target",
            input_gateway=InMemoryDriftInputGateway(
                {"baseline": {"x": [1]}, "target": {"x": [2]}}
            ),
            evidently_runner=InMemoryEvidentlyRunner(_runner_result()),
            json_writer=json_writer,
            storage=storage,  # type: ignore[arg-type]
            created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        )

    assert storage.append_calls == 1
    report_id = storage.rows[0]["report_id"]
    assert report_id != "drift-other"
    assert set(json_writer.payloads_by_report_id) == {report_id}
    assert storage.rows[0]["evidently_json_ref"] == (
        f"memory://drift-report-json/{report_id}.json"
    )


def test_invalid_rules_version_fails_before_writer_or_storage() -> None:
    rules = DriftRuleConfig()
    object.__setattr__(rules, "version", "   ")
    json_writer = InMemoryDriftReportJsonWriter()
    storage = InMemoryDriftReportStorage()

    with pytest.raises(DriftInputError, match="contract validation"):
        run_drift_report(
            "baseline",
            "target",
            input_gateway=InMemoryDriftInputGateway(
                {"baseline": {"x": [1]}, "target": {"x": [2]}}
            ),
            evidently_runner=InMemoryEvidentlyRunner(_runner_result()),
            json_writer=json_writer,
            storage=storage,
            rules=rules,
            created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        )

    assert json_writer.write_calls == []
    assert storage.append_calls == 0


def test_build_drift_alert_payload_contains_only_structural_warning_fields() -> None:
    report = run_drift_report(
        "baseline",
        "target",
        input_gateway=InMemoryDriftInputGateway(
            {"baseline": {"x": [1]}, "target": {"x": [2]}}
        ),
        evidently_runner=InMemoryEvidentlyRunner(_runner_result()),
        json_writer=InMemoryDriftReportJsonWriter(),
        storage=InMemoryDriftReportStorage(),
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    payload = build_drift_alert_payload(report)

    assert asdict(payload) == {
        "report_id": report.report_id,
        "regime_warning_level": "warning",
        "drifted_features": ("spread",),
        "evidently_json_ref": report.evidently_json_ref,
    }


def test_default_drift_dependencies_fail_closed() -> None:
    with pytest.raises(DriftInputError, match="input_gateway"):
        get_default_input_gateway()

    with pytest.raises(DriftRunnerError, match="evidently_runner"):
        get_default_evidently_runner()

    with pytest.raises(DriftStorageError, match="json_writer"):
        get_default_json_writer()

    with pytest.raises(DriftStorageError, match="storage"):
        get_default_report_storage()

    with pytest.raises(DriftInputError, match="input_gateway"):
        run_drift_report("baseline", "target")


def test_evidently_data_drift_runner_smoke_or_lazy_import_error() -> None:
    runner = EvidentlyDataDriftRunner()
    if importlib.util.find_spec("evidently") is None:
        with pytest.raises(DriftRunnerError, match="Evidently"):
            runner.run([{"x": 1}], [{"x": 2}])
        return

    pd = pytest.importorskip("pandas")
    reference = pd.DataFrame(
        {
            "x": list(range(60)),
            "stable": list(range(60)),
        }
    )
    target = pd.DataFrame(
        {
            "x": list(range(100, 160)),
            "stable": list(range(60)),
        }
    )

    result = runner.run(reference, target)

    assert "metrics" in result.evidently_json
    assert result.features
    assert any(feature.name == "x" for feature in result.features)


def test_drift_package_has_no_provider_or_http_client_dependencies() -> None:
    forbidden = re.compile(r"\b(openai|anthropic|requests|httpx)\b")
    for path in (Path(__file__).parents[1] / "src" / "audit_eval" / "drift").glob(
        "*.py"
    ):
        assert forbidden.search(path.read_text(encoding="utf-8")) is None, path
