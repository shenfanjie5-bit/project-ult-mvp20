import json
import sqlite3
from pathlib import Path

from scripts import audit_a_share_gap_candidate_evidence as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_gap_candidate_evidence_packages_ready_and_not_ready_rows(tmp_path: Path) -> None:
    readiness_path = tmp_path / "readiness.json"
    db_path = tmp_path / "hot.sqlite"
    _write_json(
        readiness_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "priority": "P2_llm_or_web_extraction",
                    "score_target": "fundamental_score",
                    "recommended_source_route": "local_llm_closed_loop",
                    "source_dependencies": ["L5.is.revenue", "L5.is.sga_rd"],
                    "model_tier": "analysis",
                    "refresh_trigger": "quarterly_filing",
                },
                {
                    "dp_id": "L8.shock.black_swan",
                    "priority": "P2_llm_or_web_extraction",
                    "score_target": "risk_discount",
                    "recommended_source_route": "event_llm_from_runtime_news",
                    "source_dependencies": ["L9.media.report", "L9.macro.geo"],
                    "model_tier": "cheap_classify",
                    "refresh_trigger": "event_driven",
                },
                {
                    "dp_id": "L0.price.contract_spot",
                    "priority": "P2_llm_or_web_extraction",
                    "score_target": "fundamental_score",
                    "recommended_source_route": "local_llm_closed_loop",
                    "source_dependencies": ["L0.cost.raw_material", "L5.is.gross_margin"],
                    "model_tier": "analysis",
                    "refresh_trigger": "quarterly_filing",
                },
                {
                    "dp_id": "L9.media.short_report",
                    "priority": "P2_llm_or_web_extraction",
                    "score_target": "risk_discount",
                    "recommended_source_route": "web_event_extraction",
                    "source_dependencies": ["L9.media.report"],
                },
                {
                    "dp_id": "L7.trade.gamma",
                    "priority": "P3_manual_review",
                    "score_target": "gamma_multiplier",
                    "recommended_source_route": "manual_design_review",
                    "source_dependencies": [],
                },
            ]
        },
    )

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE realtime_current (
            ts_code TEXT,
            dp_id TEXT,
            value_json TEXT,
            data_status TEXT,
            confidence REAL,
            source TEXT,
            updated_at INTEGER
        )
        """
    )
    conn.executemany(
        "INSERT INTO realtime_current VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "000001.SZ",
                "L5.is.revenue",
                json.dumps({"scalar": 100, "unit": "元", "period": "20260331"}),
                "Known",
                0.91,
                "tushare:income",
                1780000000,
            ),
            (
                "000001.SZ",
                "L5.is.sga_rd",
                json.dumps({"scalar": 11}),
                "Known",
                0.88,
                "tushare:income.derived",
                1780000001,
            ),
            (
                "MARKET:CN",
                "L9.media.report",
                json.dumps({"count_24h": 3, "top_headlines": ["headline"]}),
                "Known",
                0.7,
                "akshare:stock_info_global_cls",
                1780000002,
            ),
            (
                "INDUSTRY:steel",
                "L0.cost.raw_material",
                json.dumps({"scalar": 0.2}),
                "Known",
                0.66,
                "tushare:fut_daily",
                1780000004,
            ),
            (
                "000001.SZ",
                "L5.is.gross_margin",
                json.dumps({"scalar": 0.3}),
                "Known",
                0.77,
                "tushare:income.derived",
                1780000005,
            ),
            (
                "000001.SZ",
                "L5.is.revenue",
                json.dumps({"scalar": 1}),
                "Known",
                0.1,
                "mock:test",
                1780000003,
            ),
        ],
    )
    conn.commit()
    conn.close()

    report = audit.build_report(
        readiness_path=readiness_path,
        db_path=db_path,
        sample_limit=2,
    )

    assert report["summary"]["blocking_gap_count"] == 5
    assert report["summary"]["candidate_input_ready_count"] == 2
    assert report["summary"]["candidate_input_not_ready_count"] == 3
    assert report["summary"]["safe_to_upsert_without_review_count"] == 0
    assert report["summary"]["candidate_status_counts"] == {
        "needs_dedicated_web_extraction": 1,
        "partial_missing_dependency": 1,
        "partial_mixed_dependency_grain": 1,
        "ready_for_local_llm_candidate": 1,
        "ready_for_manual_design_candidate": 1,
    }
    assert report["summary"]["dependency_dp_ids_missing_runtime_rows"] == ["L9.macro.geo"]

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    ready = by_dp["L0.cost.cac"]
    assert ready["candidate_input_ready"] is True
    assert ready["upsert_recommended"] is False
    assert ready["dependency_evidence"]["L5.is.revenue"]["row_count"] == 1
    assert (
        ready["candidate_input"]["dependencies"][0]["sample_rows"][0]["value_json_compact"][
            "scalar"
        ]
        == 100
    )
    assert by_dp["L8.shock.black_swan"]["candidate_status"] == "partial_missing_dependency"
    assert by_dp["L0.price.contract_spot"]["candidate_status"] == "partial_mixed_dependency_grain"
    assert by_dp["L0.price.contract_spot"]["dependency_evidence"]["L0.cost.raw_material"][
        "namespace_counts"
    ] == {"industry": 1}
    assert by_dp["L9.media.short_report"]["candidate_status"] == "needs_dedicated_web_extraction"
    gamma = by_dp["L7.trade.gamma"]
    assert gamma["candidate_status"] == "ready_for_manual_design_candidate"
    assert gamma["candidate_input_ready"] is True
    assert gamma["candidate_input"]["manual_design_policy"]["policy_name"] == (
        "a_share_single_stock_options_applicability_candidate"
    )
    assert gamma["candidate_input"]["manual_design_policy"]["requires_known_dependencies"] is False
    assert gamma["candidate_input"]["required_output_schema"]["data_status"] == (
        "NotApplicable | Known | Unknown"
    )

    rendered = audit.render_markdown(report)
    assert "Candidate inputs ready: `2`" in rendered
    assert "`L9.macro.geo`" in rendered


def test_contract_spot_can_be_ready_with_explicit_grain_join(tmp_path: Path) -> None:
    readiness_path = tmp_path / "readiness.json"
    db_path = tmp_path / "hot.sqlite"
    universe_path = tmp_path / "universe.yaml"
    _write_json(
        readiness_path,
        {
            "rows": [
                {
                    "dp_id": "L0.price.contract_spot",
                    "priority": "P2_llm_or_web_extraction",
                    "score_target": "fundamental_score",
                    "recommended_source_route": "local_llm_closed_loop",
                    "source_dependencies": ["L0.cost.raw_material", "L5.is.gross_margin"],
                    "model_tier": "analysis",
                    "refresh_trigger": "quarterly_filing",
                }
            ]
        },
    )
    universe_path.write_text(
        """
constituents:
  - ts_code: 000001.SZ
    industry_ids: [STEEL]
  - ts_code: 000002.SZ
    industry_ids: [PHARMA]
""".lstrip(),
        encoding="utf-8",
    )

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE realtime_current (
            ts_code TEXT,
            dp_id TEXT,
            value_json TEXT,
            data_status TEXT,
            confidence REAL,
            source TEXT,
            updated_at INTEGER
        )
        """
    )
    conn.executemany(
        "INSERT INTO realtime_current VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "INDUSTRY:STEEL",
                "L0.cost.raw_material",
                json.dumps({"avg_pct_change": 0.2}),
                "Known",
                0.66,
                "tushare:fut_daily",
                1780000004,
            ),
            (
                "000001.SZ",
                "L5.is.gross_margin",
                json.dumps({"scalar": 0.3}),
                "Known",
                0.77,
                "tushare:income.derived",
                1780000005,
            ),
            (
                "000002.SZ",
                "L5.is.gross_margin",
                json.dumps({"scalar": 0.4}),
                "Known",
                0.77,
                "tushare:income.derived",
                1780000006,
            ),
        ],
    )
    conn.commit()
    conn.close()

    report = audit.build_report(
        readiness_path=readiness_path,
        db_path=db_path,
        universe_path=universe_path,
        sample_limit=2,
    )

    assert report["summary"]["candidate_input_ready_count"] == 1
    row = report["rows"][0]
    assert row["candidate_status"] == "ready_for_local_llm_candidate_with_grain_join"
    assert row["candidate_input_ready"] is True
    policy = row["candidate_input"]["grain_join_policy"]
    assert policy["join_ready_a_share_count"] == 1
    assert policy["missing_raw_material_a_share_count"] == 1
    assert policy["missing_gross_margin_a_share_count"] == 0
    assert policy["join_ready_sample"][0]["ts_code"] == "000001.SZ"
    assert policy["missing_raw_material_sample"][0]["ts_code"] == "000002.SZ"


def test_short_report_can_be_ready_with_dedicated_evidence_scan(tmp_path: Path) -> None:
    readiness_path = tmp_path / "readiness.json"
    db_path = tmp_path / "hot.sqlite"
    short_report_path = tmp_path / "short_report.json"
    _write_json(
        readiness_path,
        {
            "rows": [
                {
                    "dp_id": "L9.media.short_report",
                    "priority": "P2_llm_or_web_extraction",
                    "score_target": "risk_discount",
                    "recommended_source_route": "web_event_extraction",
                    "source_dependencies": ["L9.media.report", "L9.media.social_buzz"],
                    "model_tier": "cheap_classify",
                    "refresh_trigger": "event_driven",
                }
            ]
        },
    )
    _write_json(
        short_report_path,
        {
            "summary": {
                "news_html_files_scanned": 3,
                "parse_error_count": 0,
                "strict_short_report_documents": 2,
                "direct_a_share_short_report_documents": 1,
                "foreign_or_market_short_report_documents": 1,
                "direct_a_share_top_ts_codes": {"688256.SH": 1},
                "candidate_evidence_ready": True,
                "source_counts": {"news/cls_flash": 3},
                "strict_source_counts": {"news/cls_flash": 2},
            },
            "direct_a_share_samples": [
                {
                    "path": "/Volumes/dockcase2tb/market_data/news/cls_flash/direct.html",
                    "source": "news/cls_flash",
                    "title": "做空机构发布做空报告指控寒武纪-U",
                    "a_share_ts_codes": ["688256.SH"],
                    "excerpt": "某做空机构发布做空报告，指控寒武纪-U(688256)。",
                }
            ],
            "foreign_or_market_samples": [
                {
                    "path": "/Volumes/dockcase2tb/market_data/news/cls_flash/foreign.html",
                    "source": "news/cls_flash",
                    "title": "香橼称正在做空闪迪",
                    "a_share_ts_codes": [],
                    "excerpt": "知名做空机构香橼称正在做空闪迪。",
                }
            ],
        },
    )
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE realtime_current (
            ts_code TEXT,
            dp_id TEXT,
            value_json TEXT,
            data_status TEXT,
            confidence REAL,
            source TEXT,
            updated_at INTEGER
        )
        """
    )
    conn.commit()
    conn.close()

    report = audit.build_report(
        readiness_path=readiness_path,
        db_path=db_path,
        short_report_evidence_path=short_report_path,
    )

    assert report["summary"]["candidate_input_ready_count"] == 1
    assert report["summary"]["candidate_status_counts"] == {
        "ready_for_web_event_candidate": 1
    }
    row = report["rows"][0]
    assert row["candidate_status"] == "ready_for_web_event_candidate"
    assert row["candidate_input_ready"] is True
    evidence = row["candidate_input"]["short_report_evidence"]
    assert evidence["direct_a_share_short_report_documents"] == 1
    assert evidence["direct_a_share_top_ts_codes"] == {"688256.SH": 1}
    assert "active short-report events" in evidence["candidate_policy"]


def test_manual_design_policy_requires_known_dependencies_except_applicability_na(
    tmp_path: Path,
) -> None:
    readiness_path = tmp_path / "readiness.json"
    db_path = tmp_path / "hot.sqlite"
    _write_json(
        readiness_path,
        {
            "rows": [
                {
                    "dp_id": "L6.priced.realization_risk",
                    "priority": "P3_manual_review",
                    "score_target": "priced_in_discount",
                    "recommended_source_route": "manual_design_review",
                    "source_dependencies": [],
                },
                {
                    "dp_id": "L7.trade.gamma",
                    "priority": "P3_manual_review",
                    "score_target": "gamma_multiplier",
                    "recommended_source_route": "manual_design_review",
                    "source_dependencies": [],
                },
            ]
        },
    )
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE realtime_current (
            ts_code TEXT,
            dp_id TEXT,
            value_json TEXT,
            data_status TEXT,
            confidence REAL,
            source TEXT,
            updated_at INTEGER
        )
        """
    )
    conn.executemany(
        "INSERT INTO realtime_current VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "000001.SZ",
                "L6.priced.run_up",
                json.dumps({"d20_pct": 0.2}),
                "Known",
                0.8,
                "derived:price_history",
                1780000001,
            ),
            (
                "000001.SZ",
                "L6.priced.news_age",
                json.dumps({"magnitude": 0.3}),
                "Known",
                0.8,
                "derive:l6_priced_news_age",
                1780000002,
            ),
            (
                "000001.SZ",
                "L5.surprise.preprice",
                json.dumps({"run_up_20d_pct": 0.15}),
                "Known",
                0.8,
                "tushare:forecast+daily.derived",
                1780000003,
            ),
            (
                "000001.SZ",
                "L8.val.priced_in",
                json.dumps({"priced_in_score": 0.4}),
                "Known",
                0.8,
                "derive:l8_val_priced_in",
                1780000004,
            ),
        ],
    )
    conn.commit()
    conn.close()

    report = audit.build_report(readiness_path=readiness_path, db_path=db_path)

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    realization = by_dp["L6.priced.realization_risk"]
    assert realization["candidate_status"] == "ready_for_manual_design_candidate"
    assert realization["candidate_input_ready"] is True
    assert realization["candidate_input"]["manual_design_policy"]["requires_known_dependencies"] is True
    assert realization["source_dependencies"] == [
        "L6.priced.run_up",
        "L6.priced.news_age",
        "L5.surprise.preprice",
        "L8.val.priced_in",
    ]

    gamma = by_dp["L7.trade.gamma"]
    assert gamma["candidate_status"] == "ready_for_manual_design_candidate"
    assert gamma["candidate_input"]["manual_design_policy"]["requires_known_dependencies"] is False
    assert report["summary"]["candidate_input_ready_count"] == 2
    assert report["summary"]["candidate_input_not_ready_count"] == 0
    assert report["summary"]["dependency_dp_ids_missing_runtime_rows"] == []
