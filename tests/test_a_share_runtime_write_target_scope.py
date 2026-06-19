import json
import sqlite3
from pathlib import Path

from scripts import audit_a_share_runtime_write_target_scope as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_runtime_db(path: Path, ts_codes: list[str]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("create table realtime_current (ts_code text, dp_id text)")
        conn.executemany(
            "insert into realtime_current (ts_code, dp_id) values (?, ?)",
            [(ts_code, "L0.test") for ts_code in ts_codes],
        )
        conn.commit()
    finally:
        conn.close()


def _write_universe(path: Path, ts_codes: list[str]) -> None:
    lines = ["schema_version: 2", "constituents:"]
    for ts_code in ts_codes:
        lines.extend(
            [
                f"  - ts_code: {ts_code}",
                f"    name: {ts_code}",
                "    role: target",
                "    pool: regular",
                "    industry_ids: [TEST]",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_runtime_write_target_scope_packages_review_required_candidates(
    tmp_path: Path,
) -> None:
    approval_gate_path = tmp_path / "approval_gate.json"
    runtime_db_path = tmp_path / "hot.sqlite"
    universe_path = tmp_path / "universe.yaml"
    ts_codes = ["000001.SZ", "600000.SH", "430001.BJ", "00700.HK"]

    _write_json(
        approval_gate_path,
        {
            "write_plan": [
                {
                    "dp_id": "L7.trade.gamma",
                    "score_target": "gamma_multiplier",
                    "data_status": "Known",
                    "value_json": {
                        "multiplier": 1.0,
                        "applicability": "a_share_single_stock_no_listed_option",
                    },
                    "confidence": 0.7,
                    "payload_sha256": "gamma",
                    "approval": {"approval_id": "approved-gamma"},
                    "runtime_write_allowed": True,
                    "production_write_allowed": False,
                },
                {
                    "dp_id": "L9.media.short_report",
                    "score_target": "expectation_gap",
                    "data_status": "Known",
                    "value_json": {
                        "score": 0.0,
                        "event_state": "none_observed",
                        "direct_a_share_short_report_documents": 0,
                    },
                    "confidence": 0.6,
                    "payload_sha256": "short-report",
                    "approval": {"approval_id": "approved-short-report"},
                    "runtime_write_allowed": True,
                    "production_write_allowed": False,
                },
            ]
        },
    )
    _write_runtime_db(runtime_db_path, ts_codes)
    _write_universe(universe_path, ts_codes)

    report = audit.build_report(
        approval_gate_path=approval_gate_path,
        runtime_db_path=runtime_db_path,
        universe_path=universe_path,
    )
    summary = report["summary"]

    assert summary["approved_write_plan_entry_count"] == 2
    assert summary["runtime_a_share_ts_code_count"] == 3
    assert summary["config_a_share_ts_code_count"] == 3
    assert summary["config_runtime_a_share_exact_match"] is True
    assert summary["target_scope_candidate_count"] == 2
    assert summary["target_scope_contract_valid_count"] == 2
    assert summary["target_scope_contract_invalid_count"] == 0
    assert summary["target_scope_review_required_count"] == 2
    assert summary["target_scope_approved_count"] == 0
    assert summary["controlled_batch_plan_required_count"] == 0
    assert summary["candidate_runtime_rows_would_write_count"] == 6
    assert summary["upsert_ready_entry_count"] == 0
    assert summary["runtime_write_attempted_count"] == 0
    assert summary["production_write_allowed_count"] == 0

    by_dp_id = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp_id["L7.trade.gamma"]["target_scope_status"] == "review_required"
    assert by_dp_id["L7.trade.gamma"]["candidate_target_ts_code_count"] == 3
    assert by_dp_id["L7.trade.gamma"]["target_scope_sha256"]
    assert by_dp_id["L9.media.short_report"]["target_scope_contract_valid"] is True
    assert by_dp_id["L9.media.short_report"]["blocking_reasons"] == [
        "target_scope_candidate_requires_review_approval"
    ]
    assert (
        "This audit creates no runtime rows and no production writes"
        in audit.render_markdown(report)
    )


def test_runtime_write_target_scope_accepts_matching_scope_approvals(
    tmp_path: Path,
) -> None:
    approval_gate_path = tmp_path / "approval_gate.json"
    runtime_db_path = tmp_path / "hot.sqlite"
    universe_path = tmp_path / "universe.yaml"
    scope_approvals_path = tmp_path / "scope_approvals.json"
    ts_codes = ["000001.SZ", "600000.SH"]

    _write_json(
        approval_gate_path,
        {
            "write_plan": [
                {
                    "dp_id": "L7.trade.gamma",
                    "score_target": "gamma_multiplier",
                    "data_status": "Known",
                    "value_json": {
                        "multiplier": 1.0,
                        "applicability": "a_share_single_stock_no_listed_option",
                    },
                    "confidence": 0.7,
                    "payload_sha256": "gamma",
                    "approval": {"approval_id": "approved-gamma"},
                    "runtime_write_allowed": True,
                    "production_write_allowed": False,
                }
            ]
        },
    )
    _write_runtime_db(runtime_db_path, ts_codes)
    _write_universe(universe_path, ts_codes)
    draft = audit.build_report(
        approval_gate_path=approval_gate_path,
        runtime_db_path=runtime_db_path,
        universe_path=universe_path,
    )
    target_scope_sha256 = draft["rows"][0]["target_scope_sha256"]
    _write_json(
        scope_approvals_path,
        {
            "scope_approvals": [
                {
                    "approval_id": "scope-approval-1",
                    "dp_id": "L7.trade.gamma",
                    "approval_status": "approved",
                    "approval_scope": "runtime_target_scope",
                    "reviewer": "reviewer",
                    "approved_at": "2026-06-19T19:00:00+08:00",
                    "target_scope_sha256": target_scope_sha256,
                    "risk_acknowledged": True,
                    "production_write_allowed": False,
                }
            ]
        },
    )

    report = audit.build_report(
        approval_gate_path=approval_gate_path,
        runtime_db_path=runtime_db_path,
        universe_path=universe_path,
        scope_approvals_path=scope_approvals_path,
    )

    summary = report["summary"]
    assert summary["target_scope_review_required_count"] == 0
    assert summary["target_scope_approved_count"] == 1
    assert summary["controlled_batch_plan_required_count"] == 1
    row = report["rows"][0]
    assert row["target_scope_status"] == "scope_approved_batch_plan_required"
    assert row["target_scope_approval_valid"] is True
    assert row["blocking_reasons"] == ["controlled_batch_upsert_plan_required"]
