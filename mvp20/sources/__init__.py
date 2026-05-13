"""Real-data source adapters used by ``scripts/collector.py``.

Each module exposes ``fetch_batch(constituents, tick) -> list[Row]`` where
``Row`` is the 7-tuple ``(ts_code, dp_id, value, data_status, confidence,
source, updated_at)`` understood by ``mvp20.storage.upsert_realtime``.

- ``futu_source``  : HK / US tickers via locally-running Futu OpenD daemon
- ``tushare_source``: A-share tickers via Tushare pro HTTP API
- (mock source remains inline in ``scripts/collector.py:fetch_mock_batch``)
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(env_path: Path | None = None) -> dict[str, str]:
    """Tiny .env loader (no python-dotenv dep). Reads KEY=VALUE lines, injects
    into ``os.environ`` if not already set, and returns the parsed dict.

    Handles: blank lines, ``#`` comments, optional surrounding quotes. Does
    NOT support multi-line values or variable interpolation. Idempotent.
    """

    if env_path is None:
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    out: dict[str, str] = {}
    if not env_path.exists():
        return out
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        out[key] = val
        os.environ.setdefault(key, val)
    return out


__all__ = ["load_dotenv"]
