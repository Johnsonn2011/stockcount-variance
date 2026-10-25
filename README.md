# stockcount-variance（库存盘点差异分析工具）

把**账面库存**和**实盘结果**两个 CSV 放进来，自动算出每个 SKU 的差异数量、差异率、差异金额，标出异常项，并给出盘盈/盘亏/净差异汇总。适合仓库月末盘点后快速定位大额异常，再逐项核查原因。

## 环境要求

- Python 3.10+
- 运行时零第三方依赖；测试需要 pytest（开发依赖）

## 安装

```bash
cd stockcount-variance
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## 运行

```bash
# 方式一：安装后的命令
stockcount --book examples/book.csv --count examples/counted.csv

# 方式二：不安装，用模块运行（需在项目根目录）
PYTHONPATH=src python3 -m stockcount_variance --book examples/book.csv --count examples/counted.csv

# 导出明细 CSV / JSON
stockcount --book book.csv --count counted.csv --out report.csv --json report.json

# 自定义异常阈值（默认差异率 5%），且存在异常时以退出码 1 结束（供脚本判断）
stockcount --book book.csv --count counted.csv --threshold 0.02 --strict
```

## 输入格式

账面 CSV（表头固定）：

```csv
sku,name,book_qty,unit_cost
SKU-001,东北大米(斤),500,3.20
```

- `sku` 必填、不可重复；`name` 可空；`book_qty` 为数字（可带小数）。
- `unit_cost` 可选：整列可缺失或个别行留空，留空的行不计入金额汇总（报告中会注明项数）。

实盘 CSV：

```csv
sku,counted_qty
SKU-001,498
```

- 同一 `sku` 出现多行时自动累加（盘点常分批录入）。

## 输出说明

- **状态**：一致 / 盘盈 / 盘亏 / 仅账面（实盘未出现，按整单缺失计）/ 仅实盘（账面未出现，无成本基准、不计金额）。
- **异常标记 `*`**：仅账面、仅实盘，或 |差异率| 超过阈值。阈值内的小额盘盈盘亏只显示状态，不标异常。
- **汇总**：SKU 合计、异常项数、盘盈金额合计、盘亏金额合计、净差异金额。
- 退出码：0 正常；1 = `--strict` 且存在异常；2 = 输入文件错误（格式不符或无法读取）。

## 测试

```bash
python3 -m pytest -q
```

## 目录结构

```
stockcount-variance/
├── pyproject.toml
├── README.md
├── examples/            # 示例数据（虚构，仅演示格式与输出）
│   ├── book.csv
│   └── counted.csv
├── src/stockcount_variance/
│   ├── core.py          # 读取、差异计算、汇总
│   └── cli.py           # 命令行、文本/CSV/JSON 输出
└── tests/
    ├── test_core.py
    └── test_cli.py
```

## 说明

`examples/` 中的数据为演示用虚构数据，不对应任何真实单位的库存。
