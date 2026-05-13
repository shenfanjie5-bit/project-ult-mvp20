"""DataSourceAdapter、AlphaAnalyzer 等协议定义。"""

from contracts.protocols.alpha_analyzer import AlphaAnalyzer
from contracts.protocols.data_source_adapter import DataSourceAdapter, DataSourceBatch

__all__ = ["AlphaAnalyzer", "DataSourceAdapter", "DataSourceBatch"]
