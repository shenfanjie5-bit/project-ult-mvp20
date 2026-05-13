"""contracts 契约包根模块，暴露核心、错误码、协议与 Schema 子包。"""

from contracts import core, errors, protocols, schemas
from contracts.core.version import __version__

__all__ = ["core", "errors", "protocols", "schemas", "__version__"]
