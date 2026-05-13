"""契约版本常量与持久层版本记录对象。"""

import re
from datetime import datetime, timezone

from pydantic import BaseModel, field_validator

from contracts.core.types import AwareDatetime


__version__: str = "0.1.3"
VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class ContractVersionEntry(BaseModel):
    """契约版本发布记录。"""

    version: str
    released_at: AwareDatetime
    compatibility_note: str = ""
    breaking: bool = False

    @field_validator("version")
    @classmethod
    def version_must_be_semantic(cls, value: str) -> str:
        """确保版本号为三段式语义版本。"""
        if not VERSION_PATTERN.fullmatch(value):
            raise ValueError("version must use MAJOR.MINOR.PATCH format")
        return value


CURRENT_VERSION_ENTRY: ContractVersionEntry = ContractVersionEntry(
    version=__version__,
    released_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
    compatibility_note=(
        "Ex1/Ex2/Ex3 新增可选 producer_context 扩展槽 + Ex1 新增可选 "
        "evidence 字段 + 放宽 Ex2.affected_sectors 列表 min_length=1 约束（字段"
        "仍为 required，但接受空列表；元素仍要求 SectorId min_length=1）+ "
        "ResolutionCase 正式允许 unresolved/no-candidate 空候选列表，同时 "
        "matched/ambiguous 仍要求 candidate_entities 非空"
        "（subsystem-announcement follow-up #3 cross-repo reconciliation；"
        "纯加法 + 放宽，向后兼容）"
    ),
    breaking=False,
)


__all__ = [
    "__version__",
    "VERSION_PATTERN",
    "ContractVersionEntry",
    "CURRENT_VERSION_ENTRY",
]
