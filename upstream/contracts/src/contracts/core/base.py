"""Pydantic 合同模型共享基类。"""

from pydantic import BaseModel, ConfigDict


class ContractBaseModel(BaseModel):
    """所有合同 Pydantic 模型的共享基础配置。"""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


__all__ = ["ContractBaseModel"]
