"""Replay/query smoke against data-platform published cycle snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from audit_eval.audit.query import replay_cycle_object
from audit_eval.audit.real_cycle import build_data_platform_replay_query_context


def run_smoke(cycle_id: str, object_ref: str) -> dict[str, Any]:
    """Read a published cycle manifest and materialize its formal snapshots."""

    context = build_data_platform_replay_query_context(
        cycle_id=cycle_id,
        object_ref=object_ref,
    )
    replay_view = replay_cycle_object(
        cycle_id,
        object_ref,
        context=context,
    ).to_dict()
    replay_view["binding_source"] = "data-platform-published-cycle"
    replay_view["fixture_replay_used"] = False
    replay_view["recommendation_generated"] = False
    return replay_view


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument(
        "--object-ref",
        default="recommendation_snapshot",
        help="Formal object ref published by data-platform, without 'formal.'.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path to write the smoke replay JSON.",
    )
    args = parser.parse_args(argv)

    payload = run_smoke(args.cycle_id, args.object_ref)
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.json_output is None:
        sys.stdout.write(rendered)
        sys.stdout.write("\n")
    else:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
