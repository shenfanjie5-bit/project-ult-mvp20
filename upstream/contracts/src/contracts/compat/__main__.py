"""JSON Schema 兼容性检查 CLI 入口。"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from contracts.compat import CompatibilityCheckResult, check_compatibility
from contracts.errors import ErrorCode


def build_parser() -> argparse.ArgumentParser:
    """创建兼容性检查命令行解析器。"""

    parser = argparse.ArgumentParser(
        prog="contracts-compat",
        description="Check backward compatibility between JSON Schema exports.",
    )
    parser.add_argument(
        "--baseline",
        required=True,
        help="Baseline JSON Schema export directory, or checked-in baseline version.",
    )
    parser.add_argument(
        "--current",
        default="HEAD",
        help=(
            "Current JSON Schema export directory, checked-in baseline version, "
            "or HEAD to export current source."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for machine-readable JSON result.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """运行兼容性检查 CLI，并返回进程退出码。"""

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1

    try:
        result = check_compatibility(args.baseline, args.current)
        if args.output is not None:
            _write_result(args.output, result)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if result.is_compatible:
        return 0

    breaking_events = [event for event in result.events if event.breaking]
    print(
        f"[{ErrorCode.INCOMPATIBLE_CONTRACT_CHANGE.value}] "
        f"{len(breaking_events)} breaking change(s) detected",
        file=sys.stderr,
    )
    for event in breaking_events:
        json_pointer = event.json_pointer or "<root>"
        print(
            f"- {event.schema_name} {json_pointer} "
            f"{event.change_type}: {event.message}",
            file=sys.stderr,
        )
    return 1


def _write_result(output_path: Path, result: CompatibilityCheckResult) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
