"""Current production daily-cycle selection and Phase 0 freeze helpers."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Final

import pyarrow.parquet as pq  # type: ignore[import-untyped]

from data_platform.cycle.freeze import freeze_cycle_candidates
from data_platform.cycle.models import CycleMetadata, cycle_id_for_date
from data_platform.cycle.repository import get_cycle
from data_platform.raw import RawArtifact, RawReader

DEFAULT_CURRENT_CYCLE_SYMBOLS: Final[tuple[str, ...]] = ("600519.SH", "000001.SZ")
CURRENT_CYCLE_SYMBOLS_ENV: Final[str] = "DP_CURRENT_CYCLE_SYMBOLS"
DATA_READINESS_FAILED_NODE: Final[str] = "data_platform.current_selection"
CURRENT_CYCLE_INPUT_TABLES: Final[tuple[str, ...]] = (
    "main.stg_trade_cal",
    "main.stg_daily",
    "main.stg_stock_basic",
)

_SOURCE_ID: Final[str] = "tushare"
_TRADE_CAL_DATASET: Final[str] = "trade_cal"
_DAILY_DATASET: Final[str] = "daily"
_STOCK_BASIC_DATASET: Final[str] = "stock_basic"
_TABLE_BY_DATASET: Final[dict[str, str]] = {
    _TRADE_CAL_DATASET: "main.stg_trade_cal",
    _DAILY_DATASET: "main.stg_daily",
    _STOCK_BASIC_DATASET: "main.stg_stock_basic",
}
_SYMBOL_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9]{6}[.](?:SH|SZ|BJ)$")

GetCycleFn = Callable[[str], CycleMetadata]
FreezeCycleFn = Callable[[str], CycleMetadata]
CandidateIdLoader = Callable[[str], tuple[int, ...]]


class CurrentCycleSelectionError(RuntimeError):
    """Raised when current-cycle selection or Phase 0 readiness fails closed."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        cycle_id: str | None = None,
        evidence: Mapping[str, object] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.cycle_id = cycle_id
        self.evidence = dict(evidence or {})
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class CurrentCycleArtifactRef:
    """Evidence for one Raw Zone artifact backing a staging input."""

    source_id: str
    dataset: str
    input_table: str
    partition_date: date
    run_id: str
    path: str
    row_count: int
    written_at: datetime

    @classmethod
    def from_raw_artifact(cls, artifact: RawArtifact) -> CurrentCycleArtifactRef:
        return cls(
            source_id=artifact.source_id,
            dataset=artifact.dataset,
            input_table=_TABLE_BY_DATASET[artifact.dataset],
            partition_date=artifact.partition_date,
            run_id=artifact.run_id,
            path=str(artifact.path),
            row_count=artifact.row_count,
            written_at=artifact.written_at,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "dataset": self.dataset,
            "input_table": self.input_table,
            "partition_date": self.partition_date.isoformat(),
            "run_id": self.run_id,
            "path": self.path,
            "row_count": self.row_count,
            "written_at": self.written_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class CurrentCycleSelection:
    """Selected open trading day and its required current-cycle inputs."""

    trade_date: date
    cycle_id: str
    symbols: tuple[str, ...]
    input_tables: tuple[str, ...]
    input_artifact_refs: Mapping[str, tuple[CurrentCycleArtifactRef, ...]]
    raw_zone_path: str
    scan_metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def evidence(self) -> dict[str, object]:
        return {
            "selected_trade_date": self.trade_date.isoformat(),
            "cycle_id": self.cycle_id,
            "symbols": list(self.symbols),
            "input_tables": list(self.input_tables),
            "input_artifact_refs": _artifact_refs_as_dict(self.input_artifact_refs),
            "raw_zone_path": self.raw_zone_path,
            "scan_metadata": dict(self.scan_metadata),
        }


@dataclass(frozen=True, slots=True)
class CurrentCycleFreezeResult:
    """Phase 0 current-cycle selection plus frozen candidate evidence."""

    selection: CurrentCycleSelection
    cycle_metadata: CycleMetadata
    frozen_candidate_ids: tuple[int, ...]

    @property
    def evidence(self) -> dict[str, object]:
        return {
            **self.selection.evidence,
            "frozen_candidate_ids": list(self.frozen_candidate_ids),
            "cutoff_metadata": _cutoff_metadata(self.cycle_metadata),
        }


@dataclass(frozen=True, slots=True)
class CurrentCycleReadiness:
    """Read-only readiness result with a DataReadinessSignal-compatible view."""

    ready: bool
    cycle_id: str
    reason: str | None
    failed_node: str = DATA_READINESS_FAILED_NODE
    evidence: Mapping[str, object] = field(default_factory=dict)

    def as_data_readiness_signal(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "cycle_id": self.cycle_id,
            "reason": self.reason,
            "failed_node": self.failed_node,
        }


class CurrentCycleReadinessProvider:
    """Read-only provider surface that orchestrator can adapt without private imports."""

    def __init__(
        self,
        *,
        raw_zone_path: str | Path | None = None,
        symbols: Sequence[str] | None = None,
        get_cycle_fn: GetCycleFn = get_cycle,
        require_pg_freeze: bool = True,
    ) -> None:
        self.raw_zone_path = raw_zone_path
        self.symbols = tuple(symbols) if symbols is not None else None
        self.get_cycle_fn = get_cycle_fn
        self.require_pg_freeze = require_pg_freeze
        self._last_readiness: CurrentCycleReadiness | None = None

    def get_current_cycle_readiness(self) -> CurrentCycleReadiness:
        try:
            selection = select_current_cycle(
                raw_zone_path=self.raw_zone_path,
                symbols=self.symbols,
            )
            evidence = selection.evidence
            if self.require_pg_freeze:
                try:
                    metadata = validate_pg_freeze_conditions(
                        selection.cycle_id,
                        get_cycle_fn=self.get_cycle_fn,
                    )
                except CurrentCycleSelectionError as exc:
                    raise CurrentCycleSelectionError(
                        exc.code,
                        exc.message,
                        cycle_id=exc.cycle_id,
                        evidence={
                            **selection.evidence,
                            "pg_freeze_condition": exc.evidence,
                        },
                    ) from exc
                evidence = {
                    **evidence,
                    "pg_freeze_condition": {
                        "status": metadata.status,
                        "selection_frozen_at": _isoformat_or_none(
                            metadata.selection_frozen_at
                        ),
                    },
                }
            readiness = CurrentCycleReadiness(
                ready=True,
                cycle_id=selection.cycle_id,
                reason=None,
                evidence=evidence,
            )
        except CurrentCycleSelectionError as exc:
            readiness = CurrentCycleReadiness(
                ready=False,
                cycle_id=exc.cycle_id or "unavailable",
                reason=str(exc),
                evidence=exc.evidence,
            )
        except Exception as exc:  # pragma: no cover - defensive adapter boundary
            readiness = CurrentCycleReadiness(
                ready=False,
                cycle_id="unavailable",
                reason=f"current_cycle_unavailable: {exc}",
                evidence={"error_type": type(exc).__name__},
            )
        self._last_readiness = readiness
        return readiness

    def get_data_readiness_signal(self) -> dict[str, object]:
        return self.get_current_cycle_readiness().as_data_readiness_signal()

    def get_readiness_signal(self) -> dict[str, object]:
        return self.get_data_readiness_signal()

    def get_data_readiness(self) -> dict[str, object]:
        return self.get_data_readiness_signal()

    @property
    def readiness_signal(self) -> dict[str, object]:
        return self.get_data_readiness_signal()

    @property
    def last_evidence(self) -> Mapping[str, object]:
        if self._last_readiness is None:
            return {}
        return self._last_readiness.evidence


def select_current_cycle(
    *,
    raw_zone_path: str | Path | None = None,
    symbols: Sequence[str] | None = None,
) -> CurrentCycleSelection:
    """Select the latest open trading day from already-ingested Tushare artifacts."""

    selected_symbols = resolve_current_cycle_symbols(symbols)
    reader = RawReader(raw_zone_path)
    raw_root = reader.raw_zone_path.expanduser()

    trade_artifacts = _latest_partition_artifacts(reader, _TRADE_CAL_DATASET)
    if not trade_artifacts:
        raise CurrentCycleSelectionError(
            "missing_input_artifact_refs",
            "no trade_cal Raw Zone artifacts are available",
            evidence=_base_evidence(raw_root, selected_symbols),
        )

    open_trade_dates: list[tuple[date, RawArtifact]] = []
    for artifact in trade_artifacts:
        for row in _read_parquet_rows(artifact):
            cal_date = _parse_date_value(row.get("cal_date"), "trade_cal.cal_date", artifact)
            if _is_open_trade_cal_row(row.get("is_open")):
                open_trade_dates.append((cal_date, artifact))

    if not open_trade_dates:
        raise CurrentCycleSelectionError(
            "no_open_trade_date",
            "trade_cal artifacts contain no open trading day",
            evidence={
                **_base_evidence(raw_root, selected_symbols),
                "trade_cal_artifact_refs": [
                    CurrentCycleArtifactRef.from_raw_artifact(artifact).as_dict()
                    for artifact in trade_artifacts
                ],
            },
        )

    trade_date = max(item[0] for item in open_trade_dates)
    cycle_id = cycle_id_for_date(trade_date)
    selected_trade_artifacts = _unique_artifacts(
        artifact for candidate_date, artifact in open_trade_dates if candidate_date == trade_date
    )

    daily_artifact = _latest_partition_artifact(reader, _DAILY_DATASET, trade_date)
    stock_basic_artifact = _latest_static_artifact(reader, _STOCK_BASIC_DATASET)
    missing_ref_datasets = [
        dataset
        for dataset, artifact in (
            (_DAILY_DATASET, daily_artifact),
            (_STOCK_BASIC_DATASET, stock_basic_artifact),
        )
        if artifact is None
    ]
    if missing_ref_datasets:
        raise CurrentCycleSelectionError(
            "missing_input_artifact_refs",
            "missing required current-cycle input artifact refs: "
            + ", ".join(missing_ref_datasets),
            cycle_id=cycle_id,
            evidence={
                **_base_evidence(raw_root, selected_symbols),
                "selected_trade_date": trade_date.isoformat(),
                "cycle_id": cycle_id,
                "missing_datasets": missing_ref_datasets,
            },
        )

    if daily_artifact is None or stock_basic_artifact is None:
        # Invariant: both artifacts must be non-None after the
        # `missing_input_artifact_refs` guard above. Previously enforced via
        # `assert ... is not None`; retained as explicit raise so the
        # invariant survives `python -O` (which strips assert).
        raise AssertionError(
            "invariant: daily_artifact and stock_basic_artifact must be non-None "
            "after the missing_input_artifact_refs guard"
        )
    _assert_artifact_ref(daily_artifact)
    _assert_artifact_ref(stock_basic_artifact)
    for artifact in selected_trade_artifacts:
        _assert_artifact_ref(artifact)

    daily_symbols = _symbols_with_daily_rows(daily_artifact, trade_date, selected_symbols)
    stock_basic_symbols = _symbols_with_stock_basic_rows(stock_basic_artifact, selected_symbols)
    missing_symbols = [
        symbol
        for symbol in selected_symbols
        if symbol not in daily_symbols or symbol not in stock_basic_symbols
    ]
    if missing_symbols:
        raise CurrentCycleSelectionError(
            "missing_symbol_data",
            "current-cycle artifacts do not contain all requested symbols: "
            + ", ".join(missing_symbols),
            cycle_id=cycle_id,
            evidence={
                **_base_evidence(raw_root, selected_symbols),
                "selected_trade_date": trade_date.isoformat(),
                "cycle_id": cycle_id,
                "missing_symbols": missing_symbols,
                "daily_symbols": sorted(daily_symbols),
                "stock_basic_symbols": sorted(stock_basic_symbols),
                "input_artifact_refs": _artifact_refs_as_dict(
                    {
                        _TRADE_CAL_DATASET: tuple(
                            CurrentCycleArtifactRef.from_raw_artifact(artifact)
                            for artifact in selected_trade_artifacts
                        ),
                        _DAILY_DATASET: (
                            CurrentCycleArtifactRef.from_raw_artifact(daily_artifact),
                        ),
                        _STOCK_BASIC_DATASET: (
                            CurrentCycleArtifactRef.from_raw_artifact(stock_basic_artifact),
                        ),
                    }
                ),
            },
        )

    refs = {
        _TRADE_CAL_DATASET: tuple(
            CurrentCycleArtifactRef.from_raw_artifact(artifact)
            for artifact in selected_trade_artifacts
        ),
        _DAILY_DATASET: (CurrentCycleArtifactRef.from_raw_artifact(daily_artifact),),
        _STOCK_BASIC_DATASET: (
            CurrentCycleArtifactRef.from_raw_artifact(stock_basic_artifact),
        ),
    }
    return CurrentCycleSelection(
        trade_date=trade_date,
        cycle_id=cycle_id,
        symbols=selected_symbols,
        input_tables=CURRENT_CYCLE_INPUT_TABLES,
        input_artifact_refs=refs,
        raw_zone_path=str(raw_root),
        scan_metadata={
            "source_id": _SOURCE_ID,
            "trade_cal_latest_partition_artifact_count": len(trade_artifacts),
            "daily_partition_date": trade_date.isoformat(),
            "stock_basic_partition_mode": "static_latest",
        },
    )


def validate_pg_freeze_conditions(
    cycle_id: str,
    *,
    get_cycle_fn: GetCycleFn = get_cycle,
) -> CycleMetadata:
    """Fail closed unless the existing PG cycle row is ready for freeze."""

    try:
        metadata = get_cycle_fn(cycle_id)
    except Exception as exc:
        raise CurrentCycleSelectionError(
            "pg_freeze_conditions_unavailable",
            f"cycle_metadata row is not available for {cycle_id}",
            cycle_id=cycle_id,
            evidence={"cycle_id": cycle_id},
        ) from exc

    if metadata.status != "pending" or metadata.selection_frozen_at is not None:
        raise CurrentCycleSelectionError(
            "pg_freeze_conditions_not_ready",
            (
                "cycle_metadata must be pending and not previously frozen: "
                f"{cycle_id} status={metadata.status!r}"
            ),
            cycle_id=cycle_id,
            evidence={
                "cycle_id": cycle_id,
                "status": metadata.status,
                "selection_frozen_at": _isoformat_or_none(metadata.selection_frozen_at),
            },
        )
    return metadata


def freeze_current_cycle_candidates(
    *,
    raw_zone_path: str | Path | None = None,
    symbols: Sequence[str] | None = None,
    get_cycle_fn: GetCycleFn = get_cycle,
    freeze_fn: FreezeCycleFn = freeze_cycle_candidates,
    candidate_id_loader: CandidateIdLoader | None = None,
) -> CurrentCycleFreezeResult:
    """Select current-cycle inputs, validate PG preconditions, then freeze candidates."""

    selection = select_current_cycle(raw_zone_path=raw_zone_path, symbols=symbols)
    try:
        validate_pg_freeze_conditions(selection.cycle_id, get_cycle_fn=get_cycle_fn)
    except CurrentCycleSelectionError as exc:
        raise CurrentCycleSelectionError(
            exc.code,
            exc.message,
            cycle_id=exc.cycle_id,
            evidence={
                **selection.evidence,
                "pg_freeze_condition": exc.evidence,
            },
        ) from exc
    try:
        metadata = freeze_fn(selection.cycle_id)
    except Exception as exc:
        raise CurrentCycleSelectionError(
            "pg_freeze_failed",
            f"freeze_cycle_candidates failed for {selection.cycle_id}",
            cycle_id=selection.cycle_id,
            evidence=selection.evidence,
        ) from exc

    loader = candidate_id_loader or load_frozen_candidate_ids
    try:
        candidate_ids = loader(selection.cycle_id)
    except Exception as exc:
        raise CurrentCycleSelectionError(
            "pg_frozen_candidate_ids_unavailable",
            f"frozen candidate IDs are not available for {selection.cycle_id}",
            cycle_id=selection.cycle_id,
            evidence=selection.evidence,
        ) from exc

    return CurrentCycleFreezeResult(
        selection=selection,
        cycle_metadata=metadata,
        frozen_candidate_ids=candidate_ids,
    )


def load_frozen_candidate_ids(cycle_id: str) -> tuple[int, ...]:
    """Return frozen candidate IDs ordered by candidate_queue ingest order."""

    from data_platform.cycle.repository import _create_engine, _text

    engine = _create_engine()
    try:
        with engine.connect() as connection:
            rows = (
                connection.execute(
                    _text(
                        """
                        SELECT selection.candidate_id
                        FROM data_platform.cycle_candidate_selection AS selection
                        JOIN data_platform.candidate_queue AS candidate_queue
                          ON candidate_queue.id = selection.candidate_id
                        WHERE selection.cycle_id = :cycle_id
                        ORDER BY candidate_queue.ingest_seq ASC
                        """
                    ),
                    {"cycle_id": cycle_id},
                )
                .scalars()
                .all()
            )
    finally:
        engine.dispose()
    return tuple(int(row) for row in rows)


def resolve_current_cycle_symbols(symbols: Sequence[str] | None = None) -> tuple[str, ...]:
    """Return explicit, env-overridden, or default current-cycle Tushare symbols."""

    if symbols is None:
        raw_symbols = os.environ.get(CURRENT_CYCLE_SYMBOLS_ENV)
        if raw_symbols:
            symbols = tuple(item.strip() for item in raw_symbols.split(","))
        else:
            symbols = DEFAULT_CURRENT_CYCLE_SYMBOLS

    cleaned: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized = str(symbol).strip().upper()
        if not normalized:
            continue
        if not _SYMBOL_PATTERN.fullmatch(normalized):
            raise CurrentCycleSelectionError(
                "invalid_current_cycle_symbol",
                f"invalid Tushare ts_code symbol: {symbol!r}",
                evidence={"symbols": [str(item) for item in symbols]},
            )
        if normalized not in seen:
            cleaned.append(normalized)
            seen.add(normalized)

    if not cleaned:
        raise CurrentCycleSelectionError(
            "missing_current_cycle_symbols",
            "at least one current-cycle symbol is required",
            evidence={"symbols": []},
        )
    return tuple(cleaned)


def _latest_partition_artifacts(
    reader: RawReader,
    dataset: str,
) -> tuple[RawArtifact, ...]:
    artifacts: list[RawArtifact] = []
    for partition_date in _manifest_partition_dates(reader.raw_zone_path, dataset):
        latest = _latest_partition_artifact(reader, dataset, partition_date)
        if latest is not None:
            artifacts.append(latest)
    artifacts.sort(key=_artifact_sort_key)
    return tuple(artifacts)


def _latest_partition_artifact(
    reader: RawReader,
    dataset: str,
    partition_date: date,
) -> RawArtifact | None:
    artifacts = reader.list_artifacts(_SOURCE_ID, dataset, partition_date)
    if not artifacts:
        return None
    latest = max(artifacts, key=_artifact_sort_key)
    _assert_artifact_ref(latest)
    return latest


def _latest_static_artifact(reader: RawReader, dataset: str) -> RawArtifact | None:
    artifacts = _latest_partition_artifacts(reader, dataset)
    if not artifacts:
        return None
    return max(artifacts, key=_artifact_sort_key)


def _manifest_partition_dates(raw_zone_path: Path, dataset: str) -> tuple[date, ...]:
    dataset_path = raw_zone_path.expanduser() / _SOURCE_ID / dataset
    dates: list[date] = []
    for manifest_path in sorted(dataset_path.glob("dt=*/_manifest.json")):
        partition_name = manifest_path.parent.name
        if not partition_name.startswith("dt="):
            continue
        raw_value = partition_name.removeprefix("dt=")
        try:
            dates.append(datetime.strptime(raw_value, "%Y%m%d").date())
        except ValueError as exc:
            raise CurrentCycleSelectionError(
                "invalid_raw_partition",
                f"invalid Raw Zone partition for {dataset}: {partition_name}",
                evidence={"dataset": dataset, "manifest_path": str(manifest_path)},
            ) from exc
    return tuple(dates)


def _read_parquet_rows(artifact: RawArtifact) -> tuple[Mapping[str, object], ...]:
    _assert_artifact_ref(artifact)
    try:
        rows = pq.read_table(artifact.path).to_pylist()
    except Exception as exc:
        raise CurrentCycleSelectionError(
            "input_artifact_read_failed",
            f"failed to read input artifact {artifact.path}",
            evidence={
                "artifact": CurrentCycleArtifactRef.from_raw_artifact(artifact).as_dict()
            },
        ) from exc
    return tuple(row for row in rows if isinstance(row, Mapping))


def _assert_artifact_ref(artifact: RawArtifact) -> None:
    if not artifact.run_id or not str(artifact.path):
        raise CurrentCycleSelectionError(
            "missing_input_artifact_refs",
            f"artifact ref is incomplete for {artifact.dataset}",
            evidence={"dataset": artifact.dataset, "partition_date": artifact.partition_date.isoformat()},
        )
    if not artifact.path.exists() or not artifact.path.is_file():
        raise CurrentCycleSelectionError(
            "missing_input_artifact_refs",
            f"artifact path is missing for {artifact.dataset}: {artifact.path}",
            evidence={
                "artifact": CurrentCycleArtifactRef.from_raw_artifact(artifact).as_dict()
            },
        )


def _parse_date_value(value: object, field_name: str, artifact: RawArtifact) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw_value = "" if value is None else str(value).strip()
    if not raw_value:
        raise CurrentCycleSelectionError(
            "invalid_input_date",
            f"{field_name} is required in {artifact.dataset}",
            evidence={
                "field_name": field_name,
                "artifact": CurrentCycleArtifactRef.from_raw_artifact(artifact).as_dict(),
            },
        )
    try:
        if re.fullmatch(r"[0-9]{8}", raw_value):
            return datetime.strptime(raw_value, "%Y%m%d").date()
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise CurrentCycleSelectionError(
            "invalid_input_date",
            f"{field_name} is not a valid date: {raw_value!r}",
            evidence={
                "field_name": field_name,
                "artifact": CurrentCycleArtifactRef.from_raw_artifact(artifact).as_dict(),
            },
        ) from exc


def _is_open_trade_cal_row(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "t", "y", "yes"}


def _symbols_with_daily_rows(
    artifact: RawArtifact,
    trade_date: date,
    symbols: Sequence[str],
) -> set[str]:
    requested = set(symbols)
    available: set[str] = set()
    for row in _read_parquet_rows(artifact):
        symbol = str(row.get("ts_code") or "").strip().upper()
        if symbol not in requested:
            continue
        row_trade_date = _parse_date_value(row.get("trade_date"), "daily.trade_date", artifact)
        if row_trade_date == trade_date:
            available.add(symbol)
    return available


def _symbols_with_stock_basic_rows(
    artifact: RawArtifact,
    symbols: Sequence[str],
) -> set[str]:
    requested = set(symbols)
    return {
        str(row.get("ts_code") or "").strip().upper()
        for row in _read_parquet_rows(artifact)
        if str(row.get("ts_code") or "").strip().upper() in requested
    }


def _unique_artifacts(artifacts: Iterable[RawArtifact]) -> tuple[RawArtifact, ...]:
    by_key: dict[tuple[str, str, date, str, str], RawArtifact] = {}
    for artifact in artifacts:
        key = (
            artifact.source_id,
            artifact.dataset,
            artifact.partition_date,
            artifact.run_id,
            str(artifact.path),
        )
        by_key[key] = artifact
    return tuple(sorted(by_key.values(), key=_artifact_sort_key))


def _artifact_sort_key(artifact: RawArtifact) -> tuple[datetime, date, str]:
    return (artifact.written_at, artifact.partition_date, artifact.run_id)


def _artifact_refs_as_dict(
    refs: Mapping[str, Sequence[CurrentCycleArtifactRef]],
) -> dict[str, list[dict[str, object]]]:
    return {
        dataset: [artifact_ref.as_dict() for artifact_ref in artifact_refs]
        for dataset, artifact_refs in refs.items()
    }


def _base_evidence(raw_root: Path, symbols: Sequence[str]) -> dict[str, object]:
    return {
        "raw_zone_path": str(raw_root),
        "symbols": list(symbols),
        "input_tables": list(CURRENT_CYCLE_INPUT_TABLES),
    }


def _cutoff_metadata(metadata: CycleMetadata) -> dict[str, object]:
    return {
        "status": metadata.status,
        "cutoff_submitted_at": _isoformat_or_none(metadata.cutoff_submitted_at),
        "cutoff_ingest_seq": metadata.cutoff_ingest_seq,
        "candidate_count": metadata.candidate_count,
        "selection_frozen_at": _isoformat_or_none(metadata.selection_frozen_at),
        "cycle_created_at": metadata.created_at.isoformat(),
        "cycle_updated_at": metadata.updated_at.isoformat(),
    }


def _isoformat_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


__all__ = [
    "CURRENT_CYCLE_INPUT_TABLES",
    "CURRENT_CYCLE_SYMBOLS_ENV",
    "DATA_READINESS_FAILED_NODE",
    "DEFAULT_CURRENT_CYCLE_SYMBOLS",
    "CurrentCycleArtifactRef",
    "CurrentCycleFreezeResult",
    "CurrentCycleReadiness",
    "CurrentCycleReadinessProvider",
    "CurrentCycleSelection",
    "CurrentCycleSelectionError",
    "freeze_current_cycle_candidates",
    "load_frozen_candidate_ids",
    "resolve_current_cycle_symbols",
    "select_current_cycle",
    "validate_pg_freeze_conditions",
]
