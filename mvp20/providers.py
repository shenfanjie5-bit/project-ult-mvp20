"""Data provider catalog validation.

Lists every external market-data provider the MVP plans to integrate
(FMP, Tushare, AKShare, yfinance, futu, ...) without storing any secrets
or making any HTTP calls. Each provider declares the markets it covers,
the capabilities (price / fundamentals / news / options / ...) it
exposes, the auth scheme, and the env var that holds the secret. Actual
provider clients live upstream in ``data-platform``; mvp20 only certifies
that the catalog is well-formed and that every present-graph market is
covered by at least one provider.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


VALID_MARKETS: frozenset[str] = frozenset({"A", "HK", "US"})

# Capabilities a provider can expose. Kept open-ended (free strings) but
# validated against a curated whitelist so typos don't slip through.
VALID_CAPABILITIES: frozenset[str] = frozenset(
    {
        # Core price / fundamentals (most providers)
        "price_daily",
        "price_intraday",
        "fundamentals",
        "earnings_calendar",
        "earnings_transcripts",
        "news",
        "insider_trading",
        "institutional_holdings",
        "options_chain",
        "options_iv",
        "macro",
        "forex",
        "commodities",
        "alternative_data",
        "company_profile",
        "sec_filings",
        "analyst_estimates",
        # Microstructure / order-book (uniquely Futu OpenD among the
        # active providers; FMP is L1-only, Tushare/AKShare are EOD)
        "quote_l2",
        "tick_trades",
        "broker_queue_hk",
        "realtime_push",
        # Capital flow + cross-border flow (Futu, Tushare, AKShare)
        "capital_flow",
        "cross_border_flow",
        # HK structured products + index futures + IPO calendar
        "warrants",
        "index_futures",
        "ipo_calendar",
        # Sector / plate constituent listing (Futu HK/A; complements
        # mvp20.industries.yaml but at provider granularity)
        "sector_constituents",
        # A-share market microstructure + liquidity signals
        # (Tushare-strong; required by 资金组 / 风险组 graph paths)
        "dragon_tiger_list",       # 龙虎榜 (top_list / top_inst / hm_list)
        "limit_up_down",           # 涨跌停 / 连板 (limit_list_d / kpl_concept)
        "margin_trading",          # 融资融券 (margin / margin_detail / slb_len)
        "block_trade",             # 大宗交易 (block_trade)
        "share_unlock",            # 限售解禁 (share_float)
        "holder_count",            # 股东户数 (stk_holdernumber)
        # A-share corporate-action + risk + valuation (Tushare 138-list
        # round-2 expansion based on actual account coverage)
        "equity_pledge",           # 股权质押 (pledge_detail / pledge_stat)
        "buyback",                 # 股票回购 (repurchase)
        "risk_warning",            # ST / 退市风险警示 (stock_st / st)
        "ah_premium",              # AH 股比价 (stk_ah_comparison)
        "dividends",               # 分红送股 (dividend)
        "chip_distribution",       # 每日筹码及胜率 (cyq_perf)
        "technical_factors",       # 技术面因子专业版 (stk_factor_pro / idx_factor_pro / stk_nineturn)
        "market_index",            # 大盘 / 行业指数 (index_basic / index_dailybasic / index_weekly / sw_daily ...)
        "market_capital_flow",     # 大盘 / 板块 / 行业资金流 (moneyflow_mkt_dc / moneyflow_cnt_ths / moneyflow_ind_ths)
        "sentiment_hot_list",      # 情绪热榜 (dc_hot / ths_hot / 题材热度)
        "trading_calendar",        # 交易日历 (trade_cal / namechange / bse_mapping)
        # LLM training corpus — Tushare 大模型语料专题（uniquely valuable
        # for the core-pool LLM analysis epic; provider answers from
        # listed-company investor relations Q&A boards)
        "investor_relations_qa",   # 上证 e 互动 / 深证易互动 (irm_qa_sh / irm_qa_sz)
        # Round 4 (FMP audit — uniquely-FMP useful capabilities that
        # complement priors.valuation_mix and risk paths)
        "dcf_valuation",           # FMP /discounted-cash-flow + levered DCF
        "treasury_rates",          # FMP /stable/treasury-rates — risk-free rate for DCF / Sharpe
        "corporate_actions",       # FMP /historical-stock-split + M&A history
        "esg_score",               # FMP /esg-environmental-social-governance-data
        "government_trading",      # FMP /senate-trading + /house-disclosure (alpha edge)
        "peer_comparison",         # FMP /stock_peers — auto-find sector/industry peers
    }
)

VALID_AUTH_TYPES: frozenset[str] = frozenset(
    {"api_key", "token", "oauth", "none", "local_gateway"}
)

VALID_PROVIDER_STATUSES: frozenset[str] = frozenset(
    {"active", "planned", "deferred"}
)

PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class DataProviderCatalogValidationResult:
    ok: bool
    catalog_id: str
    provider_count: int
    active_providers: tuple[str, ...]
    market_coverage: dict[str, tuple[str, ...]]
    capability_coverage: dict[str, tuple[str, ...]]
    errors: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _string(value: object) -> str:
    return "" if value is None else str(value).strip()


def load_provider_catalog(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("provider catalog must be a YAML object")
    return payload


def validate_provider_catalog(
    path: Path,
    *,
    required_markets: set[str] | None = None,
) -> DataProviderCatalogValidationResult:
    payload = load_provider_catalog(path)
    errors: list[str] = []
    warnings: list[str] = []

    catalog_id = _string(payload.get("catalog_id"))
    if not catalog_id:
        errors.append("catalog_id is required")

    schema_version = payload.get("schema_version")
    if schema_version != 1:
        errors.append("schema_version must be 1")

    providers = payload.get("providers")
    if not isinstance(providers, list) or not providers:
        errors.append("providers must be a non-empty list")
        providers = []

    seen_ids: set[str] = set()
    active_ids: list[str] = []
    market_to_providers: dict[str, list[str]] = {m: [] for m in VALID_MARKETS}
    capability_to_providers: dict[str, list[str]] = {
        c: [] for c in VALID_CAPABILITIES
    }

    for index, entry in enumerate(providers, start=1):
        if not isinstance(entry, dict):
            errors.append(f"providers[{index}] must be a mapping")
            continue
        provider_id = _string(entry.get("id"))
        loc = f"providers[{index}]({provider_id or '?'})"
        if not provider_id:
            errors.append(f"{loc}.id is required")
            continue
        if not PROVIDER_ID_RE.fullmatch(provider_id):
            errors.append(
                f"{loc}.id must be lower_snake_case ASCII; got {provider_id!r}"
            )
        if provider_id in seen_ids:
            errors.append(f"{loc}.id duplicated: {provider_id!r}")
            continue
        seen_ids.add(provider_id)

        if not _string(entry.get("display_name")):
            errors.append(f"{loc}.display_name is required")
        if not _string(entry.get("homepage")):
            errors.append(f"{loc}.homepage is required")

        auth_type = _string(entry.get("auth_type"))
        if auth_type not in VALID_AUTH_TYPES:
            errors.append(
                f"{loc}.auth_type must be one of {sorted(VALID_AUTH_TYPES)}; "
                f"got {auth_type!r}"
            )
        # secret_env_var is required iff auth_type != none
        secret_env_var = _string(entry.get("secret_env_var"))
        if auth_type != "none" and not secret_env_var:
            errors.append(
                f"{loc}.secret_env_var is required for auth_type={auth_type!r}"
            )
        if auth_type != "none" and secret_env_var:
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", secret_env_var):
                errors.append(
                    f"{loc}.secret_env_var must be UPPER_SNAKE_CASE; got "
                    f"{secret_env_var!r}"
                )
        # The catalog must NEVER store the actual key.
        for forbidden in ("api_key", "secret", "token", "password"):
            if forbidden in entry:
                errors.append(
                    f"{loc} must not embed a literal {forbidden!r}; "
                    "store secrets only via secret_env_var reference"
                )

        base_url = _string(entry.get("base_url"))
        if base_url and not (
            base_url.startswith("https://") or base_url.startswith("http://")
        ):
            errors.append(f"{loc}.base_url must be an http(s) URL")
        # local_gateway providers (e.g. Futu OpenD) are local TCP daemons,
        # not remote HTTP endpoints, so base_url is intentionally optional;
        # connection metadata lives under `gateway`.
        if auth_type != "local_gateway" and not base_url:
            # Other auth types should still document their endpoint.
            errors.append(
                f"{loc}.base_url is required for auth_type={auth_type!r}"
            )

        gateway = entry.get("gateway")
        if auth_type == "local_gateway":
            if not isinstance(gateway, dict):
                errors.append(
                    f"{loc}.gateway block is required for "
                    "auth_type=local_gateway"
                )
            else:
                gw_host = _string(gateway.get("host"))
                if not gw_host:
                    errors.append(f"{loc}.gateway.host is required")
                gw_port = gateway.get("port")
                if not isinstance(gw_port, int) or isinstance(gw_port, bool):
                    errors.append(
                        f"{loc}.gateway.port must be an integer in [1, 65535]"
                    )
                elif not 1 <= gw_port <= 65535:
                    errors.append(
                        f"{loc}.gateway.port must be in [1, 65535]; got "
                        f"{gw_port}"
                    )

        status = _string(entry.get("status")) or "active"
        if status not in VALID_PROVIDER_STATUSES:
            errors.append(
                f"{loc}.status must be one of {sorted(VALID_PROVIDER_STATUSES)}; "
                f"got {status!r}"
            )

        markets = entry.get("supported_markets")
        if not isinstance(markets, list) or not markets:
            errors.append(f"{loc}.supported_markets must be a non-empty list")
            markets = []
        market_set: list[str] = []
        for m in markets:
            mstr = _string(m)
            if mstr not in VALID_MARKETS:
                errors.append(
                    f"{loc}.supported_markets contains unknown market "
                    f"{mstr!r}; allowed {sorted(VALID_MARKETS)}"
                )
                continue
            if mstr in market_set:
                errors.append(
                    f"{loc}.supported_markets has duplicate {mstr!r}"
                )
                continue
            market_set.append(mstr)

        capabilities = entry.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities:
            errors.append(f"{loc}.capabilities must be a non-empty list")
            capabilities = []
        cap_set: list[str] = []
        for cap in capabilities:
            cstr = _string(cap)
            if cstr not in VALID_CAPABILITIES:
                errors.append(
                    f"{loc}.capabilities contains unknown capability "
                    f"{cstr!r}; allowed {sorted(VALID_CAPABILITIES)}"
                )
                continue
            if cstr in cap_set:
                errors.append(
                    f"{loc}.capabilities has duplicate {cstr!r}"
                )
                continue
            cap_set.append(cstr)

        rate_limit = entry.get("rate_limit_per_minute")
        if rate_limit is not None:
            if not isinstance(rate_limit, int) or isinstance(rate_limit, bool):
                errors.append(
                    f"{loc}.rate_limit_per_minute must be a positive integer "
                    "(or omitted)"
                )
            elif rate_limit <= 0:
                errors.append(
                    f"{loc}.rate_limit_per_minute must be > 0"
                )

        if status == "active":
            active_ids.append(provider_id)
            for mstr in market_set:
                market_to_providers[mstr].append(provider_id)
            for cstr in cap_set:
                capability_to_providers[cstr].append(provider_id)

    # Ensure every required market has at least one ACTIVE provider.
    if required_markets:
        for market in sorted(required_markets):
            if market not in VALID_MARKETS:
                errors.append(
                    f"required_markets contains unknown market {market!r}"
                )
                continue
            if not market_to_providers.get(market):
                errors.append(
                    f"market {market!r} has no active provider; the leader "
                    "pool covers this market and needs at least one"
                )

    # Soft warning: if a provider is planned/deferred we surface it so the
    # operator can see the gap during review.
    for entry in providers:
        if not isinstance(entry, dict):
            continue
        status = _string(entry.get("status")) or "active"
        if status in {"planned", "deferred"}:
            pid = _string(entry.get("id"))
            warnings.append(f"provider {pid!r} status={status}")

    return DataProviderCatalogValidationResult(
        ok=not errors,
        catalog_id=catalog_id,
        provider_count=len(seen_ids),
        active_providers=tuple(sorted(active_ids)),
        market_coverage={
            m: tuple(sorted(market_to_providers[m]))
            for m in VALID_MARKETS
        },
        capability_coverage={
            c: tuple(sorted(capability_to_providers[c]))
            for c in VALID_CAPABILITIES
            if capability_to_providers[c]
        },
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
