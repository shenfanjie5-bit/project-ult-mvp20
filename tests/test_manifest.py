from pathlib import Path

import yaml

from mvp20.manifest import (
    INDUSTRY_COUNT,
    MAX_INDUSTRY_IDS_PER_CONSTITUENT,
    VALID_GRAPH_STATUSES,
    VALID_POOLS,
    VALID_ROLES,
    validate_industry_set,
    validate_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "config" / "mvp20.universe.yaml"
INDUSTRIES_PATH = ROOT / "config" / "mvp20.industries.yaml"


def test_industry_set_has_exactly_13_entries() -> None:
    result = validate_industry_set(INDUSTRIES_PATH)

    assert result.ok, result.errors
    assert len(result.industry_ids) == INDUSTRY_COUNT


def test_industry_set_records_graph_status_per_industry() -> None:
    result = validate_industry_set(INDUSTRIES_PATH)

    assert result.ok, result.errors
    assert set(result.industry_graph_status) == set(result.industry_ids)
    # SPACE_ECONOMY is the only one currently pending; everything else is
    # present.
    assert result.industry_graph_status["SPACE_ECONOMY"] == "pending"
    for industry_id, status in result.industry_graph_status.items():
        assert status in VALID_GRAPH_STATUSES
        if industry_id != "SPACE_ECONOMY":
            assert status == "present"


def test_industry_set_rejects_unknown_graph_status(tmp_path: Path) -> None:
    payload = yaml.safe_load(INDUSTRIES_PATH.read_text(encoding="utf-8"))
    payload["industries"][0]["graph_status"] = "weird"
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")

    result = validate_industry_set(path)

    assert not result.ok
    assert any("graph_status must be one of" in e for e in result.errors)


def test_real_universe_manifest_validates_with_pending_warning() -> None:
    result = validate_manifest(MANIFEST_PATH)

    assert result.ok, result.errors
    assert result.industry_count == INDUSTRY_COUNT
    # Real leader pool has > 100 ts_codes (A + HK + US).
    assert result.constituent_count > 100
    assert result.live_evidence_blocked is True
    # SPACE_ECONOMY is pending → its missing-constituent state is recorded
    # but only as a warning, not an error.
    assert result.industries_missing_constituents == ("SPACE_ECONOMY",)
    assert any("SPACE_ECONOMY" in w for w in result.warnings)


def test_manifest_rejects_duplicate_constituent_ts_codes(tmp_path: Path) -> None:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["constituents"][1]["ts_code"] = manifest["constituents"][0]["ts_code"]
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    result = validate_manifest(path, industries_path=INDUSTRIES_PATH)

    assert not result.ok
    assert any(error.startswith("duplicate constituent") for error in result.errors)


def test_manifest_rejects_unknown_industry_slug(tmp_path: Path) -> None:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["constituents"][0]["industry_ids"] = ["NOT_A_REAL_INDUSTRY"]
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    result = validate_manifest(path, industries_path=INDUSTRIES_PATH)

    assert not result.ok
    assert any(
        "unknown industry slug" in error for error in result.errors
    )


def test_present_industry_without_any_constituent_is_error(
    tmp_path: Path,
) -> None:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    # Strip every constituent that mentions AI_COMPUTE so that this
    # *present* industry ends up with zero members. Other industries keep
    # their constituents.
    manifest["constituents"] = [
        c for c in manifest["constituents"]
        if "AI_COMPUTE" not in c["industry_ids"]
    ]
    # Re-add at least one entry that doesn't reference AI_COMPUTE so we
    # don't trip the "must contain at least one entry" guard.
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    result = validate_manifest(path, industries_path=INDUSTRIES_PATH)

    assert not result.ok
    assert any(
        "industries without any constituent" in error and "AI_COMPUTE" in error
        for error in result.errors
    )


def test_manifest_accepts_hk_and_us_ts_codes(tmp_path: Path) -> None:
    """5-digit HK code + US ADR + Berkshire-style multi-dot US code."""

    manifest = {
        "schema_version": 2,
        "universe_id": "mvp-13-industry-v1",
        "status": "test",
        "live_evidence_blocked": True,
        "history_window_months": 120,
        "graph_depth": 2,
        "related_entity_policy": "graph_and_risk_summary_only",
        "industry_set_ref": "mvp20-industries-v1",
        "constituents": [
            {
                "ts_code": "09988.HK",
                "name": "Alibaba",
                "role": "target",
                "industry_ids": ["HK_CN_INTERNET"],
            },
            {
                "ts_code": "BABA.US",
                "name": "Alibaba ADR",
                "role": "both",
                "industry_ids": ["HK_CN_INTERNET"],
            },
            {
                "ts_code": "BRK.B.US",
                "name": "Berkshire Hathaway",
                "role": "target",
                "industry_ids": ["FINANCIAL_HIGH_DIVIDEND"],
            },
        ]
        + [
            {
                "ts_code": f"{i:06d}.SH",
                "name": f"placeholder_{slug}",
                "role": "target",
                "industry_ids": [slug],
            }
            for i, slug in enumerate(
                [
                    "AI_COMPUTE",
                    "SEMI_EQUIPMENT",
                    "ROBOTICS",
                    "NONFERROUS_METALS",
                    "INNOVATIVE_PHARMA",
                    "STORAGE_GRID",
                    "EXPORT_MFG",
                    "ANTI_INVOLUTION_CYCLICAL",
                    "DOMESTIC_CONSUMPTION",
                    "CONSUMER_ELECTRONICS",
                ],
                start=1,
            )
        ],
    }
    path = tmp_path / "ok.yaml"
    path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")

    result = validate_manifest(path, industries_path=INDUSTRIES_PATH)

    assert result.ok, result.errors


def test_manifest_max_industry_ids_is_three(tmp_path: Path) -> None:
    """3 industries on a single constituent passes; 4 fails."""

    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["constituents"][0]["industry_ids"] = [
        "AI_COMPUTE",
        "SEMI_EQUIPMENT",
        "CONSUMER_ELECTRONICS",
    ]
    path_ok = tmp_path / "ok.yaml"
    path_ok.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    assert MAX_INDUSTRY_IDS_PER_CONSTITUENT == 3
    result_ok = validate_manifest(path_ok, industries_path=INDUSTRIES_PATH)
    assert result_ok.ok, result_ok.errors

    manifest["constituents"][0]["industry_ids"] = [
        "AI_COMPUTE",
        "SEMI_EQUIPMENT",
        "CONSUMER_ELECTRONICS",
        "ROBOTICS",
    ]
    path_bad = tmp_path / "bad.yaml"
    path_bad.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    result_bad = validate_manifest(path_bad, industries_path=INDUSTRIES_PATH)
    assert not result_bad.ok
    assert any(
        f"exceeds max {MAX_INDUSTRY_IDS_PER_CONSTITUENT}" in error
        for error in result_bad.errors
    )


def test_manifest_role_field_must_be_known(tmp_path: Path) -> None:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["constituents"][0]["role"] = "stakeholder"  # not in VALID_ROLES
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")

    result = validate_manifest(path, industries_path=INDUSTRIES_PATH)

    assert not result.ok
    assert any("role must be one of" in error for error in result.errors)


def test_manifest_role_defaults_to_target_when_missing(tmp_path: Path) -> None:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    # Strip the role field from the first constituent
    manifest["constituents"][0].pop("role", None)
    path = tmp_path / "ok.yaml"
    path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")

    result = validate_manifest(path, industries_path=INDUSTRIES_PATH)

    assert result.ok, result.errors


def test_valid_role_vocabulary() -> None:
    assert VALID_ROLES == {"target", "customer", "both"}


def test_real_universe_includes_customer_role_constituents() -> None:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    customer_entries = [
        c for c in manifest["constituents"] if c.get("role") == "customer"
    ]
    # We curated upstream hyperscalers (META / MSFT / GOOGL / AMZN) as
    # customer-only — at least 4 entries should carry role=customer.
    assert len(customer_entries) >= 4


def test_valid_pool_vocabulary() -> None:
    assert VALID_POOLS == {"regular", "core"}


def test_real_universe_pool_counts_default_to_regular() -> None:
    """The shipped universe.yaml puts every constituent in regular pool;
    operators flip a hand-curated subset to core later. Pool counts are
    surfaced via ManifestValidationResult.pool_counts."""

    result = validate_manifest(MANIFEST_PATH)

    assert result.ok, result.errors
    assert result.pool_counts.get("regular", 0) == result.constituent_count
    assert result.pool_counts.get("core", 0) == 0


def test_manifest_pool_field_must_be_known(tmp_path: Path) -> None:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["constituents"][0]["pool"] = "watchlist"  # not in VALID_POOLS
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")

    result = validate_manifest(path, industries_path=INDUSTRIES_PATH)

    assert not result.ok
    assert any("pool must be one of" in e for e in result.errors)


def test_manifest_pool_defaults_to_regular_when_missing(tmp_path: Path) -> None:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["constituents"][0].pop("pool", None)
    path = tmp_path / "ok.yaml"
    path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")

    result = validate_manifest(path, industries_path=INDUSTRIES_PATH)

    assert result.ok, result.errors
    # The constituent still counts toward regular even though the field was
    # omitted on disk.
    assert result.pool_counts["regular"] == result.constituent_count


def test_manifest_pool_core_promotion_counts(tmp_path: Path) -> None:
    """Promoting a handful of constituents to pool=core should be reflected
    in pool_counts."""

    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    promoted = 0
    for constituent in manifest["constituents"]:
        if constituent.get("ts_code") in {
            "NVDA.US",
            "300308.SZ",
            "00700.HK",
            "601318.SH",
            "002594.SZ",
        }:
            constituent["pool"] = "core"
            promoted += 1
    assert promoted >= 5

    path = tmp_path / "ok_core.yaml"
    path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")

    result = validate_manifest(path, industries_path=INDUSTRIES_PATH)

    assert result.ok, result.errors
    assert result.pool_counts["core"] == promoted
    assert (
        result.pool_counts["regular"]
        == result.constituent_count - promoted
    )
