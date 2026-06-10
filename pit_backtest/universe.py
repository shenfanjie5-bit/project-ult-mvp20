"""A-share universe loading for the PIT backtest.

The pool is the 116 A-share (.SH/.SZ/.BJ) constituents of
``config/mvp20.universe.yaml`` — today's thematically-selected leaders. This is
a *survivorship-biased* set (no delisted names); the backtest report flags this
prominently. HK/US listings are excluded (A-share scope only).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_DEFAULT = Path("config/mvp20.universe.yaml")
_A_SUFFIXES = (".SH", ".SZ", ".BJ")


def load_ashare_universe(path: str | Path = _DEFAULT) -> list[dict[str, Any]]:
    """Return [{ts_code, name, industry_ids, primary_industry}] for A-shares."""

    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    out: list[dict[str, Any]] = []
    for c in data.get("constituents", []) or []:
        ts = str(c.get("ts_code", ""))
        if not ts.endswith(_A_SUFFIXES):
            continue
        inds = list(c.get("industry_ids") or [])
        out.append(
            {
                "ts_code": ts,
                "name": c.get("name"),
                "industry_ids": inds,
                "primary_industry": inds[0] if inds else None,
            }
        )
    return out


def ashare_codes(path: str | Path = _DEFAULT) -> list[str]:
    return [u["ts_code"] for u in load_ashare_universe(path)]


def primary_industry_map(path: str | Path = _DEFAULT) -> dict[str, str | None]:
    return {u["ts_code"]: u["primary_industry"] for u in load_ashare_universe(path)}
