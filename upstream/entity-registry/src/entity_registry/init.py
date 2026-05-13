"""Initialization pipeline from stock_basic canonical snapshots."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

from pydantic import BaseModel, field_validator

from entity_registry.aliases import AliasManager, generate_aliases_from_stock_basic
from entity_registry.core import (
    CanonicalEntity,
    EntityAlias,
    EntityStatus,
    EntityType,
    generate_stock_entity_id,
)
from entity_registry.fuzzy import FuzzyMatcher
from entity_registry.llm_client import ReasonerRuntimeClient
from entity_registry.ner import NERExtractor
from entity_registry.storage import (
    AliasRepository,
    EntityRepository,
    InMemoryReferenceRepository,
    InMemoryResolutionAuditReferenceRepository,
    InMemoryResolutionCaseRepository,
    ReferenceRepository,
    ResolutionCaseRepository,
)


class StockBasicRecord(BaseModel):
    """Input row from the data-platform stock_basic canonical table."""

    ts_code: str
    symbol: str
    name: str
    fullname: str | None = None
    enname: str | None = None
    cnspell: str | None = None
    market: str
    exchange: str
    list_status: str
    list_date: str | None = None
    is_hs: str | None = None

    @field_validator("ts_code", "symbol", "name", "market", "exchange", "list_status")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("required stock_basic text fields must not be empty")
        return cleaned

    @field_validator("fullname", "enname", "cnspell", "list_date", "is_hs", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)

        cleaned = value.strip()
        return cleaned or None


class InitializationResult(BaseModel):
    """Summary counters for one stock_basic initialization run."""

    entities_created: int
    aliases_created: int
    cross_listing_groups: int
    errors: list[str]


class InitializationError(RuntimeError):
    """Raised when initialization finishes with row-level errors."""

    def __init__(self, result: InitializationResult) -> None:
        self.result = result
        self.errors = result.errors
        super().__init__(
            "stock_basic initialization failed: " + "; ".join(result.errors),
        )


class RepositoryNotConfiguredError(RuntimeError):
    """Raised when the public API is used before repositories are configured."""


class StockBasicSnapshotReader(Protocol):
    """Reader contract for stock_basic snapshots used by initialization."""

    def read(self, snapshot_ref: str) -> list[StockBasicRecord]: ...


class DataPlatformStockBasicReader:
    """Read stock_basic rows from the data-platform canonical table."""

    def __init__(
        self,
        *,
        active_only: bool = False,
        canonical_loader: Callable[[bool], Any] | None = None,
    ) -> None:
        self._active_only = active_only
        self._canonical_loader = canonical_loader

    def read(self, snapshot_ref: str) -> list[StockBasicRecord]:
        table = self._load_canonical_stock_basic()
        rows = _canonical_table_to_rows(table)
        payload = [
            _stock_basic_payload_from_canonical_row(row, index, snapshot_ref)
            for index, row in enumerate(rows)
        ]
        return _validate_record_payload(payload, snapshot_ref)

    def _load_canonical_stock_basic(self) -> Any:
        if self._canonical_loader is not None:
            return self._canonical_loader(self._active_only)

        try:
            from data_platform.serving.reader import get_canonical_stock_basic
        except ImportError as exc:
            raise RuntimeError(
                "DataPlatformStockBasicReader requires project-ult-data-platform "
                "on PYTHONPATH; use FileStockBasicSnapshotReader for fixture/dev snapshots"
            ) from exc

        return get_canonical_stock_basic(active_only=self._active_only)


class FileStockBasicSnapshotReader:
    """Fixture/dev adapter for local JSON or CSV stock_basic snapshots."""

    def read(self, snapshot_ref: str) -> list[StockBasicRecord]:
        path = Path(snapshot_ref)
        if not path.exists():
            raise FileNotFoundError(snapshot_ref)

        suffix = path.suffix.lower()
        if suffix == ".json":
            payload = _load_json_payload(path)
        elif suffix == ".csv":
            payload = _load_csv_payload(path)
        else:
            raise ValueError("snapshot_ref must point to a JSON or CSV file")

        return _validate_record_payload(payload, snapshot_ref)


def load_stock_basic_records(snapshot_ref: str) -> list[StockBasicRecord]:
    """Load stock_basic records with the fixture/dev JSON/CSV adapter."""

    return FileStockBasicSnapshotReader().read(snapshot_ref)


def detect_cross_listing_groups(records: list[StockBasicRecord]) -> dict[str, str]:
    """Detect A+H listings and return a ts_code to cross-listing group mapping."""

    records_by_company: dict[str, list[StockBasicRecord]] = {}
    for record in records:
        key = _cross_listing_company_key(record)
        if key is None:
            continue
        records_by_company.setdefault(key, []).append(record)

    groups: dict[str, str] = {}
    for company_key, company_records in records_by_company.items():
        if not _has_cross_listing_shape(company_records):
            continue

        group_id = _build_cross_listing_group_id(company_key)
        for record in company_records:
            groups[record.ts_code] = group_id

    return groups


@dataclass(frozen=True, slots=True)
class _RepositoryContext:
    entity_repo: EntityRepository
    alias_repo: AliasRepository
    reference_repo: ReferenceRepository | None = None
    case_repo: ResolutionCaseRepository | None = None
    fuzzy_matcher: FuzzyMatcher | None = None
    ner_extractor: NERExtractor | None = None
    reasoner_client: ReasonerRuntimeClient | None = None


_DEFAULT_REPOSITORY_CONTEXT: _RepositoryContext | None = None
_DEFAULT_REPOSITORY_CONTEXT_LOCK = Lock()


@dataclass(frozen=True, slots=True)
class _PreparedInitialization:
    entities: tuple[CanonicalEntity, ...]
    aliases: tuple[EntityAlias, ...]
    cross_listing_groups: int
    errors: tuple[str, ...]


def configure_default_repositories(
    entity_repo: EntityRepository,
    alias_repo: AliasRepository,
    *,
    reference_repo: ReferenceRepository | None = None,
    case_repo: ResolutionCaseRepository | None = None,
    fuzzy_matcher: FuzzyMatcher | None = None,
    ner_extractor: NERExtractor | None = None,
    reasoner_client: ReasonerRuntimeClient | None = None,
) -> None:
    """Configure repositories used by public package-level APIs.

    Entity and alias repositories are enough for lookup/profile APIs. Resolution
    APIs require explicit reference and case repositories for durable audit writes.
    """

    global _DEFAULT_REPOSITORY_CONTEXT
    context = _RepositoryContext(
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        reference_repo=reference_repo,
        case_repo=case_repo,
        fuzzy_matcher=fuzzy_matcher,
        ner_extractor=ner_extractor,
        reasoner_client=reasoner_client,
    )
    with _DEFAULT_REPOSITORY_CONTEXT_LOCK:
        _DEFAULT_REPOSITORY_CONTEXT = context


def configure_default_in_memory_audit_repositories(
    entity_repo: EntityRepository,
    alias_repo: AliasRepository,
    *,
    fuzzy_matcher: FuzzyMatcher | None = None,
    ner_extractor: NERExtractor | None = None,
    reasoner_client: ReasonerRuntimeClient | None = None,
) -> tuple[InMemoryReferenceRepository, InMemoryResolutionCaseRepository]:
    """Configure default repositories with explicit in-memory audit sinks.

    This helper is for tests and local workflows only. Production resolution
    paths should pass durable audit repositories to configure_default_repositories().
    """

    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = InMemoryResolutionAuditReferenceRepository(case_repo)
    configure_default_repositories(
        entity_repo,
        alias_repo,
        reference_repo=reference_repo,
        case_repo=case_repo,
        fuzzy_matcher=fuzzy_matcher,
        ner_extractor=ner_extractor,
        reasoner_client=reasoner_client,
    )
    return reference_repo, case_repo


def reset_default_repositories() -> None:
    """Clear configured repositories for test isolation and fail-fast defaults."""

    global _DEFAULT_REPOSITORY_CONTEXT
    with _DEFAULT_REPOSITORY_CONTEXT_LOCK:
        _DEFAULT_REPOSITORY_CONTEXT = None


def get_default_repositories() -> tuple[EntityRepository, AliasRepository]:
    """Return the configured default repository pair from one context snapshot."""

    context = _get_default_repository_context()
    return context.entity_repo, context.alias_repo


def _get_default_repository_context() -> _RepositoryContext:
    """Return the configured repository context from one atomic snapshot."""

    with _DEFAULT_REPOSITORY_CONTEXT_LOCK:
        context = _DEFAULT_REPOSITORY_CONTEXT

    if context is None:
        raise RepositoryNotConfiguredError(
            "entity-registry repositories are not configured; "
            "call configure_default_repositories() before using public APIs",
        )
    return context


def get_default_resolution_repositories() -> tuple[
    EntityRepository,
    AliasRepository,
    ReferenceRepository,
    ResolutionCaseRepository,
]:
    """Return all repositories used by public resolution APIs."""

    context = _get_default_repository_context()
    if context.reference_repo is None or context.case_repo is None:
        raise RepositoryNotConfiguredError(
            "resolution audit repositories are not configured; "
            "call configure_default_repositories(..., reference_repo=..., "
            "case_repo=...) before using public resolution APIs, or use "
            "configure_default_in_memory_audit_repositories() for tests/local workflows",
        )
    return (
        context.entity_repo,
        context.alias_repo,
        context.reference_repo,
        context.case_repo,
    )


def get_default_reasoner_client() -> ReasonerRuntimeClient | None:
    """Return the configured reasoner-runtime client, if one was provided."""

    return _get_default_repository_context().reasoner_client


def get_default_entity_repository() -> EntityRepository:
    """Return the configured default entity repository."""

    entity_repo, _ = get_default_repositories()
    return entity_repo


def get_default_alias_repository() -> AliasRepository:
    """Return the configured default alias repository."""

    _, alias_repo = get_default_repositories()
    return alias_repo


def get_default_reference_repository() -> ReferenceRepository:
    """Return the configured default reference repository."""

    context = _get_default_repository_context()
    if context.reference_repo is None:
        raise RepositoryNotConfiguredError(
            "reference audit repository is not configured; "
            "call configure_default_repositories(..., reference_repo=...) before "
            "registering unresolved references, or use "
            "configure_default_in_memory_audit_repositories() for tests/local workflows",
        )
    return context.reference_repo


def get_default_resolution_case_repository() -> ResolutionCaseRepository:
    """Return the configured default resolution case repository."""

    context = _get_default_repository_context()
    if context.case_repo is None:
        raise RepositoryNotConfiguredError(
            "resolution case audit repository is not configured; "
            "call configure_default_repositories(..., case_repo=...) before "
            "recording resolution cases, or use "
            "configure_default_in_memory_audit_repositories() for tests/local workflows",
        )
    return context.case_repo


def initialize_from_stock_basic(snapshot_ref: str) -> None:
    """Initialize canonical stock entities and aliases from a stock_basic snapshot."""

    entity_repo, alias_repo = get_default_repositories()
    result = initialize_from_stock_basic_into(
        snapshot_ref,
        entity_repo,
        alias_repo,
        stock_basic_reader=_default_reader_for_snapshot(snapshot_ref),
    )
    if result.errors:
        raise InitializationError(result)


def initialize_from_stock_basic_into(
    snapshot_ref: str,
    entity_repo: EntityRepository,
    alias_repo: AliasRepository,
    stock_basic_reader: StockBasicSnapshotReader | None = None,
) -> InitializationResult:
    """Initialize stock entities into explicit repositories and return counters."""

    reader = (
        DataPlatformStockBasicReader()
        if stock_basic_reader is None
        else stock_basic_reader
    )
    prepared = _prepare_initialization_records(reader.read(snapshot_ref))
    if prepared.errors:
        return InitializationResult(
            entities_created=0,
            aliases_created=0,
            cross_listing_groups=prepared.cross_listing_groups,
            errors=list(prepared.errors),
        )

    alias_manager = AliasManager(alias_repo)
    entities_created = 0
    for entity in prepared.entities:
        if entity_repo.save_if_absent(entity):
            entities_created += 1

    aliases_created = alias_manager.add_aliases_batch(list(prepared.aliases))

    return InitializationResult(
        entities_created=entities_created,
        aliases_created=aliases_created,
        cross_listing_groups=prepared.cross_listing_groups,
        errors=[],
    )


def _prepare_initialization_records(
    records: list[StockBasicRecord],
) -> _PreparedInitialization:
    cross_listing_groups = detect_cross_listing_groups(records)
    entities: list[CanonicalEntity] = []
    aliases: list[EntityAlias] = []
    errors: list[str] = []

    for record in records:
        try:
            canonical_entity_id = generate_stock_entity_id(record.ts_code)
            entity = CanonicalEntity(
                canonical_entity_id=canonical_entity_id,
                entity_type=EntityType.STOCK,
                display_name=record.name,
                status=_entity_status_from_list_status(record.list_status),
                anchor_code=record.ts_code,
                cross_listing_group=cross_listing_groups.get(record.ts_code),
            )
            record_aliases = generate_aliases_from_stock_basic(
                record,
                canonical_entity_id,
            )
        except ValueError as exc:
            errors.append(f"{record.ts_code}: {exc}")
            continue

        entities.append(entity)
        aliases.extend(record_aliases)

    return _PreparedInitialization(
        entities=tuple(() if errors else entities),
        aliases=tuple(() if errors else aliases),
        cross_listing_groups=len(set(cross_listing_groups.values())),
        errors=tuple(errors),
    )


def _default_reader_for_snapshot(snapshot_ref: str) -> StockBasicSnapshotReader:
    if Path(snapshot_ref).exists():
        return FileStockBasicSnapshotReader()
    return DataPlatformStockBasicReader()


def _load_json_payload(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as file_obj:
            return json.load(file_obj)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON stock_basic snapshot: {exc}") from exc


def _load_csv_payload(path: Path) -> list[dict[str, str | None]]:
    with path.open(newline="", encoding="utf-8") as file_obj:
        reader = csv.DictReader(file_obj)
        if reader.fieldnames is None:
            return []
        return list(reader)


def _validate_record_payload(payload: Any, snapshot_ref: str) -> list[StockBasicRecord]:
    if isinstance(payload, dict):
        if isinstance(payload.get("records"), list):
            payload = payload["records"]
        elif isinstance(payload.get("data"), list):
            payload = payload["data"]
        else:
            raise ValueError("stock_basic JSON object must contain a records or data list")

    if not isinstance(payload, list):
        raise ValueError("stock_basic snapshot must contain a list of records")

    records: list[StockBasicRecord] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"stock_basic record at index {index} is not an object")
        try:
            records.append(StockBasicRecord.model_validate(item))
        except ValueError as exc:
            raise ValueError(
                f"invalid stock_basic record at index {index} in {snapshot_ref}: {exc}"
            ) from exc

    return records


def _canonical_table_to_rows(table: Any) -> list[Mapping[str, Any]]:
    if hasattr(table, "to_pylist"):
        rows = table.to_pylist()
    elif hasattr(table, "to_pydict"):
        rows = _rows_from_column_mapping(table.to_pydict())
    elif isinstance(table, list):
        rows = table
    else:
        raise TypeError("data-platform stock_basic reader must return a table-like object")

    if not isinstance(rows, list):
        rows = list(rows)

    normalized_rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"canonical stock_basic row at index {index} is not an object")
        normalized_rows.append(row)

    return normalized_rows


def _rows_from_column_mapping(columns: Any) -> list[dict[str, Any]]:
    if not isinstance(columns, Mapping):
        raise ValueError("canonical stock_basic column payload must be a mapping")

    materialized_columns = {
        str(name): _column_to_list(values)
        for name, values in columns.items()
    }
    if not materialized_columns:
        return []

    row_count = len(next(iter(materialized_columns.values())))
    if any(len(values) != row_count for values in materialized_columns.values()):
        raise ValueError("canonical stock_basic columns have mismatched lengths")

    return [
        {
            name: values[index]
            for name, values in materialized_columns.items()
        }
        for index in range(row_count)
    ]


def _column_to_list(values: Any) -> list[Any]:
    if hasattr(values, "to_pylist"):
        return list(values.to_pylist())
    return list(values)


def _stock_basic_payload_from_canonical_row(
    row: Mapping[str, Any],
    index: int,
    snapshot_ref: str,
) -> dict[str, Any]:
    try:
        ts_code = _required_canonical_text(row, "ts_code")
        return {
            "ts_code": ts_code,
            "symbol": row.get("symbol") or _symbol_from_ts_code(ts_code),
            "name": _required_canonical_text(row, "name"),
            "fullname": row.get("fullname"),
            "enname": row.get("enname"),
            "cnspell": row.get("cnspell"),
            "market": _required_canonical_text(row, "market"),
            "exchange": row.get("exchange") or _exchange_from_ts_code(ts_code),
            "list_status": row.get("list_status") or _list_status_from_is_active(row),
            "list_date": _canonical_date_text(row.get("list_date")),
            "is_hs": row.get("is_hs"),
        }
    except ValueError as exc:
        raise ValueError(
            f"invalid canonical stock_basic row at index {index} in {snapshot_ref}: {exc}"
        ) from exc


def _required_canonical_text(row: Mapping[str, Any], field_name: str) -> str:
    value = row.get(field_name)
    if value is None:
        raise ValueError(f"missing {field_name}")

    return str(value)


def _symbol_from_ts_code(ts_code: str) -> str:
    return ts_code.split(".", maxsplit=1)[0]


def _exchange_from_ts_code(ts_code: str) -> str:
    suffix = ts_code.rsplit(".", maxsplit=1)[-1].upper()
    exchanges = {
        "SZ": "SZSE",
        "SH": "SSE",
        "BJ": "BSE",
        "HK": "HKEX",
    }
    try:
        return exchanges[suffix]
    except KeyError as exc:
        raise ValueError(f"cannot derive exchange from ts_code {ts_code!r}") from exc


def _list_status_from_is_active(row: Mapping[str, Any]) -> str:
    if "is_active" not in row:
        raise ValueError("missing is_active")

    value = row["is_active"]
    if isinstance(value, bool):
        return "L" if value else "D"
    if isinstance(value, int) and value in {0, 1}:
        return "L" if value == 1 else "D"
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y", "l", "active"}:
            return "L"
        if normalized in {"0", "false", "f", "no", "n", "d", "inactive"}:
            return "D"

    raise ValueError("is_active must be boolean-like")


def _canonical_date_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    return str(value)


def _entity_status_from_list_status(list_status: str) -> EntityStatus:
    return EntityStatus.ACTIVE if list_status.upper() == "L" else EntityStatus.INACTIVE


def _cross_listing_company_key(record: StockBasicRecord) -> str | None:
    source_name = record.fullname or record.name
    normalized = source_name.lower()
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"[()（）【】\[\]·.,，。-]", "", normalized)
    for suffix in (
        "股份有限公司",
        "有限责任公司",
        "有限公司",
        "集团",
        "companylimited",
        "coltd",
        "limited",
        "incorporated",
    ):
        normalized = normalized.removesuffix(suffix)

    return normalized or None


def _has_cross_listing_shape(records: list[StockBasicRecord]) -> bool:
    has_mainland_listing = any(_is_mainland_listing(record) for record in records)
    has_h_listing = any(_is_h_listing(record) for record in records)
    has_cross_listing_marker = any(_has_cross_listing_marker(record) for record in records)

    return has_mainland_listing and has_h_listing and has_cross_listing_marker


def _is_mainland_listing(record: StockBasicRecord) -> bool:
    exchange = record.exchange.upper()
    ts_code = record.ts_code.upper()
    return exchange in {"SSE", "SZSE", "BSE"} or ts_code.endswith((".SH", ".SZ", ".BJ"))


def _is_h_listing(record: StockBasicRecord) -> bool:
    exchange = record.exchange.upper()
    market = record.market.upper()
    ts_code = record.ts_code.upper()
    return (
        exchange in {"HKEX", "HK", "SEHK"}
        or market in {"HK", "H"}
        or ts_code.endswith(".HK")
    )


def _has_cross_listing_marker(record: StockBasicRecord) -> bool:
    if _is_h_listing(record):
        return True
    if record.is_hs is None:
        return False

    return record.is_hs.upper() in {"H", "S"}


def _build_cross_listing_group_id(company_key: str) -> str:
    digest = hashlib.sha1(company_key.encode("utf-8")).hexdigest()[:12]
    return f"XLG_{digest}"
