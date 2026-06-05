"""Build the 同花顺 (THS) L2-industry → 12-theme classification artifacts.

Outputs (both are committed config, the permanent classification path that
``mvp20.onboard.recognize`` consults for A-shares before the legacy tushare map):

* ``config/ths_industry_map.yaml``   — THS L2 industry name → single theme
  (a 1:1 reversal of the frozen manifest's ``theme_to_ths_industries``; the THS
  L2 taxonomy partitions stocks so there is no name→theme ambiguity).
* ``config/ths_industry_members.json`` — ts_code → {ths_industry, theme}, the
  reverse membership index built by calling ``pro.ths_member`` for each mapped
  THS L2 index (881xxx.TI series). This is what lets recognize() resolve a raw
  A-share code to its THS industry (and hence theme) offline.

The script is idempotent and re-runnable; it is also the back-end for the
on-demand refresh path (``mvp20.onboard`` calls ``refresh_members_index`` when a
code misses the cached index). tushare calls are throttled.

Usage:
    python scripts/build_ths_classification.py            # build both artifacts
    python scripts/build_ths_classification.py --map-only # only the yaml (no net)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # so `from mvp20...` works when run as a script
MANIFEST_PATH = ROOT / "config" / "bulk_onboard_a_share_ths.json"
MAP_PATH = ROOT / "config" / "ths_industry_map.yaml"
MEMBERS_PATH = ROOT / "config" / "ths_industry_members.json"

_THROTTLE_S = 0.4  # between ths_member calls — stay well under tushare limits


def build_map(manifest_path: Path = MANIFEST_PATH) -> dict[str, str]:
    """Reverse ``theme_to_ths_industries`` → {ths_industry_name: theme}.

    Raises ValueError if a THS industry maps to more than one theme (the THS L2
    taxonomy is a partition, so this should never happen — fail loud if it does).
    """
    man = json.loads(manifest_path.read_text(encoding="utf-8"))
    t2i = man["theme_to_ths_industries"]
    ind2theme: dict[str, str] = {}
    clashes: dict[str, list[str]] = defaultdict(list)
    for theme, inds in t2i.items():
        for ind in inds:
            if ind in ind2theme and ind2theme[ind] != theme:
                clashes[ind].append(theme)
            ind2theme[ind] = theme
    if clashes:
        raise ValueError(f"THS industry → multiple themes (ambiguous): {dict(clashes)}")
    return ind2theme


def write_map(ind2theme: dict[str, str], out: Path = MAP_PATH) -> None:
    doc = {
        "schema_version": 1,
        "purpose": "同花顺二级行业名 → 12 主题(单一归属)。recognize() 对 A 股优先用此路径。",
        "source": "reverse of config/bulk_onboard_a_share_ths.json theme_to_ths_industries",
        "taxonomy": "同花顺二级行业 (ths_index type=I, 881xxx series)",
        "mappings": dict(sorted(ind2theme.items())),
    }
    out.write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )


def _ths_name_to_code(pro) -> dict[str, str]:
    """{industry_name: 881xxx.TI} for THS L2 industries (type=I, 881 series)."""
    df = pro.ths_index()
    out: dict[str, str] = {}
    if df is None or not len(df):
        return out
    for rec in df.to_dict(orient="records"):
        code = str(rec.get("ts_code", ""))
        typ = str(rec.get("type", ""))
        name = rec.get("name")
        if typ == "I" and code.startswith("881") and name:
            out[name] = code
    return out


def refresh_members_index(
    industries: list[str] | None = None,
    *,
    out: Path = MEMBERS_PATH,
    throttle_s: float = _THROTTLE_S,
) -> dict[str, dict]:
    """Build/refresh ts_code → {ths_industry, theme} by pulling ths_member for
    each mapped THS L2 industry. Returns the index dict and writes it to ``out``.

    ``industries`` defaults to all 62 industries in the map. tushare is imported
    lazily so ``--map-only`` and unit tests never need a token.
    """
    from mvp20.sources import tushare_source as ts

    ind2theme = build_map()
    if industries is None:
        industries = sorted(ind2theme.keys())

    pro = ts._get_pro_api()
    if pro is None:
        raise RuntimeError("tushare _get_pro_api() returned None (token/network)")

    name2code = _ths_name_to_code(pro)
    missing_codes = [n for n in industries if n not in name2code]
    if missing_codes:
        print(f"WARN: {len(missing_codes)} industry names not found in ths_index: {missing_codes}")

    index: dict[str, dict] = {}
    dup_codes: dict[str, list[str]] = defaultdict(list)
    for i, name in enumerate(industries):
        code = name2code.get(name)
        if not code:
            continue
        df = pro.ths_member(ts_code=code)
        rows = df.to_dict(orient="records") if df is not None and len(df) else []
        for rec in rows:
            con = str(rec.get("con_code", "")).upper()
            if not con:
                continue
            if con in index and index[con]["ths_industry"] != name:
                dup_codes[con].append(name)
            index[con] = {"ths_industry": name, "theme": ind2theme[name]}
        print(f"[{i+1}/{len(industries)}] {name} ({code}): {len(rows)} members")
        if i + 1 < len(industries):
            time.sleep(throttle_s)

    if dup_codes:
        # THS L2 should partition; report but keep last-write. Caller can inspect.
        print(f"WARN: {len(dup_codes)} codes appeared in >1 industry: {dict(list(dup_codes.items())[:10])}")

    payload = {
        "schema_version": 1,
        "purpose": "ts_code → {ths_industry, theme}. recognize() A-share 反查索引。",
        "source": "pro.ths_member per THS L2 index (881xxx.TI)",
        "count": len(index),
        "members": index,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return index


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map-only", action="store_true", help="only write the yaml map (no tushare)")
    args = ap.parse_args()

    ind2theme = build_map()
    write_map(ind2theme)
    print(f"wrote {MAP_PATH.relative_to(ROOT)}: {len(ind2theme)} industries → "
          f"{len(set(ind2theme.values()))} themes")

    if args.map_only:
        return
    index = refresh_members_index(sorted(ind2theme.keys()))
    print(f"wrote {MEMBERS_PATH.relative_to(ROOT)}: {len(index)} member codes")


if __name__ == "__main__":
    main()
