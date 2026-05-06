"""Post-process tables within a sheet: inherit headers from previous tables."""
from __future__ import annotations
from .table_detector import TableInfo, _is_time_value

_HEADER_KW = {
    "序号", "编号", "序", "项目", "名称", "参数", "指标", "科目",
    "合计", "小计", "汇总", "总计", "总额", "类别", "分类", "大类",
    "单位", "万元", "元", "备注", "说明", "注",
}


def _has_proper_header(tbl: TableInfo, rows: dict[int, dict[str, object]]) -> bool:
    """Check if a table has its own proper header row with >=3 header keywords."""
    header_data = rows.get(tbl.header_row, {})
    if not header_data:
        return False
    header_count = sum(
        1 for v in header_data.values()
        if isinstance(v, str) and v.strip() and any(kw in v for kw in _HEADER_KW)
    )
    return header_count >= 3


def inherit_headers_within_sheet(
    tables: list[TableInfo],
    rows: dict[int, dict[str, object]],
) -> None:
    """对同一sheet内无表头的table，继承前一个有proper header的table的header。
    
    跳过纯标题行（只有文本单元格，无header关键词的table）。
    继承内容包括：header_row, time_period_labels, 以及重新分类列角色。
    """
    last_header_row: int | None = None
    last_header_data: dict[str, object] = {}
    last_time_labels: dict[str, str] = {}
    last_is_double_header: bool = False

    for tbl in tables:
        if _has_proper_header(tbl, rows):
            # This table has its own proper header, record it
            last_header_row = tbl.header_row
            last_header_data = dict(rows.get(tbl.header_row, {}))
            last_time_labels = dict(tbl.time_period_labels)
            # Detect if this is a double-header table
            next_row_data = rows.get(tbl.header_row + 1, {})
            if next_row_data and len(tbl.time_period_labels) > 3:
                seq_in_time_cols = sum(
                    1 for col in tbl.time_period_labels
                    if col in next_row_data and isinstance(next_row_data[col], (int, float))
                    and 1 <= next_row_data[col] <= 100
                )
                last_is_double_header = seq_in_time_cols > 2
            else:
                last_is_double_header = False
            continue

        if last_header_row is None:
            continue  # No previous header to inherit from

        # Check if this is a pure title row (e.g., "全投资的折旧摊销判定条件同资本金")
        # Skip inheritance only for title-only tables (all cells are strings)
        header_data = rows.get(tbl.header_row, {})
        non_empty = [v for v in header_data.values() if v is not None]
        str_vals = [v for v in non_empty if isinstance(v, str) and v.strip()]
        has_header_kw = any(
            isinstance(v, str) and any(kw in v for kw in _HEADER_KW)
            for v in non_empty
        )
        num_vals = [v for v in non_empty if isinstance(v, (int, float)) and not isinstance(v, bool)]
        # Pure title row: only text cells, no numeric values, no header keywords
        # This skips tables like "全投资的折旧摊销判定条件同资本金" (row 243 in 表2)
        # But allows small data tables like IRR summary (row 44 in 表6)
        if len(non_empty) <= 2 and len(str_vals) == len(non_empty) and not has_header_kw:
            continue

        # Inherit the header
        tbl.header_row = last_header_row
        tbl.time_period_labels = dict(last_time_labels)
        tbl.is_double_header = last_is_double_header

        # Re-classify column roles with the inherited header
        from .table_detector import _classify_columns
        _classify_columns(tbl, rows)
