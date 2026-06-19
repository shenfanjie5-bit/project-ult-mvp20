import json
from pathlib import Path

from scripts import audit_a_share_event_text_policy_drafts as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _readiness_row(dp_id: str, score_target: str = "fundamental_score") -> dict:
    return {
        "dp_id": dp_id,
        "score_target": score_target,
        "route_bucket": "event_text_classification_required",
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
        "sample_rows": [_sample("MARKET:CN", value) for value in values],
    }


def _candidate(dp_id: str, deps: list[dict], score_target: str = "fundamental_score") -> dict:
    return {
        "dp_id": dp_id,
        "score_target": score_target,
        "source_dependencies": [dep["dp_id"] for dep in deps],
        "candidate_input": {
            "target_dp_id": dp_id,
            "score_target": score_target,
            "dependencies": deps,
        },
    }


def _market_doc_row(
    dp_id: str,
    status: str = "market_doc_review_ready",
    target_hit: str = "价格战",
    direct_hits: tuple[str, str, str] = ("A股", "产业链", "板块"),
) -> dict:
    examples = [
        {
            "market_relative_path": f"news/test/{dp_id}.html",
            "target_hits": [target_hit],
            "direct_transmission_hits": [direct_hits[0]],
            "same_sentence_hits": [
                {
                    "excerpt": f"{target_hit}压力直接传导至{direct_hits[0]}相关产业链公司。",
                    "target_hits": [target_hit],
                    "direct_transmission_hits": [direct_hits[0]],
                }
            ],
        },
        {
            "market_relative_path": f"news/test/{dp_id}-2.html",
            "target_hits": [target_hit],
            "direct_transmission_hits": [direct_hits[1]],
            "same_sentence_hits": [
                {
                    "excerpt": f"{direct_hits[1]}公司受到{target_hit}影响。",
                    "target_hits": [target_hit],
                    "direct_transmission_hits": [direct_hits[1]],
                }
            ],
        },
        {
            "market_relative_path": f"news/test/{dp_id}-3.html",
            "target_hits": [target_hit],
            "direct_transmission_hits": [direct_hits[2]],
            "same_sentence_hits": [
                {
                    "excerpt": f"相关{direct_hits[2]}继续反映{target_hit}冲击。",
                    "target_hits": [target_hit],
                    "direct_transmission_hits": [direct_hits[2]],
                }
            ],
        },
    ]
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "classification_packet_status": status,
        "blocked_reason": "classifier_review_required",
        "required_evidence": ["reviewed direction"],
        "candidate_examples": examples if status == "market_doc_review_ready" else [],
    }


def _market_doc_row_with_examples(dp_id: str, examples: list[dict]) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "classification_packet_status": "market_doc_review_ready",
        "blocked_reason": "classifier_review_required",
        "required_evidence": ["reviewed direction"],
        "candidate_examples": examples,
    }


def _fixture_candidate_rows() -> list[dict]:
    media = _dep(
        "L9.media.report",
        [
            {
                "count_24h": 3,
                "event_active": True,
                "top_headlines": [{"title": "broad market headline"}],
            }
        ],
    )
    compete = _dep(
        "L9.industry.compete_risk",
        [
            {
                "count_24h": 1,
                "event_active": True,
                "top_headlines": [{"title": "competition headline"}],
            }
        ],
    )
    policy = _dep(
        "L9.industry.policy_change",
        [
            {
                "count_24h": 1,
                "event_active": True,
                "net_policy_score": -1,
                "top_headlines": [{"title": "policy headline"}],
            }
        ],
    )
    fx = _dep(
        "L9.macro.fx",
        [{"score": 0, "direction": "neutral", "risk_event": False}],
    )
    geo = _dep(
        "L9.macro.geo",
        [
            {
                "count_24h": 2,
                "event_active": True,
                "top_headlines": [{"title": "geopolitical headline"}],
            }
        ],
    )
    return [
        _candidate("L0.compete.new_entrant", [compete, media]),
        _candidate("L0.compete.price_war", [compete, media]),
        _candidate("L0.compete.share_concentration", [compete, media]),
        _candidate("L0.policy.access_license", [policy, media]),
        _candidate("L0.policy.regulation", [policy, media]),
        _candidate("L0.policy.subsidy", [policy, media]),
        _candidate("L0.policy.tax_trade", [policy, fx]),
        _candidate("L0.tech.ai_automation", [media, compete]),
        _candidate("L0.tech.breakthrough", [media, compete]),
        _candidate("L0.tech.substitute_tech", [media, compete]),
        _candidate("L8.shock.black_swan", [media, geo], score_target="risk_discount"),
        _candidate("L8.shock.supply_break", [media, compete], score_target="risk_discount"),
    ]


def test_event_text_policy_drafts_keep_review_gated_unknowns(tmp_path: Path) -> None:
    readiness_path = tmp_path / "readiness.json"
    candidate_path = tmp_path / "candidate.json"
    fundamental_ids = [
        "L0.compete.new_entrant",
        "L0.compete.price_war",
        "L0.compete.share_concentration",
        "L0.policy.access_license",
        "L0.policy.regulation",
        "L0.policy.subsidy",
        "L0.policy.tax_trade",
        "L0.tech.ai_automation",
        "L0.tech.breakthrough",
        "L0.tech.substitute_tech",
    ]
    shock_ids = ["L8.shock.black_swan", "L8.shock.supply_break"]
    _write_json(
        readiness_path,
        {"rows": [_readiness_row(dp_id) for dp_id in fundamental_ids] + [_readiness_row(dp_id, "risk_discount") for dp_id in shock_ids]},
    )
    _write_json(candidate_path, {"rows": _fixture_candidate_rows()})

    report = audit.build_report(readiness_path, candidate_path)

    assert report["summary"]["event_text_task_count"] == 12
    assert report["summary"]["draft_known_count"] == 0
    assert report["summary"]["draft_unknown_count"] == 12
    assert report["summary"]["draft_contract_valid_count"] == 12
    assert report["summary"]["draft_contract_invalid_count"] == 0
    assert report["summary"]["bridge_validated_known_count"] == 0
    assert report["summary"]["review_required_count"] == 12
    assert report["summary"]["safe_to_upsert_without_review_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["summary"]["draft_status_counts"] == {
        "unknown_event_text_classification_required": 12
    }

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    price_war_payload = by_dp["L0.compete.price_war"]["draft_payload"]
    assert price_war_payload["data_status"] == "Unknown"
    assert (
        price_war_payload["value_json"]["blocked_reason"]
        == "event_text_requires_price_war_classification"
    )
    assert by_dp["L8.shock.black_swan"]["score_target"] == "risk_discount"
    assert by_dp["L8.shock.black_swan"]["contract_validation"]["contract_valid"]
    assert "Draft Unknown packets: `12`" in audit.render_markdown(report)


def test_event_text_policy_drafts_marks_missing_candidate_unknown(tmp_path: Path) -> None:
    readiness_path = tmp_path / "readiness.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(readiness_path, {"rows": [_readiness_row("L0.compete.price_war")]})
    _write_json(candidate_path, {"rows": []})

    report = audit.build_report(readiness_path, candidate_path)

    assert report["summary"]["draft_known_count"] == 0
    assert report["summary"]["draft_unknown_count"] == 1
    row = report["rows"][0]
    assert row["draft_status"] == "unknown_missing_candidate_evidence"
    assert row["contract_validation"]["contract_valid"]


def test_event_text_policy_drafts_uses_market_doc_packets_for_review_knowns(
    tmp_path: Path,
) -> None:
    readiness_path = tmp_path / "readiness.json"
    candidate_path = tmp_path / "candidate.json"
    market_doc_path = tmp_path / "market_doc.json"
    _write_json(
        readiness_path,
        {
            "rows": [
                _readiness_row("L0.compete.price_war"),
                _readiness_row("L0.policy.regulation"),
                _readiness_row("L0.policy.tax_trade"),
                _readiness_row("L0.compete.new_entrant"),
            ]
        },
    )
    _write_json(
        candidate_path,
        {
            "rows": [
                row
                for row in _fixture_candidate_rows()
                if row["dp_id"]
                in {
                    "L0.compete.price_war",
                    "L0.policy.regulation",
                    "L0.policy.tax_trade",
                    "L0.compete.new_entrant",
                }
            ]
        },
    )
    _write_json(
        market_doc_path,
        {
            "rows": [
                _market_doc_row("L0.compete.price_war"),
                _market_doc_row("L0.policy.regulation"),
                _market_doc_row(
                    "L0.policy.tax_trade",
                    target_hit="关税",
                    direct_hits=("出口", "进口", "供应链"),
                ),
                _market_doc_row(
                    "L0.compete.new_entrant",
                    status="requires_direct_transmission_link",
                ),
            ]
        },
    )

    report = audit.build_report(readiness_path, candidate_path, market_doc_path)

    assert report["summary"]["event_text_task_count"] == 4
    assert report["summary"]["draft_known_count"] == 3
    assert report["summary"]["draft_unknown_count"] == 1
    assert report["summary"]["bridge_validated_known_count"] == 3
    assert report["summary"]["bridge_blocked_known_count"] == 0
    assert report["summary"]["market_doc_known_review_draft_count"] == 3
    assert report["summary"]["market_doc_unknown_policy_required_count"] == 0
    assert report["summary"]["market_doc_unknown_evidence_required_count"] == 1
    assert report["summary"]["production_write_allowed_count"] == 0

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    price_war = by_dp["L0.compete.price_war"]
    assert price_war["draft_payload"]["data_status"] == "Known"
    assert price_war["draft_status"] == "draft_known_market_doc_review_required"
    assert -1.0 <= price_war["draft_payload"]["value_json"]["score"] <= 1.0
    assert price_war["bridge_validation"]["final_score_target_ready"]
    assert price_war["draft_payload"]["safe_to_upsert_without_review"] is False
    assert price_war["production_write_allowed"] is False
    assert any(
        ref.startswith("dockcase:")
        for ref in price_war["draft_payload"]["evidence_refs"]
    )
    tax_trade = by_dp["L0.policy.tax_trade"]
    assert tax_trade["draft_payload"]["data_status"] == "Known"
    assert tax_trade["draft_payload"]["value_json"]["score"] < 0
    assert tax_trade["bridge_validation"]["final_score_target_ready"]
    regulation = by_dp["L0.policy.regulation"]
    assert regulation["draft_payload"]["data_status"] == "Known"
    assert regulation["draft_payload"]["value_json"]["score"] < 0
    assert regulation["bridge_validation"]["final_score_target_ready"]
    assert by_dp["L0.compete.new_entrant"]["draft_status"] == (
        "unknown_market_doc_evidence_required"
    )


def test_event_text_policy_drafts_filters_substitute_tech_false_positives(
    tmp_path: Path,
) -> None:
    readiness_path = tmp_path / "readiness.json"
    candidate_path = tmp_path / "candidate.json"
    market_doc_path = tmp_path / "market_doc.json"
    _write_json(
        readiness_path,
        {"rows": [_readiness_row("L0.tech.substitute_tech")]},
    )
    _write_json(
        candidate_path,
        {
            "rows": [
                row
                for row in _fixture_candidate_rows()
                if row["dp_id"] == "L0.tech.substitute_tech"
            ]
        },
    )
    _write_json(
        market_doc_path,
        {
            "rows": [
                _market_doc_row_with_examples(
                    "L0.tech.substitute_tech",
                    [
                        {
                            "market_relative_path": "news/test/import-substitution.html",
                            "title": "公告全知道",
                            "target_hits": ["替代"],
                            "direct_transmission_hits": ["进口"],
                            "same_sentence_hits": [
                                {
                                    "excerpt": "公司产品在PCB、锂电等领域已规模化替代进口设备。",
                                    "target_hits": ["替代"],
                                    "direct_transmission_hits": ["进口"],
                                }
                            ],
                        },
                        {
                            "market_relative_path": "news/test/foreign-oil-route.html",
                            "title": "斯洛伐克寻求替代管道",
                            "target_hits": ["替代"],
                            "direct_transmission_hits": ["进口"],
                            "same_sentence_hits": [
                                {
                                    "excerpt": "斯洛伐克正通过输油管道进口石油替代方案保障燃料供应。",
                                    "target_hits": ["替代"],
                                    "direct_transmission_hits": ["进口"],
                                }
                            ],
                        },
                    ],
                )
            ]
        },
    )

    report = audit.build_report(readiness_path, candidate_path, market_doc_path)

    row = report["rows"][0]
    assert row["draft_status"] == "unknown_market_doc_clean_evidence_required"
    value_json = row["draft_payload"]["value_json"]
    assert value_json["blocked_reason"] == (
        "market_doc_clean_substitution_risk_evidence_required"
    )
    assert value_json["retained_market_doc_examples"] == 2
    assert value_json["clean_substitution_risk_examples"] == 0
    assert report["summary"]["draft_known_count"] == 0
    assert report["summary"]["draft_unknown_count"] == 1
    assert report["summary"]["draft_status_counts"] == {
        "unknown_market_doc_clean_evidence_required": 1
    }


def test_event_text_policy_drafts_accepts_clean_substitute_tech_risk_examples(
    tmp_path: Path,
) -> None:
    readiness_path = tmp_path / "readiness.json"
    candidate_path = tmp_path / "candidate.json"
    market_doc_path = tmp_path / "market_doc.json"
    _write_json(
        readiness_path,
        {"rows": [_readiness_row("L0.tech.substitute_tech")]},
    )
    _write_json(
        candidate_path,
        {
            "rows": [
                row
                for row in _fixture_candidate_rows()
                if row["dp_id"] == "L0.tech.substitute_tech"
            ]
        },
    )
    _write_json(
        market_doc_path,
        {
            "rows": [
                _market_doc_row_with_examples(
                    "L0.tech.substitute_tech",
                    [
                        {
                            "market_relative_path": "news/test/sub-risk-1.html",
                            "title": "新技术替代风险传导至A股产业链",
                            "target_hits": ["替代风险"],
                            "direct_transmission_hits": ["A股"],
                            "same_sentence_hits": [
                                {
                                    "excerpt": "新一代技术取代传统方案，A股相关产业链公司面临被替代风险。",
                                    "target_hits": ["取代传统", "被替代"],
                                    "direct_transmission_hits": ["A股", "产业链"],
                                }
                            ],
                        },
                        {
                            "market_relative_path": "news/test/sub-risk-2.html",
                            "title": "替代技术冲击上市公司产品线",
                            "target_hits": ["替代技术"],
                            "direct_transmission_hits": ["上市公司"],
                            "same_sentence_hits": [
                                {
                                    "excerpt": "替代技术加速成熟，上市公司原有产品线受到冲击。",
                                    "target_hits": ["替代技术", "冲击"],
                                    "direct_transmission_hits": ["上市公司"],
                                }
                            ],
                        },
                    ],
                )
            ]
        },
    )

    report = audit.build_report(readiness_path, candidate_path, market_doc_path)

    row = report["rows"][0]
    assert row["draft_status"] == "draft_known_market_doc_review_required"
    payload = row["draft_payload"]
    assert payload["data_status"] == "Known"
    assert payload["value_json"]["score"] < 0
    assert payload["value_json"]["components"]["market_doc_examples"] == 2
    assert payload["value_json"]["components"]["classification"] == (
        "substitute_technology_displacement_risk"
    )
    assert row["bridge_validation"]["final_score_target_ready"]
