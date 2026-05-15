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
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mvp20 import schema_validator  # noqa: E402

GOVERNANCE_YAML = ROOT / "config" / "llm_field_governance.yaml"
HOT_DB_PATH = ROOT / "runtime" / "hot.sqlite"

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
    excerpt_checked_nodes: int = 0
    excerpt_mis_cite_nodes: int = 0
    # Fix B (B4) — schema-drift soft-warn counters.
    schema_checked_nodes: int = 0
    schema_violating_nodes: int = 0

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
# excerpt semantic check (Fix A) — defend against mis-citation
# ---------------------------------------------------------------------------


_PUNCT_RE = re.compile(
    r"[\s\.,，。、；;:：!！\?？\(\)（）\[\]【】\"'“”‘’<>《》/\\\-—_+=*#&%$@`~]+"
)


def _normalize_text(s: Any) -> str:
    """Lowercase + strip punctuation/whitespace for fuzzy substring match.

    Used so cosmetic differences (full-width vs ASCII punctuation, trailing
    whitespace, casing) don't cause false positives.
    """

    if not isinstance(s, str):
        return ""
    return _PUNCT_RE.sub("", s.lower())


# ---------------------------------------------------------------------------
# numeric-tolerant match (Fix A2) — close the gap between LLM excerpts that
# format numbers loosely (亿元 / 万元 / %, JSON wrappers stripped) and the
# canonical SQLite/yaml stored values (raw floats, often with unit fields).
# ---------------------------------------------------------------------------


# Match number forms: 12345, 12345.67, 1.23e5, -1.5, 3,456.78. The first
# alternative requires at least one thousands separator (digit groups of 3)
# so it won't greedily eat plain integers like ``2026`` and miss them — the
# second alternative handles plain integers / decimals.
_NUMBER_RE = re.compile(
    r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?:[eE][-+]?\d+)?"
    r"|-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
)

# CN financial scale suffixes — when a number in the excerpt is followed by
# one of these, we also try its scaled value when matching against the
# actual canonical value. e.g. "248.48541亿元" should match the raw
# 24848541000.0 stored in SQLite.
_CN_SCALE_SUFFIXES: tuple[tuple[str, float], ...] = (
    ("万亿", 1e12),
    ("亿元", 1e8),
    ("亿", 1e8),
    ("万元", 1e4),
    ("万", 1e4),
    ("千", 1e3),
    ("百", 1e2),
)


def _extract_numbers(s: Any) -> list[float]:
    """Pull all numeric tokens from a string. Normalises 1.5e5, 1,234, etc.

    Returns a list of floats (already canonicalised — thousands separators
    stripped, sci-notation parsed).
    """

    if not s:
        return []
    text = str(s)
    out: list[float] = []
    for m in _NUMBER_RE.findall(text):
        try:
            cleaned = m.replace(",", "")
            out.append(float(cleaned))
        except (ValueError, OverflowError):
            continue
    return out


def _extract_numbers_with_scale(s: Any) -> list[float]:
    """Like ``_extract_numbers`` but also emits CN-scaled variants.

    For each number, if it is immediately followed by a CN scale suffix
    (亿元 / 万 / 千 / etc), the scaled value is appended *in addition to*
    the raw value. This makes "248.48541亿元" yield both 248.48541 and
    24848541000.0 so the latter can match SQLite's raw float.
    """

    if not s:
        return []
    text = str(s)
    out: list[float] = []
    for m in _NUMBER_RE.finditer(text):
        token = m.group(0)
        try:
            raw = float(token.replace(",", ""))
        except (ValueError, OverflowError):
            continue
        out.append(raw)
        # Look at what immediately follows the number for a scale suffix.
        # Allow a single space between number and suffix (e.g. "248 亿元").
        tail = text[m.end():m.end() + 6]
        tail_stripped = tail.lstrip()
        for suffix, factor in _CN_SCALE_SUFFIXES:
            if tail_stripped.startswith(suffix):
                out.append(raw * factor)
                break
    return out


def _numbers_close(a: float, b: float, rel_tol: float, abs_tol: float) -> bool:
    """True iff ``a`` and ``b`` are within ``abs_tol`` OR ``rel_tol`` (the
    latter measured against the larger magnitude). Mirrors ``math.isclose``
    but with explicit defaults that suit accounting numbers."""

    if abs(a - b) <= abs_tol:
        return True
    denom = max(abs(a), abs(b))
    if denom > 0 and abs(a - b) / denom <= rel_tol:
        return True
    return False


def _digit_substring_match(token: str, actual_value: str) -> bool:
    """True if the digit characters of ``token`` form a contiguous run
    inside the digit characters of ``actual_value``.

    This accepts period/date labels like "2026" matching "20260331" (a
    common pattern where the excerpt writes "2026Q1" and the SQLite value
    carries period "20260331"). The match is strictly on the digit-only
    projection of both strings so non-digit punctuation doesn't fool it.
    """

    if not token:
        return False
    e_digits = "".join(ch for ch in token if ch.isdigit())
    if not e_digits:
        return False
    a_digits = "".join(ch for ch in str(actual_value) if ch.isdigit())
    return e_digits in a_digits


def _numeric_tolerant_match(
    excerpt: str,
    actual_value: str,
    rel_tol: float = 1e-6,
    abs_tol: float = 1.0,
) -> bool:
    """True iff every number in ``excerpt`` has a near-equal counterpart in
    ``actual_value`` (after stripping CN scale suffixes / thousands
    separators / etc).

    Strategy
    --------
    1. Pull numbers from the excerpt via ``_extract_numbers_with_scale``
       (so "248.48541亿元" yields both 248.48541 and 24848541000.0).
       Each token is paired with its original substring form so we can
       fall back to digit-substring matching for period labels.
    2. Pull numbers from the actual value via ``_extract_numbers`` (it's
       already in canonical raw form in SQLite/yaml).
    3. For each excerpt number, accept any actual number within ``abs_tol``
       OR ``rel_tol``. Both tolerances default to tight values so we don't
       smear over genuinely-different numbers — ``rel_tol=1e-6`` is
       basically float-equality, ``abs_tol=1.0`` only absorbs rounding.
    4. If a numeric match fails, fall back to digit-substring: a "2026"
       token in the excerpt is accepted if "2026" appears as a digit
       run inside the actual value's digit projection (so "20260331"
       satisfies it). This handles period-label / quarter-marker tokens.
    5. Return True only if EVERY excerpt number is covered by EITHER a
       tolerance match OR a digit-substring match. If even one cannot be
       traced back, the excerpt fabricates a number → real mis-cite.

    Empty-number cases
    ------------------
    Excerpt without any numbers returns False — fall back to the substring
    check (this helper only claims jurisdiction over numeric citations).
    Actual without numbers also returns False — we can't tolerate-match
    against text-only sources.
    """

    # (token_string, raw_float, *scaled_floats) — keep the original token
    # string so we can do digit-substring fallback for period labels.
    if not excerpt:
        return False
    excerpt_str = str(excerpt)
    if not excerpt_str:
        return False

    excerpt_groups: list[tuple[str, list[float]]] = []
    for m in _NUMBER_RE.finditer(excerpt_str):
        token = m.group(0)
        try:
            raw = float(token.replace(",", ""))
        except (ValueError, OverflowError):
            continue
        values = [raw]
        tail = excerpt_str[m.end():m.end() + 6].lstrip()
        for suffix, factor in _CN_SCALE_SUFFIXES:
            if tail.startswith(suffix):
                values.append(raw * factor)
                break
        excerpt_groups.append((token, values))

    if not excerpt_groups:
        return False

    a_nums = _extract_numbers(actual_value)
    if not a_nums:
        # No numbers at all in actual → cannot tolerate-match. But still
        # allow digit-substring fallback (rare; covers edge cases like
        # excerpt "2026" vs actual "as_of=20260331" if the latter somehow
        # didn't parse). Conservative: keep the original False return.
        return False

    for token, values in excerpt_groups:
        matched = False
        for ex in values:
            for ac in a_nums:
                if _numbers_close(ex, ac, rel_tol, abs_tol):
                    matched = True
                    break
            if matched:
                break
        # Digit-substring fallback for period/year labels (e.g. "2026"
        # matching "20260331"). Only applied when tolerance match failed.
        if not matched and _digit_substring_match(token, actual_value):
            matched = True
        if not matched:
            return False
    return True


def _lookup_sqlite_value(
    db_path: Path,
    ts_code: str,
    dp_id: str,
) -> str:
    """Pull current ``value_json`` for ``(ts_code, dp_id)`` from realtime_current.

    Falls back to ``MARKET:<market>`` / ``INDUSTRY:<id>`` sentinels per
    ``storage.read_hot_snapshot`` logic so industry/macro dp_ids resolve.
    Returns ``""`` if the row is not found or the db is missing.
    """

    if not db_path.exists():
        return ""
    # Priority order: stock row > industry sentinels > market sentinel.
    candidates: list[str] = [ts_code]
    market_suffix: str | None = None
    if ts_code.endswith((".SH", ".SZ", ".BJ")):
        market_suffix = "MARKET:CN"
    elif ts_code.endswith(".HK"):
        market_suffix = "MARKET:HK"
    elif ts_code.endswith(".US"):
        market_suffix = "MARKET:US"

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        try:
            ind_rows = conn.execute(
                "SELECT industry_id FROM overlay_manifest WHERE ts_code = ? "
                "ORDER BY primary_industry DESC, industry_id",
                (ts_code,),
            ).fetchall()
            for (ind,) in ind_rows:
                candidates.append(f"INDUSTRY:{ind}")
        except sqlite3.OperationalError:
            # overlay_manifest may not exist in minimal test fixtures.
            pass

        if market_suffix is not None:
            candidates.append(market_suffix)

        placeholders = ",".join("?" * len(candidates))
        try:
            rows = conn.execute(
                f"SELECT ts_code, value_json FROM realtime_current "
                f"WHERE dp_id = ? AND ts_code IN ({placeholders})",
                (dp_id, *candidates),
            ).fetchall()
        except sqlite3.OperationalError:
            return ""
    finally:
        conn.close()
    if not rows:
        return ""
    priority = {t: i for i, t in enumerate(candidates)}
    rows.sort(key=lambda r: priority.get(r[0], 999))
    return rows[0][1] or ""


def verify_excerpt_semantic_match(
    node: dict[str, Any],
    ts_code: str,
    db_path: Path,
    overlays_root: Path | None = None,
) -> list[str]:
    """For each ``evidence_sources`` entry, verify the ``excerpt`` substring
    is actually present in the source it claims to cite.

    * ``kind=local_dp_id`` — excerpt must appear in the SQLite
      ``value_json`` of the cited dp_id (across the stock's own row and
      INDUSTRY/MARKET sentinels).
    * ``kind=local_overlay`` — excerpt must appear in the overlay yaml
      node's serialised ``value``.
    * ``industry_inference`` / web kinds — no excerpt semantics enforced
      here (industry_inference has no source to compare against; web kinds
      are checked separately for url+checksum+fetched_at).

    Excerpts shorter than 3 normalised chars are skipped (too short to be
    meaningful evidence). Missing excerpts are also skipped — absence of
    excerpt is a quality issue but not a mis-cite.

    Returns the list of mis-cite error messages (empty if all evidence
    excerpts trace back to their sources).
    """

    errors: list[str] = []
    ev_list = _evidence_entries(node)
    for idx, ev in enumerate(ev_list):
        if not isinstance(ev, dict):
            continue
        kind = ev.get("kind")
        excerpt = ev.get("excerpt") or ev.get("snippet") or ""
        if not excerpt:
            continue
        norm_excerpt = _normalize_text(excerpt)
        if len(norm_excerpt) < 3:
            continue

        if kind == "local_dp_id":
            src_dp = ev.get("dp_id") or ev.get("source_dp_id") or ""
            if not src_dp:
                # Some legacy rows store the dp_id inside `source`, e.g.
                # "L5.is.revenue@runtime/hot.sqlite". Salvage that form.
                src_field = ev.get("source") or ""
                if isinstance(src_field, str) and "@" in src_field:
                    src_dp = src_field.split("@", 1)[0]
            if not src_dp:
                errors.append(
                    f"ev[{idx}] kind=local_dp_id missing dp_id field"
                )
                continue
            actual = _lookup_sqlite_value(db_path, ts_code, src_dp)
            if not actual:
                errors.append(
                    f"ev[{idx}] cites {src_dp!r} but no SQLite row found for "
                    f"({ts_code} or sentinel)"
                )
                continue
            if norm_excerpt not in _normalize_text(actual):
                # Substring failed — try numeric tolerant fallback (Fix A2).
                # codex frequently re-formats values: "34988057000元" vs
                # '{"scalar": 34988057000.0}', or "248.48541亿元" vs the
                # raw 24848541000.0 stored in SQLite. If every number in
                # the excerpt has a near-equal counterpart in the actual
                # value, accept.
                if not _numeric_tolerant_match(excerpt, actual):
                    errors.append(
                        f"ev[{idx}] mis-cite: excerpt {excerpt[:60]!r} not "
                        f"in {src_dp}'s actual value {actual[:80]!r} "
                        f"(substring + numeric-tolerant both failed)"
                    )

        elif kind == "local_overlay":
            if overlays_root is None:
                continue
            path_str = ev.get("path") or ""
            target_dp = ev.get("dp_id") or ""
            if not path_str:
                continue
            yaml_path = (
                Path(path_str)
                if path_str.startswith("/")
                else overlays_root / path_str
            )
            if not yaml_path.exists():
                # Also try treating overlays_root as project root.
                alt = (
                    overlays_root.parent / path_str
                    if overlays_root.parent != overlays_root
                    else yaml_path
                )
                if alt.exists():
                    yaml_path = alt
                else:
                    errors.append(
                        f"ev[{idx}] local_overlay path {path_str!r} not found"
                    )
                    continue
            try:
                overlay = (
                    yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                )
            except (yaml.YAMLError, OSError) as exc:
                errors.append(f"ev[{idx}] overlay parse failed: {exc}")
                continue
            target_node = None
            for n in overlay.get("nodes") or []:
                if isinstance(n, dict) and n.get("dp_id") == target_dp:
                    target_node = n
                    break
            if target_node is None:
                if target_dp:
                    errors.append(
                        f"ev[{idx}] dp_id {target_dp!r} not in overlay"
                    )
                continue
            v = target_node.get("value")
            actual = (
                json.dumps(v, ensure_ascii=False)
                if v not in (None, "", [], {})
                else ""
            )
            if not actual:
                errors.append(
                    f"ev[{idx}] overlay node {target_dp!r} has no value"
                )
                continue
            if norm_excerpt not in _normalize_text(actual):
                # Substring failed — try numeric tolerant fallback (Fix A2),
                # symmetric with the local_dp_id path above.
                if not _numeric_tolerant_match(excerpt, actual):
                    errors.append(
                        f"ev[{idx}] mis-cite: excerpt {excerpt[:60]!r} not "
                        f"in overlay {target_dp}'s value {actual[:80]!r} "
                        f"(substring + numeric-tolerant both failed)"
                    )

        # kind == "industry_inference" → reasoning-only, no source to check.
        # kind ∈ WEB_KINDS → url+checksum+fetched_at checked separately.

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
    check_excerpt: bool = False,
    check_schema: bool = False,
    db_path: Path | None = None,
    overlays_root: Path | None = None,
) -> Summary:
    """Walk every overlay yaml and audit each node's evidence_sources.

    When ``check_excerpt`` is True, each evidence-bearing node also has
    its ``excerpt`` strings semantically validated against the cited
    source (SQLite for ``local_dp_id``, overlay yaml for
    ``local_overlay``). Mis-cites are reported as SOFT violations
    (severity ``warn``) and are NEVER auto-demoted, to avoid clobbering
    overlays for cosmetic excerpt drift.
    """

    if db_path is None:
        db_path = HOT_DB_PATH
    if overlays_root is None:
        overlays_root = stock_overlays_dir.parent

    summary = Summary()
    for path in _iter_overlay_files(stock_overlays_dir, industry_overlays_dir):
        summary.overlays_scanned += 1
        payload = _load_yaml(path)
        nodes = payload.get("nodes") or []
        overlay_ts_code = str(payload.get("ts_code") or "")
        # Industry overlay → use INDUSTRY:<id> sentinel as ts_code so the
        # excerpt lookup naturally resolves industry-level rows.
        if not overlay_ts_code:
            industry_id = payload.get("industry_id") or path.stem
            overlay_ts_code = f"INDUSTRY:{industry_id}"
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

            # Excerpt semantic check (Fix A): soft-warn only, never demote.
            if check_excerpt and ev_list:
                summary.excerpt_checked_nodes += 1
                excerpt_errors = verify_excerpt_semantic_match(
                    node,
                    overlay_ts_code,
                    db_path,
                    overlays_root=overlays_root,
                )
                if excerpt_errors:
                    summary.excerpt_mis_cite_nodes += 1
                for msg in excerpt_errors:
                    summary.violations.append(Violation(
                        overlay_path=path,
                        node_dp_id=dp_id,
                        node_node_id=node_id,
                        tier=tier,
                        severity="warn",
                        reason=f"excerpt_mis_cite: {msg}",
                        snippet=_stringify(ev_list),
                    ))

            # Schema-drift check (Fix B / B4): soft-warn only, never
            # demote. validate_overlay_node skips non-Known/non-filled-
            # Optionality nodes itself, so this is cheap to run over
            # every node. Mis-shaped values stay in the yaml — the
            # warning just surfaces them for the operator.
            if check_schema:
                schema_errors = schema_validator.validate_overlay_node(
                    node, strict=False,
                )
                # Only count it as "checked" when the dp_id has a schema
                # registered AND the node was eligible (Known/filled).
                # validate_overlay_node returns [] for both
                # "no schema registered" and "non-eligible status" — we
                # only want the former counted, so do a manual gate.
                eligible_status = node.get("data_status") in (
                    "Known", "Optionality",
                )
                if (
                    dp_id in schema_validator.DP_SCHEMA
                    and eligible_status
                ):
                    summary.schema_checked_nodes += 1
                    if schema_errors:
                        summary.schema_violating_nodes += 1
                for msg in schema_errors:
                    # Strip [warn] prefix for cleaner display.
                    clean = msg.removeprefix("[warn] ")
                    summary.violations.append(Violation(
                        overlay_path=path,
                        node_dp_id=dp_id,
                        node_node_id=node_id,
                        tier=tier,
                        severity="warn",
                        reason=f"schema_drift: {clean}",
                        snippet=_stringify(node.get("value")),
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
    if summary.excerpt_checked_nodes:
        print(f"- excerpt-checked nodes: {summary.excerpt_checked_nodes}")
        print(f"- excerpt mis-cite nodes: {summary.excerpt_mis_cite_nodes}")
    if summary.schema_checked_nodes:
        print(f"- schema-checked nodes: {summary.schema_checked_nodes}")
        print(f"- schema-violating nodes: {summary.schema_violating_nodes}")


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
        "--check-excerpt", action="store_true",
        help=(
            "Opt-in semantic check: verify each evidence excerpt is a "
            "substring of the cited source value (SQLite for local_dp_id, "
            "overlay yaml for local_overlay). Mis-cites are reported as "
            "soft violations and never auto-demoted."
        ),
    )
    parser.add_argument(
        "--check-schema", action="store_true",
        help=(
            "Opt-in schema-drift check: validate each node's value "
            "against mvp20.schema_validator.DP_SCHEMA. Drift is "
            "reported as soft violation and never auto-demoted "
            "(operator-actionable only)."
        ),
    )
    parser.add_argument(
        "--db-path", type=Path, default=HOT_DB_PATH,
        help="Path to runtime/hot.sqlite (only used with --check-excerpt).",
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
        check_excerpt=args.check_excerpt,
        check_schema=args.check_schema,
        db_path=args.db_path,
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
                    "excerpt_checked_nodes": summary.excerpt_checked_nodes,
                    "excerpt_mis_cite_nodes": summary.excerpt_mis_cite_nodes,
                    "schema_checked_nodes": summary.schema_checked_nodes,
                    "schema_violating_nodes": summary.schema_violating_nodes,
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
