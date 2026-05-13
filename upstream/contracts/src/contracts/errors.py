"""统一合同错误码、注册表与异常入口。"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import NoReturn, Self

from pydantic import Field, model_validator

from contracts.core.base import ContractBaseModel
from contracts.core.types import Severity


class ErrorCode(str, Enum):
    """合同模块统一错误码。"""

    CONTRACT_VALIDATION_ERROR = "CONTRACT_VALIDATION_ERROR"
    FORBIDDEN_INGEST_METADATA = "FORBIDDEN_INGEST_METADATA"
    UNKNOWN_FORMAL_OBJECT = "UNKNOWN_FORMAL_OBJECT"
    PROTOCOL_SIGNATURE_MISMATCH = "PROTOCOL_SIGNATURE_MISMATCH"
    INCOMPATIBLE_CONTRACT_CHANGE = "INCOMPATIBLE_CONTRACT_CHANGE"
    REASONER_INPUT_CONTRACT_ERROR = "REASONER_INPUT_CONTRACT_ERROR"
    REASONER_MODEL_PROVIDER_ERROR = "REASONER_MODEL_PROVIDER_ERROR"
    REASONER_TOOL_EXECUTION_ERROR = "REASONER_TOOL_EXECUTION_ERROR"
    REASONER_TIMEOUT_ERROR = "REASONER_TIMEOUT_ERROR"
    REASONER_INTERNAL_ERROR = "REASONER_INTERNAL_ERROR"


class ErrorCodeEntry(ContractBaseModel):
    """单个错误码的注册信息。"""

    code: ErrorCode
    description: str = Field(min_length=1)
    severity: Severity = Severity.ERROR


class ErrorCodeRegistry(ContractBaseModel):
    """错误码注册表。"""

    entries: tuple[ErrorCodeEntry, ...]

    @model_validator(mode="after")
    def validate_registry_completeness(self) -> Self:
        """确保注册表没有遗漏或重复错误码。"""

        registered_codes = [entry.code for entry in self.entries]
        duplicated_codes = {
            code for code in registered_codes if registered_codes.count(code) > 1
        }
        missing_codes = set(ErrorCode).difference(registered_codes)

        if duplicated_codes:
            duplicates = ", ".join(
                code.value
                for code in sorted(duplicated_codes, key=lambda item: item.value)
            )
            raise ValueError(f"duplicate error code entries: {duplicates}")

        if missing_codes:
            missing = ", ".join(
                code.value
                for code in sorted(missing_codes, key=lambda item: item.value)
            )
            raise ValueError(f"missing error code entries: {missing}")

        return self

    def get(self, code: ErrorCode | str) -> ErrorCodeEntry:
        """按错误码读取注册项，未知错误码抛出 KeyError。"""

        try:
            normalized_code = code if isinstance(code, ErrorCode) else ErrorCode(code)
        except ValueError as exc:
            raise KeyError(str(code)) from exc

        for entry in self.entries:
            if entry.code is normalized_code:
                return entry

        raise KeyError(normalized_code.value)


ERROR_CODE_REGISTRY = ErrorCodeRegistry(
    entries=(
        ErrorCodeEntry(
            code=ErrorCode.CONTRACT_VALIDATION_ERROR,
            description="合同校验失败",
        ),
        ErrorCodeEntry(
            code=ErrorCode.FORBIDDEN_INGEST_METADATA,
            description="Ex payload 禁止包含 Layer B 摄取元数据",
        ),
        ErrorCodeEntry(
            code=ErrorCode.UNKNOWN_FORMAL_OBJECT,
            description="未知 Formal Object 名称",
        ),
        ErrorCodeEntry(
            code=ErrorCode.PROTOCOL_SIGNATURE_MISMATCH,
            description="协议签名不匹配",
        ),
        ErrorCodeEntry(
            code=ErrorCode.INCOMPATIBLE_CONTRACT_CHANGE,
            description="合同变更不兼容",
        ),
        ErrorCodeEntry(
            code=ErrorCode.REASONER_INPUT_CONTRACT_ERROR,
            description="Reasoner 输入合同校验失败",
        ),
        ErrorCodeEntry(
            code=ErrorCode.REASONER_MODEL_PROVIDER_ERROR,
            description="Reasoner 模型提供方调用失败",
        ),
        ErrorCodeEntry(
            code=ErrorCode.REASONER_TOOL_EXECUTION_ERROR,
            description="Reasoner 工具执行失败",
        ),
        ErrorCodeEntry(
            code=ErrorCode.REASONER_TIMEOUT_ERROR,
            description="Reasoner 执行超时",
        ),
        ErrorCodeEntry(
            code=ErrorCode.REASONER_INTERNAL_ERROR,
            description="Reasoner 内部错误",
        ),
    )
)


class ContractError(Exception):
    """合同模块异常基类，携带统一错误码。"""

    def __init__(
        self,
        code: ErrorCode | str,
        message: str | None = None,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.code = code if isinstance(code, ErrorCode) else ErrorCode(code)
        self.message = message or get_error_description(self.code)
        self.details = dict(details or {})

        super().__init__(f"[{self.code.value}] {self.message}")


def get_error_description(code: ErrorCode | str) -> str:
    """返回错误码的中文描述。"""

    return ERROR_CODE_REGISTRY.get(code).description


def validation_error_message(code: ErrorCode | str, message: str) -> str:
    """Return stable error-code text for Pydantic validation messages."""

    normalized_code = code if isinstance(code, ErrorCode) else ErrorCode(code)
    return f"[{normalized_code.value}] {message}"


def raise_contract_error(
    code: ErrorCode | str,
    message: str | None = None,
    *,
    details: Mapping[str, object] | None = None,
) -> NoReturn:
    """抛出带统一错误码的合同异常。"""

    raise ContractError(code, message, details=details)


__all__ = [
    "ErrorCode",
    "ErrorCodeEntry",
    "ErrorCodeRegistry",
    "ERROR_CODE_REGISTRY",
    "ContractError",
    "get_error_description",
    "validation_error_message",
    "raise_contract_error",
]
