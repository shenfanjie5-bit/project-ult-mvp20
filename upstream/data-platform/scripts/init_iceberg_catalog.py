#!/usr/bin/env python3
"""Initialize the PG-backed Iceberg SQL catalog namespaces."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_platform.serving.catalog import (  # noqa: E402
    DEFAULT_NAMESPACES,
    ensure_namespaces,
    load_catalog,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialize data-platform Iceberg catalog namespaces."
    )
    parser.parse_args(argv)

    try:
        catalog = load_catalog()
        ensure_namespaces(catalog, DEFAULT_NAMESPACES)
    except Exception as exc:
        print(f"failed to initialize Iceberg catalog: {exc}", file=sys.stderr)
        return 1

    print("initialized Iceberg namespaces: " + ", ".join(DEFAULT_NAMESPACES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
