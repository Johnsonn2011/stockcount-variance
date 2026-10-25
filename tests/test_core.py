from decimal import Decimal

import pytest

from stockcount_variance.core import (
    STATUS_BOOK_ONLY,
    STATUS_COUNT_ONLY,
    STATUS_MATCH,
    STATUS_SHORTAGE,
    STATUS_SURPLUS,
    DataError,
    build_report,
    load_book,
    load_counted,
)


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_load_book_parses_rows(tmp_path):
    p = _write(tmp_path, "book.csv",
               "sku,name,book_qty,unit_cost\nA,大米,100,3.20\nB,紫菜,25,\n")
    book = load_book(p)
    assert book["A"].book_qty == Decimal("100")
    assert book["A"].unit_cost == Decimal("3.20")
    assert book["B"].unit_cost is None  # 单价留空允许


def test_load_book_duplicate_sku_raises(tmp_path):
    p = _write(tmp_path, "book.csv",
               "sku,name,book_qty,unit_cost\nA,大米,100,3.20\nA,大米,50,3.20\n")
    with pytest.raises(DataError):
        load_book(p)


def test_load_book_bad_number_raises(tmp_path):
    p = _write(tmp_path, "book.csv",
               "sku,name,book_qty,unit_cost\nA,大米,abc,3.20\n")
    with pytest.raises(DataError):
        load_book(p)


def test_load_counted_sums_duplicate_sku(tmp_path):
    p = _write(tmp_path, "count.csv", "sku,counted_qty\nA,10\nA,5\nB,3\n")
    counted = load_counted(p)
    assert counted["A"] == Decimal("15")
    assert counted["B"] == Decimal("3")


def _report(tmp_path, book_text, count_text, threshold=Decimal("0.05")):
    book = load_book(_write(tmp_path, "b.csv", book_text))
    counted = load_counted(_write(tmp_path, "c.csv", count_text))
    return build_report(book, counted, threshold=threshold)


def test_statuses_and_rates(tmp_path):
    report = _report(
        tmp_path,
        "sku,name,book_qty,unit_cost\n"
        "A,一致品,100,2\nB,盘盈品,100,2\nC,盘亏品,100,2\nD,仅账面,10,2\n",
        "sku,counted_qty\nA,100\nB,103\nC,80\nE,7\n",
    )
    rows = {r.sku: r for r in report.rows}
    assert rows["A"].status == STATUS_MATCH and not rows["A"].abnormal
    assert rows["B"].status == STATUS_SURPLUS and not rows["B"].abnormal  # 3% 在阈值内
    assert rows["C"].status == STATUS_SHORTAGE and rows["C"].abnormal  # -20% 超阈值
    assert rows["C"].diff_rate == Decimal("-0.2")
    assert rows["D"].status == STATUS_BOOK_ONLY and rows["D"].abnormal
    assert rows["D"].diff_qty == Decimal("-10")
    assert rows["E"].status == STATUS_COUNT_ONLY and rows["E"].abnormal
    assert rows["E"].diff_amount is None  # 无成本基准不计金额


def test_amount_totals(tmp_path):
    report = _report(
        tmp_path,
        "sku,name,book_qty,unit_cost\nA,甲,100,2\nB,乙,50,4\n",
        "sku,counted_qty\nA,110\nB,40\n",
    )
    assert report.surplus_amount == Decimal("20")    # +10 * 2
    assert report.shortage_amount == Decimal("-40")  # -10 * 4
    assert report.net_amount == Decimal("-20")
    assert report.total_skus == 2


def test_threshold_boundary_not_abnormal(tmp_path):
    report = _report(
        tmp_path,
        "sku,name,book_qty,unit_cost\nA,甲,200,1\n",
        "sku,counted_qty\nA,190\n",  # -5%，等于阈值不算异常
    )
    assert report.rows[0].status == STATUS_SHORTAGE
    assert report.abnormal_count == 0
