"""Command line interface for MVP20 orchestration checks."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import click

from mvp20.fixture import run_fixture_e2e
from mvp20.graph import validate_industry_graph_set
from mvp20.lock import validate_lock
from mvp20.manifest import validate_industry_set, validate_manifest
from mvp20.overlays import (
    compile_overlays_to_sqlite,
    generate_overlay_files,
    validate_overlay_set,
)
from mvp20.planning import build_backfill_plan
from mvp20.providers import validate_provider_catalog
from mvp20.server import ServerConfig, serve_forever
from mvp20.sources import load_dotenv


@click.group()
def main() -> None:
    """MVP20 orchestration commands."""


@main.command("check-futu")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=11111, show_default=True, type=int)
def check_futu_command(host: str, port: int) -> None:
    """Probe local Futu OpenD daemon: connection + market state + quote login."""

    from mvp20.sources import futu_source
    result = futu_source.health_check(host, port)
    for k, v in result.items():
        click.echo(f"{k}: {v}")
    if not result.get("ok"):
        raise click.ClickException("Futu OpenD probe failed")


@main.command("check-tushare")
def check_tushare_command() -> None:
    """Probe Tushare pro API: TUSHARE_TOKEN + trade_cal liveness."""

    load_dotenv()
    from mvp20.sources import tushare_source
    result = tushare_source.health_check()
    for k, v in result.items():
        click.echo(f"{k}: {v}")
    if not result.get("ok"):
        raise click.ClickException("Tushare probe failed")


@main.command("check-fmp")
def check_fmp_command() -> None:
    """Probe FMP API: FMP_API_KEY + /quote/AAPL liveness."""

    load_dotenv()
    from mvp20.sources import fmp_source
    result = fmp_source.health_check()
    for k, v in result.items():
        click.echo(f"{k}: {v}")
    if not result.get("ok"):
        raise click.ClickException("FMP probe failed")


@main.command("check-akshare")
def check_akshare_command() -> None:
    """Probe akshare: import + EM heat-rank endpoint reachable.

    Also prints the list of dp_ids this source actually populates so it's
    obvious what akshare contributes vs Tushare/FMP/Futu.
    """

    load_dotenv()
    from mvp20.sources import akshare_source
    result = akshare_source.health_check()
    for k, v in result.items():
        click.echo(f"{k}: {v}")
    click.echo("tier1_dp_ids:")
    for dp_id in sorted(akshare_source.TIER1_DP_IDS):
        click.echo(f"  - {dp_id}")
    if akshare_source.TIER2_TODO_DP_IDS:
        click.echo("tier2_todo_dp_ids:")
        for dp_id in sorted(akshare_source.TIER2_TODO_DP_IDS):
            click.echo(f"  - {dp_id}  (stub)")
    if not result.get("ok"):
        raise click.ClickException("akshare probe failed")


@main.command("derive")
@click.option(
    "--db", "db_path", type=click.Path(path_type=Path),
    default=Path("runtime/hot.sqlite"), show_default=True,
)
@click.option(
    "--history-days", type=int, default=90, show_default=True,
    help="Days of history to pull for derived calculations (Tushare for "
         "A-share, FMP for US/HK).",
)
@click.option(
    "--limit", "limit_companies", type=int, default=None,
    help="Process at most N companies (smoke test).",
)
@click.option(
    "--a-share-only/--all-markets", default=True, show_default=True,
    help="With --a-share-only (default) only A-share ts_codes are processed "
         "via Tushare. --all-markets also iterates US (.US) via FMP and HK "
         "(.HK) via FMP, emitting the same L11.tech.* technical pack.",
)
def derive_command(db_path: Path, history_days: int, limit_companies: int | None,
                   a_share_only: bool) -> None:
    """Compute L6.priced / L8 / L10 / L11 derived dp_ids using historical
    price windows + realtime_current snapshots. UPSERTs back with source
    ``derived:*``. With ``--all-markets`` US and HK universes are also
    processed (Tushare for A-share, FMP for US/HK)."""

    load_dotenv()
    from mvp20.derive import derive_all

    stats = derive_all(db_path, history_days=history_days,
                       limit_companies=limit_companies,
                       a_share_only=a_share_only)
    for k, v in stats.items():
        click.echo(f"{k}: {v}")


@main.command("derive-weekly")
@click.option(
    "--db", "db_path", type=click.Path(path_type=Path),
    default=Path("runtime/hot.sqlite"), show_default=True,
)
@click.option(
    "--history-weeks", type=int, default=120, show_default=True,
    help="Weeks of history to pull from Tushare pro.weekly (≥35 needed for MACD).",
)
@click.option(
    "--limit", "limit_companies", type=int, default=None,
    help="Process at most N companies (smoke test).",
)
@click.option(
    "--a-share-only/--all-markets", default=True, show_default=True,
    help="Restrict to A-share. HK/US weekly is TODO (Tushare pro.weekly only).",
)
def derive_weekly_command(
    db_path: Path, history_weeks: int, limit_companies: int | None,
    a_share_only: bool,
) -> None:
    """Compute ``L11.tech.*_weekly`` (5 dp_ids) from Tushare pro.weekly OHLCV.

    Emits ma / macd / rsi / kdj / boll on weekly bars with
    ``source="derived:technical_indicators_weekly"`` and base confidence
    ≈0.88 (lower than daily ≈0.95 to reflect weekly close lag).
    """

    load_dotenv()
    from mvp20.derive import derive_all_weekly

    stats = derive_all_weekly(
        db_path, history_weeks=history_weeks,
        limit_companies=limit_companies, a_share_only=a_share_only,
    )
    for k, v in stats.items():
        click.echo(f"{k}: {v}")


@main.command("derive-monthly")
@click.option(
    "--db", "db_path", type=click.Path(path_type=Path),
    default=Path("runtime/hot.sqlite"), show_default=True,
)
@click.option(
    "--history-months", type=int, default=36, show_default=True,
    help="Months of history to pull from Tushare pro.monthly (≥26 needed for MACD).",
)
@click.option(
    "--limit", "limit_companies", type=int, default=None,
    help="Process at most N companies (smoke test).",
)
@click.option(
    "--a-share-only/--all-markets", default=True, show_default=True,
    help="Restrict to A-share. HK/US monthly is TODO (Tushare pro.monthly only).",
)
def derive_monthly_command(
    db_path: Path, history_months: int, limit_companies: int | None,
    a_share_only: bool,
) -> None:
    """Compute ``L11.tech.*_monthly`` (5 dp_ids) from Tushare pro.monthly OHLCV.

    Emits ma / macd / rsi / kdj / boll on monthly bars with
    ``source="derived:technical_indicators_monthly"`` and base confidence
    ≈0.80 (the most-stale tier, refreshes once per month).
    """

    load_dotenv()
    from mvp20.derive import derive_all_monthly

    stats = derive_all_monthly(
        db_path, history_months=history_months,
        limit_companies=limit_companies, a_share_only=a_share_only,
    )
    for k, v in stats.items():
        click.echo(f"{k}: {v}")


@main.command("derive-snapshot")
@click.option(
    "--db", "db_path", type=click.Path(path_type=Path),
    default=Path("runtime/hot.sqlite"), show_default=True,
    help="Hot SQLite database holding realtime_current rows.",
)
@click.option(
    "--ts-codes", "ts_codes", default=None,
    help="Comma-separated ts_codes. Defaults to every stock in overlay_manifest.",
)
@click.option(
    "--governance", "governance_path",
    type=click.Path(path_type=Path),
    default=Path("config/data_point_roles.yaml"), show_default=True,
)
@click.option(
    "--show-stats/--no-show-stats", default=True, show_default=True,
)
def derive_snapshot_command(
    db_path: Path,
    ts_codes: str | None,
    governance_path: Path,
    show_stats: bool,
) -> None:
    """Run snapshot-only derive layer (Tier 1-4 formulas).

    Reads ``realtime_current`` for each ts_code, composes derived dp_ids
    (L6.path.* / L6.sens.* / L7.env.risk_appetite / L7.mood.fomo /
    L8.industry.* / L8.val.priced_in / L10.val.expansion_compression /
    L11.short.score / L11.mid.score / L11.long.score / L11.mode /
    L11.trade.signal) and UPSERTs results back with ``source="derive:*"``.
    """

    import json as _json
    load_dotenv()
    from mvp20.derive import DeriveRunner

    runner = DeriveRunner(db_path, governance_path)
    codes_list = [c.strip() for c in ts_codes.split(",") if c.strip()] if ts_codes else None
    stats = runner.run_all(codes_list)

    click.echo(f"companies_processed: {stats['companies_processed']}")
    click.echo(f"rows_emitted: {stats['rows_emitted']}")
    if show_stats:
        click.echo("dp_status_counts:")
        click.echo(_json.dumps(stats["dp_status_counts"], indent=2, ensure_ascii=False))


@main.command("aggregate-graph")
@click.option(
    "--ts-code", required=True,
    help="Stock ts_code (e.g. 300750.SZ).",
)
@click.option(
    "--industry", "industry_id",
    help="Industry id (e.g. STORAGE_GRID). If omitted we scan all stock_overlay subdirs.",
)
@click.option(
    "--stock-overlays-dir",
    type=click.Path(path_type=Path),
    default=Path("config/stock_overlays"),
    show_default=True,
)
@click.option(
    "--industry-overlays-dir",
    type=click.Path(path_type=Path),
    default=Path("config/industry_overlays"),
    show_default=True,
)
@click.option(
    "--out", "out_path",
    type=click.Path(path_type=Path),
    default=None,
    help="If set, write JSON output here. Otherwise dump to stdout.",
)
def aggregate_graph_command(
    ts_code: str,
    industry_id: str | None,
    stock_overlays_dir: Path,
    industry_overlays_dir: Path,
    out_path: Path | None,
) -> None:
    """Run spec §27 parent aggregation + §29 three-horizon scoring on a
    stock overlay. Emits JSON keyed by node_id."""

    import json

    from mvp20.aggregator import aggregate_from_paths

    # Locate the stock overlay. Either an explicit industry_id or scan for
    # the file under any industry subdir.
    overlay_path: Path | None = None
    if industry_id:
        candidate = stock_overlays_dir / industry_id / f"{ts_code}.yaml"
        if candidate.exists():
            overlay_path = candidate
    else:
        for sub in sorted(stock_overlays_dir.iterdir()):
            if not sub.is_dir():
                continue
            candidate = sub / f"{ts_code}.yaml"
            if candidate.exists():
                overlay_path = candidate
                industry_id = sub.name
                break
    if overlay_path is None or not overlay_path.exists():
        raise click.ClickException(
            f"stock overlay not found for {ts_code}"
            f"{' under ' + industry_id if industry_id else ''}"
        )

    industry_overlay_path = (
        industry_overlays_dir / f"{industry_id}.yaml"
        if industry_id else None
    )
    if industry_overlay_path and not industry_overlay_path.exists():
        industry_overlay_path = None

    result = aggregate_from_paths(overlay_path, industry_overlay_path)

    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
        click.echo(f"wrote {len(result)} nodes to {out_path}")
    else:
        click.echo(payload)


@main.command("audit-injection")
@click.option(
    "--db", "db_path", type=click.Path(path_type=Path),
    default=Path("runtime/hot.sqlite"), show_default=True,
)
@click.option(
    "--out-md", type=click.Path(path_type=Path),
    default=Path("docs/audit/injection_audit.md"), show_default=True,
    help="Markdown report for human review.",
)
@click.option(
    "--out-csv", type=click.Path(path_type=Path),
    default=Path("docs/audit/injection_audit.csv"), show_default=True,
    help="Per-company CSV for Excel review.",
)
@click.option(
    "--industry-overlays-dir", type=click.Path(path_type=Path),
    default=Path("config/industry_overlays"), show_default=True,
    help="Source for L0-inherit Known dp_ids (per-industry overlays).",
)
@click.option(
    "--coverage-audit", "coverage_audit_path", type=click.Path(path_type=Path),
    default=Path("docs/data_sources/coverage_audit.md"), show_default=True,
    help="Spec §7 250-row dp_id catalog (used as the coverage denominator).",
)
@click.option(
    "--detailed/--no-detailed", default=False, show_default=True,
    help="Include per-stock unknown/source breakdown in the markdown table.",
)
def audit_injection_command(
    db_path: Path,
    out_md: Path,
    out_csv: Path,
    industry_overlays_dir: Path,
    coverage_audit_path: Path,
    detailed: bool,
) -> None:
    """Per-company audit: three-layer coverage view.

    Layers (orthogonal):
      1. overlay schema (LLM-derived, ~33 slots per company)
      2. realtime SQLite (Tushare / FMP / Futu / akshare injections)
      3. L0 inherit (industry-level Known dp_ids)

    Output: Markdown summary + CSV detail. Run after ``collector --source real``.
    """

    from mvp20.audit import collect_audit, write_csv, write_markdown

    audits, summary = collect_audit(
        db_path,
        industry_overlays_dir=industry_overlays_dir,
        coverage_audit_path=coverage_audit_path,
    )
    write_markdown(audits, summary, out_md, detailed=detailed)
    write_csv(audits, out_csv)
    click.echo("audit complete:")
    click.echo(f"  total_companies: {summary['total_companies']}")
    click.echo(f"  spec_total: {summary['spec_total']}")
    click.echo(f"  avg_overlay_known: {summary['avg_overlay_known']:.1f}")
    click.echo(f"  avg_overlay_opt: {summary['avg_overlay_opt']:.1f}")
    click.echo(f"  avg_realtime: {summary['avg_realtime']:.1f}")
    click.echo(f"  avg_l0_inherit: {summary['avg_l0_inherit']:.1f}")
    click.echo(
        f"  avg_effective: {summary['avg_effective']:.1f} / "
        f"{summary['spec_total']} = {summary['avg_coverage_pct']:.1f}%"
    )
    click.echo(f"  with_any_realtime: {summary['with_any_realtime']}")
    click.echo(f"  with_zero_realtime: {summary['with_zero_realtime']}")
    click.echo(f"  markdown report: {out_md}")
    click.echo(f"  csv report: {out_csv}")


@main.command("validate-manifest")
@click.option("--manifest", type=click.Path(path_type=Path), required=True)
def validate_manifest_command(manifest: Path) -> None:
    result = validate_manifest(manifest)
    _emit_result(asdict(result))
    if not result.ok:
        raise click.ClickException("; ".join(result.errors))


@main.command("verify-lock")
@click.option("--lock", "lock_path", type=click.Path(path_type=Path), required=True)
def verify_lock_command(lock_path: Path) -> None:
    result = validate_lock(lock_path)
    _emit_result(asdict(result))
    if not result.ok:
        raise click.ClickException("; ".join(result.errors))


@main.command("plan-backfill")
@click.option("--manifest", type=click.Path(path_type=Path), required=True)
def plan_backfill_command(manifest: Path) -> None:
    result = build_backfill_plan(manifest)
    _emit_result(asdict(result))


@main.command("run-fixture-e2e")
def run_fixture_e2e_command() -> None:
    result = run_fixture_e2e()
    _emit_result(asdict(result) | {"ok": result.ok})
    if not result.ok:
        raise click.ClickException("fixture e2e did not satisfy MVP20 invariants")


@main.command("validate-graphs")
@click.option(
    "--graphs-dir",
    type=click.Path(path_type=Path),
    default=Path("config/industry_graphs"),
    show_default=True,
)
@click.option(
    "--industries",
    "industries_path",
    type=click.Path(path_type=Path),
    default=Path("config/mvp20.industries.yaml"),
    show_default=True,
)
def validate_graphs_command(graphs_dir: Path, industries_path: Path) -> None:
    industry_validation = validate_industry_set(industries_path)
    if not industry_validation.ok:
        for err in industry_validation.errors:
            click.echo(f"industries.yaml: {err}")
        raise click.ClickException("industries.yaml failed validation")

    result = validate_industry_graph_set(
        graphs_dir,
        valid_industry_ids=set(industry_validation.industry_ids),
        industry_graph_status=industry_validation.industry_graph_status,
    )
    _emit_result(asdict(result))
    if not result.ok:
        raise click.ClickException(
            "industry causal graphs failed validation"
        )


@main.command("validate-providers")
@click.option(
    "--providers",
    "providers_path",
    type=click.Path(path_type=Path),
    default=Path("config/data_providers.yaml"),
    show_default=True,
)
@click.option(
    "--manifest",
    type=click.Path(path_type=Path),
    default=Path("config/mvp20.universe.yaml"),
    show_default=True,
)
def validate_providers_command(providers_path: Path, manifest: Path) -> None:
    """Certify the data-provider catalog covers every market in the universe."""

    # Derive required markets from the constituent ts_codes.
    manifest_validation = validate_manifest(manifest)
    if not manifest_validation.ok:
        for err in manifest_validation.errors:
            click.echo(f"manifest: {err}")
        raise click.ClickException("universe manifest failed validation")

    import yaml

    payload = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    required_markets: set[str] = set()
    for c in payload.get("constituents") or []:
        ts = str(c.get("ts_code", ""))
        if ts.endswith(".HK"):
            required_markets.add("HK")
        elif ts.endswith(".US"):
            required_markets.add("US")
        elif ts.endswith((".SH", ".SZ", ".BJ")):
            required_markets.add("A")

    result = validate_provider_catalog(
        providers_path, required_markets=required_markets
    )
    _emit_result(asdict(result))
    if not result.ok:
        raise click.ClickException(
            "data provider catalog failed validation"
        )


@main.command("generate-overlays")
@click.option(
    "--universe",
    "universe_path",
    type=click.Path(path_type=Path),
    default=Path("config/mvp20.universe.yaml"),
    show_default=True,
)
@click.option(
    "--industries",
    "industries_path",
    type=click.Path(path_type=Path),
    default=Path("config/mvp20.industries.yaml"),
    show_default=True,
)
@click.option(
    "--industry-graphs-dir",
    type=click.Path(path_type=Path),
    default=Path("config/industry_graphs"),
    show_default=True,
)
@click.option(
    "--industry-overlays-dir",
    type=click.Path(path_type=Path),
    default=Path("config/industry_overlays"),
    show_default=True,
)
@click.option(
    "--stock-overlays-dir",
    type=click.Path(path_type=Path),
    default=Path("config/stock_overlays"),
    show_default=True,
)
@click.option("--period", default="2026-Q1", show_default=True)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help=(
        "Skip merge-preserve and regenerate every overlay from SLOT_DEFS. "
        "DESTRUCTIVE: will overwrite codex-filled Known/N/A/Optionality/Inactive "
        "values. Use only when intentionally re-baselining."
    ),
)
def generate_overlays_command(
    universe_path: Path,
    industries_path: Path,
    industry_graphs_dir: Path,
    industry_overlays_dir: Path,
    stock_overlays_dir: Path,
    period: str,
    force: bool,
) -> None:
    """Generate industry overlays and company-industry stock overlay shells."""

    result = generate_overlay_files(
        universe_path=universe_path,
        industries_path=industries_path,
        industry_graphs_dir=industry_graphs_dir,
        industry_overlays_dir=industry_overlays_dir,
        stock_overlays_dir=stock_overlays_dir,
        period=period,
        force=force,
    )
    _emit_result(result)


@main.command("validate-overlays")
@click.option(
    "--stock-overlays-dir",
    type=click.Path(path_type=Path),
    default=Path("config/stock_overlays"),
    show_default=True,
)
@click.option(
    "--industry-overlays-dir",
    type=click.Path(path_type=Path),
    default=Path("config/industry_overlays"),
    show_default=True,
)
@click.option(
    "--universe",
    "universe_path",
    type=click.Path(path_type=Path),
    default=Path("config/mvp20.universe.yaml"),
    show_default=True,
)
@click.option(
    "--industries",
    "industries_path",
    type=click.Path(path_type=Path),
    default=Path("config/mvp20.industries.yaml"),
    show_default=True,
)
def validate_overlays_command(
    stock_overlays_dir: Path,
    industry_overlays_dir: Path,
    universe_path: Path,
    industries_path: Path,
) -> None:
    """Validate generated overlay files against the graph-design contract."""

    result = validate_overlay_set(
        stock_overlays_dir,
        industry_overlays_dir,
        universe_path,
        industries_path,
    )
    _emit_overlay_result(result)
    if not result.ok:
        raise click.ClickException("overlay validation failed")


@main.command("compile-overlays")
@click.option(
    "--db",
    "db_path",
    type=click.Path(path_type=Path),
    default=Path("runtime/hot.sqlite"),
    show_default=True,
)
@click.option(
    "--stock-overlays-dir",
    type=click.Path(path_type=Path),
    default=Path("config/stock_overlays"),
    show_default=True,
)
@click.option(
    "--industry-overlays-dir",
    type=click.Path(path_type=Path),
    default=Path("config/industry_overlays"),
    show_default=True,
)
@click.option(
    "--universe",
    "universe_path",
    type=click.Path(path_type=Path),
    default=Path("config/mvp20.universe.yaml"),
    show_default=True,
)
@click.option(
    "--industries",
    "industries_path",
    type=click.Path(path_type=Path),
    default=Path("config/mvp20.industries.yaml"),
    show_default=True,
)
def compile_overlays_command(
    db_path: Path,
    stock_overlays_dir: Path,
    industry_overlays_dir: Path,
    universe_path: Path,
    industries_path: Path,
) -> None:
    """Validate YAML overlays and materialize frontend snapshots into SQLite."""

    result = compile_overlays_to_sqlite(
        db_path=db_path,
        stock_overlays_dir=stock_overlays_dir,
        industry_overlays_dir=industry_overlays_dir,
        universe_path=universe_path,
        industries_path=industries_path,
    )
    _emit_overlay_result(result)
    if not result.ok:
        raise click.ClickException("overlay compile failed")


@main.command("score-company")
@click.option(
    "--ts-code", required=True,
    help="Company ts_code (e.g. 300750.SZ).",
)
@click.option(
    "--industry", "industry_id", default=None,
    help="Restrict to a specific industry overlay (e.g. STORAGE_GRID). "
    "Defaults to the company's primary industry.",
)
@click.option(
    "--stock-overlays-dir",
    type=click.Path(path_type=Path),
    default=Path("config/stock_overlays"),
    show_default=True,
)
@click.option(
    "--db", "db_path", type=click.Path(path_type=Path),
    default=Path("runtime/hot.sqlite"), show_default=True,
)
def score_company_command(
    ts_code: str,
    industry_id: str | None,
    stock_overlays_dir: Path,
    db_path: Path,
) -> None:
    """Score one company per spec §27.1/27.3/27.4 + classify mode (§30).

    Reads the stock overlay YAML and feeds it through ``scoring.score_company``.
    Aggregator (A1) and coverage (A2) outputs are loaded lazily; if either
    module isn't available yet, the CLI falls back to a mock-aggregator
    payload derived from the overlay's static slots so the orchestration
    still demonstrates end-to-end shape.
    """

    import yaml

    from mvp20.scoring import score_company

    # ----- locate overlay -------------------------------------------------
    overlay_path: Path | None = None
    if industry_id:
        candidate = stock_overlays_dir / industry_id / f"{ts_code}.yaml"
        if candidate.exists():
            overlay_path = candidate
    if overlay_path is None and stock_overlays_dir.exists():
        for sub in stock_overlays_dir.iterdir():
            if not sub.is_dir():
                continue
            candidate = sub / f"{ts_code}.yaml"
            if candidate.exists():
                overlay_path = candidate
                break
    if overlay_path is None:
        candidate = stock_overlays_dir / f"{ts_code}.yaml"
        if candidate.exists():
            overlay_path = candidate
    if overlay_path is None:
        raise click.ClickException(
            f"stock overlay for {ts_code} not found under {stock_overlays_dir}"
        )

    overlay = yaml.safe_load(overlay_path.read_text(encoding="utf-8")) or {}

    # ----- realtime snapshot (best-effort, OK if hot.sqlite missing) -----
    # Read first so the aggregator can bridge realtime values into the score
    # (synthetic standalone-leaf nodes for participating dp_ids).
    realtime_data: dict[str, object] = {}
    try:
        from mvp20.storage import read_hot_snapshot
        realtime_data = read_hot_snapshot(db_path, ts_code)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"# realtime snapshot unavailable ({exc})")

    # ----- lazy-load A1 (aggregator) + A2 (coverage); fall back to mocks --
    aggregated_nodes: dict[str, object] = {}
    coverage_report: dict[str, object] = {}

    try:
        from mvp20.aggregator import aggregate_company_graph  # type: ignore
        aggregated_nodes = aggregate_company_graph(
            overlay, realtime_snapshot=realtime_data or None
        ) or {}
    except Exception as exc:  # noqa: BLE001 (lazy; A1 may not exist yet)
        click.echo(f"# aggregator unavailable ({exc}); using overlay-derived mock")
        aggregated_nodes = _mock_aggregator_payload(overlay)

    try:
        from mvp20.coverage import coverage_summary_for_overlay  # type: ignore
        coverage_report = coverage_summary_for_overlay(overlay) or {}
    except Exception as exc:  # noqa: BLE001
        click.echo(f"# coverage unavailable ({exc}); using overlay-derived mock")
        coverage_report = overlay.get("coverage") or {}

    result = score_company(
        stock_overlay=overlay,
        aggregated_nodes=aggregated_nodes,
        coverage_report=coverage_report,
        realtime_data=realtime_data,
    )

    # ----- emit one-line summary (per task brief) ------------------------
    click.echo("ts_code | mode | short | medium | long | signal | top_path")
    top_pos = result["top_paths"]["positive"]
    top_path = top_pos[0]["rationale"] if top_pos else "(none)"
    click.echo(
        f"{result['ts_code']} | {result['mode_display']} | "
        f"{result['short_total']:.3f} | {result['medium_total']:.3f} | "
        f"{result['long_total']:.3f} | {result['trading_signal']} | "
        f"{top_path}"
    )
    click.echo("")
    click.echo(f"mode_confidence: {result['mode_confidence']:.3f}")
    click.echo(f"mode_rationale: {result['mode_rationale']}")
    click.echo(
        f"company_score: {result['company_score']['score']:.3f} "
        f"(industry_contrib={result['company_score']['components']['industry_contrib']:.3f})"
    )
    click.echo(f"trading_meaning: {result['final_score']['trading_meaning']}")


def _mock_aggregator_payload(overlay: dict[str, object]) -> dict[str, object]:
    """Build a minimal aggregator payload from the static overlay.

    Used only when ``mvp20.aggregator`` isn't yet available (the other
    agent is still writing it). The shape mirrors what A1 is expected
    to return so ``scoring.score_company`` can run end-to-end.
    """

    nodes = overlay.get("nodes") or []
    industry_variables: list[dict[str, object]] = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        layer = str(n.get("layer") or "")
        if not layer.startswith("industry"):
            continue
        materiality = n.get("materiality") or 1.0
        direction = n.get("direction") or "neutral"
        industry_variables.append({
            "name": n.get("node_name") or n.get("dp_id"),
            "node_id": n.get("node_id"),
            "score": 0.0,  # no live evidence in mock
            "exposure": 0.0,
            "revenue_share": 1.0,
            "profit_elasticity": 1.0,
            "financial_sensitivity": 1.0,
            "valuation_sensitivity": 1.0,
            "direction": direction,
            "confidence": 0.0,
            "materiality": materiality,
        })
    return {
        "industry_variables": industry_variables,
        "company_event_score": 0.0,
        "capital_sentiment_score": 0.0,
        "risk_discount": 0.0,
        "valuation_pressure": 0.0,
        "priced_in_discount": 0.0,
        "expectation_gap_score": 0.0,
        "valuation_rerating_score": 0.0,
        "nodes": {},
    }


@main.command("coverage-report")
@click.option("--ts-code", required=True,
              help="Company ts_code, e.g. 300750.SZ.")
@click.option("--industry", "industry_id", default=None,
              help="Industry overlay variant. Defaults to the primary industry.")
@click.option(
    "--db", "db_path", type=click.Path(path_type=Path),
    default=Path("runtime/hot.sqlite"), show_default=True,
    help="SQLite hot snapshot DB containing the compiled overlay.",
)
@click.option(
    "--stock-overlays-dir", type=click.Path(path_type=Path),
    default=Path("config/stock_overlays"), show_default=True,
    help="Fallback YAML root when the SQLite snapshot is unavailable.",
)
@click.option("--top", "top_n", type=int, default=20, show_default=True,
              help="Truncate per-node table after the worst N parents.")
def coverage_report_command(
    ts_code: str,
    industry_id: str | None,
    db_path: Path,
    stock_overlays_dir: Path,
    top_n: int,
) -> None:
    """Print spec §23 Data Coverage + confidence-propagation report.

    Reads the compiled overlay from SQLite when available; otherwise loads
    the source YAML directly from ``config/stock_overlays/<industry>/<ts>.yaml``.
    Shows per-parent Data Coverage, the overall weighted coverage, and the
    list of parents whose coverage falls below the §23.2 thresholds.
    """

    import yaml

    from mvp20.coverage import coverage_summary_for_overlay
    from mvp20.storage import read_compiled_graph_snapshot

    overlay: dict[str, object] | None = None
    snapshot = read_compiled_graph_snapshot(db_path, ts_code, industry_id)
    if isinstance(snapshot, dict):
        compiled = snapshot.get("compiled_graph")
        if isinstance(compiled, dict) and compiled.get("nodes"):
            overlay = {
                "ts_code": ts_code,
                "industry_id": snapshot.get("industry_id"),
                **compiled,
            }
        elif snapshot.get("nodes"):
            overlay = dict(snapshot)
            overlay.setdefault("ts_code", ts_code)

    if overlay is None:
        candidates: list[Path] = []
        if industry_id:
            candidates.append(stock_overlays_dir / industry_id / f"{ts_code}.yaml")
        elif stock_overlays_dir.exists():
            candidates.extend(stock_overlays_dir.glob(f"*/{ts_code}.yaml"))
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            raise click.ClickException(
                f"no overlay found for ts_code={ts_code}"
                + (f" industry={industry_id}" if industry_id else "")
            )
        overlay = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    report = coverage_summary_for_overlay(overlay)
    overall = report["overall"]
    totals = overall["totals"]

    click.echo(f"ts_code: {report.get('ts_code') or ts_code}")
    click.echo(f"industry: {report.get('industry_id') or industry_id or '<primary>'}")
    click.echo(f"overall_data_coverage: {overall['data_coverage']:.4f}")
    click.echo(f"overall_warning_level: {overall['warning_level']}")
    click.echo(f"parent_node_count: {overall['n_parents']}")
    click.echo(
        "child_totals: "
        f"known={totals['n_known']}, "
        f"unknown={totals['n_unknown']}, "
        f"inactive={totals['n_inactive']}, "
        f"optionality={totals['n_optionality']}, "
        f"low_materiality={totals['n_low_materiality']}, "
        f"na={totals['n_na']}"
    )

    rows = sorted(report["per_node"], key=lambda r: r["data_coverage"])
    if top_n > 0:
        rows = rows[:top_n]
    if rows:
        click.echo("per_node:")
        for r in rows:
            click.echo(
                f"  {r.get('dp_id') or r.get('node_id')}: "
                f"coverage={r['data_coverage']:.3f} "
                f"warn={r['warning_level']} "
                f"children={r['n_children']} "
                f"applicable={r['n_applicable']} "
                f"(known={r['n_known']}, "
                f"unknown={r['n_unknown']}, "
                f"inactive={r['n_inactive']}, "
                f"optionality={r['n_optionality']}, "
                f"low_mat={r['n_low_materiality']}, "
                f"na={r['n_na']})"
            )

    alerts = report["alerts"]
    click.echo(f"alert_count: {len(alerts)}")
    for a in alerts[:50]:
        click.echo(
            f"  alert: {a.get('dp_id') or a.get('node_id')} "
            f"level={a['warning_level']} coverage={a['data_coverage']:.3f}"
        )
    if len(alerts) > 50:
        click.echo(f"  ... {len(alerts) - 50} more alerts")


@main.command("check-spec-drift")
def check_spec_drift_command() -> None:
    """Run spec drift detector (scripts/check_spec_drift.py).

    Reports drift between config/data_point_roles.yaml,
    config/llm_field_governance.yaml, runtime/hot.sqlite, and
    config/stock_overlays/**.yaml. Writes
    docs/audit/spec_drift_report_v1.{md,json}.
    """

    import subprocess
    import sys as _sys

    repo_root = Path(__file__).resolve().parent.parent
    script = repo_root / "scripts" / "check_spec_drift.py"
    rc = subprocess.run(
        [_sys.executable, str(script)], check=False
    ).returncode
    if rc != 0:
        raise click.ClickException(
            f"spec drift detector exited with code {rc} (see report)"
        )


@main.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True,
              help="Bind address; 127.0.0.1 keeps the server local-only.")
@click.option("--port", default=8701, show_default=True, type=int,
              help="HTTP port (FrontEnd defaults to talking to 8701).")
@click.option("--cors-origin", default="http://127.0.0.1:1420",
              show_default=True,
              help="Single Access-Control-Allow-Origin value to advertise.")
def serve_command(host: str, port: int, cors_origin: str) -> None:
    """Start a read-only HTTP server exposing mvp20 manifest data as JSON.

    Endpoints under /api/* feed the FrontEnd Vite app. Routes that depend on
    upstream project-ult-* modules (graph-engine, audit-eval, main-core,
    data-platform, entity-registry, reasoner-runtime) return a structured
    503 envelope so the UI can render a clean banner.
    """

    cfg = ServerConfig(host=host, port=port, cors_origin=cors_origin)
    serve_forever(cfg)


def _emit_result(payload: dict[str, object]) -> None:
    for key, value in payload.items():
        click.echo(f"{key}: {value}")


def _emit_overlay_result(result) -> None:
    click.echo(f"ok: {result.ok}")
    click.echo(f"stock_overlay_count: {result.stock_overlay_count}")
    click.echo(f"industry_overlay_count: {result.industry_overlay_count}")
    click.echo(f"membership_count: {result.membership_count}")
    click.echo(f"error_count: {len(result.errors)}")
    click.echo(f"warning_count: {len(result.warnings)}")
    for err in result.errors[:20]:
        click.echo(f"error: {err}")
    if len(result.errors) > 20:
        click.echo(f"error: ... {len(result.errors) - 20} more")
    for warning in result.warnings[:10]:
        click.echo(f"warning: {warning}")
    if len(result.warnings) > 10:
        click.echo(f"warning: ... {len(result.warnings) - 10} more")


if __name__ == "__main__":
    # Support ``python -m mvp20.cli ...`` in addition to the
    # ``mvp20`` console entry point and ``python -m mvp20 ...``.
    main()
