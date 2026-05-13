"""Schema-parity tests for canonical Iceberg DDL provider neutrality.

After M1.12 Phase B retirement, the legacy `CANONICAL_STOCK_BASIC_SPEC`
+ `CANONICAL_MART_TABLE_SPECS` are gone. The remaining canonical
business specs all live under the `canonical_v2` namespace and by
construction must not embed raw-zone lineage fields (`source_run_id`,
`raw_loaded_at`) or provider-shaped identifier columns (`ts_code`,
`index_code`).

Per data-platform CLAUDE.md: Raw Zone (raw lineage) ≠ Canonical Zone.
After M1.12 step 4, `FORBIDDEN_SCHEMA_FIELDS` extends to the raw-zone
lineage block, with a namespace bypass at `_forbidden_schema_fields_for`
that permits them only on `canonical_lineage.*` specs.

These tests are now strict (no xfail). The previous
`_M1D_LEGACY_RETIREMENT_XFAIL` marker was removed in M1.12 Step 5.
"""

from __future__ import annotations

from typing import Final

import pytest

from data_platform.ddl import iceberg_tables


CANONICAL_BUSINESS_SPECS: Final[tuple[iceberg_tables.TableSpec, ...]] = (
    iceberg_tables.CANONICAL_V2_TABLE_SPECS
)
"""All canonical Iceberg specs that hold business rows.

After M1.12 retirement, the canonical business surface is the
`canonical_v2.*` namespace alone — the v2 specs cover the promoted mart
tables plus stock_basic.
"""

FORBIDDEN_RAW_LINEAGE_FIELDS: Final[frozenset[str]] = frozenset(
    {"source_run_id", "raw_loaded_at"}
)
"""Raw-zone lineage columns that must not appear on canonical business rows.

These belong on a sibling `canonical_lineage.*` table, not on canonical
business specs. Per M1-A design + data-platform CLAUDE.md "Raw Zone ≠
Canonical Zone".
"""

FORBIDDEN_PROVIDER_SHAPED_IDENTIFIERS: Final[frozenset[str]] = frozenset(
    {"ts_code", "index_code"}
)
"""Provider-shaped identifier columns that must not appear on canonical
business rows. Provider catalog (`registry.py`) declares the canonical
identifiers (`security_id`, `index_id`, `entity_id`); the physical schema
must adopt the canonical name."""


def _spec_id(spec: iceberg_tables.TableSpec) -> str:
    return f"{spec.namespace}.{spec.name}"


@pytest.mark.parametrize(
    "spec",
    CANONICAL_BUSINESS_SPECS,
    ids=_spec_id,
)
def test_canonical_business_spec_does_not_carry_raw_lineage(
    spec: iceberg_tables.TableSpec,
) -> None:
    """Canonical business rows must not embed raw-zone lineage fields."""

    field_names = {field.name for field in spec.schema}
    leaks = sorted(field_names & FORBIDDEN_RAW_LINEAGE_FIELDS)
    assert not leaks, (
        f"{_spec_id(spec)} embeds raw-zone lineage fields {leaks}; lineage must "
        "live on a sibling canonical_lineage.* table per M1-A design"
    )


@pytest.mark.parametrize(
    "spec",
    CANONICAL_BUSINESS_SPECS,
    ids=_spec_id,
)
def test_canonical_business_spec_does_not_carry_provider_shaped_identifier(
    spec: iceberg_tables.TableSpec,
) -> None:
    """Canonical business rows must use provider-neutral identifier columns."""

    field_names = {field.name for field in spec.schema}
    provider_shaped = sorted(field_names & FORBIDDEN_PROVIDER_SHAPED_IDENTIFIERS)
    assert not provider_shaped, (
        f"{_spec_id(spec)} exposes provider-shaped identifiers {provider_shaped}; "
        "the provider catalog (registry.py field_mapping) declares canonical names "
        "such as security_id / index_id / entity_id — the physical spec must adopt "
        "those names per M1-A design"
    )


def test_FORBIDDEN_SCHEMA_FIELDS_includes_canonical_lineage_block() -> None:
    """`FORBIDDEN_SCHEMA_FIELDS` blocks the raw-zone lineage block.

    After M1.12 step 4, no future canonical business spec can silently
    re-introduce `source_run_id` / `raw_loaded_at`. The
    `canonical_lineage.*` namespace is exempted via
    `_forbidden_schema_fields_for`.
    """

    missing = sorted(FORBIDDEN_RAW_LINEAGE_FIELDS - iceberg_tables.FORBIDDEN_SCHEMA_FIELDS)
    assert not missing, (
        f"FORBIDDEN_SCHEMA_FIELDS does not block {missing}; M1.12 step 4 must "
        "extend it so canonical_v2 specs cannot re-introduce raw-zone lineage"
    )


def test_canonical_lineage_namespace_specs_keep_canonical_pk_first() -> None:
    """Every canonical_lineage.* spec leads with the canonical PK columns."""

    lineage_specs = [
        value
        for name, value in vars(iceberg_tables).items()
        if name.startswith("CANONICAL_LINEAGE_") and isinstance(value, iceberg_tables.TableSpec)
    ]
    assert lineage_specs, (
        "canonical_lineage.* specs must exist after M1.12 retirement"
    )

    for spec in lineage_specs:
        names = list(spec.schema.names)
        assert names, f"{_spec_id(spec)} has empty schema"
        assert spec.namespace == "canonical_lineage", (
            f"{_spec_id(spec)} lives outside canonical_lineage namespace"
        )
        last_metadata = {
            "source_run_id",
            "raw_loaded_at",
            "canonical_loaded_at",
        }
        # The canonical PK columns must come first; metadata columns at the end.
        first_metadata_idx = next(
            (idx for idx, name in enumerate(names) if name in last_metadata),
            len(names),
        )
        for trailing_name in names[first_metadata_idx:]:
            assert trailing_name in last_metadata or trailing_name in {
                "source_provider",
                "source_interface_id",
            }, (
                f"{_spec_id(spec)} mixes business columns and metadata; expected "
                "canonical PK first, then lineage/metadata"
            )


def test_canonical_v2_namespace_specs_do_not_carry_raw_lineage() -> None:
    """Every canonical_v2.* spec must be lineage-free at the storage layer."""

    v2_specs = [
        value
        for name, value in vars(iceberg_tables).items()
        if name.startswith("CANONICAL_V2_") and isinstance(value, iceberg_tables.TableSpec)
    ]
    assert v2_specs, "canonical_v2.* specs must exist after M1.12 retirement"

    for spec in v2_specs:
        field_names = {field.name for field in spec.schema}
        leaks = sorted(field_names & FORBIDDEN_RAW_LINEAGE_FIELDS)
        provider_shaped = sorted(field_names & FORBIDDEN_PROVIDER_SHAPED_IDENTIFIERS)
        assert not leaks and not provider_shaped, (
            f"{_spec_id(spec)} (canonical_v2) leaks {leaks or provider_shaped}; "
            "canonical_v2 must be lineage-free and provider-neutral by construction"
        )
        assert spec.namespace == "canonical_v2", (
            f"{_spec_id(spec)} mis-namespaces a CANONICAL_V2_ spec outside the "
            "canonical_v2 namespace"
        )


def test_FORBIDDEN_RAW_LINEAGE_FIELDS_set_is_stable() -> None:
    """Sentinel: the forbidden set used by this file is a stable contract.

    If a future change wants to expand the set (e.g., to include
    `source_provider` on canonical business rows), update this test
    intentionally rather than silently widening the contract.
    """

    assert FORBIDDEN_RAW_LINEAGE_FIELDS == frozenset({"source_run_id", "raw_loaded_at"})
    assert FORBIDDEN_PROVIDER_SHAPED_IDENTIFIERS == frozenset({"ts_code", "index_code"})
