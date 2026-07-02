"""Tests for ``scripts/verify_overlay_closed_loop.py`` (Z1c).

Covers:
1.  closed-loop tier (cheap_extract) with web URL  → hard violation
2.  closed-loop tier with only local kinds        → ok
3.  web_analysis tier with full url+checksum+fetched_at → ok
4.  web_analysis tier missing checksum            → soft warn (not auto-demoted)
5.  governance yaml absent                        → defaults to closed-loop
6.  dp_id absent from governance                  → defaults to closed-loop
7.  ``--strict-web-only`` only scans web_analysis tier fields
8.  ``--auto-demote`` only demotes hard violations, leaves web-tier warnings alone
9.  ``is_web_evidence`` detects URLs and web kinds
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import verify_overlay_closed_loop as v  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")


def _node(
    dp_id: str,
    *,
    evidence: list | None = None,
    data_status: str = "Known",
) -> dict:
    return {
        "node_id": f"unit:{dp_id}",
        "dp_id": dp_id,
        "node_name": dp_id,
        "data_status": data_status,
        "missing_policy": "unknown_reduce_confidence",
        "confidence": 0.6,
        "evidence_sources": evidence or [],
    }


def _overlay(nodes: list[dict]) -> dict:
    return {"nodes": nodes}


def _governance(rows: dict[str, str]) -> dict:
    """Build a governance dict mapping dp_id → model_tier."""

    return {
        "data_points": {
            dp_id: {"model_tier": tier} for dp_id, tier in rows.items()
        }
    }


# ---------------------------------------------------------------------------
# scan_node — pure unit tests on the policy table
# ---------------------------------------------------------------------------


def test_closed_loop_with_web_url_is_hard_violation() -> None:
    """Test #1: closed-loop tier (cheap_extract) with web URL → violation."""

    gov = _governance({"L0.demand.terminal": "cheap_extract"})
    node = _node(
        "L0.demand.terminal",
        evidence=[{
            "kind": "annual_report",
            "title": "AR2025",
            "url": "https://example.com/ar.pdf",
        }],
    )
    result = v.scan_node(node, gov)
    assert result["status"] == "violation"
    assert result["tier"] == "cheap_extract"
    assert any("web evidence not allowed" in e for e in result["errors"])


def test_closed_loop_with_local_only_is_ok() -> None:
    """Test #2: closed-loop tier with only local kinds → ok."""

    gov = _governance({"L1.position.channel_edge": "analysis"})
    node = _node(
        "L1.position.channel_edge",
        evidence=[
            {"kind": "local_dp_id", "source": "L5.is.revenue@runtime/hot.sqlite"},
            {"kind": "industry_inference", "reasoning": "sector cycle peak"},
        ],
    )
    result = v.scan_node(node, gov)
    assert result["status"] == "ok"
    assert result["errors"] == []


def test_closed_loop_with_local_tushare_fact_is_ok() -> None:
    """Tushare rows are closed-loop evidence when cited as local_dp_id."""

    gov = _governance({"L3.channel.mix": "cheap_extract"})
    node = _node(
        "L3.channel.mix",
        evidence=[{
            "kind": "local_dp_id",
            "dp_id": "L9.disclosure.qa_recent",
            "source": "tushare:irm_qa_sz",
            "excerpt": "公司渠道以直销为主，经销为辅。",
        }],
    )
    result = v.scan_node(node, gov)
    assert result["status"] == "ok"
    assert result["errors"] == []


def test_web_analysis_with_complete_triad_is_ok() -> None:
    """Test #3: web_analysis tier with url+checksum+fetched_at → ok."""

    gov = _governance({"L2.newbiz.tam": "web_analysis"})
    node = _node(
        "L2.newbiz.tam",
        evidence=[{
            "kind": "research_report",
            "url": "https://example.com/report.pdf",
            "checksum": "deadbeef" * 8,
            "fetched_at": "2026-05-13T08:30:00+08:00",
            "publisher": "broker-x",
            "excerpt": "..."
        }],
    )
    result = v.scan_node(node, gov)
    assert result["status"] == "ok"
    assert result["errors"] == []
    assert result["warnings"] == []


def test_web_analysis_missing_checksum_is_soft_warn() -> None:
    """Test #4: web_analysis missing checksum → warning, not error."""

    gov = _governance({"L2.newbiz.tam": "web_analysis"})
    node = _node(
        "L2.newbiz.tam",
        evidence=[{
            "kind": "research_report",
            "url": "https://example.com/report.pdf",
            # NB: no checksum, no fetched_at
        }],
    )
    result = v.scan_node(node, gov)
    assert result["status"] == "warning"
    assert result["errors"] == []
    assert any("checksum" in w for w in result["warnings"])
    assert any("fetched_at" in w for w in result["warnings"])


def test_governance_yaml_absent_defaults_to_closed_loop() -> None:
    """Test #5: governance dict empty → any web URL is a violation."""

    gov: dict = {}  # like load_governance() when file missing
    node = _node(
        "L0.demand.terminal",
        evidence=[{
            "kind": "external_url",
            "url": "https://example.com/x.html",
        }],
    )
    result = v.scan_node(node, gov)
    assert result["status"] == "violation"
    assert result["tier"] is None
    assert any("unregistered" in e or "None" in e for e in result["errors"])


def test_dp_id_not_in_governance_defaults_to_closed_loop() -> None:
    """Test #6: dp_id absent from governance → same as no governance."""

    gov = _governance({"some.other.dp": "web_analysis"})
    node = _node(
        "L0.supply.capacity",
        evidence=[{"kind": "annual_report", "url": "https://x.com/ar.pdf"}],
    )
    result = v.scan_node(node, gov)
    assert result["status"] == "violation"
    assert result["tier"] is None


# ---------------------------------------------------------------------------
# is_web_evidence — detection sanity
# ---------------------------------------------------------------------------


def test_is_web_evidence_detects_url_in_source() -> None:
    assert v.is_web_evidence({"kind": "local_dp_id", "source": "https://x.com"})


def test_is_web_evidence_detects_web_kind_without_url() -> None:
    assert v.is_web_evidence({"kind": "annual_report"})


def test_is_web_evidence_rejects_pure_local() -> None:
    assert not v.is_web_evidence({"kind": "local_dp_id", "source": "L5.is.revenue"})
    assert not v.is_web_evidence({"kind": "industry_inference", "reasoning": "..."})


def test_is_web_evidence_handles_bare_url_string() -> None:
    assert v.is_web_evidence("https://example.com/x")
    assert not v.is_web_evidence("config/industry_overlays/X.yaml#L0.demand")


# ---------------------------------------------------------------------------
# audit_overlays — end-to-end with tmp_path
# ---------------------------------------------------------------------------


def _setup_overlays(tmp_path: Path, *, with_governance: bool):
    """Create a temp tree of overlays. Returns (industry_dir, stock_dir,
    governance_path)."""

    industry_dir = tmp_path / "config" / "industry_overlays"
    stock_dir = tmp_path / "config" / "stock_overlays"
    gov_path = tmp_path / "config" / "llm_field_governance.yaml"
    industry_dir.mkdir(parents=True, exist_ok=True)
    stock_dir.mkdir(parents=True, exist_ok=True)

    # Industry overlay: one closed-loop violation + one web_analysis ok
    _write_yaml(industry_dir / "AI_COMPUTE.yaml", _overlay([
        _node(
            "L0.demand.terminal",
            evidence=[{
                "kind": "annual_report",  # web kind → closed-loop violation
                "url": "https://x.com/ar.pdf",
            }],
        ),
        _node(
            "L0.supply.capacity",
            evidence=[{
                "kind": "research_report",
                "url": "https://broker.com/r.pdf",
                "checksum": "a" * 64,
                "fetched_at": "2026-05-01T00:00:00+08:00",
            }],
        ),
    ]))

    # Stock overlay: one ok local
    sub = stock_dir / "AI_COMPUTE"
    sub.mkdir(exist_ok=True)
    _write_yaml(sub / "300750.SZ.yaml", _overlay([
        _node(
            "L1.position.channel_edge",
            evidence=[{"kind": "local_dp_id", "source": "L5.is.revenue@runtime/hot.sqlite"}],
        ),
    ]))

    if with_governance:
        _write_yaml(gov_path, {
            "data_points": {
                "L0.demand.terminal": {"model_tier": "cheap_extract"},
                "L0.supply.capacity": {"model_tier": "web_analysis"},
                "L1.position.channel_edge": {"model_tier": "analysis"},
            },
        })
    return industry_dir, stock_dir, gov_path


def test_audit_overlays_with_governance_classifies_tiers(tmp_path: Path) -> None:
    industry_dir, stock_dir, gov_path = _setup_overlays(tmp_path, with_governance=True)
    governance = v.load_governance(gov_path)
    summary = v.audit_overlays(
        stock_overlays_dir=stock_dir,
        industry_overlays_dir=industry_dir,
        governance=governance,
    )
    assert summary.overlays_scanned == 2
    assert summary.nodes_scanned == 3
    assert summary.web_analysis_nodes == 1
    assert summary.closed_loop_nodes == 2  # cheap_extract + analysis
    assert summary.unregistered_nodes == 0
    assert summary.hard_violations == 1   # L0.demand.terminal
    assert summary.warn_violations == 0   # supply.capacity web is well-formed


def test_load_governance_missing_returns_empty(tmp_path: Path) -> None:
    """Test #5 reinforce: load_governance on missing file → empty dict."""

    assert v.load_governance(tmp_path / "nope.yaml") == {}


def test_audit_overlays_without_governance_treats_all_as_closed_loop(
    tmp_path: Path,
) -> None:
    """Test #5 e2e: governance absent → both web-bearing nodes violate."""

    industry_dir, stock_dir, gov_path = _setup_overlays(tmp_path, with_governance=False)
    governance = v.load_governance(gov_path)
    assert governance == {}
    summary = v.audit_overlays(
        stock_overlays_dir=stock_dir,
        industry_overlays_dir=industry_dir,
        governance=governance,
    )
    # Both AI_COMPUTE nodes carry web evidence → both violations.
    # L1.position.channel_edge is local-only → ok.
    assert summary.hard_violations == 2
    assert summary.unregistered_nodes == 3


def test_strict_web_only_skips_closed_loop_nodes(tmp_path: Path) -> None:
    """Test #7: --strict-web-only only scans web_analysis tier fields."""

    industry_dir, stock_dir, gov_path = _setup_overlays(tmp_path, with_governance=True)
    governance = v.load_governance(gov_path)
    summary = v.audit_overlays(
        stock_overlays_dir=stock_dir,
        industry_overlays_dir=industry_dir,
        governance=governance,
        strict_web_only=True,
    )
    # Even though L0.demand.terminal violates, strict-web-only skips it.
    # L0.supply.capacity is web_analysis and well-formed → no violation.
    assert summary.hard_violations == 0
    assert summary.warn_violations == 0


def test_strict_web_only_still_flags_malformed_web_evidence(tmp_path: Path) -> None:
    """Variant of #7: malformed web evidence on web_analysis tier still warns."""

    industry_dir = tmp_path / "config" / "industry_overlays"
    stock_dir = tmp_path / "config" / "stock_overlays"
    industry_dir.mkdir(parents=True)
    stock_dir.mkdir(parents=True)
    _write_yaml(industry_dir / "X.yaml", _overlay([
        _node(
            "L2.newbiz.tam",
            evidence=[{"kind": "annual_report", "url": "https://x.com/x.pdf"}],
            # missing checksum + fetched_at
        ),
    ]))
    gov = _governance({"L2.newbiz.tam": "web_analysis"})
    summary = v.audit_overlays(
        stock_overlays_dir=stock_dir,
        industry_overlays_dir=industry_dir,
        governance=gov,
        strict_web_only=True,
    )
    assert summary.hard_violations == 0
    assert summary.warn_violations >= 2  # missing checksum + fetched_at


# ---------------------------------------------------------------------------
# auto-demote
# ---------------------------------------------------------------------------


def test_auto_demote_only_touches_hard_violations(tmp_path: Path) -> None:
    """Test #8: --auto-demote demotes the cheap_extract violator, leaves
    well-formed web_analysis alone."""

    industry_dir, stock_dir, gov_path = _setup_overlays(tmp_path, with_governance=True)
    governance = v.load_governance(gov_path)
    summary = v.audit_overlays(
        stock_overlays_dir=stock_dir,
        industry_overlays_dir=industry_dir,
        governance=governance,
        auto_demote=True,
    )
    assert summary.demoted_nodes == 1

    # Re-read the overlay and check that L0.demand.terminal was demoted.
    rewritten = yaml.safe_load((industry_dir / "AI_COMPUTE.yaml").read_text())
    by_dp = {n["dp_id"]: n for n in rewritten["nodes"]}
    demoted = by_dp["L0.demand.terminal"]
    assert demoted["data_status"] == "Unknown"
    assert demoted["evidence_sources"] == []
    assert "evidence_violation" in demoted["missing_reason"]
    # The web_analysis-tier well-formed node must NOT be demoted.
    untouched = by_dp["L0.supply.capacity"]
    assert untouched["data_status"] == "Known"
    assert untouched["evidence_sources"], "well-formed web evidence preserved"


def test_auto_demote_does_not_touch_web_warnings(tmp_path: Path) -> None:
    """Web-tier soft warning (missing checksum) must NOT auto-demote."""

    industry_dir = tmp_path / "config" / "industry_overlays"
    stock_dir = tmp_path / "config" / "stock_overlays"
    industry_dir.mkdir(parents=True)
    stock_dir.mkdir(parents=True)
    _write_yaml(industry_dir / "X.yaml", _overlay([
        _node(
            "L2.newbiz.tam",
            evidence=[{"kind": "annual_report", "url": "https://x.com/x.pdf"}],
        ),
    ]))
    gov = _governance({"L2.newbiz.tam": "web_analysis"})
    summary = v.audit_overlays(
        stock_overlays_dir=stock_dir,
        industry_overlays_dir=industry_dir,
        governance=gov,
        auto_demote=True,
    )
    assert summary.demoted_nodes == 0
    # Re-read: data_status untouched
    out = yaml.safe_load((industry_dir / "X.yaml").read_text())
    assert out["nodes"][0]["data_status"] == "Known"


# ---------------------------------------------------------------------------
# _decode_value_json — CJK excerpt matching (regression for the --check-excerpt
# bug where Chinese annual-report / IR citations false-failed because SQLite
# stores value_json ascii-escaped and PDF section text carries embedded
# newlines).
# ---------------------------------------------------------------------------


def test_decode_value_json_decodes_ascii_escaped_cjk() -> None:
    import json

    # realtime_current rows are written with ensure_ascii=True (json default),
    # so CJK lands as \uXXXX. The verifier must decode before substring match.
    raw = json.dumps({"sections": {"risk": "汇率波动的风险"}}, ensure_ascii=True)
    assert "\\u" in raw  # precondition: the stored form really is escaped
    decoded = v._decode_value_json(raw)
    assert "汇率波动的风险" in decoded
    # the exact path the excerpt check uses
    assert v._normalize_text("汇率波动的风险") in v._normalize_text(decoded)


def test_decode_value_json_newline_in_cjk_does_not_break_match() -> None:
    import json

    # PDF text extraction routinely injects newlines/spaces mid-phrase. A
    # json.dumps round-trip would re-escape the newline as a literal "\n"
    # whose stripped backslash leaves a stray "n" that splits the CJK run and
    # breaks the match — flattening keeps real whitespace instead.
    raw = json.dumps(
        {"sections": {"risk": "汇率的大幅波动将会对公司的进出口业务产生\n直接影响"}},
        ensure_ascii=True,
    )
    decoded = v._decode_value_json(raw)
    excerpt = "汇率的大幅波动将会对公司的进出口业务产生直接影响"
    assert v._normalize_text(excerpt) in v._normalize_text(decoded)


def test_decode_value_json_numbers_preserved_for_numeric_fallback() -> None:
    import json

    raw = json.dumps({"scalar": 35470325836.04, "unit": "元"}, ensure_ascii=True)
    decoded = v._decode_value_json(raw)
    assert "35470325836.04" in decoded
    assert "元" in decoded


def test_decode_value_json_passthrough_on_non_json() -> None:
    assert v._decode_value_json("not json {") == "not json {"
    assert v._decode_value_json("") == ""
