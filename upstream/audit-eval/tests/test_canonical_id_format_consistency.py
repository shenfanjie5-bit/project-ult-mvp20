"""Cross-case canonical_entity_id format guard.

Reconciliation guard added in audit-eval v0.2.4.

Pre-v0.2.4 the shared cases had a doc/code drift: case_001 and
case_fuzzy_alias_simple used ``ENT_STOCK_<symbol>_<exchange>``
(underscore) while the live entity-registry runtime
``generate_stock_entity_id(ts_code) = f'ENT_STOCK_{ts_code}'`` produces
the dot form ``ENT_STOCK_<symbol>.<exchange>``. Phase B added 2 new
tushare-derived cases that adopted the runtime format ahead of the
older cases, leaving an inconsistent fixture corpus where 2 cases
were runtime-aligned and 3 cases (case_001, case_fuzzy_alias_simple,
case_ex3_negative) were not.

v0.2.4 reconciles all 5 cases to the runtime format. THIS TEST
prevents future regression — every shared case in every pack must
carry only dot-form ENT_STOCK_* IDs. If a future PR adds a new case
or modifies an existing one with the underscore form, this test
fails loudly with the offending case + field path + value.

The guard is generic: it walks the full payload tree of every case
in every pack, so it covers cases shipped under any new pack added
later (no per-case maintenance needed).
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from audit_eval_fixtures import iter_cases, list_packs, load_case


#: Underscore-form ID pattern that this guard explicitly REJECTS.
#: Matches ``ENT_STOCK_300750_SZ``, ``ENT_STOCK_03750_HK``, etc.
_DEPRECATED_UNDERSCORE_FORM = re.compile(
    r"\bENT_STOCK_\d+_(SZ|SH|BJ|HK)\b"
)


def _walk_strings(payload: Any, path: str = "") -> list[tuple[str, str]]:
    """Yield ``(json_path, string_value)`` for every string leaf in a
    nested dict/list payload. Used to scan fixture payloads exhaustively
    without hard-coding which fields hold canonical IDs (a new field
    name introduced later is automatically covered)."""

    found: list[tuple[str, str]] = []
    if isinstance(payload, str):
        found.append((path or "<root>", payload))
    elif isinstance(payload, dict):
        for key, value in payload.items():
            found.extend(_walk_strings(value, f"{path}.{key}" if path else key))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            found.extend(_walk_strings(item, f"{path}[{index}]"))
    return found


def _all_case_refs() -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for pack_name in list_packs():
        for ref in iter_cases(pack_name):
            refs.append((ref.pack_name, ref.case_id))
    return refs


@pytest.mark.parametrize(
    "pack_name, case_id",
    _all_case_refs(),
    ids=lambda v: v if isinstance(v, str) else "_",
)
def test_no_case_carries_deprecated_underscore_canonical_id_form(
    pack_name: str, case_id: str
) -> None:
    """For each shared case, walk every payload section (input, context,
    expected, manifest_refs, metadata) and assert no string value
    matches the deprecated underscore canonical-id form. Any match
    means the fixture has regressed away from the runtime-aligned
    project-wide convention reconciled in v0.2.4."""

    case = load_case(pack_name, case_id)

    offences: list[tuple[str, str, str]] = []
    for section in ("input", "context", "expected", "manifest_refs", "metadata"):
        payload = getattr(case, section)
        for json_path, value in _walk_strings(payload, section):
            if _DEPRECATED_UNDERSCORE_FORM.search(value):
                offences.append((section, json_path, value))

    assert not offences, (
        f"case {pack_name}/{case_id} carries deprecated underscore canonical "
        f"ENT_STOCK_*_<exchange> id form (project-wide convention since "
        f"v0.2.4 is the dot form ENT_STOCK_*.<exchange>, matching the live "
        f"entity-registry runtime generate_stock_entity_id). Offending "
        f"locations:\n"
        + "\n".join(
            f"  {section}: {path} = {value!r}"
            for section, path, value in offences
        )
    )


def test_at_least_one_case_per_pack_exists() -> None:
    """Sanity: the parametrized guard above is meaningful only if every
    pack actually contains cases. If a future cleanup empties a pack,
    the guard becomes silently vacuous; this test catches that."""

    packs = list_packs()
    assert packs, "no fixture packs found — fixture corpus is empty"
    for pack_name in packs:
        cases = list(iter_cases(pack_name))
        assert cases, f"pack {pack_name!r} contains no cases — guard would be vacuous"
