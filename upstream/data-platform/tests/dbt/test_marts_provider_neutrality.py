"""dbt mart SQL parity tests for provider-neutrality.

After M1.14 cleanup, the legacy `dbt/models/marts/` directory is gone. The
remaining canonical write surface is `marts_v2/*` (provider-neutral business
columns) + `marts_lineage/*` (provider-attributed lineage columns). These
tests assert each side carries what it should and rejects what it should not.

Per data-platform CLAUDE.md "Raw Zone ≠ Canonical Zone": canonical_v2 marts
must not surface raw-zone lineage (`source_run_id`, `raw_loaded_at`) and must
not forward provider-shaped identifiers (`ts_code`, `index_code`); lineage
marts must explicitly carry the lineage block.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Final, Iterable

import pytest


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
V2_MARTS_DIR: Final[Path] = (
    PROJECT_ROOT / "src" / "data_platform" / "dbt" / "models" / "marts_v2"
)
LINEAGE_MARTS_DIR: Final[Path] = (
    PROJECT_ROOT / "src" / "data_platform" / "dbt" / "models" / "marts_lineage"
)
DERIVATION_MARTS_DIR: Final[Path] = (
    PROJECT_ROOT / "src" / "data_platform" / "dbt" / "models" / "marts_derivations"
)

FORBIDDEN_LINEAGE_TOKENS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"(?<![A-Za-z0-9_])source_run_id(?![A-Za-z0-9_])"),
    re.compile(r"(?<![A-Za-z0-9_])raw_loaded_at(?![A-Za-z0-9_])"),
)
FORBIDDEN_PROVIDER_SHAPED_TOKENS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"(?<![A-Za-z0-9_])ts_code(?![A-Za-z0-9_])"),
    re.compile(r"(?<![A-Za-z0-9_])index_code(?![A-Za-z0-9_])"),
)


def _v2_mart_sql_files() -> Iterable[Path]:
    if not V2_MARTS_DIR.is_dir():
        return ()
    return sorted(p for p in V2_MARTS_DIR.glob("*.sql") if p.is_file())


def _lineage_mart_sql_files() -> Iterable[Path]:
    if not LINEAGE_MARTS_DIR.is_dir():
        return ()
    return sorted(p for p in LINEAGE_MARTS_DIR.glob("*.sql") if p.is_file())


def _derivation_mart_sql_files() -> Iterable[Path]:
    if not DERIVATION_MARTS_DIR.is_dir():
        return ()
    return sorted(p for p in DERIVATION_MARTS_DIR.glob("*.sql") if p.is_file())


@pytest.mark.parametrize(
    "mart_sql",
    list(_v2_mart_sql_files()),
    ids=lambda p: p.name,
)
def test_canonical_v2_mart_sql_does_not_select_lineage_columns(
    mart_sql: Path,
) -> None:
    """Canonical_v2 mart SQL must be lineage-free at the SELECT."""

    body = mart_sql.read_text(encoding="utf-8")
    leaks = sorted(
        match.group(0)
        for pattern in FORBIDDEN_LINEAGE_TOKENS
        for match in pattern.finditer(body)
    )
    assert not leaks, (
        f"{mart_sql.relative_to(PROJECT_ROOT)} (canonical_v2) surfaces lineage "
        f"{sorted(set(leaks))}"
    )


@pytest.mark.parametrize(
    "mart_sql",
    list(_v2_mart_sql_files()),
    ids=lambda p: p.name,
)
def test_canonical_v2_mart_sql_does_not_select_provider_shaped_identifier(
    mart_sql: Path,
) -> None:
    """Canonical_v2 mart SELECT must not forward provider-shaped identifiers.

    Acceptable inside the SQL is `... ts_code AS security_id ...` (alias). The
    test scans for bare `ts_code` references not followed by ` AS ` within a
    short window, to avoid false-positives on aliases.
    """

    body = mart_sql.read_text(encoding="utf-8")
    if not body.strip():
        pytest.skip(f"{mart_sql.name} is empty")

    bare_provider_shaped: list[str] = []
    for pattern in FORBIDDEN_PROVIDER_SHAPED_TOKENS:
        for match in pattern.finditer(body):
            start = match.end()
            window = body[start : start + 8].lower().lstrip()
            if window.startswith("as "):
                continue
            bare_provider_shaped.append(match.group(0))
    assert not bare_provider_shaped, (
        f"{mart_sql.relative_to(PROJECT_ROOT)} (canonical_v2) forwards bare "
        f"provider-shaped identifier {sorted(set(bare_provider_shaped))}; rename via "
        "`<provider> AS <canonical_id>` is required"
    )


@pytest.mark.parametrize(
    "mart_sql",
    list(_lineage_mart_sql_files()),
    ids=lambda p: p.name,
)
def test_lineage_mart_sql_carries_lineage_columns(
    mart_sql: Path,
) -> None:
    """canonical_lineage marts must carry source_run_id + raw_loaded_at SELECT."""

    body = mart_sql.read_text(encoding="utf-8").lower()
    if not body.strip():
        pytest.skip(f"{mart_sql.name} is empty")

    assert "source_run_id" in body, (
        f"{mart_sql.relative_to(PROJECT_ROOT)} (lineage mart) must SELECT source_run_id"
    )
    assert "raw_loaded_at" in body, (
        f"{mart_sql.relative_to(PROJECT_ROOT)} (lineage mart) must SELECT raw_loaded_at"
    )


def test_dim_security_lineage_mart_discloses_composite_source_interface() -> None:
    """dim_security lineage must not claim all contributed fields came from stock_basic."""

    mart_sql = LINEAGE_MARTS_DIR / "mart_lineage_dim_security.sql"
    body = mart_sql.read_text(encoding="utf-8").lower()

    assert "concat_ws(" in body
    assert "stock_basic" in body
    assert "stock_company" in body
    assert "namechange" in body
    assert "stock_basic_source_run_id" in body
    assert "stock_company_source_run_id" in body
    assert "namechange_source_run_id" in body
    assert "cast('stock_basic' as varchar) as source_interface_id" not in body


@pytest.mark.parametrize(
    "mart_sql",
    list(_derivation_mart_sql_files()),
    ids=lambda p: p.name,
)
def test_derivation_business_mart_sql_is_provider_neutral(mart_sql: Path) -> None:
    """Derivation business marts must only expose provider-neutral fields."""

    body = mart_sql.read_text(encoding="utf-8")
    lowered = body.lower()
    forbidden_patterns = (
        *FORBIDDEN_LINEAGE_TOKENS,
        *FORBIDDEN_PROVIDER_SHAPED_TOKENS,
        re.compile(r"ref\(['\"]stg_"),
        re.compile(r"tushare"),
    )
    leaks = sorted(
        match.group(0)
        for pattern in forbidden_patterns
        for match in pattern.finditer(lowered)
    )

    assert not leaks, (
        f"{mart_sql.relative_to(PROJECT_ROOT)} (derivation business mart) "
        f"leaks provider/raw tokens {sorted(set(leaks))}"
    )
