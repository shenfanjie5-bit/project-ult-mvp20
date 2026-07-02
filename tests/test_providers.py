"""Tests for the data provider catalog (config/data_providers.yaml)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from mvp20.providers import (
    VALID_AUTH_TYPES,
    VALID_CAPABILITIES,
    VALID_MARKETS,
    VALID_PROVIDER_STATUSES,
    validate_provider_catalog,
)


ROOT = Path(__file__).resolve().parents[1]
PROVIDERS_PATH = ROOT / "config" / "data_providers.yaml"


# ---------------------------------------------------------------------------
# Vocabulary sanity
# ---------------------------------------------------------------------------


def test_provider_vocabularies_have_expected_members() -> None:
    assert VALID_MARKETS == {"A", "HK", "US"}
    assert "api_key" in VALID_AUTH_TYPES
    assert "none" in VALID_AUTH_TYPES
    assert "active" in VALID_PROVIDER_STATUSES
    assert {"price_daily", "options_chain", "options_iv", "news"} <= VALID_CAPABILITIES


# ---------------------------------------------------------------------------
# Real catalog
# ---------------------------------------------------------------------------


def test_real_provider_catalog_validates_with_universe_markets() -> None:
    result = validate_provider_catalog(
        PROVIDERS_PATH, required_markets={"A", "HK", "US"}
    )

    assert result.ok, result.errors
    assert result.catalog_id == "mvp20-providers-v1"
    assert result.provider_count >= 5
    assert "fmp" in result.active_providers
    assert "tushare" in result.active_providers
    assert "futu" in result.active_providers
    # Every market in the leader pool has at least one active provider.
    for market in ("A", "HK", "US"):
        assert result.market_coverage[market], market


def test_options_data_covered_by_futu_only_on_starter_tier() -> None:
    """On FMP Starter ($14/mo), options_chain / options_iv are NOT
    accessible — Futu OpenD is the sole active provider for options.
    When FMP upgrades to Premium, these capabilities should be restored
    to FMP and this test should assert {fmp, futu}."""

    result = validate_provider_catalog(PROVIDERS_PATH)

    assert "futu" in result.capability_coverage["options_chain"]
    assert "futu" in result.capability_coverage["options_iv"]
    # FMP currently locked behind Premium tier; document the gap
    assert "fmp" not in result.capability_coverage["options_chain"]
    assert "fmp" not in result.capability_coverage["options_iv"]


def test_fmp_serves_us_market_first_class() -> None:
    result = validate_provider_catalog(PROVIDERS_PATH)
    assert "fmp" in result.market_coverage["US"]


def test_futu_serves_hk_and_us() -> None:
    result = validate_provider_catalog(PROVIDERS_PATH)
    assert "futu" in result.market_coverage["HK"]
    assert "futu" in result.market_coverage["US"]


def test_futu_uniquely_covers_microstructure_capabilities() -> None:
    """Order-book / tick / broker-queue / push capabilities have no
    equivalent in FMP, AKShare or yfinance — Futu OpenD is the sole
    active provider."""

    result = validate_provider_catalog(PROVIDERS_PATH)

    futu_only = ("quote_l2", "tick_trades", "broker_queue_hk",
                 "realtime_push", "warrants", "index_futures")
    for cap in futu_only:
        providers = result.capability_coverage.get(cap, ())
        assert providers == ("futu",), (cap, providers)


def test_fmp_starter_tier_unique_capabilities() -> None:
    """On Starter, FMP retains insider_trading (basic) as a single-source
    capability. After 2026-05 user-verified probing, sec_filings,
    dcf_valuation, and analyst_estimates (dual-sourced w/ tushare) are
    also reachable on Starter. earnings_transcripts remains Premium-locked
    with NO active provider."""

    result = validate_provider_catalog(PROVIDERS_PATH)

    # FMP-only on Starter
    assert result.capability_coverage.get("insider_trading", ()) == ("fmp",)
    assert result.capability_coverage.get("sec_filings", ()) == ("fmp",)
    assert result.capability_coverage.get("dcf_valuation", ()) == ("fmp",)


def test_premium_locked_capabilities_have_no_active_provider() -> None:
    """Capabilities behind FMP Premium that have no fallback provider
    should be present in the vocabulary but NOT in capability_coverage
    (capability_coverage only lists capabilities with ≥1 active provider).

    Note 2026-05: user-verified that sec_filings, dcf_valuation, and
    analyst_estimates ARE reachable on the Starter tier, so they were
    moved to the active capability list. earnings_transcripts remains
    the only single-sourced FMP-only capability with no active provider."""

    result = validate_provider_catalog(PROVIDERS_PATH)

    no_fallback_premium = ("earnings_transcripts",)
    for cap in no_fallback_premium:
        providers = result.capability_coverage.get(cap, ())
        assert providers == (), (cap, providers,
                                "should be empty until FMP upgrades to Premium")


def test_ultimate_locked_capabilities_have_no_active_provider() -> None:
    """ESG / government trading need FMP Ultimate ($49/mo) — until then
    no active provider claims them."""

    result = validate_provider_catalog(PROVIDERS_PATH)

    for cap in ("esg_score", "government_trading"):
        providers = result.capability_coverage.get(cap, ())
        assert providers == (), (cap, providers,
                                 "should be empty until FMP upgrades to Ultimate")


def test_analyst_estimates_dual_sourced_fmp_and_tushare() -> None:
    """analyst_estimates is dual-sourced: FMP Starter (user-verified
    2026-05 — /stable/analyst-estimates is reachable) plus Tushare's
    report_rc endpoint. Operators can cross-validate analyst forecasts
    against both sources."""

    result = validate_provider_catalog(PROVIDERS_PATH)

    providers = result.capability_coverage.get("analyst_estimates", ())
    assert set(providers) == {"fmp", "tushare"}, providers


def test_round4_fmp_starter_accessible_unique_capabilities() -> None:
    """Round 4 introduced 6 FMP-unique capabilities. Of those, 3 are
    accessible on Starter ($14/mo) and currently active; 3 require
    higher tiers and are tier-locked."""

    result = validate_provider_catalog(PROVIDERS_PATH)

    starter_accessible = ("treasury_rates", "corporate_actions", "peer_comparison")
    for cap in starter_accessible:
        providers = result.capability_coverage.get(cap, ())
        assert providers == ("fmp",), (cap, providers)


def test_round4_futu_company_profile_added() -> None:
    """Round 4 (Futu audit) added company_profile to Futu — it should now
    have 5-source coverage (every active provider)."""

    result = validate_provider_catalog(PROVIDERS_PATH)

    providers = result.capability_coverage.get("company_profile", ())
    assert set(providers) == {"akshare", "fmp", "futu", "tushare", "yfinance"}


def test_endpoint_csvs_exist_and_have_expected_rows() -> None:
    """The CSV inventories in docs/data_sources/ should be present and
    cover their respective endpoint counts."""

    docs_dir = ROOT / "docs" / "data_sources"
    assert (docs_dir / "tushare_endpoints.csv").exists()
    assert (docs_dir / "futu_endpoints.csv").exists()
    assert (docs_dir / "fmp_endpoints.csv").exists()
    assert (docs_dir / "README.md").exists()
    assert (docs_dir / "FMP_TIER_REQUIREMENTS.md").exists()

    import csv as _csv

    with open(docs_dir / "tushare_endpoints.csv", encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))
    # 145 endpoint rows: user-supplied snapshot plus current code-path additions.
    assert len(rows) == 145

    with open(docs_dir / "fmp_endpoints.csv", encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))
    # FMP inventory includes ~80 endpoints
    assert len(rows) >= 70


def test_tushare_round3_a_share_specific_capabilities_present() -> None:
    """Round-3 expansion (after reconciling Tushare 138-endpoint coverage):
    A-share specific capabilities should be present and have at least one
    Chinese-market provider."""

    result = validate_provider_catalog(PROVIDERS_PATH)

    a_share_caps = (
        "equity_pledge", "ah_premium", "chip_distribution",
        "risk_warning", "sentiment_hot_list", "market_capital_flow",
    )
    for cap in a_share_caps:
        providers = result.capability_coverage.get(cap, ())
        assert "tushare" in providers, (cap, providers)
        assert "akshare" in providers, (cap, providers)


def test_investor_relations_qa_is_tushare_unique() -> None:
    """上证 e 互动 / 深证易互动 (irm_qa_sh / irm_qa_sz) is unique to
    Tushare's 大模型语料专题数据 — primary fuel for the future core-pool
    LLM analysis epic."""

    result = validate_provider_catalog(PROVIDERS_PATH)

    providers = result.capability_coverage.get("investor_relations_qa", ())
    assert providers == ("tushare",), providers


def test_dividends_have_four_providers() -> None:
    """Dividends are the high-yield strategy backbone for the financial
    sector — should be covered by 4 providers for cross-validation."""

    result = validate_provider_catalog(PROVIDERS_PATH)

    providers = result.capability_coverage.get("dividends", ())
    assert {"tushare", "akshare", "fmp", "yfinance"} <= set(providers)


def test_market_index_covered_by_all_active_providers() -> None:
    """Market beta extraction (r_market in `r_i = β_m·r_market + β_s·r_sector + α`)
    needs index quotes from every market — all 5 active providers must
    declare market_index capability."""

    result = validate_provider_catalog(PROVIDERS_PATH)

    providers = result.capability_coverage.get("market_index", ())
    assert set(providers) == {"akshare", "fmp", "futu", "tushare", "yfinance"}


def test_capital_flow_and_cross_border_have_three_providers() -> None:
    """A-share / HK capital-flow + Stock Connect 北向/南向 have three
    sources (Tushare + AKShare + Futu) — operators can cross-validate."""

    result = validate_provider_catalog(PROVIDERS_PATH)

    for cap in ("capital_flow", "cross_border_flow"):
        providers = result.capability_coverage.get(cap, ())
        assert set(providers) == {"akshare", "futu", "tushare"}, (cap, providers)


def test_planned_provider_emits_warning_only() -> None:
    result = validate_provider_catalog(PROVIDERS_PATH)
    assert any(
        "fred" in w and "planned" in w for w in result.warnings
    ), result.warnings


def test_deferred_status_emits_warning_via_synthetic_catalog(tmp_path: Path) -> None:
    """Coverage for the deferred-status warning path. Uses a synthetic
    catalog because the shipped catalog currently has no deferred entries
    (futu was promoted to active)."""

    catalog = _load()
    # Force one provider to deferred. Pick yfinance so US still has fmp +
    # futu as active sources and the required-markets check passes.
    for provider in catalog["providers"]:
        if provider["id"] == "yfinance":
            provider["status"] = "deferred"
            break
    path = _write(tmp_path, catalog)

    result = validate_provider_catalog(path)

    assert any(
        "yfinance" in w and "deferred" in w for w in result.warnings
    ), result.warnings


# ---------------------------------------------------------------------------
# Negative cases
# ---------------------------------------------------------------------------


def _load() -> dict:
    return yaml.safe_load(PROVIDERS_PATH.read_text(encoding="utf-8"))


def _write(tmp: Path, payload: dict) -> Path:
    p = tmp / "x.yaml"
    p.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return p


def test_missing_required_market_fails(tmp_path: Path) -> None:
    catalog = _load()
    catalog["providers"] = [
        c for c in catalog["providers"] if "US" not in c["supported_markets"]
    ]
    path = _write(tmp_path, catalog)

    result = validate_provider_catalog(path, required_markets={"US"})

    assert not result.ok
    assert any("market 'US' has no active provider" in e for e in result.errors)


def test_unknown_capability_rejected(tmp_path: Path) -> None:
    catalog = _load()
    catalog["providers"][0]["capabilities"].append("crystal_ball")
    path = _write(tmp_path, catalog)

    result = validate_provider_catalog(path)

    assert not result.ok
    assert any(
        "unknown capability" in e and "crystal_ball" in e for e in result.errors
    )


def test_unknown_market_rejected(tmp_path: Path) -> None:
    catalog = _load()
    catalog["providers"][0]["supported_markets"].append("Mars")
    path = _write(tmp_path, catalog)

    result = validate_provider_catalog(path)

    assert not result.ok
    assert any(
        "unknown market" in e and "Mars" in e for e in result.errors
    )


def test_duplicate_provider_id_rejected(tmp_path: Path) -> None:
    catalog = _load()
    dup = deepcopy(catalog["providers"][0])
    catalog["providers"].append(dup)
    path = _write(tmp_path, catalog)

    result = validate_provider_catalog(path)

    assert not result.ok
    assert any("id duplicated" in e for e in result.errors)


def test_invalid_provider_id_format_rejected(tmp_path: Path) -> None:
    catalog = _load()
    catalog["providers"][0]["id"] = "FMP"  # uppercase not allowed
    path = _write(tmp_path, catalog)

    result = validate_provider_catalog(path)

    assert not result.ok
    assert any("lower_snake_case" in e for e in result.errors)


def test_secret_env_var_required_for_api_key_auth(tmp_path: Path) -> None:
    catalog = _load()
    for provider in catalog["providers"]:
        if provider["id"] == "fmp":
            provider.pop("secret_env_var")
            break
    path = _write(tmp_path, catalog)

    result = validate_provider_catalog(path)

    assert not result.ok
    assert any("secret_env_var is required" in e for e in result.errors)


def test_inline_secret_rejected(tmp_path: Path) -> None:
    """Storing the literal API key in the catalog must fail validation."""

    catalog = _load()
    for provider in catalog["providers"]:
        if provider["id"] == "fmp":
            provider["api_key"] = "hardcoded-secret-NEVER-COMMIT"
            break
    path = _write(tmp_path, catalog)

    result = validate_provider_catalog(path)

    assert not result.ok
    assert any("must not embed a literal" in e for e in result.errors)


def test_invalid_base_url_rejected(tmp_path: Path) -> None:
    catalog = _load()
    catalog["providers"][0]["base_url"] = "ftp://bad.example.com"
    path = _write(tmp_path, catalog)

    result = validate_provider_catalog(path)

    assert not result.ok
    assert any("base_url must be an http(s) URL" in e for e in result.errors)


def test_zero_rate_limit_rejected(tmp_path: Path) -> None:
    catalog = _load()
    catalog["providers"][0]["rate_limit_per_minute"] = 0
    path = _write(tmp_path, catalog)

    result = validate_provider_catalog(path)

    assert not result.ok
    assert any("rate_limit_per_minute" in e and "> 0" in e for e in result.errors)


# ---------------------------------------------------------------------------
# local_gateway auth (Futu OpenD)
# ---------------------------------------------------------------------------


def test_local_gateway_requires_gateway_block(tmp_path: Path) -> None:
    catalog = _load()
    for provider in catalog["providers"]:
        if provider["id"] == "futu":
            provider.pop("gateway", None)
            break
    path = _write(tmp_path, catalog)

    result = validate_provider_catalog(path)

    assert not result.ok
    assert any(
        "gateway block is required for auth_type=local_gateway" in e
        for e in result.errors
    )


def test_local_gateway_requires_host(tmp_path: Path) -> None:
    catalog = _load()
    for provider in catalog["providers"]:
        if provider["id"] == "futu":
            provider["gateway"] = {"port": 11111}
            break
    path = _write(tmp_path, catalog)

    result = validate_provider_catalog(path)

    assert not result.ok
    assert any("gateway.host is required" in e for e in result.errors)


def test_local_gateway_port_range_enforced(tmp_path: Path) -> None:
    catalog = _load()
    for provider in catalog["providers"]:
        if provider["id"] == "futu":
            provider["gateway"]["port"] = 70000  # outside 1..65535
            break
    path = _write(tmp_path, catalog)

    result = validate_provider_catalog(path)

    assert not result.ok
    assert any(
        "gateway.port must be in [1, 65535]" in e for e in result.errors
    )


def test_local_gateway_does_not_require_base_url(tmp_path: Path) -> None:
    """Futu OpenD has no remote HTTP endpoint — base_url omission is OK
    for local_gateway providers."""

    catalog = _load()
    for provider in catalog["providers"]:
        if provider["id"] == "futu":
            provider.pop("base_url", None)
            break
    path = _write(tmp_path, catalog)

    result = validate_provider_catalog(path)

    assert result.ok, result.errors


def test_non_local_gateway_requires_base_url(tmp_path: Path) -> None:
    """Cloud REST providers (FMP, Tushare, etc.) must declare base_url."""

    catalog = _load()
    for provider in catalog["providers"]:
        if provider["id"] == "fmp":
            provider.pop("base_url", None)
            break
    path = _write(tmp_path, catalog)

    result = validate_provider_catalog(path)

    assert not result.ok
    assert any(
        "base_url is required for auth_type" in e for e in result.errors
    )
