from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from contracts.compat import check_compatibility  # noqa: E402
from contracts.export import (  # noqa: E402
    SCHEMA_MODEL_REGISTRY,
    SchemaArtifact,
    export_json_schemas,
)


def export_to(path: Path) -> tuple[SchemaArtifact, ...]:
    return export_json_schemas(path, version="0.1.0")


def mutate_schema_type(schema_path: Path, field_name: str, new_type: str) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    properties = schema["properties"]
    assert isinstance(properties, dict)
    field_schema = properties[field_name]
    assert isinstance(field_schema, dict)

    field_schema["type"] = new_type
    schema_path.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_json_schema_full_export_under_five_seconds(tmp_path: Path) -> None:
    output_dir = tmp_path / "json_schema"

    started_at = time.perf_counter()
    artifacts = export_to(output_dir)
    elapsed = time.perf_counter() - started_at

    print(f"json schema export: schemas={len(artifacts)} elapsed={elapsed:.6f}s")
    assert len(artifacts) == len(SCHEMA_MODEL_REGISTRY)
    assert elapsed < 5.0


def test_compatibility_check_under_ten_seconds(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    current = tmp_path / "current"
    export_to(baseline)
    shutil.copytree(baseline, current)

    started_at = time.perf_counter()
    result = check_compatibility(baseline, current)
    elapsed = time.perf_counter() - started_at

    print(
        f"compatibility check: "
        f"schemas={len(SCHEMA_MODEL_REGISTRY)} elapsed={elapsed:.6f}s"
    )
    assert result.is_compatible is True
    assert elapsed < 10.0


def test_breaking_change_detection_under_ten_seconds(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    current = tmp_path / "current"
    export_to(baseline)
    shutil.copytree(baseline, current)
    mutate_schema_type(
        current / "ex1_candidate_fact.schema.json",
        "confidence",
        "string",
    )

    started_at = time.perf_counter()
    result = check_compatibility(baseline, current)
    elapsed = time.perf_counter() - started_at

    print(
        "breaking compatibility check: "
        f"schemas={len(SCHEMA_MODEL_REGISTRY)} elapsed={elapsed:.6f}s"
    )
    assert result.is_compatible is False
    assert any(event.breaking for event in result.events)
    assert elapsed < 10.0
