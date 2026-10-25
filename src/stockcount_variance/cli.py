"""命令行入口：stockcount --book book.csv --count counted.csv [选项]"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .core import DataError, Report, VarianceRow, build_report, load_book, load_counted


def _fmt_qty(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return format(value.normalize(), "f")


def _fmt_money(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}"


def _fmt_rate(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def render_text(report: Report) -> str:
    headers = ["SKU", "品名", "账面", "实盘", "差异", "差异率", "差异金额", "状态", "异常"]
    table = []
    for r in report.rows:
        table.append([
            r.sku, r.name or "—", _fmt_qty(r.book_qty), _fmt_qty(r.counted_qty),
            _fmt_qty(r.diff_qty), _fmt_rate(r.diff_rate), _fmt_money(r.diff_amount),
            r.status, "*" if r.abnormal else "",
        ])
    widths = [max(len(headers[i]), *(len(row[i]) for row in table)) if table
              else len(headers[i]) for i in range(len(headers))]

    def line(cells: list[str]) -> str:
        return "  ".join(c.ljust(widths[i]) for i, c in enumerate(cells)).rstrip()

    out = [line(headers), line(["-" * w for w in widths])]
    out.extend(line(row) for row in table)
    out.append("")
    out.append(f"SKU 合计：{report.total_skus}　异常项：{report.abnormal_count}"
               f"（阈值 |差异率| > {report.threshold * 100:.0f}% 或单边缺失）")
    out.append(f"盘盈金额合计：{_fmt_money(report.surplus_amount)}")
    out.append(f"盘亏金额合计：{_fmt_money(report.shortage_amount)}")
    out.append(f"净差异金额：{_fmt_money(report.net_amount)}")
    if report.rows_without_cost:
        out.append(f"注：{report.rows_without_cost} 项无成本单价，未计入金额汇总。")
    return "\n".join(out)


def write_csv(report: Report, path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sku", "name", "book_qty", "counted_qty", "diff_qty",
                    "diff_rate", "unit_cost", "diff_amount", "status", "abnormal"])
        for r in report.rows:
            w.writerow([
                r.sku, r.name,
                _fmt_qty(r.book_qty) if r.book_qty is not None else "",
                _fmt_qty(r.counted_qty) if r.counted_qty is not None else "",
                _fmt_qty(r.diff_qty) if r.diff_qty is not None else "",
                f"{r.diff_rate:.4f}" if r.diff_rate is not None else "",
                _fmt_qty(r.unit_cost) if r.unit_cost is not None else "",
                f"{r.diff_amount:.2f}" if r.diff_amount is not None else "",
                r.status, "Y" if r.abnormal else "",
            ])


def write_json(report: Report, path: str | Path) -> None:
    def row_dict(r: VarianceRow) -> dict:
        return {
            "sku": r.sku, "name": r.name,
            "book_qty": str(r.book_qty) if r.book_qty is not None else None,
            "counted_qty": str(r.counted_qty) if r.counted_qty is not None else None,
            "diff_qty": str(r.diff_qty) if r.diff_qty is not None else None,
            "diff_rate": str(r.diff_rate) if r.diff_rate is not None else None,
            "unit_cost": str(r.unit_cost) if r.unit_cost is not None else None,
            "diff_amount": str(r.diff_amount) if r.diff_amount is not None else None,
            "status": r.status, "abnormal": r.abnormal,
        }

    payload = {
        "threshold": str(report.threshold),
        "summary": {
            "total_skus": report.total_skus,
            "abnormal_count": report.abnormal_count,
            "surplus_amount": f"{report.surplus_amount:.2f}",
            "shortage_amount": f"{report.shortage_amount:.2f}",
            "net_amount": f"{report.net_amount:.2f}",
        },
        "rows": [row_dict(r) for r in report.rows],
    }
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stockcount",
        description="库存盘点差异分析：对比账面库存与实盘数量，输出差异报告。",
    )
    parser.add_argument("--book", required=True, help="账面库存 CSV 路径")
    parser.add_argument("--count", required=True, help="实盘 CSV 路径")
    parser.add_argument("--threshold", default="0.05",
                        help="异常差异率阈值，默认 0.05（5%%）")
    parser.add_argument("--out", help="将差异明细导出为 CSV 的路径")
    parser.add_argument("--json", help="将报告导出为 JSON 的路径")
    parser.add_argument("--strict", action="store_true",
                        help="存在异常项时以退出码 1 结束（供脚本/CI 判断）")
    args = parser.parse_args(argv)

    try:
        threshold = Decimal(args.threshold)
    except InvalidOperation:
        print(f"错误：--threshold 不是数字：{args.threshold}", file=sys.stderr)
        return 2

    try:
        book = load_book(args.book)
        counted = load_counted(args.count)
    except DataError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"错误：无法读取文件：{e}", file=sys.stderr)
        return 2

    report = build_report(book, counted, threshold=threshold)
    print(render_text(report))

    if args.out:
        write_csv(report, args.out)
        print(f"\n明细已导出：{args.out}")
    if args.json:
        write_json(report, args.json)
        print(f"JSON 已导出：{args.json}")

    if args.strict and report.abnormal_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
