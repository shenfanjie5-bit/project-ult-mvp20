from __future__ import annotations

import importlib
import pathlib
import re
import sys

import pytest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
CHINESE_CHARACTER_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def import_errors() -> object:
    sys.path.insert(0, str(SRC_DIR))
    try:
        return importlib.import_module("contracts.errors")
    finally:
        sys.path.remove(str(SRC_DIR))


def test_errors_public_api_imports() -> None:
    errors = import_errors()

    for public_name in [
        "ErrorCode",
        "ErrorCodeEntry",
        "ErrorCodeRegistry",
        "ERROR_CODE_REGISTRY",
        "ContractError",
        "get_error_description",
        "validation_error_message",
        "raise_contract_error",
    ]:
        assert hasattr(errors, public_name)
        assert public_name in errors.__all__


def test_error_registry_covers_every_error_code() -> None:
    errors = import_errors()

    assert {
        entry.code for entry in errors.ERROR_CODE_REGISTRY.entries
    } == set(errors.ErrorCode)


def test_reasoner_error_codes_are_registered() -> None:
    errors = import_errors()
    expected_codes = {
        "REASONER_INPUT_CONTRACT_ERROR",
        "REASONER_MODEL_PROVIDER_ERROR",
        "REASONER_TOOL_EXECUTION_ERROR",
        "REASONER_TIMEOUT_ERROR",
        "REASONER_INTERNAL_ERROR",
    }

    registered_codes = {
        entry.code.value for entry in errors.ERROR_CODE_REGISTRY.entries
    }

    assert expected_codes <= registered_codes
    for code in expected_codes:
        assert errors.ERROR_CODE_REGISTRY.get(code).code.value == code


def test_error_descriptions_are_non_empty_chinese_strings() -> None:
    errors = import_errors()

    for entry in errors.ERROR_CODE_REGISTRY.entries:
        assert entry.description.strip()
        assert CHINESE_CHARACTER_PATTERN.search(entry.description)


def test_error_registry_gets_entries_by_enum_and_string() -> None:
    errors = import_errors()
    enum_entry = errors.ERROR_CODE_REGISTRY.get(
        errors.ErrorCode.CONTRACT_VALIDATION_ERROR
    )
    string_entry = errors.ERROR_CODE_REGISTRY.get("CONTRACT_VALIDATION_ERROR")

    assert enum_entry is string_entry
    assert enum_entry.description == errors.get_error_description(
        errors.ErrorCode.CONTRACT_VALIDATION_ERROR
    )


def test_error_registry_get_rejects_unknown_code() -> None:
    errors = import_errors()

    with pytest.raises(KeyError):
        errors.ERROR_CODE_REGISTRY.get("not_a_code")


def test_contract_error_preserves_code_and_formats_message() -> None:
    errors = import_errors()

    error = errors.ContractError(errors.ErrorCode.CONTRACT_VALIDATION_ERROR)

    assert error.code is errors.ErrorCode.CONTRACT_VALIDATION_ERROR
    assert error.message == "合同校验失败"
    assert error.details == {}
    assert errors.ErrorCode.CONTRACT_VALIDATION_ERROR.value in str(error)
    assert "合同校验失败" in str(error)


def test_contract_error_normalizes_string_error_code() -> None:
    errors = import_errors()

    error = errors.ContractError("CONTRACT_VALIDATION_ERROR")

    assert error.code is errors.ErrorCode.CONTRACT_VALIDATION_ERROR
    assert error.message == "合同校验失败"


def test_validation_error_message_includes_stable_error_code() -> None:
    errors = import_errors()

    assert errors.validation_error_message(
        errors.ErrorCode.FORBIDDEN_INGEST_METADATA,
        "submitted_at is not allowed",
    ) == "[FORBIDDEN_INGEST_METADATA] submitted_at is not allowed"


def test_raise_contract_error_raises_contract_error_with_details() -> None:
    errors = import_errors()

    with pytest.raises(errors.ContractError) as exc_info:
        errors.raise_contract_error(
            errors.ErrorCode.FORBIDDEN_INGEST_METADATA,
            details={"field": "submitted_at"},
        )

    assert exc_info.value.code is errors.ErrorCode.FORBIDDEN_INGEST_METADATA
    assert exc_info.value.details == {"field": "submitted_at"}
