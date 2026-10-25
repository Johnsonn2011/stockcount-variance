"""stockcount-variance: 库存盘点差异分析工具。"""

from .core import (
    BookItem,
    DataError,
    Report,
    VarianceRow,
    build_report,
    load_book,
    load_counted,
)

__version__ = "0.1.0"

__all__ = [
    "BookItem",
    "DataError",
    "Report",
    "VarianceRow",
    "build_report",
    "load_book",
    "load_counted",
    "__version__",
]
