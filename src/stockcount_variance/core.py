"""核心逻辑：读取账面/实盘 CSV，计算盘点差异并生成报告数据。

输入格式
--------
账面 CSV（--book）：sku,name,book_qty,unit_cost
    - sku 必填且不可重复；name 可空；book_qty 为数字；
    - unit_cost 可选：整列可缺失，或个别行留空（该行不计算差异金额）。
实盘 CSV（--count）：sku,counted_qty
    - 同一 sku 出现多行时累加（盘点常分批录入）。

差异规则
--------
- 差异数量 = 实盘 - 账面；差异率 = 差异数量 / 账面（账面为 0 时差异率为空）。
- 状态：一致 / 盘盈 / 盘亏 / 仅账面（实盘未出现）/ 仅实盘（账面未出现）。
- 异常标记：仅账面、仅实盘，或 |差异率| 超过阈值（默认 5%）。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

STATUS_MATCH = "一致"
STATUS_SURPLUS = "盘盈"
STATUS_SHORTAGE = "盘亏"
STATUS_BOOK_ONLY = "仅账面"
STATUS_COUNT_ONLY = "仅实盘"

DEFAULT_THRESHOLD = Decimal("0.05")


class DataError(ValueError):
    """输入 CSV 格式不符合要求时抛出。"""


@dataclass
class BookItem:
    sku: str
    name: str
    book_qty: Decimal
    unit_cost: Decimal | None


@dataclass
class VarianceRow:
    sku: str
    name: str
    book_qty: Decimal | None
    counted_qty: Decimal | None
    diff_qty: Decimal | None
    diff_rate: Decimal | None
    unit_cost: Decimal | None
    diff_amount: Decimal | None
    status: str
    abnormal: bool


@dataclass
class Report:
    rows: list[VarianceRow]
    threshold: Decimal

    @property
    def total_skus(self) -> int:
        return len(self.rows)

    @property
    def abnormal_count(self) -> int:
        return sum(1 for r in self.rows if r.abnormal)

    @property
    def surplus_amount(self) -> Decimal:
        return sum(
            (r.diff_amount for r in self.rows
             if r.diff_amount is not None and r.diff_amount > 0),
            Decimal("0"),
        )

    @property
    def shortage_amount(self) -> Decimal:
        """盘亏金额合计（负数）。"""
        return sum(
            (r.diff_amount for r in self.rows
             if r.diff_amount is not None and r.diff_amount < 0),
            Decimal("0"),
        )

    @property
    def net_amount(self) -> Decimal:
        return self.surplus_amount + self.shortage_amount

    @property
    def rows_without_cost(self) -> int:
        return sum(1 for r in self.rows if r.diff_amount is None and r.diff_qty)


def _decimal(raw: str | None, *, field_name: str, sku: str, source: str,
             allow_empty: bool = False) -> Decimal | None:
    text = (raw or "").strip()
    if text == "":
        if allow_empty:
            return None
        raise DataError(f"{source} 中 SKU {sku!r} 的 {field_name} 为空")
    try:
        return Decimal(text)
    except InvalidOperation:
        raise DataError(
            f"{source} 中 SKU {sku!r} 的 {field_name} 不是数字：{raw!r}"
        ) from None


def _read_rows(path: str | Path, source: str) -> list[dict]:
    p = Path(path)
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise DataError(f"{source} 文件为空：{p}")
        return [row for row in reader
                if any((v or "").strip() for v in row.values())]


def load_book(path: str | Path) -> dict[str, BookItem]:
    """读取账面库存 CSV，返回 {sku: BookItem}。sku 重复时抛 DataError。"""
    rows = _read_rows(path, "账面")
    book: dict[str, BookItem] = {}
    for row in rows:
        sku = (row.get("sku") or "").strip()
        if not sku:
            raise DataError("账面文件中存在 sku 为空的行")
        if sku in book:
            raise DataError(f"账面文件中 SKU 重复：{sku}")
        book[sku] = BookItem(
            sku=sku,
            name=(row.get("name") or "").strip(),
            book_qty=_decimal(row.get("book_qty"), field_name="book_qty",
                               sku=sku, source="账面"),
            unit_cost=_decimal(row.get("unit_cost"), field_name="unit_cost",
                                sku=sku, source="账面", allow_empty=True),
        )
    return book


def load_counted(path: str | Path) -> dict[str, Decimal]:
    """读取实盘 CSV，返回 {sku: 实盘数量}。同一 sku 多行累加。"""
    rows = _read_rows(path, "实盘")
    counted: dict[str, Decimal] = {}
    for row in rows:
        sku = (row.get("sku") or "").strip()
        if not sku:
            raise DataError("实盘文件中存在 sku 为空的行")
        qty = _decimal(row.get("counted_qty"), field_name="counted_qty",
                       sku=sku, source="实盘")
        counted[sku] = counted.get(sku, Decimal("0")) + qty
    return counted


def build_report(book: dict[str, BookItem], counted: dict[str, Decimal],
                 threshold: Decimal = DEFAULT_THRESHOLD) -> Report:
    rows: list[VarianceRow] = []
    for sku in sorted(set(book) | set(counted)):
        item = book.get(sku)
        counted_qty = counted.get(sku)

        if item is not None and counted_qty is not None:
            diff = counted_qty - item.book_qty
            rate = (diff / item.book_qty) if item.book_qty != 0 else None
            if diff == 0:
                status = STATUS_MATCH
            elif diff > 0:
                status = STATUS_SURPLUS
            else:
                status = STATUS_SHORTAGE
            amount = diff * item.unit_cost if item.unit_cost is not None else None
            abnormal = status != STATUS_MATCH and (
                rate is None or abs(rate) > threshold
            )
            rows.append(VarianceRow(
                sku=sku, name=item.name, book_qty=item.book_qty,
                counted_qty=counted_qty, diff_qty=diff, diff_rate=rate,
                unit_cost=item.unit_cost, diff_amount=amount,
                status=status, abnormal=abnormal,
            ))
        elif item is not None:  # 仅账面：实盘未出现，按整单缺失计差异
            diff = -item.book_qty
            amount = diff * item.unit_cost if item.unit_cost is not None else None
            rows.append(VarianceRow(
                sku=sku, name=item.name, book_qty=item.book_qty,
                counted_qty=None, diff_qty=diff,
                diff_rate=Decimal("-1") if item.book_qty != 0 else None,
                unit_cost=item.unit_cost, diff_amount=amount,
                status=STATUS_BOOK_ONLY, abnormal=True,
            ))
        else:  # 仅实盘：账面未出现，无成本基准，不计金额
            rows.append(VarianceRow(
                sku=sku, name="", book_qty=None, counted_qty=counted_qty,
                diff_qty=counted_qty, diff_rate=None, unit_cost=None,
                diff_amount=None, status=STATUS_COUNT_ONLY, abnormal=True,
            ))
    return Report(rows=rows, threshold=threshold)
