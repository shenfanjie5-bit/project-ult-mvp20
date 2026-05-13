"""audit-eval shared fixtures package.

Distributed *with* ``project-ult-audit-eval`` (not as a separate distribution).
Other project-ult modules consume this package to wire fixture-backed
regression tests against a single source of truth — see
``SUBPROJECT_TESTING_STANDARD.md`` §5.

Usage:

    from audit_eval_fixtures import iter_cases, load_case

    for ref in iter_cases("minimal_cycle"):
        case = load_case(ref.pack_name, ref.case_id)
        actual = my_unit_under_test(case.input, case.context)
        assert actual == case.expected, (
            f"{ref.case_id}: drift detected (golden updated {case.metadata['golden_updated_at']})"
        )

Public packs (see ``data/``):
    - ``minimal_cycle``         — minimal daily cycle baseline
    - ``event_cases``           — event/entity/candidate boundary cases
    - ``historical_replay_pack``— historical replay & regression baseline
"""

from __future__ import annotations

from audit_eval_fixtures._impl import (
    FixtureError,
    fixture_root,
    fixture_version,
    iter_cases,
    list_packs,
    load_case,
)
from audit_eval_fixtures._models import Case, CaseRef

__all__ = [
    "Case",
    "CaseRef",
    "FixtureError",
    "fixture_root",
    "fixture_version",
    "iter_cases",
    "list_packs",
    "load_case",
]
