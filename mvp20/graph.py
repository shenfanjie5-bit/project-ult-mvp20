"""Industry causal graph schema and validators (v3.1.1 + 4 views).

Each industry owns one ``industry_graphs/<slug>.yaml`` file describing:

1. ``priors``: industry-level prior parameter pack (16 sections from v3.1
   template — boundary / state probabilities / shock model / path dedup
   groups / exposure / financial vector / valuation mix / tail risk /
   validation signals / falsification / tradability panel / workflow /
   one-line summary).
2. ``nodes``: nodes of the causal graph appearing in this industry. Node
   ids are globally unique across all industry graph files; the same id
   may appear in multiple files (cross-industry sharing) provided the
   declarations agree on ``label_cn``, ``layer`` and ``type``. Only
   ``industry_tags`` are merged as a union.
3. ``edges``: edges with ``polarity``, ``beta_positive``, ``beta_negative``,
   ``threshold``, ``lag``, ``dedup_group`` and a non-empty ``views`` list.
4. ``views``: four required render views — causal_propagation, core_factor,
   supply_chain, risk — that filter the underlying nodes/edges.

Walk-through fixtures live under ``industry_graphs/fixtures/*.yaml`` and
reference node/edge ids declared in industry graphs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------


class NodeLayer(str, Enum):
    EVENT = "event"
    INDUSTRY_SIGNAL = "industry_signal"
    FINANCIAL = "financial"
    VALUATION = "valuation"
    STOCK = "stock"
    RISK = "risk"
    SUPPLY_CHAIN = "supply_chain"


class Polarity(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"


VALID_DEDUP_GROUPS: frozenset[str] = frozenset(
    {
        # Core 8 groups (v3.1 §6 main groups)
        "需求组",
        "价格组",
        "成本组",
        "政策组",
        "技术组",
        "竞争组",
        "资金组",
        "风险组",
        # Extended groups used by individual industries
        "供给组",
        "盈利组",
        "事件组",
        "叙事组",
        "质量组",
        "信用组",
        "库存组",
        "估值组",
    }
)

VALID_STATE_NAMES: frozenset[str] = frozenset(
    {"强多头", "温和多头", "结构分化", "杀估值", "等待验证"}
)

VALID_VIEW_IDS: frozenset[str] = frozenset(
    {"causal_propagation", "core_factor", "supply_chain", "risk"}
)


NODE_ID_PREFIXES: frozenset[str] = frozenset(
    {"EVENT", "SIGNAL", "FIN", "VAL", "RISK", "STATE", "COMPANY", "SUPPLY"}
)

NODE_ID_RE = re.compile(r"^([A-Z][A-Z0-9]*)\.[A-Za-z0-9_.]+$")

PROBABILITY_TOLERANCE = 1e-2


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndustryGraphValidationResult:
    ok: bool
    industry_id: str
    graph_status: str
    node_count: int
    edge_count: int
    view_keys: tuple[str, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class IndustryGraphSetValidationResult:
    ok: bool
    industry_graph_count: int
    graph_status_pending: tuple[str, ...]
    total_nodes: int
    total_edges: int
    unique_nodes_across_graphs: int
    walkthroughs_validated: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WalkthroughValidationResult:
    ok: bool
    fixture_id: str
    errors: tuple[str, ...]


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: file must be a YAML object")
    return payload


def _string(value: object) -> str:
    return "" if value is None else str(value).strip()


# ---------------------------------------------------------------------------
# Single-graph validation
# ---------------------------------------------------------------------------


def validate_industry_graph(
    path: Path,
    *,
    valid_industry_ids: set[str] | None = None,
    expected_graph_status: dict[str, str] | None = None,
) -> IndustryGraphValidationResult:
    """Validate a single ``industry_graphs/<slug>.yaml`` file.

    The validation is intra-graph only: it does not check cross-graph node id
    consistency or unresolved edge references that point to other industry
    graphs. Use ``validate_industry_graph_set`` for whole-set validation.
    """

    errors: list[str] = []
    warnings: list[str] = []

    payload = _load_yaml(path)

    industry_id = _string(payload.get("industry_id"))
    industry_name_cn = _string(payload.get("industry_name_cn"))
    graph_status = _string(payload.get("graph_status")) or "present"

    if not industry_id:
        errors.append("industry_id is required")
    elif valid_industry_ids is not None and industry_id not in valid_industry_ids:
        errors.append(
            f"industry_id {industry_id!r} not declared in industries.yaml"
        )
    if not industry_name_cn:
        errors.append("industry_name_cn is required")
    if graph_status not in {"present", "pending"}:
        errors.append(
            f"graph_status must be 'present' or 'pending'; got {graph_status!r}"
        )
    if (
        expected_graph_status is not None
        and industry_id in expected_graph_status
        and expected_graph_status[industry_id] != graph_status
    ):
        errors.append(
            "graph_status mismatch with industries.yaml: "
            f"file says {graph_status!r}, "
            f"industries.yaml says {expected_graph_status[industry_id]!r}"
        )

    schema_version = payload.get("schema_version")
    if schema_version != 1:
        errors.append("schema_version must be 1")

    if graph_status == "pending":
        nodes = payload.get("nodes") or []
        edges = payload.get("edges") or []
        views = payload.get("views") or {}
        if not isinstance(nodes, list):
            errors.append("nodes must be a list")
            nodes = []
        if not isinstance(edges, list):
            errors.append("edges must be a list")
            edges = []
        if not isinstance(views, dict):
            errors.append("views must be a mapping")
            views = {}
        warnings.append("pending graph stub skipped from strict graph validation")
        return IndustryGraphValidationResult(
            ok=not errors,
            industry_id=industry_id,
            graph_status=graph_status,
            node_count=len(nodes),
            edge_count=len(edges),
            view_keys=tuple(sorted(views.keys())),
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    # ---- priors ----
    priors = payload.get("priors")
    if not isinstance(priors, dict):
        errors.append("priors must be a mapping")
        priors = {}
    errors.extend(_validate_priors(priors))

    # ---- nodes ----
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        errors.append("nodes must be a list")
        nodes = []
    seen_node_ids: set[str] = set()
    for index, node in enumerate(nodes, start=1):
        if not isinstance(node, dict):
            errors.append(f"nodes[{index}] must be a mapping")
            continue
        errors.extend(
            _validate_node_fields(node, location=f"nodes[{index}]")
        )
        node_id = _string(node.get("id"))
        if node_id and node_id in seen_node_ids:
            errors.append(
                f"nodes[{index}].id duplicated within graph: {node_id}"
            )
        if node_id:
            seen_node_ids.add(node_id)

    # ---- edges ----
    edges = payload.get("edges")
    if not isinstance(edges, list):
        errors.append("edges must be a list")
        edges = []
    seen_edge_ids: set[str] = set()
    for index, edge in enumerate(edges, start=1):
        if not isinstance(edge, dict):
            errors.append(f"edges[{index}] must be a mapping")
            continue
        errors.extend(
            _validate_edge_fields(edge, location=f"edges[{index}]")
        )
        edge_id = _string(edge.get("id"))
        if edge_id and edge_id in seen_edge_ids:
            errors.append(
                f"edges[{index}].id duplicated within graph: {edge_id}"
            )
        if edge_id:
            seen_edge_ids.add(edge_id)
        # source/target must be declared somewhere; intra-graph existence
        # checked here, cross-graph existence checked by set validator.
        source = _string(edge.get("source"))
        target = _string(edge.get("target"))
        if source and source not in seen_node_ids and source not in {
            _string(n.get("id"))
            for n in nodes
            if isinstance(n, dict)
        }:
            warnings.append(
                f"edges[{index}].source {source!r} not declared locally "
                "(may be a cross-graph reference; will be checked at set level)"
            )
        if target and target not in seen_node_ids and target not in {
            _string(n.get("id"))
            for n in nodes
            if isinstance(n, dict)
        }:
            warnings.append(
                f"edges[{index}].target {target!r} not declared locally "
                "(may be a cross-graph reference; will be checked at set level)"
            )

    # ---- views ----
    views = payload.get("views")
    if not isinstance(views, dict):
        errors.append("views must be a mapping")
        views = {}
    view_keys = tuple(views.keys()) if isinstance(views, dict) else ()
    missing_views = VALID_VIEW_IDS - set(view_keys)
    if missing_views:
        errors.append(
            "views missing required keys: " + ", ".join(sorted(missing_views))
        )
    extra_views = set(view_keys) - VALID_VIEW_IDS
    if extra_views:
        errors.append(
            "views has unknown keys: " + ", ".join(sorted(extra_views))
        )
    for view_key, view_payload in views.items():
        if not isinstance(view_payload, dict):
            errors.append(f"views[{view_key}] must be a mapping")
            continue
        if not _string(view_payload.get("description")):
            errors.append(f"views[{view_key}].description is required")

    return IndustryGraphValidationResult(
        ok=not errors,
        industry_id=industry_id,
        graph_status=graph_status,
        node_count=len(nodes),
        edge_count=len(edges),
        view_keys=tuple(sorted(view_keys)),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _validate_priors(priors: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not priors:
        errors.append("priors is empty")
        return errors

    state_priors = priors.get("state_probabilities")
    if not isinstance(state_priors, list) or len(state_priors) != 5:
        errors.append("priors.state_probabilities must be a list of 5 entries")
    else:
        seen_states: set[str] = set()
        prob_total = 0.0
        for index, state in enumerate(state_priors, start=1):
            if not isinstance(state, dict):
                errors.append(
                    f"priors.state_probabilities[{index}] must be a mapping"
                )
                continue
            name = _string(state.get("name"))
            prob = state.get("probability")
            if name not in VALID_STATE_NAMES:
                errors.append(
                    f"priors.state_probabilities[{index}].name unknown: {name!r}"
                )
            if name in seen_states:
                errors.append(
                    f"priors.state_probabilities[{index}].name duplicated: {name!r}"
                )
            seen_states.add(name)
            if not isinstance(prob, (int, float)) or isinstance(prob, bool):
                errors.append(
                    f"priors.state_probabilities[{index}].probability must be numeric"
                )
                continue
            if not 0.0 <= float(prob) <= 1.0:
                errors.append(
                    f"priors.state_probabilities[{index}].probability out of [0,1]"
                )
            prob_total += float(prob)
        if abs(prob_total - 1.0) > PROBABILITY_TOLERANCE:
            errors.append(
                "priors.state_probabilities probabilities must sum to 1.0 "
                f"(±{PROBABILITY_TOLERANCE}); got {prob_total:.4f}"
            )

    valuation = priors.get("valuation_mix")
    if not isinstance(valuation, dict):
        errors.append("priors.valuation_mix must be a mapping")
    else:
        weights = valuation.get("weights")
        if not isinstance(weights, dict) or not weights:
            errors.append("priors.valuation_mix.weights must be a non-empty mapping")
        else:
            total = 0.0
            for model_name, weight in weights.items():
                if not isinstance(model_name, str) or not model_name.strip():
                    errors.append(
                        "priors.valuation_mix.weights has empty model name"
                    )
                    continue
                if not isinstance(weight, (int, float)) or isinstance(
                    weight, bool
                ):
                    errors.append(
                        f"priors.valuation_mix.weights[{model_name!r}] must be numeric"
                    )
                    continue
                if not 0.0 <= float(weight) <= 1.0:
                    errors.append(
                        f"priors.valuation_mix.weights[{model_name!r}] out of [0,1]"
                    )
                total += float(weight)
            if abs(total - 1.0) > PROBABILITY_TOLERANCE:
                errors.append(
                    "priors.valuation_mix.weights must sum to 1.0 "
                    f"(±{PROBABILITY_TOLERANCE}); got {total:.4f}"
                )

    dedup_groups = priors.get("path_dedup_groups")
    if dedup_groups is not None:
        if not isinstance(dedup_groups, list):
            errors.append("priors.path_dedup_groups must be a list")
        else:
            for index, group in enumerate(dedup_groups, start=1):
                group_str = _string(group)
                if group_str not in VALID_DEDUP_GROUPS:
                    errors.append(
                        f"priors.path_dedup_groups[{index}] unknown: {group_str!r}"
                    )

    # Soft requirements: at least the major narrative fields are present.
    for required in (
        "boundary",
        "shock_model",
        "exposure",
        "financial_vector",
        "tail_risk",
        "validation_signals",
        "falsification",
        "workflow_steps",
        "one_line_summary",
    ):
        if required not in priors:
            errors.append(f"priors.{required} is required")

    return errors


def _validate_node_fields(node: dict[str, Any], *, location: str) -> list[str]:
    errors: list[str] = []
    node_id = _string(node.get("id"))
    if not node_id:
        errors.append(f"{location}.id is required")
    elif not NODE_ID_RE.fullmatch(node_id):
        errors.append(
            f"{location}.id {node_id!r} must match <PREFIX>.<slug>"
        )
    else:
        prefix = node_id.split(".", 1)[0]
        if prefix not in NODE_ID_PREFIXES:
            errors.append(
                f"{location}.id prefix {prefix!r} not in supported set "
                f"({', '.join(sorted(NODE_ID_PREFIXES))})"
            )

    layer = _string(node.get("layer"))
    try:
        NodeLayer(layer)
    except ValueError:
        errors.append(
            f"{location}.layer must be one of "
            f"{', '.join(sorted(member.value for member in NodeLayer))}; "
            f"got {layer!r}"
        )

    if not _string(node.get("type")):
        errors.append(f"{location}.type is required")
    if not _string(node.get("label_cn")):
        errors.append(f"{location}.label_cn is required")

    industry_tags = node.get("industry_tags")
    if not isinstance(industry_tags, list) or not industry_tags:
        errors.append(f"{location}.industry_tags must be a non-empty list")
    else:
        for tag in industry_tags:
            if not isinstance(tag, str) or not tag.strip():
                errors.append(f"{location}.industry_tags has empty entry")

    properties = node.get("properties")
    if properties is not None and not isinstance(properties, dict):
        errors.append(f"{location}.properties must be a mapping if present")

    return errors


def _validate_edge_fields(edge: dict[str, Any], *, location: str) -> list[str]:
    errors: list[str] = []

    if not _string(edge.get("id")):
        errors.append(f"{location}.id is required")
    if not _string(edge.get("source")):
        errors.append(f"{location}.source is required")
    if not _string(edge.get("target")):
        errors.append(f"{location}.target is required")
    if not _string(edge.get("relation")):
        errors.append(f"{location}.relation is required")

    polarity = _string(edge.get("polarity"))
    try:
        Polarity(polarity)
    except ValueError:
        errors.append(
            f"{location}.polarity must be one of "
            f"{', '.join(sorted(member.value for member in Polarity))}; "
            f"got {polarity!r}"
        )

    for beta_field in ("beta_positive", "beta_negative"):
        value = edge.get(beta_field)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"{location}.{beta_field} must be numeric")
            continue
        if not 0.0 <= float(value) <= 2.0:
            errors.append(
                f"{location}.{beta_field} must be within [0, 2]; got {value}"
            )

    dedup_group = _string(edge.get("dedup_group"))
    if dedup_group not in VALID_DEDUP_GROUPS:
        errors.append(
            f"{location}.dedup_group must be one of "
            f"{sorted(VALID_DEDUP_GROUPS)}; got {dedup_group!r}"
        )

    views = edge.get("views")
    if not isinstance(views, list) or not views:
        errors.append(f"{location}.views must be a non-empty list")
    else:
        for view_id in views:
            view_str = _string(view_id)
            if view_str not in VALID_VIEW_IDS:
                errors.append(
                    f"{location}.views contains unknown id {view_str!r}; "
                    f"allowed: {sorted(VALID_VIEW_IDS)}"
                )

    return errors


# ---------------------------------------------------------------------------
# Set-level validation
# ---------------------------------------------------------------------------


def validate_industry_graph_set(
    graphs_dir: Path,
    *,
    valid_industry_ids: set[str],
    industry_graph_status: dict[str, str],
    fixtures_dir: Path | None = None,
) -> IndustryGraphSetValidationResult:
    """Validate every industry graph file in ``graphs_dir`` plus fixtures.

    - ``valid_industry_ids`` and ``industry_graph_status`` come from
      ``mvp20.industries.yaml`` (the manifest validation result).
    - Industries with ``graph_status='pending'`` may have no graph file or a
      minimal pending stub; pending stubs are not counted as active graphs.
    - Cross-graph node id consistency is enforced.
    - Edge source/target ids must resolve to a node declared in any graph.
    - Walk-through fixtures (under ``graphs_dir / 'fixtures'`` or the
      explicit ``fixtures_dir``) must reference declared node/edge ids.
    """

    errors: list[str] = []
    warnings: list[str] = []

    # Discover graph files.
    graph_paths: dict[str, Path] = {}
    for path in sorted(graphs_dir.glob("*.yaml")):
        # Skip fixtures dir; only top-level files map to industries.
        if path.parent == graphs_dir:
            graph_paths[path.stem] = path

    # Pending industries may have no file or a minimal stub; present
    # industries MUST have a full graph file.
    pending_industries = sorted(
        industry_id
        for industry_id, status in industry_graph_status.items()
        if status == "pending"
    )
    for industry_id in pending_industries:
        if industry_id in graph_paths:
            try:
                payload = _load_yaml(graph_paths[industry_id])
                file_status = _string(payload.get("graph_status")) or "present"
            except Exception as exc:  # noqa: BLE001
                file_status = "load_error"
                errors.append(f"{graph_paths[industry_id].name}: load failed: {exc}")
            if file_status != "pending":
                errors.append(
                    f"industry {industry_id} is marked pending but has a non-pending "
                    f"graph file: {graph_paths[industry_id]}"
                )
            else:
                warnings.append(f"industry {industry_id} graph pending stub present")
        else:
            warnings.append(f"industry {industry_id} graph pending")

    for industry_id, status in industry_graph_status.items():
        if status == "present" and industry_id not in graph_paths:
            errors.append(
                f"industry {industry_id} is marked present but has no graph "
                f"file at {graphs_dir / (industry_id + '.yaml')}"
            )

    # Per-file validation + cross-graph aggregation.
    node_declarations: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    edge_ids_seen: set[str] = set()
    total_nodes = 0
    total_edges = 0
    active_graph_count = 0

    for industry_id, path in graph_paths.items():
        single = validate_industry_graph(
            path,
            valid_industry_ids=valid_industry_ids,
            expected_graph_status=industry_graph_status,
        )
        for err in single.errors:
            errors.append(f"{path.name}: {err}")
        for warn in single.warnings:
            warnings.append(f"{path.name}: {warn}")

        if single.graph_status == "pending":
            continue
        active_graph_count += 1

        # Collect node declarations and edges for cross-graph checks.
        try:
            payload = _load_yaml(path)
        except Exception as exc:  # noqa: BLE001 - surface load errors uniformly
            errors.append(f"{path.name}: load failed: {exc}")
            continue
        nodes = payload.get("nodes") or []
        edges = payload.get("edges") or []
        if isinstance(nodes, list):
            total_nodes += len(nodes)
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                node_id = _string(node.get("id"))
                if node_id:
                    node_declarations.setdefault(node_id, []).append(
                        (path.name, node)
                    )
        if isinstance(edges, list):
            total_edges += len(edges)
            for edge in edges:
                if not isinstance(edge, dict):
                    continue
                edge_id = _string(edge.get("id"))
                if edge_id:
                    if edge_id in edge_ids_seen:
                        errors.append(
                            f"edge id {edge_id!r} duplicated across files "
                            f"(latest in {path.name})"
                        )
                    edge_ids_seen.add(edge_id)

    # Cross-graph node id consistency.
    for node_id, declarations in node_declarations.items():
        if len(declarations) <= 1:
            continue
        first_file, first_node = declarations[0]
        first_label = _string(first_node.get("label_cn"))
        first_layer = _string(first_node.get("layer"))
        first_type = _string(first_node.get("type"))
        for file_name, node in declarations[1:]:
            if _string(node.get("label_cn")) != first_label:
                errors.append(
                    f"node {node_id!r} label_cn differs between "
                    f"{first_file} and {file_name}"
                )
            if _string(node.get("layer")) != first_layer:
                errors.append(
                    f"node {node_id!r} layer differs between "
                    f"{first_file} and {file_name}"
                )
            if _string(node.get("type")) != first_type:
                errors.append(
                    f"node {node_id!r} type differs between "
                    f"{first_file} and {file_name}"
                )

    declared_node_ids: set[str] = set(node_declarations.keys())

    # Cross-graph edge endpoint resolution.
    for industry_id, path in graph_paths.items():
        try:
            payload = _load_yaml(path)
        except Exception:
            continue
        edges = payload.get("edges") or []
        if not isinstance(edges, list):
            continue
        for index, edge in enumerate(edges, start=1):
            if not isinstance(edge, dict):
                continue
            for endpoint in ("source", "target"):
                node_id = _string(edge.get(endpoint))
                if node_id and node_id not in declared_node_ids:
                    errors.append(
                        f"{path.name}: edges[{index}].{endpoint} "
                        f"references undeclared node {node_id!r}"
                    )

    # Walk-through fixtures.
    walkthroughs_validated = 0
    fix_dir = fixtures_dir if fixtures_dir is not None else graphs_dir / "fixtures"
    if fix_dir.exists():
        for fixture_path in sorted(fix_dir.glob("*.yaml")):
            result = validate_walkthrough(
                fixture_path,
                declared_node_ids=declared_node_ids,
                declared_edge_ids=edge_ids_seen,
            )
            walkthroughs_validated += 1
            for err in result.errors:
                errors.append(f"{fixture_path.name}: {err}")

    unique_node_count = len(declared_node_ids)

    return IndustryGraphSetValidationResult(
        ok=not errors,
        industry_graph_count=active_graph_count,
        graph_status_pending=tuple(pending_industries),
        total_nodes=total_nodes,
        total_edges=total_edges,
        unique_nodes_across_graphs=unique_node_count,
        walkthroughs_validated=walkthroughs_validated,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def validate_walkthrough(
    path: Path,
    *,
    declared_node_ids: set[str],
    declared_edge_ids: set[str],
) -> WalkthroughValidationResult:
    errors: list[str] = []
    payload = _load_yaml(path)
    fixture_id = _string(payload.get("fixture_id"))
    if not fixture_id:
        errors.append("fixture_id is required")

    given_event = payload.get("given_event")
    if not isinstance(given_event, dict):
        errors.append("given_event must be a mapping")
    else:
        node_id = _string(given_event.get("node_id"))
        if not node_id:
            errors.append("given_event.node_id is required")
        elif node_id not in declared_node_ids:
            errors.append(
                f"given_event.node_id {node_id!r} not declared in any graph"
            )
        surprise = given_event.get("surprise")
        if surprise is not None:
            if not isinstance(surprise, (int, float)) or isinstance(
                surprise, bool
            ):
                errors.append("given_event.surprise must be numeric")
            elif not -1.0 <= float(surprise) <= 1.0:
                errors.append(
                    f"given_event.surprise must be in [-1, 1]; got {surprise}"
                )

    target = payload.get("target")
    if not isinstance(target, dict):
        errors.append("target must be a mapping")
    else:
        node_id = _string(target.get("node_id"))
        if not node_id:
            errors.append("target.node_id is required")
        elif node_id not in declared_node_ids:
            errors.append(
                f"target.node_id {node_id!r} not declared in any graph"
            )

    paths = payload.get("propagation_paths")
    if not isinstance(paths, dict):
        errors.append("propagation_paths must be a mapping")
    else:
        for direction in ("positive", "negative"):
            sequence_list = paths.get(direction)
            if sequence_list is None:
                errors.append(
                    f"propagation_paths.{direction} is required"
                )
                continue
            if not isinstance(sequence_list, list):
                errors.append(
                    f"propagation_paths.{direction} must be a list"
                )
                continue
            for index, entry in enumerate(sequence_list, start=1):
                if not isinstance(entry, dict):
                    errors.append(
                        f"propagation_paths.{direction}[{index}] must be a mapping"
                    )
                    continue
                sequence = entry.get("sequence")
                if not isinstance(sequence, list) or len(sequence) < 2:
                    errors.append(
                        f"propagation_paths.{direction}[{index}].sequence "
                        "must be a list of >= 2 node ids"
                    )
                    sequence = []
                for node_id in sequence:
                    node_id_str = _string(node_id)
                    if node_id_str not in declared_node_ids:
                        errors.append(
                            f"propagation_paths.{direction}[{index}].sequence "
                            f"references undeclared node {node_id_str!r}"
                        )
                edges_used = entry.get("edges_used")
                if edges_used is not None:
                    if not isinstance(edges_used, list):
                        errors.append(
                            f"propagation_paths.{direction}[{index}].edges_used "
                            "must be a list when present"
                        )
                    else:
                        for edge_id in edges_used:
                            if _string(edge_id) not in declared_edge_ids:
                                errors.append(
                                    f"propagation_paths.{direction}[{index}].edges_used "
                                    f"references undeclared edge "
                                    f"{_string(edge_id)!r}"
                                )
                strength = entry.get("aggregate_strength")
                if strength is not None:
                    if not isinstance(strength, (int, float)) or isinstance(
                        strength, bool
                    ):
                        errors.append(
                            f"propagation_paths.{direction}[{index}].aggregate_strength "
                            "must be numeric"
                        )

    verdict = payload.get("verdict")
    if not isinstance(verdict, dict):
        errors.append("verdict must be a mapping")
    else:
        net_dir = _string(verdict.get("net_direction"))
        if net_dir not in {"positive", "negative", "neutral"}:
            errors.append(
                "verdict.net_direction must be one of "
                "{positive, negative, neutral}; got "
                f"{net_dir!r}"
            )

    return WalkthroughValidationResult(
        ok=not errors,
        fixture_id=fixture_id,
        errors=tuple(errors),
    )
