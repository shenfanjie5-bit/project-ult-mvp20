"""Storage and adapter boundaries for drift reporting."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from threading import Lock
from typing import Any, Protocol

from audit_eval._boundary import assert_no_forbidden_write
from audit_eval.contracts.common import JsonObject
from audit_eval.contracts.drift_report import DriftReport
from audit_eval.drift.schema import DriftedFeature, EvidentlyRunResult


class DriftInputError(RuntimeError):
    """Raised when drift input data is unavailable or invalid."""


class DriftRunnerError(RuntimeError):
    """Raised when an Evidently run cannot be produced."""


class DriftStorageError(RuntimeError):
    """Raised when drift report storage is unavailable or fails."""


class DriftInputGateway(Protocol):
    """Input boundary for reference and target feature windows."""

    def load_feature_window(self, ref: str) -> Any:
        """Load one point-in-time feature window by ref."""


class EvidentlyRunner(Protocol):
    """Boundary for generating Evidently drift report payloads."""

    def run(self, reference_data: Any, target_data: Any) -> EvidentlyRunResult:
        """Run drift evaluation over reference and target data."""


class DriftReportJsonWriter(Protocol):
    """Boundary owned by the data-platform report JSON integration."""

    def write_report_json(self, report_id: str, payload: JsonObject) -> str:
        """Persist one Evidently JSON payload and return its external ref."""


class DriftReportStorage(Protocol):
    """Analytical storage boundary for drift reports."""

    def append_drift_report(self, report: DriftReport) -> str:
        """Append a validated drift report and return its id."""


class InMemoryDriftInputGateway:
    """In-memory feature-window gateway for tests and Lite workflows."""

    def __init__(self, windows: Mapping[str, Any]) -> None:
        self.windows = deepcopy(dict(windows))
        self.loaded_refs: list[str] = []

    def load_feature_window(self, ref: str) -> Any:
        self.loaded_refs.append(ref)
        try:
            return deepcopy(self.windows[ref])
        except KeyError as exc:
            raise DriftInputError(f"Feature window ref not found: {ref}") from exc


class InMemoryEvidentlyRunner:
    """In-memory Evidently runner for deterministic tests."""

    def __init__(self, result: EvidentlyRunResult) -> None:
        self.result = result
        self.calls: list[tuple[Any, Any]] = []

    def run(self, reference_data: Any, target_data: Any) -> EvidentlyRunResult:
        self.calls.append((deepcopy(reference_data), deepcopy(target_data)))
        return self.result


class InMemoryDriftReportJsonWriter:
    """In-memory report JSON writer for deterministic tests."""

    def __init__(self, ref_prefix: str = "memory://drift-report-json") -> None:
        self.ref_prefix = ref_prefix.rstrip("/")
        self.payloads_by_report_id: dict[str, JsonObject] = {}
        self.write_calls: list[tuple[str, JsonObject]] = []
        self._lock = Lock()

    def write_report_json(self, report_id: str, payload: JsonObject) -> str:
        assert_no_forbidden_write(payload, path="$.evidently_json")
        payload_copy = deepcopy(payload)
        with self._lock:
            self.payloads_by_report_id[report_id] = payload_copy
            self.write_calls.append((report_id, payload_copy))
        return f"{self.ref_prefix}/{report_id}.json"

    def delete_report_json(self, report_id: str) -> None:
        with self._lock:
            self.payloads_by_report_id.pop(report_id, None)


class InMemoryDriftReportStorage:
    """In-memory analytical drift report storage for tests and Lite workflows."""

    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []
        self.append_calls = 0
        self._lock = Lock()

    def append_drift_report(self, report: DriftReport) -> str:
        row = report.model_dump(mode="json")
        assert_no_forbidden_write(row, path="$.drift_report")
        with self._lock:
            self.append_calls += 1
            self.rows.append(deepcopy(row))
        return report.report_id


class EvidentlyDataDriftRunner:
    """Lazy Evidently adapter for deterministic data drift reports."""

    def run(self, reference_data: Any, target_data: Any) -> EvidentlyRunResult:
        try:
            payload = self._run_modern(reference_data, target_data)
        except ImportError:
            payload = self._run_legacy(reference_data, target_data)
        features = _extract_feature_results(payload)
        return EvidentlyRunResult(
            evidently_json=payload,
            features=features,
            total_feature_count=_extract_total_feature_count(payload, features),
        )

    def _run_modern(self, reference_data: Any, target_data: Any) -> JsonObject:
        try:
            from evidently import Report  # type: ignore[import-not-found, import-untyped]
            from evidently.presets import DataDriftPreset  # type: ignore[import-not-found, import-untyped]
        except ImportError as exc:
            raise ImportError("modern Evidently API unavailable") from exc

        report = Report([DataDriftPreset()])
        snapshot = report.run(
            current_data=target_data,
            reference_data=reference_data,
        )
        return _snapshot_to_payload(snapshot)

    def _run_legacy(self, reference_data: Any, target_data: Any) -> JsonObject:
        report_cls, preset_cls = _load_legacy_evidently_classes()
        report = report_cls(metrics=[preset_cls()])
        report.run(reference_data=reference_data, current_data=target_data)
        return _snapshot_to_payload(report)


def get_default_input_gateway() -> DriftInputGateway:
    """Return configured drift input gateway, or fail closed."""

    raise DriftInputError(
        "No default drift input gateway is configured; pass input_gateway=..."
    )


def get_default_evidently_runner() -> EvidentlyRunner:
    """Return configured Evidently runner, or fail closed."""

    raise DriftRunnerError(
        "No default Evidently runner is configured; pass evidently_runner=..."
    )


def get_default_json_writer() -> DriftReportJsonWriter:
    """Return configured drift report JSON writer, or fail closed."""

    raise DriftStorageError(
        "No default drift report JSON writer is configured; pass json_writer=..."
    )


def get_default_report_storage() -> DriftReportStorage:
    """Return configured drift report analytical storage, or fail closed."""

    raise DriftStorageError(
        "No default drift report storage is configured; pass storage=..."
    )


def _load_legacy_evidently_classes() -> tuple[type[Any], type[Any]]:
    import_errors: list[Exception] = []
    for report_module, preset_module in (
        ("evidently.legacy.report", "evidently.legacy.metric_preset"),
        ("evidently.report", "evidently.metric_preset"),
    ):
        try:
            report_mod = __import__(report_module, fromlist=["Report"])
            preset_mod = __import__(preset_module, fromlist=["DataDriftPreset"])
            return report_mod.Report, preset_mod.DataDriftPreset
        except ImportError as exc:
            import_errors.append(exc)
    raise DriftRunnerError(
        "Evidently is not installed with a supported data drift report API"
    ) from import_errors[-1]


def _snapshot_to_payload(snapshot: Any) -> JsonObject:
    if hasattr(snapshot, "dict"):
        payload = snapshot.dict()
    elif hasattr(snapshot, "as_dict"):
        payload = snapshot.as_dict()
    elif hasattr(snapshot, "dump_dict"):
        payload = snapshot.dump_dict()
    elif hasattr(snapshot, "json"):
        payload = json.loads(snapshot.json())
    else:
        raise DriftRunnerError("Evidently report did not expose JSON content")

    if not isinstance(payload, dict):
        raise DriftRunnerError("Evidently report JSON content must be an object")
    return payload


def _extract_feature_results(payload: JsonObject) -> tuple[DriftedFeature, ...]:
    features: list[DriftedFeature] = []
    seen_names: set[str] = set()

    for mapping in _iter_mappings(payload):
        drift_by_columns = mapping.get("drift_by_columns")
        if isinstance(drift_by_columns, Mapping):
            for fallback_name, feature_payload in drift_by_columns.items():
                if not isinstance(feature_payload, Mapping):
                    continue
                feature = _feature_from_legacy_mapping(
                    fallback_name=fallback_name,
                    payload=feature_payload,
                )
                if feature is not None and feature.name not in seen_names:
                    seen_names.add(feature.name)
                    features.append(feature)

    metrics = payload.get("metrics")
    if isinstance(metrics, Sequence) and not isinstance(
        metrics,
        (str, bytes, bytearray),
    ):
        for metric in metrics:
            if not isinstance(metric, Mapping):
                continue
            feature = _feature_from_modern_metric(metric)
            if feature is not None and feature.name not in seen_names:
                seen_names.add(feature.name)
                features.append(feature)

    return tuple(features)


def _feature_from_legacy_mapping(
    *,
    fallback_name: object,
    payload: Mapping[str, object],
) -> DriftedFeature | None:
    name = payload.get("column_name", fallback_name)
    if not isinstance(name, str) or not name.strip():
        return None
    score = _optional_float(
        payload.get("drift_score", payload.get("score", payload.get("value")))
    )
    statistic = _optional_float(
        payload.get("statistic", payload.get("stattest_statistic"))
    )
    threshold = _optional_float(
        payload.get("threshold", payload.get("stattest_threshold"))
    )
    if threshold is None or (score is None and statistic is None):
        return None
    raw_drifted = payload.get("drift_detected", payload.get("drifted"))
    drifted = (
        bool(raw_drifted)
        if raw_drifted is not None
        else _derive_drifted(
            score if score is not None else statistic,
            threshold,
            str(payload.get("stattest_name", "")),
        )
    )
    return DriftedFeature(
        name=name,
        score=score,
        statistic=statistic,
        threshold=threshold,
        drifted=drifted,
    )


def _feature_from_modern_metric(metric: Mapping[str, object]) -> DriftedFeature | None:
    config = metric.get("config")
    if not isinstance(config, Mapping):
        return None
    metric_type = str(config.get("type", ""))
    metric_name = str(metric.get("metric_name", ""))
    if "ValueDrift" not in metric_type and not metric_name.startswith("ValueDrift"):
        return None
    name = config.get("column")
    if not isinstance(name, str) or not name.strip():
        return None
    score = _optional_float(metric.get("value"))
    threshold = _optional_float(config.get("threshold"))
    if score is None or threshold is None:
        return None
    method = str(config.get("method", metric_name))
    return DriftedFeature(
        name=name,
        score=score,
        statistic=None,
        threshold=threshold,
        drifted=_derive_drifted(score, threshold, method),
    )


def _extract_total_feature_count(
    payload: JsonObject,
    features: tuple[DriftedFeature, ...],
) -> int:
    metrics = payload.get("metrics")
    if isinstance(metrics, Sequence) and not isinstance(
        metrics,
        (str, bytes, bytearray),
    ):
        for metric in metrics:
            if not isinstance(metric, Mapping):
                continue
            value = metric.get("value")
            if not isinstance(value, Mapping):
                continue
            count = _optional_float(value.get("count"))
            share = _optional_float(value.get("share"))
            if count is not None and share and share > 0:
                return max(len(features), int(round(count / share)))
    return len(features)


def _derive_drifted(value: float | None, threshold: float, method: str) -> bool:
    if value is None:
        return False
    method_name = method.lower().replace("-", "_")
    if "p_value" in method_name or "pvalue" in method_name:
        return value <= threshold
    return value >= threshold


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _iter_mappings(payload: object) -> tuple[Mapping[str, object], ...]:
    if isinstance(payload, Mapping):
        mappings: list[Mapping[str, object]] = [payload]
        for value in payload.values():
            mappings.extend(_iter_mappings(value))
        return tuple(mappings)
    if isinstance(payload, Sequence) and not isinstance(
        payload,
        (str, bytes, bytearray),
    ):
        mappings = []
        for value in payload:
            mappings.extend(_iter_mappings(value))
        return tuple(mappings)
    return ()


__all__ = [
    "DriftInputError",
    "DriftInputGateway",
    "DriftReportJsonWriter",
    "DriftReportStorage",
    "DriftRunnerError",
    "DriftStorageError",
    "EvidentlyDataDriftRunner",
    "EvidentlyRunner",
    "InMemoryDriftInputGateway",
    "InMemoryDriftReportJsonWriter",
    "InMemoryDriftReportStorage",
    "InMemoryEvidentlyRunner",
    "get_default_evidently_runner",
    "get_default_input_gateway",
    "get_default_json_writer",
    "get_default_report_storage",
]
