"""JSON Schema 自动导出 CLI 入口。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from contracts.core import __version__
from contracts.export import export_json_schemas


def build_parser() -> argparse.ArgumentParser:
    """创建 JSON Schema 导出命令行解析器。"""

    parser = argparse.ArgumentParser(
        prog="contracts-export",
        description="Export contracts Pydantic models as JSON Schema artifacts.",
    )
    parser.add_argument(
        "--output-dir",
        "--out",
        dest="output_dir",
        type=Path,
        default=Path("artifacts/json_schema"),
        help="Directory for generated JSON Schema files.",
    )
    parser.add_argument(
        "--version",
        default=__version__,
        help="Contract version metadata written into generated schemas.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """运行导出 CLI，并返回进程退出码。"""

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1

    export_json_schemas(args.output_dir, version=args.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
