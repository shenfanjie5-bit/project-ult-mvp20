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


WHITELIST_KEYS = frozenset({
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

    overlay_path.write_text(
        yaml.safe_dump(overlay, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"  salvage: parsed {len(chunks) - parse_failed}/{len(chunks)} "
          f"chunks; {parse_failed} parse_failed", file=sys.stderr)
    return updated, unmatched


def apply_patch(overlay_path: Path, patch_path: Path) -> tuple[int, int]:
    """Apply patch to overlay. Returns (n_updated, n_unmatched)."""
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
        return _salvage_apply(overlay, overlay_path, patch_raw)

    if not isinstance(patch, dict):
        print(f"ERROR: patch is not a dict (got {type(patch).__name__})",
              file=sys.stderr)
        return 0, 0

    nodes_by_dp: dict[str, dict] = {}
    for n in overlay.get("nodes") or []:
        dp = n.get("dp_id")
        if dp:
            nodes_by_dp[dp] = n

    updated, unmatched = 0, 0
    patch_nodes = patch.get("nodes") or []
    if not isinstance(patch_nodes, list):
        print(f"ERROR: patch.nodes is not a list", file=sys.stderr)
        return 0, 0

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

    overlay_path.write_text(
        yaml.safe_dump(overlay, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return updated, unmatched


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("overlay")
    parser.add_argument("patch")
    args = parser.parse_args()
    u, n = apply_patch(Path(args.overlay), Path(args.patch))
    print(f"updated {u} nodes, unmatched {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
