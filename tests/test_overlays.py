"""Tests for stock/industry overlay generation, validation, and compilation."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
import pytest

from mvp20.overlays import (
    Membership,
    build_stock_overlay,
    compile_overlays_to_sqlite,
    expand_memberships,
    validate_overlay_set,
    validate_stock_overlay,
)
from mvp20.storage import read_compiled_graph_snapshot, read_overlay_alerts


ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_PATH = ROOT / "config" / "mvp20.universe.yaml"
INDUSTRIES_PATH = ROOT / "config" / "mvp20.industries.yaml"
STOCK_OVERLAYS_DIR = ROOT / "config" / "stock_overlays"
INDUSTRY_OVERLAYS_DIR = ROOT / "config" / "industry_overlays"
INDUSTRY_GRAPHS_DIR = ROOT / "config" / "industry_graphs"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _sample_stock_overlay() -> dict:
    return _load(STOCK_OVERLAYS_DIR / "STORAGE_GRID" / "300750.SZ.yaml")


@pytest.fixture(scope="module")
def compiled_overlay_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    db_path = tmp_path_factory.mktemp("overlay-db") / "hot.sqlite"
    result = compile_overlays_to_sqlite(
        db_path=db_path,
        stock_overlays_dir=STOCK_OVERLAYS_DIR,
        industry_overlays_dir=INDUSTRY_OVERLAYS_DIR,
        universe_path=UNIVERSE_PATH,
        industries_path=INDUSTRIES_PATH,
    )
    assert result.ok, result.errors[:10]
    return db_path


def test_membership_expansion_count() -> None:
    memberships = expand_memberships(UNIVERSE_PATH, INDUSTRIES_PATH)

    # Corpus-size-agnostic (the universe grows via bulk-onboard): assert the
    # invariant — every universe constituent expands to >=1 membership and the
    # set of unique ts_codes matches the universe exactly — rather than a frozen
    # count that would drift on every onboard.
    universe = _load(UNIVERSE_PATH)
    n_constituents = len({str(c["ts_code"]).upper() for c in universe.get("constituents", [])})
    assert len({m.ts_code.upper() for m in memberships}) == n_constituents
    assert len(memberships) >= n_constituents  # a stock may join >1 industry
    assert sum(1 for m in memberships if m.ts_code == "300750.SZ") == 1


def test_space_economy_pending_stub() -> None:
    assert (INDUSTRY_GRAPHS_DIR / "SPACE_ECONOMY.yaml").exists()
    assert (INDUSTRY_OVERLAYS_DIR / "SPACE_ECONOMY.yaml").exists()
    assert not (STOCK_OVERLAYS_DIR / "SPACE_ECONOMY").exists()

    graph = _load(INDUSTRY_GRAPHS_DIR / "SPACE_ECONOMY.yaml")
    overlay = _load(INDUSTRY_OVERLAYS_DIR / "SPACE_ECONOMY.yaml")
    assert graph["graph_status"] == "pending"
    assert overlay["graph_status"] == "pending"


def test_stock_overlay_path_scheme() -> None:
    nested_files = list(STOCK_OVERLAYS_DIR.glob("*/*.yaml"))
    flat_files = list(STOCK_OVERLAYS_DIR.glob("*.yaml"))
    # Invariant (growth-robust): overlays live under <industry>/<code>.yaml — no
    # flat files at the root — and there is at least one nested overlay.
    assert not flat_files, f"overlays must be nested <industry>/<code>.yaml; flat: {flat_files[:5]}"
    assert len(nested_files) > 0
    assert (STOCK_OVERLAYS_DIR / "STORAGE_GRID" / "300750.SZ.yaml").exists()
    assert (STOCK_OVERLAYS_DIR / "AI_COMPUTE" / "002463.SZ.yaml").exists()
    assert (STOCK_OVERLAYS_DIR / "CONSUMER_ELECTRONICS" / "002463.SZ.yaml").exists()


def test_required_node_fields() -> None:
    payload = _sample_stock_overlay()
    required_fields = {
        "node_id",
        "node_name",
        "node_type",
        "layer",
        "data_status",
        "missing_policy",
        "calculation_type",
        "aggregation_policy",
    }

    # X5: 32 original derived slots + 26 closed-loop slots = 58.
    # Z3: + 53 net-new bucket-C/D LLM-candidate slots → 111.
    # Track-B: + 4 script-fillable scoring slots (L9.company.buyback_dividend /
    # earnings_guidance, L8.gov.insider_sell / management_change) → 115 total.
    assert len([n for n in payload["nodes"] if n.get("derived_slot")]) == 115
    for node in payload["nodes"]:
        assert required_fields <= set(node)


def test_edge_type_separation() -> None:
    payload = _sample_stock_overlay()

    assert payload["hierarchy_edges"]
    assert payload["causal_edges"]
    assert all(e["edge_type"] == "Parent-Child" for e in payload["hierarchy_edges"])
    assert all(e["edge_type"] != "Parent-Child" for e in payload["causal_edges"])


def test_na_renormalization_policy_does_not_alert() -> None:
    membership = Membership(
        ts_code="TEST.SZ",
        name="测试公司",
        industry_id="AI_COMPUTE",
        primary_industry=True,
        all_industries=("AI_COMPUTE",),
        role="target",
        pool="regular",
    )
    payload = build_stock_overlay(membership)
    node = next(n for n in payload["nodes"] if n["dp_id"] == "L0.cost.rent")
    node["data_status"] = "N/A"
    node["status"] = "N/A"
    node["missing_policy"] = "not_applicable_remove"
    node["missing_reason"] = None
    node["active_weight"] = 0.0

    errors, warnings = validate_stock_overlay(payload)

    assert not errors
    assert not any("L0.cost.rent" in warning for warning in warnings)


def test_unknown_required_alert() -> None:
    payload = _sample_stock_overlay()
    # Pick any currently-Unknown node and promote its required_level so that
    # validate_stock_overlay must flag it. We dispatch by data_status (not by
    # a hard-coded dp_id) so this stays correct as individual nodes get
    # enriched from Unknown -> Known in the overlay.
    node = next(n for n in payload["nodes"] if n.get("data_status") == "Unknown")
    node["required_level"] = "required"

    errors, _ = validate_stock_overlay(payload)

    assert any("required node is Unknown" in err for err in errors)


def test_low_data_coverage_blocks_strong_conclusion() -> None:
    payload = _sample_stock_overlay()

    assert payload["coverage"]["data_coverage"] < 0.3
    assert payload["scores"]["stock_final_score"]["current_mode"] == "等待验证"


def test_optional_node_dual_value() -> None:
    payload = _sample_stock_overlay()
    optional_nodes = [n for n in payload["nodes"] if n["data_status"] == "Optionality"]

    assert optional_nodes
    for node in optional_nodes:
        assert set(node["value"]) >= {"current_contribution", "future_option_value"}


def test_snapshot_contains_four_score_layers() -> None:
    payload = _sample_stock_overlay()

    assert set(payload["scores"]) >= {
        "node_scores",
        "path_scores",
        "company_score",
        "stock_final_score",
    }


def test_validate_overlay_set_accepts_generated_corpus() -> None:
    result = validate_overlay_set(
        STOCK_OVERLAYS_DIR,
        INDUSTRY_OVERLAYS_DIR,
        UNIVERSE_PATH,
        INDUSTRIES_PATH,
    )

    assert result.ok, result.errors[:10]
    # Growth-robust: the counts must be internally consistent (one overlay per
    # membership, count matches the files on disk) rather than a frozen number
    # that drifts as bulk-onboard grows the universe.
    nested = list(STOCK_OVERLAYS_DIR.glob("*/*.yaml"))
    assert result.stock_overlay_count == len(nested)
    assert result.membership_count == result.stock_overlay_count
    assert result.industry_overlay_count == 13
    assert result.warnings


def test_compile_overlays_to_sqlite_snapshot(compiled_overlay_db: Path) -> None:
    snapshot = read_compiled_graph_snapshot(compiled_overlay_db, "300750.SZ")
    assert snapshot is not None
    assert snapshot["industry_id"] == "STORAGE_GRID"
    assert snapshot["compiled_graph"]["nodes"]
    assert snapshot["scores"]["stock_final_score"]["current_mode"] == "等待验证"
    governed = [
        n for n in snapshot["compiled_graph"]["nodes"]
        if n.get("dp_id") and n.get("dp_id") != "company"
    ]
    assert governed
    assert all("field_role" in n and "score_target" in n for n in governed)

    alerts = read_overlay_alerts(compiled_overlay_db, "300750.SZ", "STORAGE_GRID")
    assert any(a["severity"] == "WARN" for a in alerts)


def test_compiled_cross_industry_snapshot_switch(compiled_overlay_db: Path) -> None:
    default_snapshot = read_compiled_graph_snapshot(compiled_overlay_db, "002463.SZ")
    switched_snapshot = read_compiled_graph_snapshot(
        compiled_overlay_db,
        "002463.SZ",
        industry_id="CONSUMER_ELECTRONICS",
    )

    assert default_snapshot is not None
    assert switched_snapshot is not None
    assert default_snapshot["industry_id"] == "AI_COMPUTE"
    assert switched_snapshot["industry_id"] == "CONSUMER_ELECTRONICS"
    assert set(default_snapshot["available_industries"]) == {
        "AI_COMPUTE",
        "CONSUMER_ELECTRONICS",
    }


def test_compiled_payload_is_json_serializable() -> None:
    payload = _sample_stock_overlay()
    json.dumps(payload, ensure_ascii=False)
