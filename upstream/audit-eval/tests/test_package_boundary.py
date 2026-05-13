import importlib

import pytest

from audit_eval._boundary import BoundaryViolationError, assert_no_forbidden_write


def test_all_subpackages_importable() -> None:
    for package_name in (
        "audit_eval.audit",
        "audit_eval.retro",
        "audit_eval.drift",
        "audit_eval.backtest",
        "audit_eval.ui",
        "audit_eval.contracts",
    ):
        importlib.import_module(package_name)


def test_boundary_forbids_feature_weight_multiplier() -> None:
    with pytest.raises(BoundaryViolationError):
        assert_no_forbidden_write({"feature_weight_multiplier": 1.2})


def test_boundary_allows_plain_payload() -> None:
    assert_no_forbidden_write({})
    assert_no_forbidden_write({"alert_score": 2})
