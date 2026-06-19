import json
import sqlite3
from pathlib import Path

import yaml

from scripts import audit_a_share_l0_source_readiness as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")


def test_l0_source_readiness_classifies_routes_and_dependencies(tmp_path: Path) -> None:
    gap_path = tmp_path / "gap.json"
    governance_path = tmp_path / "governance.yaml"
    spec_path = tmp_path / "spec.yaml"
    db_path = tmp_path / "hot.sqlite"
    dockcase_root = tmp_path / "database_all"
    market_root = tmp_path / "market_data"
    dockcase_root.mkdir()
    market_root.mkdir()
    (dockcase_root / "sample.csv").write_text("x\n1\n", encoding="utf-8")

    _write_json(
        gap_path,
        {
            "participating_gap_rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "blocking_gap": True,
                    "priority": "P2_llm_or_web_extraction",
                    "score_target": "fundamental_score",
                    "source_data_state": "missing",
                },
                {
                    "dp_id": "L9.media.short_report",
                    "blocking_gap": True,
                    "priority": "P2_llm_or_web_extraction",
                    "score_target": "expectation_gap",
                    "source_data_state": "missing",
                },
                {
                    "dp_id": "L7.trade.gamma",
                    "blocking_gap": True,
                    "priority": "P3_manual_review",
                    "score_target": "gamma_multiplier",
                    "source_data_state": "missing",
                },
                {
                    "dp_id": "L0.cost.raw_material",
                    "blocking_gap": False,
                    "priority": "P0_add_formula_high_coverage",
                },
            ]
        },
    )
    _write_yaml(
        governance_path,
        {
            "data_points": {
                "L0.cost.cac": {
                    "route": "llm_close",
                    "model_tier": "analysis",
                    "refresh_trigger": "quarterly_filing",
                    "source_dependencies": ["L5.is.sga_rd", "L5.is.revenue"],
                },
                "L9.media.short_report": {
                    "route": "llm_close",
                    "model_tier": "cheap_classify",
                    "refresh_trigger": "event_driven",
                    "source_dependencies": ["L9.media.report"],
                },
            }
        },
    )
    _write_yaml(
        spec_path,
        {
            "data_points": {
                "L0.cost.cac": {"source_status": "missing"},
                "L9.media.short_report": {"source_status": "○"},
                "L7.trade.gamma": {"source_status": "$"},
            }
        },
    )

    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE realtime_current (ts_code TEXT, dp_id TEXT, data_status TEXT, source TEXT)"
    )
    conn.executemany(
        "INSERT INTO realtime_current VALUES (?, ?, ?, ?)",
        [
            ("000001.SZ", "L5.is.sga_rd", "Known", "tushare:test"),
            ("000001.SZ", "L5.is.revenue", "Known", "mock:test"),
            ("MARKET:CN", "L9.media.report", "Known", "akshare:cls"),
        ],
    )
    conn.commit()
    conn.close()

    report = audit.build_report(
        gap_path=gap_path,
        governance_path=governance_path,
        spec_path=spec_path,
        db_path=db_path,
        dockcase_data_root=dockcase_root,
        market_data_root=market_root,
    )

    assert report["summary"]["blocking_gap_count"] == 3
    assert report["summary"]["direct_structured_tushare_remaining"] == 0
    assert report["summary"]["recommended_source_route_counts"] == {
        "local_llm_closed_loop": 1,
        "manual_design_review": 1,
        "web_event_extraction": 1,
    }
    assert report["dockcase"]["database_all_file_count"] == 1
    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L0.cost.cac"]["recommended_source_route"] == "local_llm_closed_loop"
    assert by_dp["L0.cost.cac"]["dependency_state"]["L5.is.sga_rd"]["rows"] == 1
    assert by_dp["L0.cost.cac"]["dependency_state"]["L5.is.revenue"]["rows"] == 0
    assert by_dp["L9.media.short_report"]["recommended_source_route"] == "web_event_extraction"
    assert by_dp["L7.trade.gamma"]["recommended_source_route"] == "manual_design_review"

    rendered = audit.render_markdown(report)
    assert "Direct structured Tushare remaining: `0`" in rendered
    assert "`L9.media.short_report`" in rendered
