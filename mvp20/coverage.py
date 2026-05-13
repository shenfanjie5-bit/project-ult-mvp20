"""Data Coverage + confidence propagation + N/A renormalization (spec §23).

Pure functions implementing the missing-node summary rules from
`图谱设计.md` §23. Nothing in this module talks to SQLite or YAML directly —
it only consumes plain ``dict`` payloads (the same shape used by the
overlay/aggregator pipeline) and returns the derived numbers.

5 missing states recognised (spec §23):

- N/A          : not applicable → dropped from numerator AND denominator,
                  remaining siblings are renormalised.
- Unknown      : applicable but unobservable → counted in the denominator,
                  not in the numerator → drags Data Coverage down.
- Inactive     : node exists but not currently triggered → still counted as
                  "known" for coverage (the absence of trigger is itself a
                  known data point).
- Optionality  : future option node, scored as ``(current, option_value)``
                  rather than a single contribution.
- LowMateriality : applicable but contributes <5% revenue/profit, can be
                  folded away (proxy: ``materiality < 0.05``).

The public surface is:

- :func:`compute_data_coverage`            — Σ known&applicable / Σ applicable
- :func:`renormalize_weights`              — drop N/A, renormalise rest to 1
- :func:`propagate_confidence`             — Base × Coverage × Evidence
- :func:`adjust_path_score`                — Raw × Confidence
- :func:`handle_optionality`               — (current_score, option_score)
- :func:`coverage_warning_level`           — ok / low_confidence / no_strong
- :func:`classify_missing_state`           — bucket a node into 6 states
- :func:`coverage_summary_for_node`        — one parent + its children
- :func:`coverage_summary_for_overlay`     — every parent in a stock overlay
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

# ---------------------------------------------------------------------------
# Constants — single source of truth for spec §23 thresholds.
# ---------------------------------------------------------------------------

EVIDENCE_QUALITY_MAP: dict[str, float] = {
    "low": 0.5,
    "medium": 0.75,
    "high": 1.0,
}

# spec §23.4 — "如果收入占比 < 5% 且利润占比 < 5% 且当前没有重大事件"
LOW_MATERIALITY_THRESHOLD: float = 0.05

# spec §23.2 — Data Coverage warning bands
LOW_CONFIDENCE_THRESHOLD: float = 0.50
NO_STRONG_CONCLUSION_THRESHOLD: float = 0.30

# Statuses that count as "known and applicable" for the coverage numerator.
# Per spec §23.2 the numerator is "已知且适用子节点权重之和". Inactive nodes
# are explicitly known (a confirmed non-trigger), so they go in the numerator.
# Unknown nodes are applicable but NOT known, so they are denominator-only.
_KNOWN_STATUSES: frozenset[str] = frozenset({"Known", "Inactive"})

# Statuses that are dropped completely (numerator and denominator).
_NOT_APPLICABLE_STATUSES: frozenset[str] = frozenset({"NA", "N/A"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node_weight(node: Mapping[str, Any]) -> float:
    """Pick the weight used by §23 formulas.

    Spec talks about "子节点权重". The overlay schema stores this as
    ``base_weight`` (static) and ``active_weight`` (event-modulated). We
    prefer ``active_weight`` if present because §23.3 (Inactive) explicitly
    sets ``active_weight = 0`` while keeping ``base_weight`` intact, and the
    parent rollup is what we are modelling here.
    """

    w = node.get("active_weight")
    if w is None:
        w = node.get("base_weight")
    if w is None:
        w = 1.0
    try:
        return float(w)
    except (TypeError, ValueError):
        return 1.0


def _normalise_status(raw: Any) -> str:
    """Map various N/A spellings + None to a stable token used internally."""

    if raw is None:
        return "Unknown"
    s = str(raw).strip()
    if s in ("N/A", "NA", "n/a"):
        return "NA"
    if s == "Low Materiality":
        return "LowMateriality"
    return s


# ---------------------------------------------------------------------------
# Spec §23 — classification
# ---------------------------------------------------------------------------


def classify_missing_state(node: Mapping[str, Any]) -> str:
    """Bucket a node into one of {Known, NA, Unknown, Inactive, Optionality,
    LowMateriality}.

    Priority:
      1. ``data_status`` (explicit author intent wins)
      2. ``missing_policy`` (fall back to policy mapping)
      3. ``materiality`` (spec §23.4 proxy: <0.05 → LowMateriality)
    """

    raw_status = node.get("data_status")
    if raw_status is not None:
        status = _normalise_status(raw_status)
        if status in {"Known", "NA", "Unknown", "Inactive", "Optionality", "LowMateriality"}:
            # Honour explicit author intent first, but still apply the
            # low-materiality demotion when the node is otherwise just
            # "Known" but tiny — spec §23.4 "适用但影响很小".
            if status == "Known":
                mat = node.get("materiality")
                if mat is not None:
                    try:
                        if float(mat) < LOW_MATERIALITY_THRESHOLD:
                            return "LowMateriality"
                    except (TypeError, ValueError):
                        pass
            return status

    policy = (node.get("missing_policy") or "").strip()
    policy_map = {
        "not_applicable_remove": "NA",
        "unknown_reduce_confidence": "Unknown",
        "inactive_zero_weight": "Inactive",
        "optionality_track": "Optionality",
        "low_materiality_fold": "LowMateriality",
        "known": "Known",
    }
    if policy in policy_map:
        bucketed = policy_map[policy]
        if bucketed == "Known":
            mat = node.get("materiality")
            if mat is not None:
                try:
                    if float(mat) < LOW_MATERIALITY_THRESHOLD:
                        return "LowMateriality"
                except (TypeError, ValueError):
                    pass
        return bucketed

    mat = node.get("materiality")
    if mat is not None:
        try:
            if float(mat) < LOW_MATERIALITY_THRESHOLD:
                return "LowMateriality"
        except (TypeError, ValueError):
            pass

    return "Unknown"


# ---------------------------------------------------------------------------
# Spec §23.1 — N/A renormalisation
# ---------------------------------------------------------------------------


def renormalize_weights(children: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    """Drop N/A children and renormalise the rest so their weights sum to 1.

    spec §23.1: "父节点汇总时剔除该节点，并重归一化其他适用子节点权重".

    Returns a mapping ``{dp_id: weight}``. N/A children are absent from the
    result. If every child is N/A (or the applicable total is 0), returns an
    empty dict — the caller is responsible for treating that as
    "all-not-applicable".
    """

    applicable: list[tuple[str, float]] = []
    for node in children:
        state = classify_missing_state(node)
        if state == "NA":
            continue
        dp_id = node.get("dp_id") or node.get("node_id")
        if dp_id is None:
            continue
        applicable.append((str(dp_id), _node_weight(node)))

    total = sum(w for _, w in applicable)
    if total <= 0:
        return {}
    return {dp_id: w / total for dp_id, w in applicable}


# ---------------------------------------------------------------------------
# Spec §23.2 — Data Coverage
# ---------------------------------------------------------------------------


def compute_data_coverage(children: Iterable[Mapping[str, Any]]) -> float:
    """Data Coverage = Σ(known & applicable weight) / Σ(applicable weight).

    spec §23.2 formula (literal): "已知且适用子节点权重之和 / 全部适用子节点
    权重之和".

    - Applicable = ``data_status != 'N/A'``
    - Known      = ``data_status in {'Known', 'Inactive'}`` (Unknown is NOT
                   known — its whole purpose is to drag coverage down)

    Returns ``0.0`` when there are no applicable children (everything was
    N/A or the list was empty). Otherwise returns a value in ``[0.0, 1.0]``.
    """

    known_w = 0.0
    applicable_w = 0.0
    for node in children:
        state = classify_missing_state(node)
        if state == "NA":
            continue
        w = _node_weight(node)
        applicable_w += w
        # LowMateriality is applicable but not "known" unless the source
        # status was Known/Inactive — classify_missing_state may have
        # demoted a Known node to LowMateriality. Honour the original
        # data_status for the "known" bucket.
        original = _normalise_status(node.get("data_status"))
        if state in _KNOWN_STATUSES or original in _KNOWN_STATUSES:
            known_w += w
    if applicable_w <= 0:
        return 0.0
    return max(0.0, min(1.0, known_w / applicable_w))


def coverage_warning_level(coverage: float) -> str:
    """Map Data Coverage to one of: ``ok`` / ``low_confidence`` /
    ``no_strong_conclusion``.

    spec §23.2:

      Data Coverage < 50%   → 提示父节点判断置信度较低 (``low_confidence``)
      Data Coverage < 30%   → 禁止输出强结论 (``no_strong_conclusion``)
    """

    if coverage < NO_STRONG_CONCLUSION_THRESHOLD:
        return "no_strong_conclusion"
    if coverage < LOW_CONFIDENCE_THRESHOLD:
        return "low_confidence"
    return "ok"


# ---------------------------------------------------------------------------
# Spec §23.2 — Confidence propagation
# ---------------------------------------------------------------------------


def propagate_confidence(
    parent_base_confidence: float,
    data_coverage: float,
    evidence_quality: str | float,
) -> float:
    """Parent Confidence = Base × Data Coverage × Evidence Quality.

    ``evidence_quality`` accepts either the categorical string {low, medium,
    high} (mapped via :data:`EVIDENCE_QUALITY_MAP`) or a raw float already
    in ``[0, 1]``. Anything outside the mapping defaults to ``medium``.
    """

    if isinstance(evidence_quality, str):
        eq = EVIDENCE_QUALITY_MAP.get(
            evidence_quality.strip().lower(),
            EVIDENCE_QUALITY_MAP["medium"],
        )
    else:
        try:
            eq = float(evidence_quality)
        except (TypeError, ValueError):
            eq = EVIDENCE_QUALITY_MAP["medium"]

    base = max(0.0, min(1.0, float(parent_base_confidence)))
    cov = max(0.0, min(1.0, float(data_coverage)))
    eq = max(0.0, min(1.0, float(eq)))
    return base * cov * eq


def adjust_path_score(raw_score: float, confidence: float) -> float:
    """Adjusted Path Score = Raw × Confidence (spec §23.2 last block)."""

    return float(raw_score) * max(0.0, min(1.0, float(confidence)))


# ---------------------------------------------------------------------------
# Spec §23.5 — Optionality
# ---------------------------------------------------------------------------


def handle_optionality(node: Mapping[str, Any]) -> tuple[float, float]:
    """Return ``(current_score, option_score)`` for an Optionality node.

    spec §23.5: "评分要拆成两部分":

      当前财务贡献：按收入 / 利润占比计算
      未来估值期权：按市场空间、成功概率、时间和证据质量计算

    Reads from ``node['value']``. Expected sub-fields (all optional —
    missing values default to neutral 0/1 so the math degrades gracefully):

      - ``current_revenue_share`` or ``current_contribution`` → current_score
      - ``market_space`` × ``success_prob`` × ``time_factor``
        × evidence quality → option_score

    Returns ``(0.0, 0.0)`` for a fresh / empty node so callers can still add
    these into a sum without polluting it.
    """

    value = node.get("value") or {}
    if not isinstance(value, Mapping):
        value = {}

    def _num(key: str, default: float = 0.0) -> float:
        v = value.get(key)
        if v is None:
            return default
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    current = _num("current_revenue_share", default=_num("current_contribution"))

    market_space = _num("market_space")
    success_prob = _num("success_prob")
    # Time factor: how close the option is to materialising. Default 1.0 so
    # an author who only supplies market_space × success_prob still gets a
    # sensible number.
    time_factor = _num("time_factor", default=1.0)

    eq_raw = value.get("evidence_quality") or node.get("evidence_quality")
    if isinstance(eq_raw, str):
        eq = EVIDENCE_QUALITY_MAP.get(eq_raw.strip().lower(), EVIDENCE_QUALITY_MAP["medium"])
    else:
        try:
            eq = float(eq_raw) if eq_raw is not None else 0.0
        except (TypeError, ValueError):
            eq = 0.0

    option = market_space * success_prob * time_factor * eq
    return float(current), float(option)


# ---------------------------------------------------------------------------
# Integration helpers
# ---------------------------------------------------------------------------


def coverage_summary_for_node(
    node: Mapping[str, Any],
    children: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """One-shot coverage report for a parent + its direct children.

    Returns:
        ``{
            "node_id": str | None,            # parent node id (for traceability)
            "dp_id": str | None,
            "data_coverage": float,
            "warning_level": str,
            "n_na": int, "n_unknown": int, "n_inactive": int,
            "n_known": int, "n_optionality": int, "n_low_materiality": int,
            "normalized_weights": {dp_id: weight},
            "n_children": int,
            "n_applicable": int,             # children with state != NA
        }``
    """

    counts = {
        "n_na": 0,
        "n_unknown": 0,
        "n_inactive": 0,
        "n_known": 0,
        "n_optionality": 0,
        "n_low_materiality": 0,
    }
    n_applicable = 0
    for child in children:
        state = classify_missing_state(child)
        if state == "NA":
            counts["n_na"] += 1
            continue
        n_applicable += 1
        if state == "Unknown":
            counts["n_unknown"] += 1
        elif state == "Inactive":
            counts["n_inactive"] += 1
        elif state == "Known":
            counts["n_known"] += 1
        elif state == "Optionality":
            counts["n_optionality"] += 1
        elif state == "LowMateriality":
            counts["n_low_materiality"] += 1

    coverage = compute_data_coverage(children)
    return {
        "node_id": node.get("node_id"),
        "dp_id": node.get("dp_id"),
        "data_coverage": coverage,
        "warning_level": coverage_warning_level(coverage),
        **counts,
        "normalized_weights": renormalize_weights(children),
        "n_children": len(children),
        "n_applicable": n_applicable,
    }


def coverage_summary_for_overlay(overlay_yaml: Mapping[str, Any]) -> dict[str, Any]:
    """Walk an entire stock overlay and emit a per-parent coverage report.

    Returns:
        ``{
            "ts_code": str | None,
            "industry_id": str | None,
            "per_node": [coverage_summary_for_node(...)],
            "overall": {
                "data_coverage": float,        # weighted-avg across all parents
                "warning_level": str,
                "n_parents": int,
                "totals": {n_na, n_unknown, ...},
            },
            "alerts": [
                {"node_id", "dp_id", "warning_level", "data_coverage"}
            ],
        }``
    """

    nodes = list(overlay_yaml.get("nodes") or [])
    by_id: dict[str, Mapping[str, Any]] = {
        str(n.get("node_id")): n for n in nodes if n.get("node_id")
    }

    # children_of maps parent node_id → list of child node payloads.
    children_of: dict[str, list[Mapping[str, Any]]] = {}
    for n in nodes:
        parent = n.get("parent_node")
        if parent is None:
            continue
        children_of.setdefault(str(parent), []).append(n)

    # Also accept explicit `child_nodes` lists on the parent (covers the
    # company node case where parent_node may be null on it but child_nodes
    # enumerates the company subgraph).
    for n in nodes:
        explicit = n.get("child_nodes") or []
        if not explicit:
            continue
        bucket = children_of.setdefault(str(n.get("node_id")), [])
        existing_ids = {str(c.get("node_id")) for c in bucket}
        for cid in explicit:
            cid_s = str(cid)
            if cid_s in existing_ids:
                continue
            child = by_id.get(cid_s)
            if child is not None:
                bucket.append(child)
                existing_ids.add(cid_s)

    per_node: list[dict[str, Any]] = []
    totals = {
        "n_na": 0,
        "n_unknown": 0,
        "n_inactive": 0,
        "n_known": 0,
        "n_optionality": 0,
        "n_low_materiality": 0,
    }
    weighted_coverage_num = 0.0
    weighted_coverage_den = 0.0

    for parent_id, kids in children_of.items():
        if not kids:
            continue
        parent = by_id.get(parent_id, {"node_id": parent_id})
        summary = coverage_summary_for_node(parent, kids)
        per_node.append(summary)
        for k in totals:
            totals[k] += summary[k]
        # Weight each parent's coverage by its number of applicable children
        # for the overall rollup.
        weight = float(summary["n_applicable"])
        if weight > 0:
            weighted_coverage_num += summary["data_coverage"] * weight
            weighted_coverage_den += weight

    overall_cov = (
        weighted_coverage_num / weighted_coverage_den
        if weighted_coverage_den > 0
        else 0.0
    )
    alerts = [
        {
            "node_id": s["node_id"],
            "dp_id": s["dp_id"],
            "warning_level": s["warning_level"],
            "data_coverage": s["data_coverage"],
        }
        for s in per_node
        if s["warning_level"] != "ok"
    ]

    return {
        "ts_code": overlay_yaml.get("ts_code"),
        "industry_id": overlay_yaml.get("industry_id"),
        "per_node": per_node,
        "overall": {
            "data_coverage": overall_cov,
            "warning_level": coverage_warning_level(overall_cov),
            "n_parents": len(per_node),
            "totals": totals,
        },
        "alerts": alerts,
    }


__all__ = [
    "EVIDENCE_QUALITY_MAP",
    "LOW_MATERIALITY_THRESHOLD",
    "LOW_CONFIDENCE_THRESHOLD",
    "NO_STRONG_CONCLUSION_THRESHOLD",
    "classify_missing_state",
    "compute_data_coverage",
    "renormalize_weights",
    "propagate_confidence",
    "adjust_path_score",
    "handle_optionality",
    "coverage_warning_level",
    "coverage_summary_for_node",
    "coverage_summary_for_overlay",
]
