#!/usr/bin/env python3
"""Apply a yaml patch (list of node updates) onto an overlay yaml.

Patch format::

    nodes:
      - dp_id: L1.role.tag
        data_status: Known
        value: {...}
        confidence: 0.7
        evidence_sources: [...]
        source_fingerprint_at_fill: <hex>
        last_filled_period: "2026Q1"
        last_event_id: null

For each patch entry, match the overlay yaml node by dp_id and merge.
Reports updated / unmatched counts and exits 0 on success.

Robust to mildly malformed patches:
- ignores unknown top-level keys (everything outside ``nodes:``)
- ignores patch entries without a ``dp_id``
- preserves any overlay-level fields the patch doesn't touch
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mvp20 import schema_validator  # noqa: E402

FORMULA_TEXT = (
    "Direction × Event Strength × Transmission Strength × Company Exposure × "
    "Business Share × Profit Sensitivity × Confidence × Time Factor × Surprise × "
    "Funding Amplifier - Priced-in Discount - Risk Discount"
)
EVIDENCE_QUALITY_VALUES = frozenset({"low", "medium", "high"})

WHITELIST_KEYS = frozenset({
    "status",
    "data_status",
    "value",
    "confidence",
    "evidence_quality",
    "evidence_sources",
    "source_fingerprint_at_fill",
    "last_filled_period",
    "last_event_id",
    "last_updated",
    "missing_reason",
    "data_coverage",
    "strength",
    "priced_in",
    "exposure",
    "financial_sensitivity",
    "valuation_sensitivity",
    "trigger_condition",
    "invalidation_condition",
    "data_source",
    "related_business",
    "related_metrics",
})


def _dump_overlay_yaml(overlay: dict) -> str:
    """Dump overlays with a wide line width to avoid wrapping formula strings."""

    text = yaml.safe_dump(
        overlay,
        allow_unicode=True,
        sort_keys=False,
        width=10000,
    )
    return text.replace(
        "formula: Direction × Event Strength × Transmission Strength × Company Exposure × Business Share × Profit Sensitivity ×\n"
        "      Confidence × Time Factor × Surprise × Funding Amplifier - Priced-in Discount - Risk Discount",
        f"formula: {FORMULA_TEXT}",
    )


def _validate_patch_node_metadata(patch_node: dict) -> list[str]:
    """Validate patch-level metadata that value-schema checks do not cover."""

    errors: list[str] = []
    if "evidence_quality" in patch_node:
        value = patch_node.get("evidence_quality")
        if value is not None and not isinstance(value, str):
            errors.append(
                "evidence_quality must be one of low/medium/high as a string "
                f"(got {type(value).__name__})"
            )
        elif isinstance(value, str) and value not in EVIDENCE_QUALITY_VALUES:
            errors.append(
                "evidence_quality must be one of low/medium/high "
                f"(got {value!r})"
            )
    return errors


def _salvage_apply(overlay: dict, overlay_path: Path,
                   patch_raw: str) -> tuple[int, int]:
    """Parse the patch entry-by-entry, skipping any block that fails yaml.

    The minimax model occasionally emits unescaped double-quotes inside
    a quoted string (e.g. ``"全球'2+2'格局"`` → ``"全球"2+2"格局"``)
    which kills full-document parsing. This salvage path splits on the
    top-level ``  - dp_id:`` marker and tries each chunk standalone, so
    one bad node doesn't prevent the other ~49 from being applied.
    """
    import re
    nodes_by_dp: dict[str, dict] = {}
    for n in overlay.get("nodes") or []:
        dp = n.get("dp_id")
        if dp:
            nodes_by_dp[dp] = n

    # Split into chunks on lines that start a new top-level patch node.
    # Indent level: 2 spaces, then "- dp_id:"
    chunks: list[str] = []
    current: list[str] = []
    for line in patch_raw.splitlines():
        if re.match(r"^\s{2}- dp_id:\s*", line):
            if current:
                chunks.append("\n".join(current))
            current = [line]
        else:
            if current:
                current.append(line)
    if current:
        chunks.append("\n".join(current))

    updated, unmatched, parse_failed = 0, 0, 0
    for chunk in chunks:
        # Wrap as a single-entry mini patch and try to parse
        mini = "nodes:\n" + chunk
        try:
            parsed = yaml.safe_load(mini)
        except yaml.YAMLError:
            parse_failed += 1
            continue
        if not isinstance(parsed, dict):
            parse_failed += 1
            continue
        for patch_node in (parsed.get("nodes") or []):
            if not isinstance(patch_node, dict):
                continue
            dp = patch_node.get("dp_id")
            if not dp:
                continue
            if dp in nodes_by_dp:
                target = nodes_by_dp[dp]
                for k, v in patch_node.items():
                    if k == "dp_id":
                        continue
                    if k in WHITELIST_KEYS:
                        target[k] = v
                updated += 1
            else:
                unmatched += 1

    overlay_path.write_text(_dump_overlay_yaml(overlay), encoding="utf-8")
    print(f"  salvage: parsed {len(chunks) - parse_failed}/{len(chunks)} "
          f"chunks; {parse_failed} parse_failed", file=sys.stderr)
    return updated, unmatched


def _validate_patch_node_schemas(
    patch_nodes: list,
    *,
    strict: bool,
) -> dict[str, list[str]]:
    """Run schema_validator.validate_overlay_node over each patch entry.

    Returns ``{dp_id: [errors]}`` for nodes with schema violations. In
    strict mode, ``[warn]``-prefixed lines from the validator are
    promoted into hard errors (callers reject the whole patch). In
    non-strict mode, they remain in the output but are treated as
    advisory warnings.
    """

    errors_by_dp: dict[str, list[str]] = {}
    for patch_node in patch_nodes:
        if not isinstance(patch_node, dict):
            continue
        dp = patch_node.get("dp_id")
        if not dp:
            continue
        errs = schema_validator.validate_overlay_node(patch_node, strict=strict)
        if strict:
            errs.extend(_validate_patch_node_metadata(patch_node))
        if errs:
            errors_by_dp[dp] = errs
    return errors_by_dp


def apply_patch(
    overlay_path: Path,
    patch_path: Path,
    *,
    strict_schema: bool = False,
    log_violations: bool = True,
) -> tuple[int, int, dict[str, list[str]]]:
    """Apply patch to overlay. Returns ``(n_updated, n_unmatched, schema_errors)``.

    Fix B (B3): each patch node is validated against
    ``mvp20.schema_validator.DP_SCHEMA``. When ``strict_schema=True``,
    any node with schema errors is REJECTED — the overlay is not
    rewritten, and the caller gets a non-empty ``schema_errors`` dict so
    the upstream pipeline (codex_dispatch.sh / run_ab_test.sh) can
    decide whether to retry or escalate.

    With ``strict_schema=False`` (default for backward compat), schema
    drift is logged but still applied — preserves the previous behaviour
    so this can be enabled gradually without breaking existing pipelines.
    """

    overlay = yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
    patch_raw = patch_path.read_text(encoding="utf-8")
    try:
        patch = yaml.safe_load(patch_raw)
    except yaml.YAMLError as e:
        # First-line root cause goes to stderr; attempt salvage by
        # parsing each top-level ``- dp_id:`` block independently so a
        # single malformed entry doesn't sink the whole patch.
        print(f"WARN: yaml parse failed ({e.__class__.__name__}); "
              f"attempting per-entry salvage", file=sys.stderr)
        u, n = _salvage_apply(overlay, overlay_path, patch_raw)
        return u, n, {}

    if not isinstance(patch, dict):
        print(f"ERROR: patch is not a dict (got {type(patch).__name__})",
              file=sys.stderr)
        return 0, 0, {}

    nodes_by_dp: dict[str, dict] = {}
    for n in overlay.get("nodes") or []:
        dp = n.get("dp_id")
        if dp:
            nodes_by_dp[dp] = n

    patch_nodes = patch.get("nodes") or []
    if not isinstance(patch_nodes, list):
        print(f"ERROR: patch.nodes is not a list", file=sys.stderr)
        return 0, 0, {}

    # Fix B (B3): pre-flight schema validation. Run BEFORE mutating
    # nodes_by_dp so a strict reject doesn't leave the overlay partly
    # updated.
    schema_errors = _validate_patch_node_schemas(
        patch_nodes, strict=strict_schema,
    )
    # In non-strict mode, drop [warn]-prefixed lines from blocking. We
    # only block on hard errors there.
    if strict_schema and schema_errors:
        print(
            f"REJECTED {len(schema_errors)} nodes with schema errors "
            f"(strict_schema=True):",
            file=sys.stderr,
        )
        for dp, errs in schema_errors.items():
            print(f"  {dp}: {errs}", file=sys.stderr)
        return 0, 0, schema_errors

    if log_violations and schema_errors:
        # Strip [warn] prefix from advisory-only display to avoid double
        # logging while still flagging the problem.
        n_warn = sum(
            1
            for errs in schema_errors.values()
            if all(e.startswith("[warn]") for e in errs)
        )
        n_err = len(schema_errors) - n_warn
        print(
            f"WARN: {len(schema_errors)} schema violation(s) "
            f"({n_err} hard + {n_warn} warn); use --strict-schema to reject. "
            f"Showing first 5:",
            file=sys.stderr,
        )
        for dp, errs in list(schema_errors.items())[:5]:
            print(f"  {dp}: {errs}", file=sys.stderr)

    updated, unmatched = 0, 0
    for patch_node in patch_nodes:
        if not isinstance(patch_node, dict):
            continue
        dp = patch_node.get("dp_id")
        if not dp:
            continue
        if dp in nodes_by_dp:
            target = nodes_by_dp[dp]
            for k, v in patch_node.items():
                if k == "dp_id":
                    continue
                # Apply whitelisted keys only — protects schema fields like
                # node_id, parent_node, child_nodes, required_level, etc.
                if k in WHITELIST_KEYS:
                    target[k] = v
            updated += 1
        else:
            unmatched += 1

    overlay_path.write_text(_dump_overlay_yaml(overlay), encoding="utf-8")
    return updated, unmatched, schema_errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("overlay")
    parser.add_argument("patch")
    parser.add_argument(
        "--strict-schema",
        action="store_true",
        help=(
            "Reject the entire patch if any node fails schema validation "
            "against mvp20.schema_validator.DP_SCHEMA. Default off — schema "
            "drift is logged but applied (backward compat). Turn on once "
            "the LLM is reliably emitting spec'd output."
        ),
    )
    args = parser.parse_args()
    u, n, schema_errors = apply_patch(
        Path(args.overlay),
        Path(args.patch),
        strict_schema=args.strict_schema,
    )
    print(f"updated {u} nodes, unmatched {n}")
    if schema_errors:
        # Filter out pure-warn entries from the exit-code path.
        hard = [
            dp
            for dp, errs in schema_errors.items()
            if any(not e.startswith("[warn]") for e in errs)
        ]
        print(
            f"schema warnings: {len(schema_errors)} dp_id(s) "
            f"({len(hard)} hard)",
        )
        if args.strict_schema and hard:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
