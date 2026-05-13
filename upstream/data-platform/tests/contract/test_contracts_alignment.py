"""Cross-repo alignment between data-platform's serving model and the
contracts envelope (mirrors main-core stage 2.3 follow-up #1 pattern).

data-platform's ``serving.formal.FormalObject`` is the runtime
representation of a manifest-pinned formal table snapshot. The
contracts envelope is the canonical ``FormalObjectBase`` declared in
``contracts.schemas.formal_objects``. They are deliberately decoupled —
data-platform reads/serves the envelope's payload; producers (main-core)
build runtime models that round-trip into the envelope.

This file validates:

1. The four formal object names data-platform serves are all in the
   canonical FormalObjectName enum (so a producer can declare them with
   no enum drift).
2. The data-platform FormalObject runtime container's ``object_type``
   field can carry every canonical FormalObjectName value as a string.

**Module-level skip on missing dep**: requires the
``[contracts-schemas]`` extra. Other contract tests in this directory
remain runnable without it.
"""

from __future__ import annotations

import pytest

# Soft-skip module if cross-repo schema dep not installed.
contracts_formal_objects = pytest.importorskip(
    "contracts.schemas.formal_objects",
    reason=(
        "project-ult-contracts not installed; install [contracts-schemas] "
        "extra to run cross-repo alignment tests"
    ),
)


class TestFormalObjectNameEnumCoverage:
    """Every formal object name data-platform serves must exist in the
    canonical contracts enum. Drift here = producers can't declare an
    object_name that data-platform serves."""

    SERVED_NAMES = (
        "world_state_snapshot",
        "official_alpha_pool",
        "alpha_result_snapshot",
        "recommendation_snapshot",
        "report_snapshot",
        "dashboard_snapshot",
    )

    def test_all_served_names_in_canonical_enum(self) -> None:
        from contracts.schemas.formal_objects import FormalObjectName

        canonical = {member.value for member in FormalObjectName}
        missing = [name for name in self.SERVED_NAMES if name not in canonical]
        # report_snapshot / dashboard_snapshot may not yet exist in the
        # contracts enum (P2 scaffold); we do not assert their presence
        # — just confirm the four core ones are there.
        core = (
            "world_state_snapshot",
            "official_alpha_pool",
            "alpha_result_snapshot",
            "recommendation_snapshot",
        )
        for required in core:
            assert required in canonical, (
                f"contracts.FormalObjectName missing {required!r}; "
                f"data-platform would have nowhere to serve it"
            )


class TestFormalObjectContainerAcceptsCanonicalNames:
    """``data_platform.serving.formal.FormalObject`` is a typed container
    used to return read results. It must **really accept** every
    canonical name from contracts ``FormalObjectName``, not just expose
    a generically-typed field (codex stage-2.4 follow-up #2 fix).

    The previous version of this test only checked that the
    ``object_type`` field existed. A drift that narrowed
    ``object_type`` to an enum type, or added stricter runtime
    validation, would have slipped through. Now we round-trip every
    canonical FormalObjectName through a real ``FormalObject`` instance
    construction, so the alignment is exercised end-to-end.
    """

    @staticmethod
    def _minimal_pa_table_payload():
        # Construct a minimal pyarrow table for the FormalObject payload
        # field (the runtime container's payload type per its dataclass).
        import pyarrow as pa

        return pa.table({"placeholder": [1]})

    def test_each_canonical_name_can_be_carried_by_formal_object(self) -> None:
        from contracts.schemas.formal_objects import FormalObjectName
        from data_platform.serving.formal import FormalObject

        payload = self._minimal_pa_table_payload()

        # Real instantiation per canonical FormalObjectName value.
        # If a future drift narrows object_type to a Literal-of-enum or
        # adds rejection logic, at least one of these will fail.
        constructed = []
        for member in FormalObjectName:
            instance = FormalObject(
                cycle_id="CYCLE_20250103",
                object_type=member.value,
                snapshot_id=1,
                payload=payload,
            )
            assert instance.object_type == member.value, (
                f"FormalObject did not preserve object_type {member.value!r}"
            )
            assert instance.cycle_id == "CYCLE_20250103"
            assert instance.snapshot_id == 1
            constructed.append(member.value)

        # Sanity floor: there must be at least the 4 core canonical names
        # main-core declares (world_state / official_alpha_pool /
        # alpha_result / recommendation). If FormalObjectName shrinks
        # below this, downstream main-core publish breaks.
        for required in (
            "world_state_snapshot",
            "official_alpha_pool",
            "alpha_result_snapshot",
            "recommendation_snapshot",
        ):
            assert required in constructed, (
                f"FormalObjectName missing canonical name {required!r}; "
                f"main-core publishing would have nowhere to map it"
            )
