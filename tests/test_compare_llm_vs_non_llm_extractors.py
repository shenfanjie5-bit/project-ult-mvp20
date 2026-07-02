from collections import Counter
import json
import sqlite3
from pathlib import Path

from mvp20 import schema_validator
from scripts import compare_llm_vs_non_llm_extractors as cmp


def _conn(rows: list[tuple[str, str, str, object, str]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE realtime_current (
            ts_code TEXT,
            dp_id TEXT,
            value_json TEXT,
            data_status TEXT,
            source TEXT,
            updated_at TEXT
        )
        """
    )
    for ts_code, dp_id, status, value, source in rows:
        conn.execute(
            "INSERT INTO realtime_current VALUES (?, ?, ?, ?, ?, ?)",
            (ts_code, dp_id, json.dumps(value, ensure_ascii=False), status, source, "2026-06-23"),
        )
    return conn


def _info(ts_code: str, industry_id: str, name: str) -> cmp.OverlayInfo:
    return cmp.OverlayInfo(ts_code=ts_code, industry_id=industry_id, name=name, path=Path("/tmp/overlay.yaml"))


def test_llm_scope_includes_82_fields_with_cheap_extract() -> None:
    scope = cmp._llm_scope(cmp.ROOT, include_cheap_extract=True)
    tiers = Counter(entry.get("model_tier") for entry in scope.values())

    assert len(scope) == 82
    assert tiers == {
        "cheap_extract": 6,
        "cheap_classify": 18,
        "analysis": 50,
        "web_analysis": 8,
    }


def test_channel_mix_sales_mode_table_parser() -> None:
    text = """
    分销售模式
    直销 37,738,951,113.82 98.69% 23,500,873,808.86 98.49% 60.59%
    渠道 500,984,526.85 1.31% 361,285,929.51 1.51% 38.67%
    """

    assert cmp._parse_channel_mix_from_text(text) == {
        "direct_pct": 98.69,
        "distributor_pct": 1.31,
        "ecommerce_pct": 0.0,
        "others_pct": 0.0,
    }


def test_channel_mix_business_proxy_for_b2b() -> None:
    proxy = cmp._channel_mix_proxy_from_business_text(
        "主营业务为高密度印制线路板PCB的研发、生产和销售，服务全球企业客户。"
    )

    assert proxy is not None
    assert "dominant_channel=b2b_direct_or_project" in proxy["notes"]
    assert proxy["ecommerce_pct"] == 0.0


def test_channel_mix_business_proxy_for_service_channels() -> None:
    cases = {
        "主要从事人寿保险、健康保险、意外伤害保险等各类人身保险业务。": "dominant_channel=insurance_agent_direct_service",
        "公司拥有覆盖全国的现代通信网络和全球客户服务体系，发展物联网业务和智慧城市。": "dominant_channel=telecom_direct_and_service_network",
        "主要业务包括整车、汽车新车销售、二手车经销、汽车零配件批发。": "dominant_channel=auto_dealer_and_direct_sales",
        "主要采取航次租船、定期租船、COA及参与市场联营体运作(POOL)的经营模式。": "dominant_channel=shipping_contract_service",
    }

    for text, expected_note in cases.items():
        proxy = cmp._channel_mix_proxy_from_business_text(text)
        assert proxy is not None
        assert expected_note in proxy["notes"]


def test_summarize_separates_event_gate_from_parser_gap() -> None:
    rows = [
        {
            "dp_id": "L8.shock.black_swan",
            "model_tier": "cheap_classify",
            "participates_in_score": True,
            "candidate": {"category": "event_policy_gated", "method": "event_keyword_screen"},
            "comparison": {
                "baseline_available": True,
                "candidate_available": False,
                "comparison_bucket": "non_llm_missing_llm_available:gated",
            },
        },
        {
            "dp_id": "L3.customer.segment_mix",
            "model_tier": "analysis",
            "participates_in_score": False,
            "candidate": {"category": "unclassified", "method": "no_non_llm_extractor"},
            "comparison": {
                "baseline_available": True,
                "candidate_available": False,
                "comparison_bucket": "non_llm_missing_llm_available",
            },
        },
    ]
    summary = cmp._summarize(
        rows,
        {
            "L8.shock.black_swan": {"model_tier": "cheap_classify"},
            "L3.customer.segment_mix": {"model_tier": "analysis"},
        },
        {},
        [],
    )

    assert summary["event_review_gate_fields"] == ["L8.shock.black_swan"]
    assert summary["extractor_gap_fields"] == ["L3.customer.segment_mix"]


def test_litigation_execution_title_does_not_trigger_review() -> None:
    conn = _conn(
        [
            (
                "300750.SZ",
                "L9.company.mgmt_litigation",
                "Known",
                {"events": [{"type": "高管离职", "title": "执行董事", "person": "欧阳楚英"}]},
                "tushare:stk_managers",
            ),
            (
                "300750.SZ",
                "L9.media.report",
                "Known",
                {"negative_count": 0, "items": []},
                "local:media_report",
            ),
        ]
    )
    candidate = cmp._event_candidate(
        "L8.gov.litigation",
        _info("300750.SZ", "STORAGE_GRID", "宁德时代"),
        conn,
        {"L8.gov.litigation": {"source_dependencies": ["L9.company.mgmt_litigation", "L9.media.report"]}},
    )

    assert candidate["data_status"] == "Inactive"
    assert candidate["value"]["event_state"] == "none_observed"
    assert candidate["value"]["keyword_hits"] == []


def test_financial_service_rules_cover_cost_and_price_signals() -> None:
    annual_text = "融资融券利息收入同比增长，主要得益于融资融券规模的增长，融资融券利率随市场利率下行有所下降。"
    conn = _conn(
        [
            (
                "600999.SH",
                "L1.company.main_business",
                "Known",
                {"main_business": "财富管理和机构业务、投资银行、投资管理、投资及交易等金融服务"},
                "tushare:stock_company",
            ),
            (
                "600999.SH",
                "L9.disclosure.annual_report",
                "Known",
                {"sections": {"business_overview": annual_text}},
                "annual_report:cninfo:2025",
            ),
            (
                "600999.SH",
                "L2.segment.gross_margin",
                "Known",
                {"segments": [{"item": "证券投资业务", "gross_margin_pct": 76.27}]},
                "tushare:fina_mainbz",
            ),
        ]
    )
    info = _info("600999.SH", "FINANCIAL_HIGH_DIVIDEND", "招商证券")

    cost = cmp._formula_candidate("L4.cost.rent_energy_logistics", info, conn, {})
    discount = cmp._formula_candidate("L4.price.discount", info, conn, {})
    pricing = cmp._formula_candidate("L4.price.pricing_power", info, conn, {})

    assert cost["data_status"] == "N/A"
    assert cost["method"] == "industry_applicability_matrix"
    assert discount["data_status"] == "Known"
    assert discount["value"]["trend"] == "rate_down"
    assert pricing["data_status"] == "Known"
    assert pricing["value"]["strength"] == "moderate"


def test_product_portfolio_falls_back_to_main_business_lines() -> None:
    conn = _conn(
        [
            (
                "600754.SH",
                "L1.company.main_business",
                "Known",
                {
                    "main_business": "全服务型酒店营运及管理业务、有限服务型酒店营运及管理业务和食品及餐饮业务\n境内酒店服务业务,境外酒店服务业务"
                },
                "tushare:stock_company",
            )
        ]
    )

    candidate = cmp._formula_candidate("L3.product.portfolio", _info("600754.SH", "CONSUMER_SERVICE", "锦江酒店"), conn, {})

    assert candidate["data_status"] == "Known"
    assert candidate["value"]["products"] == [
        {"name": "全服务型酒店营运及管理业务", "revenue_pct": None},
        {"name": "有限服务型酒店营运及管理业务", "revenue_pct": None},
        {"name": "食品及餐饮业务", "revenue_pct": None},
    ]


def test_domestic_overseas_falls_back_to_main_business_presence() -> None:
    conn = _conn(
        [
            (
                "600754.SH",
                "L1.company.main_business",
                "Known",
                {"main_business": "境内酒店服务业务,境外酒店服务业务,餐饮服务业务及其他业务"},
                "tushare:stock_company",
            ),
            (
                "600754.SH",
                "L5.is.revenue",
                "Known",
                3120656918.51,
                "tushare:income",
            ),
        ]
    )

    candidate = cmp._formula_candidate(
        "L3.region.domestic_overseas",
        _info("600754.SH", "CONSUMER_SERVICE", "锦江酒店"),
        conn,
        {},
    )

    assert candidate["data_status"] == "Known"
    assert candidate["method"] == "main_business_region_parser"
    assert candidate["value"]["domestic_pct"] is None
    assert candidate["value"]["overseas_pct"] is None
    assert candidate["value"]["total_revenue_cny"] == 3120656918.51


def test_fx_geo_can_use_macro_fx_without_region_mix() -> None:
    conn = _conn(
        [
            (
                "600754.SH",
                "L9.macro.fx",
                "Known",
                {"value": 0.1052},
                "tushare:macro_fx",
            )
        ]
    )

    candidate = cmp._region_related_candidate("L3.region.fx_geo", _info("600754.SH", "CONSUMER_SERVICE", "锦江酒店"), conn)

    assert candidate["data_status"] == "Proxy"
    assert candidate["method"] == "macro_fx_only"
    assert candidate["value"]["domestic_pct"] is None
    assert candidate["value"]["overseas_pct"] is None
    assert candidate["value"]["fx_exposure_score"] == 0.0


def test_minimal_schemas_cover_non_llm_first_outputs() -> None:
    cases = {
        "L2.segment.opex_ratio": {"opex_ratio": 0.12, "score": -0.4, "notes": "ok"},
        "L2.segment.profit_share": {
            "segments": [{"item": "A", "revenue_pct": 60.0, "gross_margin_pct": 30.0, "gross_profit_share_pct": 70.0}],
            "top_profit_share_pct": 70.0,
        },
        "L3.channel.cost": {"ratio": 0.2, "score": -0.8, "notes": "ok"},
        "L3.channel.efficiency": {"sga_rd_ratio_revenue": 0.2, "score": 0.2},
        "L3.region.domestic_overseas": {
            "domestic_pct": None,
            "overseas_pct": None,
            "total_revenue_cny": 1.0,
            "regions": [{"name": "境内", "revenue_pct": None}],
            "source": "main_business",
        },
        "L3.region.fx_geo": {"domestic_pct": None, "overseas_pct": None, "fx_exposure_score": 0.0, "macro_fx_present": True},
        "L4.share.market": {"rank": 1, "share_pct": 12.3, "market_size_unit": "peer_runtime_revenue_sum"},
        "L4.share.substitution": {"yoy_pct": 5.0, "score": 0.1, "notes": "revenue growth proxy"},
        "L4.volume.sales": {"yoy_pct": 5.0, "score": 0.1, "notes": "revenue growth proxy"},
        "L4.volume.orders": {"yoy_pct": 5.0, "score": 0.1, "notes": "revenue growth proxy"},
        "L4.volume.shipments": {"yoy_pct": 5.0, "score": 0.1, "notes": "revenue growth proxy"},
    }

    for dp_id, value in cases.items():
        assert schema_validator.validate_value(dp_id, value) == []
