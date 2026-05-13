import inspect
import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import get_type_hints

import pytest

import entity_registry
import entity_registry.init as init_module
from entity_registry.core import AliasType, EntityStatus
from entity_registry.init import (
    DataPlatformStockBasicReader,
    FileStockBasicSnapshotReader,
    InitializationError,
    InitializationResult,
    RepositoryNotConfiguredError,
    StockBasicRecord,
    detect_cross_listing_groups,
    initialize_from_stock_basic,
    initialize_from_stock_basic_into,
    load_stock_basic_records,
)
from entity_registry.storage import (
    InMemoryAliasRepository,
    InMemoryEntityRepository,
    InMemoryReferenceRepository,
    InMemoryResolutionCaseRepository,
)


FIXTURE_PATH = Path("tests/fixtures/stock_basic_sample.json")


@pytest.fixture(autouse=True)
def reset_public_repositories() -> Iterator[None]:
    entity_registry.reset_default_repositories()
    yield
    entity_registry.reset_default_repositories()


def initialize_from_fixture(
    entity_repo: InMemoryEntityRepository,
    alias_repo: InMemoryAliasRepository,
) -> InitializationResult:
    return initialize_from_stock_basic_into(
        str(FIXTURE_PATH),
        entity_repo,
        alias_repo,
        stock_basic_reader=FileStockBasicSnapshotReader(),
    )


def test_stock_basic_record_normalizes_optional_empty_strings() -> None:
    record = StockBasicRecord(
        ts_code="300750.SZ",
        symbol="300750",
        name="宁德时代",
        fullname="",
        enname=" ",
        cnspell="NDSD",
        market="创业板",
        exchange="SZSE",
        list_status="L",
        list_date="",
        is_hs="",
    )

    assert record.fullname is None
    assert record.enname is None
    assert record.list_date is None
    assert record.is_hs is None


def test_initialization_result_builds() -> None:
    result = InitializationResult(
        entities_created=1,
        aliases_created=2,
        cross_listing_groups=0,
        errors=[],
    )

    assert result.entities_created == 1
    assert result.errors == []


def test_public_initialize_from_stock_basic_matches_project_contract() -> None:
    signature = inspect.signature(entity_registry.initialize_from_stock_basic)

    assert list(signature.parameters) == ["snapshot_ref"]
    assert (
        get_type_hints(entity_registry.initialize_from_stock_basic)["return"]
        is type(None)
    )


def test_public_initialize_from_stock_basic_fails_fast_without_repositories() -> None:
    with pytest.raises(RepositoryNotConfiguredError, match="not configured"):
        initialize_from_stock_basic(str(FIXTURE_PATH))


def test_default_repository_context_returns_one_atomic_pair() -> None:
    first_entity_repo = InMemoryEntityRepository()
    first_alias_repo = InMemoryAliasRepository()
    second_entity_repo = InMemoryEntityRepository()
    second_alias_repo = InMemoryAliasRepository()
    entity_registry.configure_default_repositories(first_entity_repo, first_alias_repo)

    entity_repo, alias_repo = entity_registry.get_default_repositories()
    entity_registry.configure_default_repositories(second_entity_repo, second_alias_repo)

    assert entity_repo is first_entity_repo
    assert alias_repo is first_alias_repo
    current_entity_repo, current_alias_repo = entity_registry.get_default_repositories()
    assert current_entity_repo is second_entity_repo
    assert current_alias_repo is second_alias_repo


def test_resolution_repositories_fail_fast_without_explicit_audit_repositories() -> None:
    entity_registry.configure_default_repositories(
        InMemoryEntityRepository(),
        InMemoryAliasRepository(),
    )

    with pytest.raises(
        RepositoryNotConfiguredError,
        match="resolution audit repositories are not configured",
    ):
        init_module.get_default_resolution_repositories()


def test_public_resolve_mention_fails_without_explicit_audit_repositories() -> None:
    entity_registry.configure_default_repositories(
        InMemoryEntityRepository(),
        InMemoryAliasRepository(),
    )

    with pytest.raises(
        RepositoryNotConfiguredError,
        match="resolution audit repositories are not configured",
    ):
        entity_registry.resolve_mention("贵州茅台")


def test_reference_repository_fails_fast_without_explicit_audit_repository() -> None:
    entity_registry.configure_default_repositories(
        InMemoryEntityRepository(),
        InMemoryAliasRepository(),
    )

    with pytest.raises(
        RepositoryNotConfiguredError,
        match="reference audit repository is not configured",
    ):
        init_module.get_default_reference_repository()


def test_public_register_unresolved_reference_fails_without_explicit_audit_repository() -> None:
    entity_registry.configure_default_repositories(
        InMemoryEntityRepository(),
        InMemoryAliasRepository(),
    )

    with pytest.raises(
        RepositoryNotConfiguredError,
        match="reference audit repository is not configured",
    ):
        entity_registry.register_unresolved_reference(
            {
                "reference_id": "ref-public",
                "raw_mention_text": "Unknown Corp",
                "source_context": {},
            }
        )


def test_in_memory_audit_repositories_require_named_local_opt_in() -> None:
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()

    reference_repo, case_repo = (
        init_module.configure_default_in_memory_audit_repositories(
            entity_repo,
            alias_repo,
        )
    )

    configured = init_module.get_default_resolution_repositories()
    assert isinstance(reference_repo, InMemoryReferenceRepository)
    assert isinstance(case_repo, InMemoryResolutionCaseRepository)
    assert configured == (entity_repo, alias_repo, reference_repo, case_repo)


def test_package_in_memory_audit_helper_configures_public_resolution() -> None:
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()
    reference_repo, case_repo = (
        entity_registry.configure_default_in_memory_audit_repositories(
            entity_repo,
            alias_repo,
        )
    )
    initialize_from_fixture(entity_repo, alias_repo)

    result = entity_registry.resolve_mention("贵州茅台")
    unresolved = reference_repo.find_unresolved()

    assert result.resolved_entity is not None
    assert result.resolved_entity.entity_id == "ENT_STOCK_600519.SH"
    assert unresolved == []
    assert len(case_repo.find_by_reference(next(iter(reference_repo._references)))) == 1


def test_public_initialize_uses_captured_repository_context(monkeypatch: pytest.MonkeyPatch) -> None:
    first_entity_repo = InMemoryEntityRepository()
    first_alias_repo = InMemoryAliasRepository()
    second_entity_repo = InMemoryEntityRepository()
    second_alias_repo = InMemoryAliasRepository()
    entity_registry.configure_default_repositories(first_entity_repo, first_alias_repo)

    class ReconfiguringReader:
        def read(self, snapshot_ref: str) -> list[StockBasicRecord]:
            entity_registry.configure_default_repositories(
                second_entity_repo,
                second_alias_repo,
            )
            return [StockBasicRecord(**make_minimal_record_payload())]

    monkeypatch.setattr(
        init_module,
        "_default_reader_for_snapshot",
        lambda snapshot_ref: ReconfiguringReader(),
    )

    initialize_from_stock_basic("stock-basic-from-test-reader")

    assert first_entity_repo.get("ENT_STOCK_300750.SZ") is not None
    assert first_alias_repo.find_by_entity("ENT_STOCK_300750.SZ")
    assert second_entity_repo.list_all() == []
    assert second_alias_repo.find_by_entity("ENT_STOCK_300750.SZ") == []


def test_public_initialize_from_stock_basic_returns_none_for_fixture_snapshot() -> None:
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()
    entity_registry.configure_default_repositories(entity_repo, alias_repo)

    result = initialize_from_stock_basic(str(FIXTURE_PATH))

    assert result is None
    entity = entity_registry.lookup_alias("平安银行")
    assert entity is not None
    assert entity.canonical_entity_id == "ENT_STOCK_000001.SZ"
    assert entity_repo.get("ENT_STOCK_000001.SZ") is not None
    assert alias_repo.find_by_entity("ENT_STOCK_000001.SZ")


def test_public_initialize_from_stock_basic_raises_on_row_errors(tmp_path: Path) -> None:
    snapshot = tmp_path / "bad-id.json"
    valid_payload = make_minimal_record_payload(
        ts_code="688019.SH",
        symbol="688019",
        name="安集科技",
    )
    invalid_payload = make_minimal_record_payload(ts_code="300750 SZ")
    snapshot.write_text(json.dumps([valid_payload, invalid_payload]), encoding="utf-8")
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()
    entity_registry.configure_default_repositories(entity_repo, alias_repo)

    with pytest.raises(InitializationError) as exc_info:
        initialize_from_stock_basic(str(snapshot))

    assert exc_info.value.errors
    assert "300750 SZ" in str(exc_info.value)
    assert entity_repo.list_all() == []
    assert alias_repo.find_by_text("安集科技") == []


def test_load_stock_basic_records_from_json_fixture() -> None:
    records = load_stock_basic_records(str(FIXTURE_PATH))

    assert len(records) == 24
    assert records[0].ts_code == "000001.SZ"
    assert records[0].name == "平安银行"


def test_load_stock_basic_records_supports_records_object(tmp_path: Path) -> None:
    snapshot = tmp_path / "stock_basic.json"
    snapshot.write_text(
        json.dumps({"records": [make_minimal_record_payload()]}),
        encoding="utf-8",
    )

    records = load_stock_basic_records(str(snapshot))

    assert len(records) == 1
    assert records[0].ts_code == "300750.SZ"


def test_load_stock_basic_records_supports_data_object(tmp_path: Path) -> None:
    snapshot = tmp_path / "stock_basic.json"
    snapshot.write_text(
        json.dumps({"data": [make_minimal_record_payload()]}),
        encoding="utf-8",
    )

    records = load_stock_basic_records(str(snapshot))

    assert len(records) == 1


def test_load_stock_basic_records_from_csv(tmp_path: Path) -> None:
    snapshot = tmp_path / "stock_basic.csv"
    snapshot.write_text(
        "\n".join(
            [
                "ts_code,symbol,name,fullname,enname,cnspell,market,exchange,list_status,list_date,is_hs",
                "300750.SZ,300750,宁德时代,宁德时代新能源科技股份有限公司,CATL,NDSD,创业板,SZSE,L,20180611,H",
            ]
        ),
        encoding="utf-8",
    )

    records = load_stock_basic_records(str(snapshot))

    assert len(records) == 1
    assert records[0].symbol == "300750"


def test_load_stock_basic_records_missing_path_raises_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_stock_basic_records("tests/fixtures/missing_stock_basic.json")


def test_load_stock_basic_records_invalid_json_raises_value_error(tmp_path: Path) -> None:
    snapshot = tmp_path / "bad.json"
    snapshot.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON"):
        load_stock_basic_records(str(snapshot))


def test_load_stock_basic_records_rejects_wrong_json_shape(tmp_path: Path) -> None:
    snapshot = tmp_path / "bad.json"
    snapshot.write_text(json.dumps({"unexpected": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="records or data"):
        load_stock_basic_records(str(snapshot))


def test_load_stock_basic_records_rejects_invalid_record(tmp_path: Path) -> None:
    snapshot = tmp_path / "bad.json"
    payload = make_minimal_record_payload()
    payload["name"] = ""
    snapshot.write_text(json.dumps([payload]), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid stock_basic record"):
        load_stock_basic_records(str(snapshot))


def test_load_stock_basic_records_allows_missing_optional_fields(tmp_path: Path) -> None:
    snapshot = tmp_path / "stock_basic.json"
    payload = make_minimal_record_payload()
    del payload["enname"]
    del payload["cnspell"]
    del payload["is_hs"]
    snapshot.write_text(json.dumps([payload]), encoding="utf-8")

    records = load_stock_basic_records(str(snapshot))

    assert records[0].enname is None
    assert records[0].cnspell is None
    assert records[0].is_hs is None


def test_load_stock_basic_records_rejects_unsupported_suffix(tmp_path: Path) -> None:
    snapshot = tmp_path / "stock_basic.txt"
    snapshot.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON or CSV"):
        load_stock_basic_records(str(snapshot))


def test_data_platform_reader_maps_canonical_stock_basic_rows() -> None:
    calls: list[bool] = []

    def canonical_loader(active_only: bool) -> FakeCanonicalTable:
        calls.append(active_only)
        return FakeCanonicalTable(
            [
                make_canonical_stock_basic_row(),
                make_canonical_stock_basic_row(
                    ts_code="000003.SZ",
                    symbol="000003",
                    name="PT金田A",
                    is_active=False,
                    list_date=None,
                ),
            ]
        )

    reader = DataPlatformStockBasicReader(canonical_loader=canonical_loader)

    records = reader.read("canonical.stock_basic")

    assert calls == [False]
    assert records[0].ts_code == "300750.SZ"
    assert records[0].exchange == "SZSE"
    assert records[0].list_status == "L"
    assert records[0].list_date == "20180611"
    assert records[1].list_status == "D"
    assert records[1].list_date is None


def test_initialize_from_stock_basic_into_uses_data_platform_reader_interface() -> None:
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()
    reader = DataPlatformStockBasicReader(
        canonical_loader=lambda _active_only: FakeCanonicalTable(
            [make_canonical_stock_basic_row()]
        )
    )

    result = initialize_from_stock_basic_into(
        "canonical.stock_basic",
        entity_repo,
        alias_repo,
        stock_basic_reader=reader,
    )

    entity = entity_repo.get("ENT_STOCK_300750.SZ")
    assert result.entities_created == 1
    assert entity is not None
    assert entity.anchor_code == "300750.SZ"
    assert alias_repo.find_by_text("宁德时代")


def test_initialize_from_stock_basic_into_defaults_to_data_platform_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_read(
        self: DataPlatformStockBasicReader,
        snapshot_ref: str,
    ) -> list[StockBasicRecord]:
        calls.append(snapshot_ref)
        return [StockBasicRecord.model_validate(make_minimal_record_payload())]

    monkeypatch.setattr(DataPlatformStockBasicReader, "read", fake_read)

    result = initialize_from_stock_basic_into(
        "canonical.stock_basic",
        InMemoryEntityRepository(),
        InMemoryAliasRepository(),
    )

    assert calls == ["canonical.stock_basic"]
    assert result.entities_created == 1


def test_detect_cross_listing_groups_identifies_fixture_pairs() -> None:
    groups = detect_cross_listing_groups(load_stock_basic_records(str(FIXTURE_PATH)))

    assert groups["300750.SZ"] == groups["03750.HK"]
    assert groups["601318.SH"] == groups["02318.HK"]
    assert len(set(groups.values())) == 2
    assert set(groups) == {"300750.SZ", "03750.HK", "601318.SH", "02318.HK"}


def test_detect_cross_listing_groups_requires_a_and_h_shape() -> None:
    records = [
        StockBasicRecord.model_validate(make_minimal_record_payload()),
        StockBasicRecord.model_validate(
            make_minimal_record_payload(ts_code="300751.SZ", symbol="300751")
        ),
    ]

    assert detect_cross_listing_groups(records) == {}


def test_initialize_from_stock_basic_creates_entities_for_all_fixture_records() -> None:
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()

    result = initialize_from_fixture(entity_repo, alias_repo)

    assert result.entities_created == 24
    assert len(entity_repo.list_all()) == 24
    assert result.errors == []


def test_initialize_from_stock_basic_creates_required_aliases() -> None:
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()

    result = initialize_from_fixture(entity_repo, alias_repo)

    assert result.aliases_created >= 48
    for entity in entity_repo.list_all():
        aliases = alias_repo.find_by_entity(entity.canonical_entity_id)
        alias_types = {alias.alias_type for alias in aliases}
        assert AliasType.SHORT_NAME in alias_types
        assert AliasType.CODE in alias_types


def test_initialize_from_stock_basic_sets_active_and_inactive_statuses() -> None:
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()

    initialize_from_fixture(entity_repo, alias_repo)

    active_entity = entity_repo.get("ENT_STOCK_300750.SZ")
    inactive_entity = entity_repo.get("ENT_STOCK_000003.SZ")

    assert active_entity is not None
    assert inactive_entity is not None
    assert active_entity.status is EntityStatus.ACTIVE
    assert inactive_entity.status is EntityStatus.INACTIVE


def test_initialize_from_stock_basic_is_idempotent() -> None:
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()

    first = initialize_from_fixture(entity_repo, alias_repo)
    second = initialize_from_fixture(entity_repo, alias_repo)

    assert first.entities_created == 24
    assert second.entities_created == 0
    assert second.aliases_created == 0
    assert len(entity_repo.list_all()) == 24


def test_initialize_from_stock_basic_uses_atomic_entity_insert() -> None:
    entity_repo = NoExistsEntityRepository()
    alias_repo = InMemoryAliasRepository()

    result = initialize_from_fixture(entity_repo, alias_repo)

    assert result.entities_created == 24
    assert len(entity_repo.list_all()) == 24


def test_initialize_from_stock_basic_is_idempotent_under_concurrent_runs() -> None:
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(
                lambda _: initialize_from_stock_basic_into(
                    str(FIXTURE_PATH),
                    entity_repo,
                    alias_repo,
                    stock_basic_reader=FileStockBasicSnapshotReader(),
                ),
                range(4),
            )
        )

    assert sum(result.entities_created for result in results) == 24
    assert len(entity_repo.list_all()) == 24

    stored_aliases = [
        alias
        for entity in entity_repo.list_all()
        for alias in alias_repo.find_by_entity(entity.canonical_entity_id)
    ]
    semantic_keys = {
        (alias.canonical_entity_id, alias.alias_text, alias.alias_type)
        for alias in stored_aliases
    }
    assert len(stored_aliases) == len(semantic_keys)
    assert sum(result.aliases_created for result in results) == len(stored_aliases)


def test_initialize_from_stock_basic_keeps_a_and_h_independent_but_linked() -> None:
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()

    result = initialize_from_fixture(entity_repo, alias_repo)

    a_share = entity_repo.get("ENT_STOCK_300750.SZ")
    h_share = entity_repo.get("ENT_STOCK_03750.HK")
    assert a_share is not None
    assert h_share is not None
    assert a_share.canonical_entity_id != h_share.canonical_entity_id
    assert a_share.cross_listing_group == h_share.cross_listing_group
    assert a_share.cross_listing_group is not None
    assert result.cross_listing_groups == 2


def test_initialize_from_stock_basic_allows_duplicate_short_name_for_a_and_h() -> None:
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()

    initialize_from_fixture(entity_repo, alias_repo)

    aliases = alias_repo.find_by_text("宁德时代")
    assert {alias.canonical_entity_id for alias in aliases} == {
        "ENT_STOCK_300750.SZ",
        "ENT_STOCK_03750.HK",
    }


def test_initialize_from_stock_basic_empty_snapshot_returns_zero_counts(tmp_path: Path) -> None:
    snapshot = tmp_path / "empty.json"
    snapshot.write_text("[]", encoding="utf-8")

    result = initialize_from_stock_basic_into(
        str(snapshot),
        InMemoryEntityRepository(),
        InMemoryAliasRepository(),
        stock_basic_reader=FileStockBasicSnapshotReader(),
    )

    assert result == InitializationResult(
        entities_created=0,
        aliases_created=0,
        cross_listing_groups=0,
        errors=[],
    )


def test_initialize_from_stock_basic_reports_invalid_entity_id(tmp_path: Path) -> None:
    snapshot = tmp_path / "bad-id.json"
    valid_payload = make_minimal_record_payload(
        ts_code="688019.SH",
        symbol="688019",
        name="安集科技",
    )
    invalid_payload = make_minimal_record_payload(ts_code="300750 SZ")
    snapshot.write_text(json.dumps([valid_payload, invalid_payload]), encoding="utf-8")
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()

    result = initialize_from_stock_basic_into(
        str(snapshot),
        entity_repo,
        alias_repo,
        stock_basic_reader=FileStockBasicSnapshotReader(),
    )

    assert result.entities_created == 0
    assert result.aliases_created == 0
    assert result.errors
    assert entity_repo.list_all() == []
    assert alias_repo.find_by_text("安集科技") == []


def make_minimal_record_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ts_code": "300750.SZ",
        "symbol": "300750",
        "name": "宁德时代",
        "fullname": "宁德时代新能源科技股份有限公司",
        "enname": "Contemporary Amperex Technology Co., Limited",
        "cnspell": "NDSD",
        "market": "创业板",
        "exchange": "SZSE",
        "list_status": "L",
        "list_date": "20180611",
        "is_hs": "H",
    }
    payload.update(overrides)
    return payload


def make_canonical_stock_basic_row(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ts_code": "300750.SZ",
        "symbol": "300750",
        "name": "宁德时代",
        "market": "创业板",
        "list_date": date(2018, 6, 11),
        "is_active": True,
        "source_run_id": "test-run",
        "canonical_loaded_at": "2026-04-16T00:00:00",
    }
    payload.update(overrides)
    return payload


class FakeCanonicalTable:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def to_pylist(self) -> list[dict[str, object]]:
        return list(self._rows)


class NoExistsEntityRepository(InMemoryEntityRepository):
    def exists(self, entity_id: str) -> bool:
        raise AssertionError(f"exists() should not be used for {entity_id}")
