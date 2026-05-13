"""Schema-parity tests for canonical writer provider-neutrality.

After M1.12 Phase B retirement, the legacy `CANONICAL_MART_LOAD_SPECS`
+ `load_canonical_marts` write surface is gone. The remaining canonical
write path is `CANONICAL_V2_MART_LOAD_SPECS` + the paired
`CANONICAL_LINEAGE_MART_LOAD_SPECS`. By construction:

* `canonical_v2.*` load specs must NOT require raw-zone lineage
  (`source_run_id`, `raw_loaded_at`) or provider-shaped identifiers
  (`ts_code`, `index_code`).
* `canonical_lineage.*` load specs MUST require `source_run_id` +
  `raw_loaded_at` because that is exactly what the lineage namespace
  is for.

These tests are now strict (no xfail). The previous
`_M1D_LEGACY_RETIREMENT_XFAIL` marker was removed in M1.12 Step 5.
"""

from __future__ import annotations

from typing import Final

import pytest

from data_platform.serving import canonical_writer


FORBIDDEN_LINEAGE_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset(
    {"source_run_id", "raw_loaded_at"}
)
FORBIDDEN_PROVIDER_SHAPED_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset(
    {"ts_code", "index_code"}
)


def _spec_id(spec: canonical_writer.CanonicalLoadSpec) -> str:
    return spec.identifier


@pytest.mark.parametrize(
    "spec",
    canonical_writer.CANONICAL_V2_MART_LOAD_SPECS,
    ids=_spec_id,
)
def test_canonical_v2_mart_load_spec_does_not_require_raw_lineage(
    spec: canonical_writer.CanonicalLoadSpec,
) -> None:
    """Canonical_v2 mart writer specs must not require raw-zone lineage."""

    required = set(spec.required_columns)
    leaks = sorted(required & FORBIDDEN_LINEAGE_REQUIRED_COLUMNS)
    assert not leaks, (
        f"{_spec_id(spec)} writer spec requires raw-zone lineage {leaks}; "
        "lineage must be loaded via the sibling CANONICAL_LINEAGE_MART_LOAD_SPECS entry"
    )


@pytest.mark.parametrize(
    "spec",
    canonical_writer.CANONICAL_V2_MART_LOAD_SPECS,
    ids=_spec_id,
)
def test_canonical_v2_mart_load_spec_does_not_require_provider_shaped_identifier(
    spec: canonical_writer.CanonicalLoadSpec,
) -> None:
    """Canonical_v2 mart writer specs must use provider-neutral identifier columns."""

    required = set(spec.required_columns)
    provider_shaped = sorted(required & FORBIDDEN_PROVIDER_SHAPED_REQUIRED_COLUMNS)
    assert not provider_shaped, (
        f"{_spec_id(spec)} writer spec requires provider-shaped identifier "
        f"columns {provider_shaped}; the canonical contract uses security_id / "
        "index_id / entity_id"
    )


def test_FORBIDDEN_PAYLOAD_FIELDS_extends_to_canonical_lineage() -> None:
    """`FORBIDDEN_PAYLOAD_FIELDS` blocks the raw-zone lineage block.

    After M1.12 step 4, the canonical-business write path rejects
    `source_run_id` / `raw_loaded_at`. The lineage namespace bypass at
    `_forbidden_payload_fields_for` permits them only on
    `canonical_lineage.*` identifiers.
    """

    missing = sorted(FORBIDDEN_LINEAGE_REQUIRED_COLUMNS - canonical_writer.FORBIDDEN_PAYLOAD_FIELDS)
    assert not missing, (
        f"FORBIDDEN_PAYLOAD_FIELDS does not block {missing}; M1.12 step 4 must "
        "extend the set so canonical_v2 spec creation rejects raw-zone lineage"
    )


def test_canonical_v2_load_specs_drop_raw_lineage() -> None:
    """Every CANONICAL_V2_*_LOAD_SPEC must be lineage-free at the writer boundary."""

    v2_load_specs_collections = [
        value
        for name, value in vars(canonical_writer).items()
        if name.startswith("CANONICAL_V2_")
        and isinstance(value, tuple)
        and value
        and isinstance(value[0], canonical_writer.CanonicalLoadSpec)
    ]
    assert v2_load_specs_collections, (
        "CANONICAL_V2_*_LOAD_SPECS must exist after M1.12 retirement"
    )

    for collection in v2_load_specs_collections:
        for spec in collection:
            required = set(spec.required_columns)
            leaks = sorted(required & FORBIDDEN_LINEAGE_REQUIRED_COLUMNS)
            assert not leaks, (
                f"{spec.identifier} (canonical_v2) requires raw-zone lineage {leaks}; "
                "v2 must be lineage-free by construction"
            )
            provider_shaped = sorted(required & FORBIDDEN_PROVIDER_SHAPED_REQUIRED_COLUMNS)
            assert not provider_shaped, (
                f"{spec.identifier} (canonical_v2) requires provider-shaped "
                f"identifier {provider_shaped}; rename via field_mapping must apply"
            )


def test_canonical_lineage_load_specs_carry_lineage_explicitly() -> None:
    """Every CANONICAL_LINEAGE_*_LOAD_SPEC must require lineage columns."""

    lineage_load_specs_collections = [
        value
        for name, value in vars(canonical_writer).items()
        if name.startswith("CANONICAL_LINEAGE_")
        and isinstance(value, tuple)
        and value
        and isinstance(value[0], canonical_writer.CanonicalLoadSpec)
    ]
    assert lineage_load_specs_collections, (
        "CANONICAL_LINEAGE_*_LOAD_SPECS must exist after M1.12 retirement"
    )

    for collection in lineage_load_specs_collections:
        for spec in collection:
            required = set(spec.required_columns)
            assert "source_run_id" in required, (
                f"{spec.identifier} (canonical_lineage) must require source_run_id"
            )
            assert "raw_loaded_at" in required, (
                f"{spec.identifier} (canonical_lineage) must require raw_loaded_at"
            )
