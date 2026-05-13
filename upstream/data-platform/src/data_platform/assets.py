"""Orchestrator-neutral asset and resource factories for data-platform."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Literal, cast

from data_platform.adapters.base import AssetSpec, DataSourceAdapter
from data_platform.adapters.tushare.assets import TUSHARE_ASSETS
from data_platform.config import Settings, get_settings
from data_platform.raw import RawReader, RawWriter
from data_platform.serving.canonical_writer import (
    CANONICAL_LINEAGE_MART_LOAD_SPECS,
    CANONICAL_V2_MART_LOAD_SPECS,
)
from data_platform.serving.catalog import load_catalog

AssetKind = Literal["raw", "dbt", "canonical"]
AssetKey = tuple[str, ...]

DBT_PROJECT_DIR = Path(__file__).resolve().parent / "dbt"
DBT_MODEL_DIR = DBT_PROJECT_DIR / "models"
RAW_FETCH_CALLABLES: Mapping[str, str] = {
    "tushare": "data_platform.adapters.tushare.adapter:run_tushare_asset",
}
DBT_RUNNER_CALLABLE = "dbt.cli.main:dbtRunner"
CANONICAL_V2_MARTS_CALLABLE = (
    "data_platform.serving.canonical_writer:load_canonical_v2_marts"
)
CANONICAL_V2_MARTS_ASSET_KEY: AssetKey = ("canonical_v2", "canonical_marts")
CANONICAL_V2_MARTS_ASSET_IDENTIFIER = "canonical_v2.canonical_marts"
_REF_PATTERN = re.compile(r"\{\{\s*ref\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}")


@dataclass(frozen=True, slots=True)
class DataPlatformAssetSpec:
    """Pure Python description of one asset-like unit owned by data-platform."""

    key: AssetKey
    kind: AssetKind
    deps: tuple[AssetKey, ...]
    metadata: dict[str, Any]
    callable_import_path: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", tuple(self.key))
        object.__setattr__(self, "deps", tuple(tuple(dep) for dep in self.deps))
        metadata = dict(self.metadata)
        metadata.setdefault("callable_import_path", self.callable_import_path)
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True, slots=True)
class _DbtModelInfo:
    name: str
    path: Path
    refs: tuple[str, ...]
    layer: str


class _TushareAssetAdapter(DataSourceAdapter):
    """Read-only adapter descriptor used by asset specs without requiring a token."""

    def source_id(self) -> str:
        return "tushare"

    def get_assets(self) -> list[AssetSpec]:
        return list(TUSHARE_ASSETS)

    def get_resources(self) -> dict[str, Any]:
        return {"token_env": "DP_TUSHARE_TOKEN"}

    def get_staging_dbt_models(self) -> list[str]:
        return [f"stg_{asset.dataset}" for asset in TUSHARE_ASSETS]

    def get_quota_config(self) -> dict[str, Any]:
        return {"requests_per_minute": 200, "daily_credit_quota": None}


def build_default_adapters() -> list[DataSourceAdapter]:
    """Return the default source adapter descriptors for spec generation."""

    return [_TushareAssetAdapter()]


def build_assets(
    adapters: Sequence[DataSourceAdapter] | None = None,
) -> list[DataPlatformAssetSpec]:
    """Build the orchestrator-consumable Raw, dbt, and canonical asset specs."""

    resolved_adapters = list(adapters) if adapters is not None else build_default_adapters()
    specs: list[DataPlatformAssetSpec] = []
    raw_deps_by_staging_model: dict[str, list[AssetKey]] = {}
    selected_staging_models: list[str] = []

    for adapter in resolved_adapters:
        source_id = _adapter_source_id(adapter)
        resources = _json_safe(adapter.get_resources())
        quota_config = _json_safe(adapter.get_quota_config())
        assets = adapter.get_assets()
        raw_key_by_dataset = {
            asset.dataset: _raw_key(source_id, asset)
            for asset in assets
        }

        for asset in assets:
            callable_import_path = _raw_callable_import_path(adapter, source_id)
            asset_metadata = _json_safe(asset.metadata or {})
            specs.append(
                DataPlatformAssetSpec(
                    key=raw_key_by_dataset[asset.dataset],
                    kind="raw",
                    deps=(),
                    metadata={
                        **asset_metadata,
                        "source_id": source_id,
                        "asset_name": asset.name,
                        "dataset": asset.dataset,
                        "partition": asset.partition,
                        "schema": _schema_metadata(asset),
                        "adapter_resources": resources,
                        "quota_config": quota_config,
                    },
                    callable_import_path=callable_import_path,
                )
            )

        for model_name in adapter.get_staging_dbt_models():
            selected_staging_models.append(model_name)
            dataset = _dataset_from_staging_model(model_name)
            if dataset is None:
                continue
            raw_key = raw_key_by_dataset.get(dataset)
            if raw_key is not None:
                raw_deps_by_staging_model.setdefault(model_name, []).append(raw_key)

    dbt_models = _discover_dbt_models(DBT_MODEL_DIR)
    selected_dbt_models = _selected_dbt_models(
        selected_staging_models,
        dbt_models,
        canonical_relations=_canonical_duckdb_relations(),
    )
    specs.extend(_build_dbt_specs(selected_dbt_models, dbt_models, raw_deps_by_staging_model))
    specs.extend(_build_canonical_specs(selected_dbt_models))
    return specs


def build_resources(settings: Settings | None = None) -> dict[str, Any]:
    """Build runtime resources used by the external orchestrator wiring."""

    resolved_settings = settings or get_settings()
    return {
        "settings": resolved_settings,
        "raw_writer": RawWriter(
            resolved_settings.raw_zone_path,
            iceberg_warehouse_path=resolved_settings.iceberg_warehouse_path,
        ),
        "raw_reader": RawReader(resolved_settings.raw_zone_path),
        "iceberg_catalog": load_catalog(settings=resolved_settings),
        "duckdb_path": resolved_settings.duckdb_path,
        "dbt_project_dir": DBT_PROJECT_DIR,
        "data_storage_root_path": resolved_settings.data_storage_root_path,
        "raw_zone_path": resolved_settings.raw_zone_path,
        "processed_data_path": resolved_settings.processed_data_path,
        "iceberg_warehouse_path": resolved_settings.iceberg_warehouse_path,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for smoke-checking the exported asset specs."""

    parser = argparse.ArgumentParser(description="Print data-platform asset specs.")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    parser.add_argument("--kind", choices=("raw", "dbt", "canonical"), help="filter by kind")
    args = parser.parse_args(argv)

    specs = build_assets()
    if args.kind:
        specs = [spec for spec in specs if spec.kind == args.kind]

    payload = [_spec_to_json(spec) for spec in specs]
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0

    for item in payload:
        print(" ".join(item["key"]))
    return 0


def _adapter_source_id(adapter: DataSourceAdapter) -> str:
    source_id = getattr(adapter, "source_id", None)
    if callable(source_id):
        value = str(source_id())
        if value:
            return value

    resources = adapter.get_resources()
    configured_source_id = resources.get("source_id")
    if configured_source_id:
        return str(configured_source_id)

    class_name = adapter.__class__.__name__
    suffix = "Adapter"
    if class_name.endswith(suffix):
        class_name = class_name[: -len(suffix)]
    return _to_snake_case(class_name)


def _raw_key(source_id: str, asset: AssetSpec) -> AssetKey:
    return ("raw", source_id, asset.dataset)


def _dbt_key(model_name: str) -> AssetKey:
    return ("dbt", model_name)


def _canonical_key(identifier: str) -> AssetKey:
    return tuple(identifier.split("."))


def _raw_callable_import_path(adapter: DataSourceAdapter, source_id: str) -> str:
    if source_id in RAW_FETCH_CALLABLES:
        return RAW_FETCH_CALLABLES[source_id]
    if hasattr(adapter, "fetch"):
        return f"{adapter.__class__.__module__}:{adapter.__class__.__qualname__}.fetch"
    return ""


def _schema_metadata(asset: AssetSpec) -> list[dict[str, str]]:
    return [
        {"name": field.name, "type": str(field.type)}
        for field in asset.schema
    ]


def _dataset_from_staging_model(model_name: str) -> str | None:
    prefix = "stg_"
    if not model_name.startswith(prefix):
        return None
    return model_name.removeprefix(prefix)


def _discover_dbt_models(model_dir: Path) -> dict[str, _DbtModelInfo]:
    models: dict[str, _DbtModelInfo] = {}
    if not model_dir.exists():
        return models

    for path in sorted(model_dir.rglob("*.sql")):
        model_name = path.stem
        sql = path.read_text(encoding="utf-8")
        refs = tuple(dict.fromkeys(_REF_PATTERN.findall(sql)))
        layer = path.parent.name
        models[model_name] = _DbtModelInfo(
            name=model_name,
            path=path,
            refs=refs,
            layer=layer,
        )
    return models


def _selected_dbt_models(
    staging_models: Sequence[str],
    dbt_models: Mapping[str, _DbtModelInfo],
    *,
    canonical_relations: Sequence[str],
) -> list[str]:
    selected = set(staging_models)
    selected.update(canonical_relations)

    changed = True
    while changed:
        changed = False
        for model_name in tuple(selected):
            info = dbt_models.get(model_name)
            if info is None:
                continue
            for ref in info.refs:
                if ref not in selected:
                    selected.add(ref)
                    changed = True

    ordered: list[str] = []
    visited: set[str] = set()

    def visit(model_name: str) -> None:
        if model_name in visited:
            return
        info = dbt_models.get(model_name)
        if info is not None:
            for ref in info.refs:
                if ref in selected:
                    visit(ref)
        visited.add(model_name)
        if model_name in selected:
            ordered.append(model_name)

    for model_name in staging_models:
        visit(model_name)
    for model_name in canonical_relations:
        visit(model_name)
    for model_name in sorted(selected):
        visit(model_name)
    return ordered


def _canonical_duckdb_relations() -> tuple[str, ...]:
    return (
        *(spec.duckdb_relation for spec in CANONICAL_V2_MART_LOAD_SPECS),
        *(spec.duckdb_relation for spec in CANONICAL_LINEAGE_MART_LOAD_SPECS),
    )


def _build_dbt_specs(
    selected_model_names: Sequence[str],
    dbt_models: Mapping[str, _DbtModelInfo],
    raw_deps_by_staging_model: Mapping[str, list[AssetKey]],
) -> list[DataPlatformAssetSpec]:
    specs: list[DataPlatformAssetSpec] = []
    for model_name in selected_model_names:
        info = dbt_models.get(model_name)
        deps = [
            _dbt_key(ref)
            for ref in (info.refs if info is not None else ())
        ]
        deps.extend(raw_deps_by_staging_model.get(model_name, ()))
        layer = info.layer if info is not None else _model_layer(model_name)
        metadata: dict[str, Any] = {
            "model": model_name,
            "layer": layer,
            "dbt_project_dir": str(DBT_PROJECT_DIR),
            "dbt_args": ["run", "--select", model_name],
        }
        if info is not None:
            metadata["model_path"] = str(info.path.relative_to(DBT_PROJECT_DIR))

        specs.append(
            DataPlatformAssetSpec(
                key=_dbt_key(model_name),
                kind="dbt",
                deps=tuple(dict.fromkeys(deps)),
                metadata=metadata,
                callable_import_path=DBT_RUNNER_CALLABLE,
            )
        )
    return specs


def _build_canonical_specs(
    selected_dbt_models: Sequence[str],
) -> list[DataPlatformAssetSpec]:
    v2_mart_deps = tuple(
        _dbt_key(load_spec.duckdb_relation)
        for load_spec in (
            *CANONICAL_V2_MART_LOAD_SPECS,
            *CANONICAL_LINEAGE_MART_LOAD_SPECS,
        )
    )
    return [
        DataPlatformAssetSpec(
            key=CANONICAL_V2_MARTS_ASSET_KEY,
            kind="canonical",
            deps=v2_mart_deps,
            metadata={
                "identifier": CANONICAL_V2_MARTS_ASSET_IDENTIFIER,
                "canonical_identifiers": [
                    load_spec.identifier for load_spec in CANONICAL_V2_MART_LOAD_SPECS
                ],
                "lineage_identifiers": [
                    load_spec.identifier for load_spec in CANONICAL_LINEAGE_MART_LOAD_SPECS
                ],
                "duckdb_relations": [
                    load_spec.duckdb_relation
                    for load_spec in (
                        *CANONICAL_V2_MART_LOAD_SPECS,
                        *CANONICAL_LINEAGE_MART_LOAD_SPECS,
                    )
                ],
                "required_columns_by_identifier": {
                    load_spec.identifier: list(load_spec.required_columns)
                    for load_spec in (
                        *CANONICAL_V2_MART_LOAD_SPECS,
                        *CANONICAL_LINEAGE_MART_LOAD_SPECS,
                    )
                },
                "writer": "v2_marts",
                "write_group": "canonical_v2_marts",
                "serialization_required": True,
            },
            callable_import_path=CANONICAL_V2_MARTS_CALLABLE,
        )
    ]


def _model_layer(model_name: str) -> str:
    if model_name.startswith("stg_"):
        return "staging"
    if model_name.startswith("int_"):
        return "intermediate"
    if model_name.startswith("mart_"):
        return "marts"
    return "unknown"


def _spec_to_json(spec: DataPlatformAssetSpec) -> dict[str, Any]:
    return cast(dict[str, Any], _json_safe(asdict(spec)))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _to_snake_case(value: str) -> str:
    value = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return value.lower()


__all__ = [
    "AssetKey",
    "AssetKind",
    "CANONICAL_V2_MARTS_ASSET_KEY",
    "DBT_PROJECT_DIR",
    "DataPlatformAssetSpec",
    "build_assets",
    "build_default_adapters",
    "build_resources",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
