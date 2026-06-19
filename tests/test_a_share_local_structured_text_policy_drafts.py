import json
from pathlib import Path

from scripts import audit_a_share_local_structured_text_policy_drafts as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _readiness_row(dp_id: str) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "route_bucket": "local_structured_text_llm_required",
        "dependency_readiness": "all_dependencies_have_material_known_coverage",
    }


def _sample(ts_code: str, value: dict) -> dict:
    return {
        "ts_code": ts_code,
        "data_status": "Known",
        "confidence": 0.8,
        "source": "test",
        "value_json_compact": value,
    }


def _dep(dp_id: str, values: list[dict]) -> dict:
    return {
        "dp_id": dp_id,
        "row_count": len(values),
        "known_count": len(values),
        "sample_rows": [_sample(f"00000{idx}.SZ", value) for idx, value in enumerate(values, start=1)],
    }


def _candidate(dp_id: str, deps: list[dict]) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "source_dependencies": [dep["dp_id"] for dep in deps],
        "candidate_input": {
            "target_dp_id": dp_id,
            "score_target": "fundamental_score",
            "dependencies": deps,
        },
    }


def _fixture_candidate_rows() -> list[dict]:
    revenue = _dep("L5.is.revenue", [{"scalar": 1000.0}, {"scalar": 1200.0}])
    gross_margin = _dep("L5.is.gross_margin", [{"scalar": 0.24}, {"scalar": 0.21}])
    sga_rd = _dep(
        "L5.is.sga_rd",
        [{"sga_rd_ratio_revenue": 0.12}, {"sga_rd_ratio_revenue": 0.16}],
    )
    qa_recent = _dep(
        "L9.disclosure.qa_recent",
        [
            {
                "snippet": "投资者问答包含股东户数、分红和产能计划等内容。",
                "source_kind": "ir_qa",
            }
        ],
    )
    return [
        _candidate("L0.demand.user_count", [revenue, qa_recent]),
        _candidate("L0.price.discount", [gross_margin, qa_recent]),
        _candidate("L0.supply.channel_service", [sga_rd, qa_recent]),
    ]


def _channel_service_candidate() -> dict:
    sga_rd = _dep(
        "L5.is.sga_rd",
        [{"sga_rd_ratio_revenue": 0.12}, {"sga_rd_ratio_revenue": 0.16}],
    )
    qa_recent = _dep(
        "L9.disclosure.qa_recent",
        [
            {
                "top_qa": [
                    {
                        "question": "产品有哪些使用场景？",
                        "answer": "公司产品已在公交、冷链物流、长途牵引重卡上实现批量配套销售，并在国内多个省市都有批量运营。",
                        "date": "20260515",
                    }
                ],
                "latest_date": "20260515",
            }
        ],
    )
    return _candidate("L0.supply.channel_service", [sga_rd, qa_recent])


def _discount_pressure_candidate() -> dict:
    gross_margin = _dep("L5.is.gross_margin", [{"scalar": 0.18}, {"scalar": 0.21}])
    qa_recent = _dep(
        "L9.disclosure.qa_recent",
        [
            {
                "top_qa": [
                    {
                        "question": "公司毛利率为什么下降？",
                        "answer": (
                            "国内产品价格下降主要受医院采购预算缩减、竞争环境激烈、"
                            "医保持续深化改革等因素影响。随着肿标甲功试剂集采开始执行，"
                            "公司预计毛利率还会略受影响。"
                        ),
                        "date": "20260429",
                    }
                ],
                "latest_date": "20260429",
            }
        ],
    )
    return _candidate("L0.price.discount", [gross_margin, qa_recent])


def _user_count_demand_candidate() -> dict:
    revenue = _dep("L5.is.revenue", [{"scalar": 1000.0}, {"scalar": 1200.0}])
    qa_recent = _dep(
        "L9.disclosure.qa_recent",
        [
            {
                "top_qa": [
                    {
                        "question": "公司客户和订单情况如何？",
                        "answer": (
                            "公司LNG保温绝热板材业务订单数量饱满，新客户拓展顺利，"
                            "半导体材料业务订单将根据下游客户产能落地释放情况逐步起量。"
                        ),
                        "date": "20260428",
                    },
                    {
                        "question": "公司用户规模是否增长？",
                        "answer": (
                            "2026年，公司进一步提升全渠道运营能力，推动用户规模与订单贡献稳定增长，"
                            "持续提升会员价值。"
                        ),
                        "date": "20260514",
                    },
                ],
                "latest_date": "20260514",
            }
        ],
    )
    return _candidate("L0.demand.user_count", [revenue, qa_recent])


def _shareholder_count_noise_candidate() -> dict:
    revenue = _dep("L5.is.revenue", [{"scalar": 1000.0}, {"scalar": 1200.0}])
    qa_recent = _dep(
        "L9.disclosure.qa_recent",
        [
            {
                "top_qa": [
                    {
                        "question": "请问最新股东户数是多少？",
                        "answer": (
                            "截至2026年5月29日，公司股东总数为600,160户，"
                            "其中A股股东599,878户，H股股东282户。"
                        ),
                        "date": "20260529",
                    }
                ],
                "latest_date": "20260529",
            }
        ],
    )
    return _candidate("L0.demand.user_count", [revenue, qa_recent])


def test_local_structured_text_policy_drafts_keep_review_gated_unknowns(tmp_path: Path) -> None:
    readiness_path = tmp_path / "readiness.json"
    candidate_path = tmp_path / "candidate.json"
    dp_ids = [
        "L0.demand.user_count",
        "L0.price.discount",
        "L0.supply.channel_service",
    ]
    _write_json(readiness_path, {"rows": [_readiness_row(dp_id) for dp_id in dp_ids]})
    _write_json(candidate_path, {"rows": _fixture_candidate_rows()})

    report = audit.build_report(readiness_path, candidate_path)

    assert report["summary"]["local_structured_text_task_count"] == 3
    assert report["summary"]["draft_known_count"] == 0
    assert report["summary"]["draft_unknown_count"] == 3
    assert report["summary"]["draft_contract_valid_count"] == 3
    assert report["summary"]["draft_contract_invalid_count"] == 0
    assert report["summary"]["bridge_validated_known_count"] == 0
    assert report["summary"]["review_required_count"] == 3
    assert report["summary"]["safe_to_upsert_without_review_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["summary"]["draft_status_counts"] == {
        "unknown_text_classification_required": 3
    }

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    user_payload = by_dp["L0.demand.user_count"]["draft_payload"]
    assert user_payload["data_status"] == "Unknown"
    assert (
        user_payload["value_json"]["blocked_reason"]
        == "qa_recent_requires_customer_user_extraction"
    )
    assert by_dp["L0.demand.user_count"]["contract_validation"]["contract_valid"]
    assert "Draft Unknown packets: `3`" in audit.render_markdown(report)


def test_local_structured_text_policy_drafts_marks_missing_candidate_unknown(tmp_path: Path) -> None:
    readiness_path = tmp_path / "readiness.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(readiness_path, {"rows": [_readiness_row("L0.demand.user_count")]})
    _write_json(candidate_path, {"rows": []})

    report = audit.build_report(readiness_path, candidate_path)

    assert report["summary"]["draft_known_count"] == 0
    assert report["summary"]["draft_unknown_count"] == 1
    row = report["rows"][0]
    assert row["draft_status"] == "unknown_missing_candidate_evidence"
    assert row["contract_validation"]["contract_valid"]


def test_local_structured_text_policy_drafts_channel_service_known_review(
    tmp_path: Path,
) -> None:
    readiness_path = tmp_path / "readiness.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(
        readiness_path,
        {"rows": [_readiness_row("L0.supply.channel_service")]},
    )
    _write_json(candidate_path, {"rows": [_channel_service_candidate()]})

    report = audit.build_report(readiness_path, candidate_path)

    assert report["summary"]["draft_known_count"] == 1
    assert report["summary"]["draft_unknown_count"] == 0
    assert report["summary"]["bridge_validated_known_count"] == 1
    assert report["summary"]["bridge_blocked_known_count"] == 0
    assert report["summary"]["qa_channel_service_known_draft_count"] == 1
    row = report["rows"][0]
    payload = row["draft_payload"]
    assert payload["data_status"] == "Known"
    assert row["draft_status"] == "draft_known_qa_channel_service_review_required"
    assert row["bridge_validation"]["final_score_target_ready"]
    assert -1.0 <= payload["value_json"]["score"] <= 1.0
    assert payload["safe_to_upsert_without_review"] is False
    assert row["production_write_allowed"] is False
    assert "批量配套" in payload["value_json"]["components"]["matched_keywords"]


def test_local_structured_text_policy_drafts_discount_pressure_known_review(
    tmp_path: Path,
) -> None:
    readiness_path = tmp_path / "readiness.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(
        readiness_path,
        {"rows": [_readiness_row("L0.price.discount")]},
    )
    _write_json(candidate_path, {"rows": [_discount_pressure_candidate()]})

    report = audit.build_report(readiness_path, candidate_path)

    assert report["summary"]["draft_known_count"] == 1
    assert report["summary"]["draft_unknown_count"] == 0
    assert report["summary"]["bridge_validated_known_count"] == 1
    assert report["summary"]["qa_discount_pressure_known_draft_count"] == 1
    row = report["rows"][0]
    payload = row["draft_payload"]
    assert payload["data_status"] == "Known"
    assert row["draft_status"] == "draft_known_qa_discount_pressure_review_required"
    assert row["bridge_validation"]["final_score_target_ready"]
    assert -1.0 <= payload["value_json"]["score"] < 0.0
    assert payload["safe_to_upsert_without_review"] is False
    assert row["production_write_allowed"] is False
    assert "价格下降" in payload["value_json"]["components"]["matched_keywords"]


def test_local_structured_text_policy_drafts_user_count_known_review(
    tmp_path: Path,
) -> None:
    readiness_path = tmp_path / "readiness.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(
        readiness_path,
        {"rows": [_readiness_row("L0.demand.user_count")]},
    )
    _write_json(candidate_path, {"rows": [_user_count_demand_candidate()]})

    report = audit.build_report(readiness_path, candidate_path)

    assert report["summary"]["draft_known_count"] == 1
    assert report["summary"]["draft_unknown_count"] == 0
    assert report["summary"]["bridge_validated_known_count"] == 1
    assert report["summary"]["qa_user_count_known_draft_count"] == 1
    row = report["rows"][0]
    payload = row["draft_payload"]
    assert payload["data_status"] == "Known"
    assert row["draft_status"] == "draft_known_qa_user_count_review_required"
    assert row["bridge_validation"]["final_score_target_ready"]
    assert 0.0 < payload["value_json"]["score"] <= 1.0
    assert payload["safe_to_upsert_without_review"] is False
    assert row["production_write_allowed"] is False
    components = payload["value_json"]["components"]
    assert "订单数量" in components["matched_keywords"]
    assert "用户规模" in components["matched_keywords"]
    assert "股东户数" in components["excluded_contexts"]


def test_local_structured_text_policy_drafts_excludes_shareholder_count_noise(
    tmp_path: Path,
) -> None:
    readiness_path = tmp_path / "readiness.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(
        readiness_path,
        {"rows": [_readiness_row("L0.demand.user_count")]},
    )
    _write_json(candidate_path, {"rows": [_shareholder_count_noise_candidate()]})

    report = audit.build_report(readiness_path, candidate_path)

    assert report["summary"]["draft_known_count"] == 0
    assert report["summary"]["draft_unknown_count"] == 1
    row = report["rows"][0]
    assert row["draft_status"] == "unknown_text_classification_required"
    assert row["draft_payload"]["value_json"]["blocked_reason"] == (
        "qa_recent_requires_customer_user_extraction"
    )
