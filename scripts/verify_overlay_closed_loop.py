#!/usr/bin/env python3
"""Scan all overlay yamls and report evidence-policy violations, sliced by
``model_tier`` declared in ``config/llm_field_governance.yaml`` (Z1c).

Two policy tiers:

* **closed-loop tier** — ``model_tier ∈ {cheap_extract, cheap_classify,
  analysis}``. ``evidence_sources`` may only use ``local_dp_id`` /
  ``local_overlay`` / ``industry_inference``. Any ``http(s)://`` URL or
  web-style kind (``annual_report`` / ``research_report`` /
  ``investor_relations`` / ``external_url`` / ``web_fetch``) is a HARD
  violation and may be auto-demoted back to ``data_status: Unknown``.

* **web-enabled tier** — ``model_tier == web_analysis``. The four web
  kinds above are allowed, plus the closed-loop trio. Each web evidence
  entry MUST carry ``url`` + ``checksum`` (sha256 of fetched body) +
  ``fetched_at`` (ISO timestamp). Missing any of these is a SOFT
  violation (warn only, not auto-demoted) so a flaky LLM run does not
  destroy an otherwise reasonable answer.

If ``config/llm_field_governance.yaml`` is absent (pre-Z1b state) or the
dp_id is not registered there, the dp_id is treated as closed-loop —
this is forward-compatible: any new override that lands in governance.yaml
relaxes constraints exactly where intended.

Usage::

    python scripts/verify_overlay_closed_loop.py
    python scripts/verify_overlay_closed_loop.py --auto-demote
    python scripts/verify_overlay_closed_loop.py --strict-web-only
    python scripts/verify_overlay_closed_loop.py --governance custom/path.yaml
    python scripts/verify_overlay_closed_loop.py --stock-overlays-dir custom/path

See ``docs/codex/codex_fill_guide.md`` §2a for the authoritative rule.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GOVERNANCE_YAML = ROOT / "config" / "llm_field_governance.yaml"

LOCAL_KINDS = {"local_dp_id", "local_overlay", "industry_inference"}
WEB_KINDS = {
    "annual_report",
    "research_report",
    "investor_relations",
    "external_url",
    "web_fetch",
}
CLOSED_LOOP_TIERS = {"cheap_extract", "cheap_classify", "analysis"}
WEB_ANALYSIS_TIER = "web_analysis"

URL_RE = re.compile(r"https?://", re.IGNORECASE)


# ---------------------------------------------------------------------------
# governance loader
# ---------------------------------------------------------------------------


def load_governance(path: Path | None = None) -> dict[str, Any]:
    """Load LLM field governance yaml.

    Returns empty dict if file missing (forward-compatible: pre-Z1b state
    is treated as closed-loop-by-default for every dp_id).
    """

    target = path if path is not None else GOVERNANCE_YAML
    if not target.exists():
        return {}
    try:
        return yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:  # pragma: no cover — corruption path
        sys.stderr.write(f"WARN: cannot parse {target}: {exc}\n")
        return {}


def get_model_tier(dp_id: str, governance: dict[str, Any]) -> str | None:
    """Look up dp_id's model_tier. Returns None if not registered."""

    data_points = governance.get("data_points") or {}
    entry = data_points.get(dp_id)
    if not entry:
        return None
    return entry.get("model_tier")


# ---------------------------------------------------------------------------
# data classes
# ---------------------------------------------------------------------------


@dataclass
class Violation:
    overlay_path: Path
    node_dp_id: str
    node_node_id: str
    tier: str | None
    severity: str  # "error" | "warn"
    reason: str
    snippet: str = ""

    def as_row(self) -> dict[str, Any]:
        return {
            "overlay_path": str(self.overlay_path),
            "dp_id": self.node_dp_id,
            "node_id": self.node_node_id,
            "tier": self.tier or "unknown",
            "severity": self.severity,
            "reason": self.reason,
            "snippet": self.snippet[:200],
        }


@dataclass
class Summary:
    overlays_scanned: int = 0
    nodes_scanned: int = 0
    nodes_with_evidence: int = 0
    closed_loop_nodes: int = 0
    web_analysis_nodes: int = 0
    unregistered_nodes: int = 0
    violations: list[Violation] = field(default_factory=list)
    demoted_nodes: int = 0

    @property
    def hard_violations(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warn_violations(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warn")


# ---------------------------------------------------------------------------
# yaml helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _dump_yaml(path: Path, payload: dict[str, Any]) -> None:
    rendered = yaml.safe_dump(
        payload,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )
    path.write_text(rendered, encoding="utf-8")


def _evidence_entries(node: dict[str, Any]) -> list[Any]:
    """Return the evidence_sources list (or empty)."""

    sources = node.get("evidence_sources")
    if not sources:
        return []
    if isinstance(sources, list):
        return list(sources)
    return [sources]


def _stringify(entry: Any) -> str:
    """Compact string form of an evidence entry for snippet display."""

    if isinstance(entry, (dict, list)):
        try:
            return json.dumps(entry, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(entry)
    return str(entry)


# ---------------------------------------------------------------------------
# evidence classification
# ---------------------------------------------------------------------------


def is_web_evidence(entry: Any) -> bool:
    """Detect if an evidence_source entry uses web/external kinds or URLs."""

    if entry is None:
        return False
    if isinstance(entry, str):
        return bool(URL_RE.search(entry))
    if not isinstance(entry, dict):
        return False
    kind = entry.get("kind")
    if isinstance(kind, str) and kind in WEB_KINDS:
        return True
    # Even with an unknown / local kind, any nested http(s):// makes it web.
    src = entry.get("source") or ""
    url = entry.get("url") or ""
    if isinstance(src, str) and URL_RE.search(src):
        return True
    if isinstance(url, str) and URL_RE.search(url):
        return True
    # Last-resort sweep over scalar values.
    for v in entry.values():
        if isinstance(v, str) and URL_RE.search(v):
            return True
    return False


def validate_web_evidence(entry: Any) -> list[str]:
    """Return list of validation errors for a web evidence entry.

    Empty list = the entry has the required ``url + checksum + fetched_at``
    triad. Non-dict entries are rejected wholesale because they cannot carry
    structured metadata.
    """

    if not isinstance(entry, dict):
        return ["web evidence must be a dict with url+checksum+fetched_at"]
    errors: list[str] = []
    if not entry.get("url"):
        errors.append("web evidence missing url")
    if not entry.get("checksum"):
        errors.append("web evidence missing checksum")
    if not entry.get("fetched_at"):
        errors.append("web evidence missing fetched_at")
    return errors


# ---------------------------------------------------------------------------
# node-level scan
# ---------------------------------------------------------------------------


def scan_node(
    node: dict[str, Any],
    governance: dict[str, Any],
) -> dict[str, Any]:
    """Audit a node's evidence_sources against its declared model_tier.

    Returns ``{tier, status, errors, warnings, web_count}`` where ``status``
    is one of ``ok`` / ``violation`` / ``warning``.

    Logic
    -----
    * tier == ``web_analysis`` ⇒ web evidence is allowed. Each web entry
      must carry url+checksum+fetched_at; missing → warnings (soft).
    * tier ∈ closed-loop set OR tier == None (unregistered) ⇒ any web
      evidence is a HARD violation (errors).
    """

    dp_id = str(node.get("dp_id") or "")
    tier = get_model_tier(dp_id, governance) if dp_id else None
    ev_list = _evidence_entries(node)
    web_evs = [ev for ev in ev_list if is_web_evidence(ev)]

    if tier == WEB_ANALYSIS_TIER:
        warnings: list[str] = []
        for ev in web_evs:
            warnings.extend(validate_web_evidence(ev))
        if warnings:
            return {
                "tier": tier,
                "status": "warning",
                "errors": [],
                "warnings": warnings,
                "web_count": len(web_evs),
            }
        return {
            "tier": tier,
            "status": "ok",
            "errors": [],
            "warnings": [],
            "web_count": len(web_evs),
        }

    # Closed-loop tier (including unregistered → default closed-loop).
    if web_evs:
        tier_label = tier or "unregistered"
        return {
            "tier": tier,
            "status": "violation",
            "errors": [
                f"web evidence not allowed for tier={tier_label}; "
                f"found {len(web_evs)} web evidence entries"
            ],
            "warnings": [],
            "web_count": len(web_evs),
        }
    return {
        "tier": tier,
        "status": "ok",
        "errors": [],
        "warnings": [],
        "web_count": 0,
    }


# ---------------------------------------------------------------------------
# auto-demote
# ---------------------------------------------------------------------------


def _demote_node(node: dict[str, Any], reason: str) -> bool:
    """Demote a violating node back to Unknown + clear its evidence.

    Returns True if the node was actually mutated.
    """

    mutated = False
    if node.get("data_status") != "Unknown":
        node["data_status"] = "Unknown"
        node["status"] = "Unknown"
        node["missing_policy"] = "unknown_reduce_confidence"
        node["confidence"] = None
        node["missing_reason"] = f"evidence_violation_{reason}"
        mutated = True
    if node.get("evidence_sources"):
        node["evidence_sources"] = []
        mutated = True
    if node.get("data_source"):
        node["data_source"] = None
        mutated = True
    return mutated


# ---------------------------------------------------------------------------
# overlay walk
# ---------------------------------------------------------------------------


def _iter_overlay_files(
    stock_overlays_dir: Path,
    industry_overlays_dir: Path,
) -> Iterable[Path]:
    if industry_overlays_dir.exists():
        for path in sorted(industry_overlays_dir.glob("*.yaml")):
            yield path
    if stock_overlays_dir.exists():
        for path in sorted(stock_overlays_dir.glob("*/*.yaml")):
            yield path


def audit_overlays(
    *,
    stock_overlays_dir: Path,
    industry_overlays_dir: Path,
    governance: dict[str, Any],
    auto_demote: bool = False,
    strict_web_only: bool = False,
) -> Summary:
    """Walk every overlay yaml and audit each node's evidence_sources."""

    summary = Summary()
    for path in _iter_overlay_files(stock_overlays_dir, industry_overlays_dir):
        summary.overlays_scanned += 1
        payload = _load_yaml(path)
        nodes = payload.get("nodes") or []
        path_dirty = False
        for node in nodes:
            summary.nodes_scanned += 1
            ev_list = _evidence_entries(node)
            if ev_list:
                summary.nodes_with_evidence += 1
            result = scan_node(node, governance)
            tier = result["tier"]
            if tier == WEB_ANALYSIS_TIER:
                summary.web_analysis_nodes += 1
            elif tier in CLOSED_LOOP_TIERS:
                summary.closed_loop_nodes += 1
            else:
                summary.unregistered_nodes += 1

            if strict_web_only and tier != WEB_ANALYSIS_TIER:
                continue

            dp_id = str(node.get("dp_id") or "<dp_id>")
            node_id = str(node.get("node_id") or "<node_id>")
            for err in result["errors"]:
                summary.violations.append(Violation(
                    overlay_path=path,
                    node_dp_id=dp_id,
                    node_node_id=node_id,
                    tier=tier,
                    severity="error",
                    reason=err,
                    snippet=_stringify(ev_list),
                ))
            for warn in result["warnings"]:
                summary.violations.append(Violation(
                    overlay_path=path,
                    node_dp_id=dp_id,
                    node_node_id=node_id,
                    tier=tier,
                    severity="warn",
                    reason=warn,
                    snippet=_stringify(ev_list),
                ))

            # web_analysis warnings are NOT auto-demoted (could be a small
            # LLM fill miss like missing checksum). Only hard errors on
            # closed-loop / unregistered tiers trigger demote.
            if auto_demote and result["status"] == "violation":
                reason = "closed_loop_web_evidence"
                if _demote_node(node, reason=reason):
                    path_dirty = True
                    summary.demoted_nodes += 1

        if path_dirty:
            _dump_yaml(path, payload)
    return summary


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------


def _print_violations(violations: list[Violation]) -> None:
    if not violations:
        print("# closed-loop verify: no violations found")
        return
    print("# closed-loop verify: violations")
    print()
    print("| overlay | dp_id | tier | severity | reason | snippet |")
    print("|---|---|---|---|---|---|")
    for v in violations:
        row = v.as_row()
        print(
            f"| `{row['overlay_path']}` "
            f"| `{row['dp_id']}` "
            f"| {row['tier']} "
            f"| {row['severity']} "
            f"| {row['reason']} "
            f"| `{row['snippet']}` |"
        )


def _print_summary(summary: Summary) -> None:
    print()
    print("# summary")
    print(f"- overlays scanned: {summary.overlays_scanned}")
    print(f"- nodes scanned: {summary.nodes_scanned}")
    print(f"- nodes with evidence_sources: {summary.nodes_with_evidence}")
    print(f"- closed-loop tier nodes: {summary.closed_loop_nodes}")
    print(f"- web_analysis tier nodes: {summary.web_analysis_nodes}")
    print(f"- unregistered (default closed-loop) nodes: {summary.unregistered_nodes}")
    print(f"- hard violations (error): {summary.hard_violations}")
    print(f"- soft violations (warn): {summary.warn_violations}")
    print(f"- auto-demoted nodes: {summary.demoted_nodes}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stock-overlays-dir", type=Path,
        default=ROOT / "config" / "stock_overlays",
        help="Directory of compiled stock overlay yaml files.",
    )
    parser.add_argument(
        "--industry-overlays-dir", type=Path,
        default=ROOT / "config" / "industry_overlays",
        help="Directory of industry overlay yaml files.",
    )
    parser.add_argument(
        "--governance", type=Path, default=GOVERNANCE_YAML,
        help="Path to config/llm_field_governance.yaml (Z1b output).",
    )
    parser.add_argument(
        "--auto-demote", action="store_true",
        help=(
            "Rewrite hard-violating nodes back to data_status=Unknown in "
            "place. Web-tier warnings are never auto-demoted."
        ),
    )
    parser.add_argument(
        "--strict-web-only", action="store_true",
        help="Only scan web_analysis tier fields.",
    )
    parser.add_argument(
        "--out-json", type=Path, default=None,
        help="Optional path to write the violation list as JSON.",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Only print summary and exit code.",
    )
    args = parser.parse_args(argv)

    governance = load_governance(args.governance)
    summary = audit_overlays(
        stock_overlays_dir=args.stock_overlays_dir,
        industry_overlays_dir=args.industry_overlays_dir,
        governance=governance,
        auto_demote=args.auto_demote,
        strict_web_only=args.strict_web_only,
    )
    if not args.quiet:
        _print_violations(summary.violations)
    _print_summary(summary)

    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(
            json.dumps(
                {
                    "overlays_scanned": summary.overlays_scanned,
                    "nodes_scanned": summary.nodes_scanned,
                    "nodes_with_evidence": summary.nodes_with_evidence,
                    "closed_loop_nodes": summary.closed_loop_nodes,
                    "web_analysis_nodes": summary.web_analysis_nodes,
                    "unregistered_nodes": summary.unregistered_nodes,
                    "hard_violations": summary.hard_violations,
                    "warn_violations": summary.warn_violations,
                    "demoted_nodes": summary.demoted_nodes,
                    "violations": [v.as_row() for v in summary.violations],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    return 1 if summary.hard_violations > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
