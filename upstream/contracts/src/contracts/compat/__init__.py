"""JSON Schema 兼容性检查库入口。"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

from pydantic import Field

from contracts.core import ContractBaseModel, Severity
from contracts.export import export_json_schemas


class CompatibilityRule(ContractBaseModel):
    """单条兼容性规则定义。"""

    rule_id: str = Field(min_length=1)
    rule_name: str = Field(min_length=1)
    severity: Severity
    description: str = Field(min_length=1)
    applies_to: tuple[str, ...]


class CompatibilityEvent(ContractBaseModel):
    """兼容性检查发现的单个变更事件。"""

    schema_name: str
    change_type: str
    json_pointer: str
    message: str
    breaking: bool


class CompatibilityCheckResult(ContractBaseModel):
    """一次 schema set 兼容性检查结果。"""

    baseline: str
    current: str
    events: tuple[CompatibilityEvent, ...]

    @property
    def is_compatible(self) -> bool:
        """没有 breaking event 即兼容。"""

        return not any(event.breaking for event in self.events)


COMPATIBILITY_RULES: tuple[CompatibilityRule, ...] = (
    CompatibilityRule(
        rule_id="schema_removed",
        rule_name="Schema removal",
        severity=Severity.ERROR,
        description="Exported schema files must not be removed.",
        applies_to=("schema",),
    ),
    CompatibilityRule(
        rule_id="field_removed",
        rule_name="Field removal",
        severity=Severity.ERROR,
        description="Existing JSON Schema properties must not be removed.",
        applies_to=("properties",),
    ),
    CompatibilityRule(
        rule_id="required_field_changed",
        rule_name="Required field change",
        severity=Severity.ERROR,
        description="Required field additions or removals are breaking changes.",
        applies_to=("required",),
    ),
    CompatibilityRule(
        rule_id="field_shape_changed",
        rule_name="Field shape change",
        severity=Severity.ERROR,
        description="Field type, $ref, anyOf, or oneOf changes are breaking.",
        applies_to=("properties",),
    ),
    CompatibilityRule(
        rule_id="optional_field_added",
        rule_name="Optional field addition",
        severity=Severity.INFO,
        description="New optional JSON Schema properties are compatible changes.",
        applies_to=("properties",),
    ),
    CompatibilityRule(
        rule_id="enum_value_changed",
        rule_name="Enum value change",
        severity=Severity.ERROR,
        description="Enum value removals are breaking; additions are compatible.",
        applies_to=("enum",),
    ),
    CompatibilityRule(
        rule_id="schema_invariant_changed",
        rule_name="Schema invariant change",
        severity=Severity.ERROR,
        description="JSON Schema dependent invariants must not change silently.",
        applies_to=("allOf", "x-contract-runtime-invariants"),
    ),
    CompatibilityRule(
        rule_id="field_runtime_validation_changed",
        rule_name="Field runtime validation change",
        severity=Severity.ERROR,
        description=(
            "Runtime scalar validation metadata such as strictness must not "
            "change silently."
        ),
        applies_to=("properties",),
    ),
)


def load_schema_directory(path: str | Path) -> dict[str, dict[str, object]]:
    """读取 JSON Schema 导出目录，并按 schema name 返回 schema 内容。"""

    return _load_schema_directory(path, allow_missing_schema_files=False)


def _load_schema_directory(
    path: str | Path,
    *,
    allow_missing_schema_files: bool,
) -> dict[str, dict[str, object]]:
    schema_dir = Path(path)
    manifest_path = schema_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"manifest.json not found in schema directory: {schema_dir}")

    manifest = _read_json_object(manifest_path)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError(f"manifest artifacts must be a list: {manifest_path}")

    schemas: dict[str, dict[str, object]] = {}
    seen_schema_names: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, Mapping):
            raise ValueError(f"manifest artifact #{index} must be an object")

        schema_name = artifact.get("name")
        if not isinstance(schema_name, str) or not schema_name:
            raise ValueError(f"manifest artifact #{index} has invalid schema name")

        if schema_name in seen_schema_names:
            raise ValueError(f"duplicate schema name in manifest: {schema_name}")
        seen_schema_names.add(schema_name)

        schema_path = schema_dir / f"{schema_name}.schema.json"
        if not schema_path.is_file():
            if allow_missing_schema_files:
                continue
            raise ValueError(
                f"schema file missing for {schema_name}: {schema_path}"
            )

        schemas[schema_name] = _read_json_object(schema_path)

    return schemas


def compare_schema_sets(
    baseline: Mapping[str, dict[str, object]],
    current: Mapping[str, dict[str, object]],
    *,
    baseline_label: str = "baseline",
    current_label: str = "current",
) -> CompatibilityCheckResult:
    """比较两个 JSON Schema set，并返回兼容性事件。"""

    events: list[CompatibilityEvent] = []
    baseline_names = set(baseline)
    current_names = set(current)

    for schema_name in sorted(baseline_names.difference(current_names)):
        events.append(
            CompatibilityEvent(
                schema_name=schema_name,
                change_type="schema_removed",
                json_pointer="",
                message=f"schema {schema_name!r} is missing from current export",
                breaking=True,
            )
        )

    for schema_name in sorted(baseline_names.intersection(current_names)):
        _compare_schema(
            schema_name,
            baseline[schema_name],
            current[schema_name],
            events,
        )

    return CompatibilityCheckResult(
        baseline=baseline_label,
        current=current_label,
        events=tuple(events),
    )


def check_compatibility(
    baseline: str | Path,
    current: str | Path = "HEAD",
) -> CompatibilityCheckResult:
    """加载导出目录并执行兼容性检查。"""

    baseline_schemas = _load_schema_reference(
        baseline,
        allow_missing_schema_files=False,
    )
    baseline_label = str(baseline)

    if str(current) == "HEAD":
        with tempfile.TemporaryDirectory(prefix="contracts-compat-current-") as tmp_dir:
            export_json_schemas(tmp_dir)
            current_schemas = load_schema_directory(tmp_dir)
            return compare_schema_sets(
                baseline_schemas,
                current_schemas,
                baseline_label=baseline_label,
                current_label="HEAD",
            )

    current_schemas = _load_schema_reference(
        current,
        allow_missing_schema_files=True,
    )
    return compare_schema_sets(
        baseline_schemas,
        current_schemas,
        baseline_label=baseline_label,
        current_label=str(current),
    )


def _load_schema_reference(
    reference: str | Path,
    *,
    allow_missing_schema_files: bool,
) -> dict[str, dict[str, object]]:
    filesystem_dir = _resolve_schema_directory(reference)
    if (filesystem_dir / "manifest.json").is_file():
        return _load_schema_directory(
            filesystem_dir,
            allow_missing_schema_files=allow_missing_schema_files,
        )

    packaged_dir = _resolve_packaged_schema_directory(reference)
    if packaged_dir is not None:
        with resources.as_file(packaged_dir) as schema_dir:
            return _load_schema_directory(
                schema_dir,
                allow_missing_schema_files=allow_missing_schema_files,
            )

    return _load_schema_directory(
        filesystem_dir,
        allow_missing_schema_files=allow_missing_schema_files,
    )


def _resolve_schema_directory(reference: str | Path) -> Path:
    candidate = Path(reference)
    if (candidate / "manifest.json").is_file():
        return candidate

    version = str(reference)
    project_root = Path(__file__).resolve().parents[3]
    for root in (project_root, Path.cwd()):
        baseline_dir = root / "artifacts" / "baselines" / version / "json_schema"
        if (baseline_dir / "manifest.json").is_file():
            return baseline_dir

    return candidate


def _resolve_packaged_schema_directory(reference: str | Path) -> Traversable | None:
    version = str(reference)
    if not version or "/" in version or "\\" in version:
        return None

    baseline_dir = resources.files("contracts").joinpath(
        "baselines",
        version,
        "json_schema",
    )
    if baseline_dir.joinpath("manifest.json").is_file():
        return baseline_dir

    return None


def _compare_schema(
    schema_name: str,
    baseline_schema: Mapping[str, object],
    current_schema: Mapping[str, object],
    events: list[CompatibilityEvent],
) -> None:
    baseline_properties = _object_mapping(baseline_schema.get("properties"))
    current_properties = _object_mapping(current_schema.get("properties"))
    baseline_required = _string_set(baseline_schema.get("required"))
    current_required = _string_set(current_schema.get("required"))

    removed_fields = set(baseline_properties).difference(current_properties)
    for field_name in sorted(removed_fields):
        events.append(
            CompatibilityEvent(
                schema_name=schema_name,
                change_type="field_removed",
                json_pointer=f"/properties/{_escape_json_pointer(field_name)}",
                message=f"field {field_name!r} was removed",
                breaking=True,
            )
        )

    added_fields = set(current_properties).difference(baseline_properties)
    for field_name in sorted(added_fields.difference(current_required)):
        events.append(
            CompatibilityEvent(
                schema_name=schema_name,
                change_type="optional_field_added",
                json_pointer=f"/properties/{_escape_json_pointer(field_name)}",
                message=f"optional field {field_name!r} was added",
                breaking=False,
            )
        )

    for field_name in sorted(baseline_required.difference(current_required)):
        if field_name in removed_fields:
            continue
        events.append(
            CompatibilityEvent(
                schema_name=schema_name,
                change_type="required_field_removed",
                json_pointer=f"/required/{_escape_json_pointer(field_name)}",
                message=f"field {field_name!r} was removed from required",
                breaking=True,
            )
        )

    for field_name in sorted(current_required.difference(baseline_required)):
        events.append(
            CompatibilityEvent(
                schema_name=schema_name,
                change_type="required_field_added",
                json_pointer=f"/required/{_escape_json_pointer(field_name)}",
                message=f"field {field_name!r} was added to required",
                breaking=True,
            )
        )

    common_fields = set(baseline_properties).intersection(current_properties)
    for field_name in sorted(common_fields):
        _compare_property_shape(
            schema_name,
            field_name,
            baseline_properties[field_name],
            current_properties[field_name],
            events,
        )

    allowed_resolution_case_relaxation = (
        _is_resolution_case_candidate_entities_relaxation(
            schema_name,
            baseline_schema,
            current_schema,
        )
    )
    ignored_enum_pointers = (
        frozenset({"/allOf/1/if/properties/decision/enum"})
        if allowed_resolution_case_relaxation
        else frozenset()
    )

    _compare_enums(
        schema_name,
        baseline_schema,
        current_schema,
        events,
        ignored_pointers=ignored_enum_pointers,
    )
    _compare_contract_extensions(
        schema_name,
        baseline_schema,
        current_schema,
        events,
        allowed_resolution_case_relaxation=allowed_resolution_case_relaxation,
    )


def _compare_property_shape(
    schema_name: str,
    field_name: str,
    baseline_property: object,
    current_property: object,
    events: list[CompatibilityEvent],
) -> None:
    if not isinstance(baseline_property, Mapping) or not isinstance(
        current_property, Mapping
    ):
        if baseline_property != current_property:
            events.append(
                CompatibilityEvent(
                    schema_name=schema_name,
                    change_type="field_schema_changed",
                    json_pointer=f"/properties/{_escape_json_pointer(field_name)}",
                    message=f"field {field_name!r} schema changed",
                    breaking=True,
                )
            )
        return

    checks = (
        ("type", "field_type_changed", "type"),
        ("$ref", "field_ref_changed", "$ref"),
        ("anyOf", "field_any_of_changed", "anyOf"),
        ("oneOf", "field_one_of_changed", "oneOf"),
        (
            "x-contract-runtime-validation",
            "field_runtime_validation_changed",
            "runtime validation",
        ),
    )
    for key, change_type, label in checks:
        baseline_value = baseline_property.get(key)
        current_value = current_property.get(key)
        if baseline_value == current_value:
            continue

        pointer_key = _escape_json_pointer(key)
        events.append(
            CompatibilityEvent(
                schema_name=schema_name,
                change_type=change_type,
                json_pointer=(
                    f"/properties/{_escape_json_pointer(field_name)}/{pointer_key}"
                ),
                message=f"field {field_name!r} {label} changed",
                breaking=True,
            )
        )


def _compare_contract_extensions(
    schema_name: str,
    baseline_schema: Mapping[str, object],
    current_schema: Mapping[str, object],
    events: list[CompatibilityEvent],
    *,
    allowed_resolution_case_relaxation: bool = False,
) -> None:
    baseline_extensions = _collect_contract_extension_values(baseline_schema)
    current_extensions = _collect_contract_extension_values(current_schema)

    for pointer in sorted(set(baseline_extensions).union(current_extensions)):
        if baseline_extensions.get(pointer) == current_extensions.get(pointer):
            continue
        if (
            pointer == "/allOf"
            and allowed_resolution_case_relaxation
            and _resolution_case_all_of_relaxation_is_exact(
                baseline_schema,
                current_schema,
            )
        ):
            continue

        events.append(
            CompatibilityEvent(
                schema_name=schema_name,
                change_type="schema_invariant_changed",
                json_pointer=pointer,
                message=f"contract invariant metadata changed at {pointer}",
                breaking=True,
            )
        )


def _collect_contract_extension_values(
    value: object,
    pointer: str = "",
) -> dict[str, object]:
    extensions: dict[str, object] = {}

    if isinstance(value, Mapping):
        for key in ("allOf", "x-contract-runtime-invariants"):
            if key in value:
                key_pointer = f"{pointer}/{_escape_json_pointer(key)}"
                extensions[key_pointer] = value[key]

        for key, child in value.items():
            child_pointer = f"{pointer}/{_escape_json_pointer(str(key))}"
            extensions.update(_collect_contract_extension_values(child, child_pointer))

    if isinstance(value, list):
        for index, child in enumerate(value):
            child_pointer = f"{pointer}/{index}"
            extensions.update(_collect_contract_extension_values(child, child_pointer))

    return extensions


def _compare_enums(
    schema_name: str,
    baseline_schema: Mapping[str, object],
    current_schema: Mapping[str, object],
    events: list[CompatibilityEvent],
    *,
    ignored_pointers: frozenset[str] = frozenset(),
) -> None:
    baseline_enums = _collect_enums(baseline_schema)
    current_enums = _collect_enums(current_schema)

    for pointer in sorted(set(baseline_enums).union(current_enums)):
        if pointer in ignored_pointers:
            continue
        baseline_values = baseline_enums.get(pointer, ())
        current_values = current_enums.get(pointer, ())

        removed_values = _ordered_difference(baseline_values, current_values)
        if removed_values:
            events.append(
                CompatibilityEvent(
                    schema_name=schema_name,
                    change_type="enum_value_removed",
                    json_pointer=pointer,
                    message=(
                        "enum values were removed: "
                        + ", ".join(repr(value) for value in removed_values)
                    ),
                    breaking=True,
                )
            )

        added_values = _ordered_difference(current_values, baseline_values)
        if added_values:
            events.append(
                CompatibilityEvent(
                    schema_name=schema_name,
                    change_type="enum_value_added",
                    json_pointer=pointer,
                    message=(
                        "enum values were added: "
                        + ", ".join(repr(value) for value in added_values)
                    ),
                    breaking=False,
                )
            )


def _collect_enums(value: object, pointer: str = "") -> dict[str, tuple[object, ...]]:
    enums: dict[str, tuple[object, ...]] = {}

    if isinstance(value, Mapping):
        enum_value = value.get("enum")
        if isinstance(enum_value, list):
            enum_pointer = f"{pointer}/enum" if pointer else "/enum"
            enums[enum_pointer] = tuple(enum_value)

        for key, child in value.items():
            child_pointer = f"{pointer}/{_escape_json_pointer(str(key))}"
            enums.update(_collect_enums(child, child_pointer))

    if isinstance(value, list):
        for index, child in enumerate(value):
            child_pointer = f"{pointer}/{index}"
            enums.update(_collect_enums(child, child_pointer))

    return enums


_RESOLUTION_CASE_LEGACY_ALLOF: list[dict[str, object]] = [
    {
        "if": {"properties": {"decision": {"const": "matched"}}},
        "then": {
            "properties": {"resolved_entity": {"not": {"type": "null"}}},
            "required": ["resolved_entity"],
        },
    },
    {
        "if": {
            "properties": {
                "decision": {"enum": ["ambiguous", "unresolved"]},
            }
        },
        "then": {"properties": {"resolved_entity": {"type": "null"}}},
    },
]

_RESOLUTION_CASE_RELAXED_ALLOF: list[dict[str, object]] = [
    {
        "if": {"properties": {"decision": {"const": "matched"}}},
        "then": {
            "properties": {
                "candidate_entities": {"minItems": 1},
                "resolved_entity": {"not": {"type": "null"}},
            },
            "required": ["resolved_entity"],
        },
    },
    {
        "if": {"properties": {"decision": {"const": "ambiguous"}}},
        "then": {
            "properties": {
                "candidate_entities": {"minItems": 1},
                "resolved_entity": {"type": "null"},
            },
        },
    },
    {
        "if": {"properties": {"decision": {"const": "unresolved"}}},
        "then": {"properties": {"resolved_entity": {"type": "null"}}},
    },
]


def _is_resolution_case_candidate_entities_relaxation(
    schema_name: str,
    baseline_schema: Mapping[str, object],
    current_schema: Mapping[str, object],
) -> bool:
    """Allow the approved v0.1.3 ResolutionCase no-candidate relaxation.

    The v0.1.0 export had ``candidate_entities.minItems=1`` globally.
    Runtime v0.1.3 relaxed only the unresolved branch so unresolved/no-
    candidate cases are valid, while matched and ambiguous still require
    candidates. This is a compatibility relaxation, not a breaking schema
    invariant change, as long as the current JSON Schema encodes exactly
    that conditional shape.
    """

    if schema_name != "resolution_case":
        return False

    baseline_candidates = _schema_property(baseline_schema, "candidate_entities")
    current_candidates = _schema_property(current_schema, "candidate_entities")
    if baseline_candidates.get("minItems") != 1:
        return False
    if "minItems" in current_candidates:
        return False

    return _resolution_case_all_of_relaxation_is_exact(
        baseline_schema,
        current_schema,
    )


def _resolution_case_all_of_relaxation_is_exact(
    baseline_schema: Mapping[str, object],
    current_schema: Mapping[str, object],
) -> bool:
    return (
        baseline_schema.get("allOf") == _RESOLUTION_CASE_LEGACY_ALLOF
        and current_schema.get("allOf") == _RESOLUTION_CASE_RELAXED_ALLOF
    )


def _schema_property(
    schema: Mapping[str, object],
    property_name: str,
) -> Mapping[str, object]:
    return _object_mapping(
        _object_mapping(schema.get("properties")).get(property_name)
    )


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"JSON document must be an object: {path}")

    return data


def _object_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return {}

    return {str(key): item for key, item in value.items()}


def _string_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()

    return {item for item in value if isinstance(item, str)}


def _ordered_difference(
    candidate_values: tuple[object, ...],
    existing_values: tuple[object, ...],
) -> tuple[object, ...]:
    return tuple(value for value in candidate_values if value not in existing_values)


def _escape_json_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


__all__ = [
    "CompatibilityRule",
    "CompatibilityEvent",
    "CompatibilityCheckResult",
    "COMPATIBILITY_RULES",
    "load_schema_directory",
    "compare_schema_sets",
    "check_compatibility",
]
