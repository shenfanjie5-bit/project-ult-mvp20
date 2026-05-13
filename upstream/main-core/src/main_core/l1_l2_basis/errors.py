"""Local exception types for L1/L2 basis reads."""

from __future__ import annotations

from main_core.common.errors import MainCoreError


class L1L2BasisError(MainCoreError):
    """Base exception for L1/L2 basis read failures."""


class DataPlatformReadError(L1L2BasisError):
    """Raised when a data-platform port returns invalid basis data."""


__all__ = ["DataPlatformReadError", "L1L2BasisError"]
