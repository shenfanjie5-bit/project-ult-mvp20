import json
from pathlib import Path

from scripts import audit_a_share_runtime_scope_approvals as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_runtime_scope_approvals_accept_deterministic_scope_rows(
    tmp_path: Path,
) -> None:
    target_scope_path = tmp_path / "target_scope.json"
    _write_json(
        target_scope_path,
        {
            "rows": [
                {
                    "dp_id": "L7.trade.gamma",
                    "score_target": "gamma_multiplier",
                    "target_scope_status": "review_required",
                    "target_scope_contract_valid": True,
                    "target_scope_sha256": "gamma-scope",
                    "payload_sha256": "gamma-payload",
                    "target_scope_policy": {
                        "scope_kind": "current_a_share_single_stock_universe"
                    },
                    "target_scope_payload": {
                        "value_requirements": {
                            "multiplier": 1.0,
                            "applicability": "a_share_single_stock_no_listed_option",
                        }
                    },
                    "candidate_target_ts_code_count": 3,
                    "candidate_runtime_rows_would_write": 3,
                    "runtime_write_attempted": False,
                    "production_write_allowed": False,
                },
                {
                    "dp_id": "L9.media.short_report",
                    "score_target": "expectation_gap",
                    "target_scope_status": "review_required",
                    "target_scope_contract_valid": True,
                    "target_scope_sha256": "short-report-scope",
                    "payload_sha256": "short-report-payload",
                    "target_scope_policy": {
                        "scope_kind": "current_a_share_single_stock_universe"
                    },
                    "target_scope_payload": {
                        "value_requirements": {
                            "score": 0.0,
                            "event_state": "none_observed",
                            "direct_a_share_short_report_documents": 0,
                        }
                    },
                    "candidate_target_ts_code_count": 3,
                    "candidate_runtime_rows_would_write": 3,
                    "runtime_write_attempted": False,
                    "production_write_allowed": False,
                },
            ]
        },
    )

    report = audit.build_report(
        target_scope_path=target_scope_path,
        approved_at="2026-06-19T19:00:00+08:00",
    )

    summary = report["summary"]
    assert summary["target_scope_row_count"] == 2
    assert summary["scope_approval_record_count"] == 2
    assert summary["approved_runtime_target_scope_count"] == 2
    assert summary["scope_policy_rejected_count"] == 0
    assert summary["candidate_runtime_rows_would_write_count"] == 6
    assert summary["runtime_write_attempted_count"] == 0
    assert summary["production_write_allowed_count"] == 0
    approvals_by_dp = {row["dp_id"]: row for row in report["scope_approvals"]}
    assert approvals_by_dp["L7.trade.gamma"]["approval_scope"] == "runtime_target_scope"
    assert approvals_by_dp["L9.media.short_report"]["target_scope_sha256"] == (
        "short-report-scope"
    )
    assert "These records approve only" in audit.render_markdown(report)
