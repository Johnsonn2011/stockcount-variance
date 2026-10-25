import csv
import json

from stockcount_variance.cli import main

BOOK = "sku,name,book_qty,unit_cost\nA,大米,100,3.20\nB,紫菜,25,290\n"
COUNT_OK = "sku,counted_qty\nA,100\nB,25\n"
COUNT_BAD = "sku,counted_qty\nA,100\nB,5\n"  # B 盘亏 80%，异常


def _files(tmp_path, count_text):
    book = tmp_path / "book.csv"
    book.write_text(BOOK, encoding="utf-8")
    count = tmp_path / "count.csv"
    count.write_text(count_text, encoding="utf-8")
    return str(book), str(count)


def test_cli_ok_exit_zero(tmp_path, capsys):
    book, count = _files(tmp_path, COUNT_OK)
    code = main(["--book", book, "--count", count])
    out = capsys.readouterr().out
    assert code == 0
    assert "异常项：0" in out
    assert "大米" in out


def test_cli_strict_exit_one_on_abnormal(tmp_path):
    book, count = _files(tmp_path, COUNT_BAD)
    assert main(["--book", book, "--count", count]) == 0  # 非 strict 不拦截
    assert main(["--book", book, "--count", count, "--strict"]) == 1


def test_cli_exports_csv_and_json(tmp_path):
    book, count = _files(tmp_path, COUNT_BAD)
    out_csv = tmp_path / "report.csv"
    out_json = tmp_path / "report.json"
    code = main(["--book", book, "--count", count,
                 "--out", str(out_csv), "--json", str(out_json)])
    assert code == 0
    with out_csv.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert {r["sku"] for r in rows} == {"A", "B"}
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["summary"]["abnormal_count"] == 1
    assert payload["summary"]["shortage_amount"] == "-5800.00"


def test_cli_missing_file_exit_two(tmp_path, capsys):
    code = main(["--book", str(tmp_path / "nope.csv"),
                 "--count", str(tmp_path / "nope2.csv")])
    assert code == 2
    assert "错误" in capsys.readouterr().err
