import pytest

from audit_eval._boundary import BoundaryViolationError, assert_no_forbidden_write


def test_boundary_forbids_top_level_feature_weight_multiplier() -> None:
    with pytest.raises(BoundaryViolationError, match="feature_weight_multiplier"):
        assert_no_forbidden_write({"feature_weight_multiplier": 1})


def test_boundary_reports_nested_mapping_path() -> None:
    with pytest.raises(
        BoundaryViolationError,
        match=r"\$\.nested\.feature_weight_multiplier",
    ):
        assert_no_forbidden_write({"nested": {"feature_weight_multiplier": 1}})


def test_boundary_reports_sequence_index_path() -> None:
    with pytest.raises(
        BoundaryViolationError,
        match=r"\$\[0\]\.safe\.feature_weight_multiplier",
    ):
        assert_no_forbidden_write([{"safe": {"feature_weight_multiplier": 1}}])


def test_boundary_respects_custom_root_path() -> None:
    with pytest.raises(
        BoundaryViolationError,
        match=r"\$\.metadata\.feature_weight_multiplier",
    ):
        assert_no_forbidden_write(
            {"feature_weight_multiplier": 1},
            path="$.metadata",
        )
