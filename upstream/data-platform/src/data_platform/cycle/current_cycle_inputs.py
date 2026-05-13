"""Provider-neutral current-cycle canonical input loader."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Final

import pyarrow as pa  # type: ignore[import-untyped]

from data_platform.cycle.models import _cycle_date_from_id
from data_platform.serving import reader as canonical_reader
from data_platform.serving.canonical_datasets import (
    canonical_alias_column_for_dataset,
    canonical_table_for_dataset,
    canonical_table_identifier_for_dataset,
)


PRICE_BAR_DATASET: Final[str] = "price_bar"
SECURITY_MASTER_DATASET: Final[str] = "security_master"
REQUIRED_INPUT_DATASETS: Final[tuple[str, str]] = (
    PRICE_BAR_DATASET,
    SECURITY_MASTER_DATASET,
)
CANONICAL_ENTITY_TABLE: Final[str] = "canonical_entity"
ENTITY_ALIAS_TABLE: Final[str] = "entity_alias"
DAILY_FREQUENCY: Final[str] = "daily"

CurrentCycleInputRow = dict[str, object]
SnapshotSpec = Mapping[str, int]


class CurrentCycleInputsUnavailable(RuntimeError):
    """Raised when current-cycle canonical inputs cannot be proven complete."""

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


def current_cycle_inputs(
    cycle_id: str,
    selection_ref: str,
    candidate_ids: Sequence[str | int],
    as_of_snapshot: SnapshotSpec | None = None,
) -> tuple[CurrentCycleInputRow, ...]:
    """Load provider-neutral canonical rows for one frozen current cycle.

    The loader reads only canonical Iceberg/DuckDB serving tables. Candidate
    identifiers may be canonical entity ids or aliases resolvable through
    canonical.entity_alias.
    """

    trade_date = _cycle_date_from_id(cycle_id)
    normalized_selection_ref = _validate_selection_ref(selection_ref)
    normalized_candidates = _validate_candidate_ids(candidate_ids)
    snapshot_spec = _normalize_snapshot_spec(as_of_snapshot)
    snapshot_ids = _canonical_snapshot_ids(snapshot_spec, cycle_id=cycle_id)

    try:
        canonical_entities = _records(
            _read_canonical_table(
                CANONICAL_ENTITY_TABLE,
                columns=["canonical_entity_id"],
                snapshot_spec=snapshot_spec,
            )
        )
        entity_aliases = _records(
            _read_canonical_table(
                ENTITY_ALIAS_TABLE,
                columns=["alias", "canonical_entity_id"],
                snapshot_spec=snapshot_spec,
            )
        )
        security_alias_column = canonical_alias_column_for_dataset(SECURITY_MASTER_DATASET)
        price_alias_column = canonical_alias_column_for_dataset(PRICE_BAR_DATASET)
        security_rows = _records(
            _read_dataset(
                SECURITY_MASTER_DATASET,
                columns=[security_alias_column, "market", "industry"],
                snapshot_spec=snapshot_spec,
            )
        )
        price_rows = _records(
            _read_dataset(
                PRICE_BAR_DATASET,
                columns=[
                    price_alias_column,
                    "trade_date",
                    "freq",
                    "close",
                    "pre_close",
                    "pct_chg",
                    "vol",
                    "amount",
                ],
                snapshot_spec=snapshot_spec,
            )
        )
    except Exception as exc:
        raise CurrentCycleInputsUnavailable(
            "canonical_read_failed",
            "failed to read required canonical current-cycle inputs",
            cycle_id=cycle_id,
            evidence={"error_type": type(exc).__name__},
        ) from exc

    resolver = _EntityResolver(canonical_entities, entity_aliases, cycle_id=cycle_id)
    security_by_alias = _security_rows_by_alias(
        security_rows, alias_column=security_alias_column
    )
    price_by_alias = _price_rows_by_alias(
        price_rows,
        trade_date=trade_date,
        alias_column=price_alias_column,
    )

    rows: list[CurrentCycleInputRow] = []
    missing_rows: list[dict[str, object]] = []
    for candidate_id in normalized_candidates:
        resolved = resolver.resolve(candidate_id)
        selected_alias = _select_candidate_alias(
            candidate_id=resolved.candidate_id,
            aliases=resolved.aliases,
            security_by_alias=security_by_alias,
            price_by_alias=price_by_alias,
        )
        if selected_alias is None:
            missing_rows.append(
                {
                    "candidate_id": resolved.candidate_id,
                    "entity_id": resolved.entity_id,
                    "reason": "missing canonical candidate row",
                }
            )
            continue

        security = security_by_alias.get(selected_alias)
        price = price_by_alias.get(selected_alias)
        if security is None or price is None:
            missing_rows.append(
                {
                    "candidate_id": resolved.candidate_id,
                    "entity_id": resolved.entity_id,
                    "reason": "missing canonical security or price row",
                }
            )
            continue

        row = _current_cycle_row(
            cycle_id=cycle_id,
            selection_ref=normalized_selection_ref,
            candidate_id=resolved.candidate_id,
            entity_id=resolved.entity_id,
            trade_date=trade_date,
            price=price,
            security=security,
            snapshot_ids=snapshot_ids,
        )
        rows.append(row)

    if missing_rows:
        raise CurrentCycleInputsUnavailable(
            "canonical_candidate_rows_missing",
            "missing canonical rows for current-cycle candidates",
            cycle_id=cycle_id,
            evidence={"missing_rows": missing_rows},
        )

    return tuple(rows)


def load_current_cycle_inputs(
    cycle_id: str,
    selection_ref: str,
    candidate_ids: Sequence[str | int],
    as_of_snapshot: SnapshotSpec | None = None,
) -> tuple[CurrentCycleInputRow, ...]:
    """Alias for callers that prefer a verb-style loader name."""

    return current_cycle_inputs(
        cycle_id,
        selection_ref,
        candidate_ids,
        as_of_snapshot,
    )


class _ResolvedCandidate:
    def __init__(
        self,
        *,
        candidate_id: str,
        entity_id: str,
        aliases: tuple[str, ...],
    ) -> None:
        self.candidate_id = candidate_id
        self.entity_id = entity_id
        self.aliases = aliases


class _EntityResolver:
    def __init__(
        self,
        entity_rows: Sequence[Mapping[str, object]],
        alias_rows: Sequence[Mapping[str, object]],
        *,
        cycle_id: str,
    ) -> None:
        self._cycle_id = cycle_id
        self._entity_ids = {
            str(row["canonical_entity_id"]).strip()
            for row in entity_rows
            if str(row.get("canonical_entity_id", "")).strip()
        }
        self._alias_to_entity: dict[str, str] = {}
        self._entity_to_aliases: dict[str, list[str]] = {}
        for row in alias_rows:
            alias = str(row.get("alias", "")).strip()
            entity_id = str(row.get("canonical_entity_id", "")).strip()
            if not alias or not entity_id:
                continue
            self._alias_to_entity[alias] = entity_id
            self._entity_to_aliases.setdefault(entity_id, []).append(alias)

    def resolve(self, candidate_id: str) -> _ResolvedCandidate:
        if candidate_id in self._entity_ids:
            aliases = tuple(sorted(set(self._entity_to_aliases.get(candidate_id, []))))
            if not aliases:
                raise CurrentCycleInputsUnavailable(
                    "canonical_entity_alias_missing",
                    "canonical entity has no alias for current-cycle inputs",
                    cycle_id=self._cycle_id,
                    evidence={"candidate_id": candidate_id, "entity_id": candidate_id},
                )
            return _ResolvedCandidate(
                candidate_id=candidate_id,
                entity_id=candidate_id,
                aliases=aliases,
            )

        entity_id = self._alias_to_entity.get(candidate_id)
        if entity_id is None or entity_id not in self._entity_ids:
            raise CurrentCycleInputsUnavailable(
                "canonical_entity_missing",
                "candidate cannot be resolved to a canonical entity row",
                cycle_id=self._cycle_id,
                evidence={"candidate_id": candidate_id},
            )
        aliases = tuple(
            sorted({candidate_id, *self._entity_to_aliases.get(entity_id, [])})
        )
        return _ResolvedCandidate(
            candidate_id=candidate_id,
            entity_id=entity_id,
            aliases=aliases,
        )


def _read_dataset(
    dataset_id: str,
    *,
    columns: list[str],
    snapshot_spec: SnapshotSpec,
) -> pa.Table:
    snapshot_id = _snapshot_id_for_key(
        snapshot_spec,
        dataset_id,
        canonical_table_for_dataset(dataset_id),
        canonical_table_identifier_for_dataset(dataset_id),
    )
    if snapshot_id is not None:
        return canonical_reader.read_canonical_dataset_snapshot(dataset_id, snapshot_id).select(
            columns
        )
    return canonical_reader.read_canonical_dataset(dataset_id, columns=columns)


def _read_canonical_table(
    table: str,
    *,
    columns: list[str],
    snapshot_spec: SnapshotSpec,
) -> pa.Table:
    snapshot_id = _snapshot_id_for_key(
        snapshot_spec,
        table,
        f"canonical.{table}",
        table,
    )
    if snapshot_id is not None:
        return canonical_reader.read_iceberg_snapshot(
            f"canonical.{table}",
            snapshot_id,
        ).select(columns)
    return canonical_reader.read_canonical(table, columns=columns)


def _canonical_snapshot_ids(
    snapshot_spec: SnapshotSpec,
    *,
    cycle_id: str,
) -> dict[str, int]:
    if snapshot_spec:
        missing = [
            dataset_id
            for dataset_id in REQUIRED_INPUT_DATASETS
            if _snapshot_id_for_key(
                snapshot_spec,
                dataset_id,
                canonical_table_for_dataset(dataset_id),
                canonical_table_identifier_for_dataset(dataset_id),
            )
            is None
        ]
        if missing:
            raise CurrentCycleInputsUnavailable(
                "canonical_snapshot_missing",
                "as_of_snapshot is missing required canonical dataset snapshots",
                cycle_id=cycle_id,
                evidence={"missing_datasets": missing},
            )
        return {
            dataset_id: _required_snapshot_id(snapshot_spec, dataset_id)
            for dataset_id in REQUIRED_INPUT_DATASETS
        }

    try:
        return {
            dataset_id: canonical_reader.canonical_snapshot_id_for_dataset(dataset_id)
            for dataset_id in REQUIRED_INPUT_DATASETS
        }
    except Exception as exc:
        raise CurrentCycleInputsUnavailable(
            "canonical_snapshot_missing",
            "required canonical mart snapshot is unavailable",
            cycle_id=cycle_id,
            evidence={"error_type": type(exc).__name__},
        ) from exc


def _snapshot_id_for_key(
    snapshot_spec: SnapshotSpec,
    *keys: str,
) -> int | None:
    for key in keys:
        snapshot_id = snapshot_spec.get(key)
        if snapshot_id is not None:
            return snapshot_id
    return None


def _required_snapshot_id(snapshot_spec: SnapshotSpec, dataset_id: str) -> int:
    snapshot_id = _snapshot_id_for_key(
        snapshot_spec,
        dataset_id,
        canonical_table_for_dataset(dataset_id),
        canonical_table_identifier_for_dataset(dataset_id),
    )
    if snapshot_id is None:
        msg = f"missing required canonical snapshot for {dataset_id}"
        raise ValueError(msg)
    return snapshot_id


def _normalize_snapshot_spec(
    as_of_snapshot: SnapshotSpec | None,
) -> SnapshotSpec:
    if as_of_snapshot is None:
        return {}
    normalized: dict[str, int] = {}
    for key, value in as_of_snapshot.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            msg = f"snapshot id must be a positive integer: {value!r}"
            raise ValueError(msg)
        normalized[str(key)] = value
    return normalized


def _records(table: pa.Table) -> list[dict[str, object]]:
    return [dict(row) for row in table.to_pylist()]


def _security_rows_by_alias(
    rows: Sequence[Mapping[str, object]],
    *,
    alias_column: str = "ts_code",
) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    for row in rows:
        alias = str(row.get(alias_column, "")).strip()
        if alias:
            result[alias] = row
    return result


def _price_rows_by_alias(
    rows: Sequence[Mapping[str, object]],
    *,
    trade_date: date,
    alias_column: str = "ts_code",
) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    for row in rows:
        alias = str(row.get(alias_column, "")).strip()
        if not alias:
            continue
        if _date_value(row.get("trade_date")) != trade_date:
            continue
        if str(row.get("freq", "")).strip().lower() != DAILY_FREQUENCY:
            continue
        result[alias] = row
    return result


def _select_candidate_alias(
    *,
    candidate_id: str,
    aliases: Sequence[str],
    security_by_alias: Mapping[str, Mapping[str, object]],
    price_by_alias: Mapping[str, Mapping[str, object]],
) -> str | None:
    ordered_aliases = (candidate_id, *tuple(alias for alias in aliases if alias != candidate_id))
    for alias in ordered_aliases:
        if alias in security_by_alias and alias in price_by_alias:
            return alias
    return None


def _current_cycle_row(
    *,
    cycle_id: str,
    selection_ref: str,
    candidate_id: str,
    entity_id: str,
    trade_date: date,
    price: Mapping[str, object],
    security: Mapping[str, object],
    snapshot_ids: Mapping[str, int],
) -> CurrentCycleInputRow:
    close = _float_value(price.get("close"))
    pre_close = _float_value(price.get("pre_close"))
    return_1d = _return_1d(price.get("pct_chg"), close=close, pre_close=pre_close)
    canonical_dataset_refs = list(REQUIRED_INPUT_DATASETS)
    canonical_snapshot_ids = {
        dataset_id: int(snapshot_ids[dataset_id]) for dataset_id in canonical_dataset_refs
    }
    lineage_refs = [
        f"cycle:{cycle_id}",
        f"selection:{selection_ref}",
        f"candidate:{candidate_id}",
        *[
            f"canonical:{dataset_id}@{canonical_snapshot_ids[dataset_id]}"
            for dataset_id in canonical_dataset_refs
        ],
    ]
    return {
        "entity_id": entity_id,
        "trade_date": trade_date.isoformat(),
        "close": close,
        "pre_close": pre_close,
        "return_1d": return_1d,
        "volume": _float_value(price.get("vol")),
        "amount": _float_value(price.get("amount")),
        "market": _optional_text(security.get("market")),
        "industry": _optional_text(security.get("industry")),
        "canonical_dataset_refs": canonical_dataset_refs,
        "canonical_snapshot_ids": canonical_snapshot_ids,
        "lineage_refs": lineage_refs,
    }


def _return_1d(
    pct_chg: object,
    *,
    close: float | None,
    pre_close: float | None,
) -> float | None:
    pct_value = _float_value(pct_chg)
    if pct_value is not None:
        return pct_value / 100.0
    if close is None or pre_close is None or pre_close == 0.0:
        return None
    return (close - pre_close) / pre_close


def _float_value(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        msg = f"numeric field must not be boolean: {value!r}"
        raise TypeError(msg)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    return None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date_value(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        raw = value.strip()
        if "-" in raw:
            return date.fromisoformat(raw)
        return datetime.strptime(raw, "%Y%m%d").date()
    return None


def _validate_selection_ref(selection_ref: str) -> str:
    if not isinstance(selection_ref, str) or not selection_ref.strip():
        msg = "selection_ref must be a non-empty string"
        raise ValueError(msg)
    return selection_ref.strip()


def _validate_candidate_ids(candidate_ids: Sequence[str | int]) -> tuple[str, ...]:
    if isinstance(candidate_ids, str) or not isinstance(candidate_ids, Sequence):
        msg = "candidate_ids must be a non-empty sequence"
        raise TypeError(msg)
    normalized = tuple(str(candidate_id).strip() for candidate_id in candidate_ids)
    if not normalized or any(not candidate_id for candidate_id in normalized):
        msg = "candidate_ids must be a non-empty sequence of non-empty values"
        raise ValueError(msg)
    duplicates = sorted(
        {
            candidate_id
            for candidate_id in normalized
            if normalized.count(candidate_id) > 1
        }
    )
    if duplicates:
        msg = "candidate_ids must be unique: "
        raise ValueError(msg + ", ".join(duplicates))
    return normalized


__all__ = [
    "CurrentCycleInputRow",
    "CurrentCycleInputsUnavailable",
    "REQUIRED_INPUT_DATASETS",
    "current_cycle_inputs",
    "load_current_cycle_inputs",
]
