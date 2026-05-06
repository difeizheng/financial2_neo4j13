"""Annotate cells with time_period based on table time column detection.

This module runs after the three-layer graph is built. It traverses each
table's time_period_labels (col_letter -> period_label), and for every cell
under those time columns within the table's data range, sets cell.time_period
if the cell's value is non-empty.
"""
from __future__ import annotations

from ..models.graph import FinancialGraph


def annotate_cell_time_periods(graph: FinancialGraph) -> int:
    """根据 table 的时间列信息，给 cell 添加 time_period 属性。

    只对有明确 time_period_labels 的 table 做标注。
    只标注 value 为数字或非空的 cell。

    Returns:
        标注的 cell 数量。
    """
    annotated_count = 0

    for table in graph.tables.values():
        # 跳过没有明确时间列的 table
        if not table.time_period_labels:
            continue

        data_range = table.data_row_range
        if not data_range or len(data_range) != 2:
            continue

        data_start, data_end = data_range
        if not data_start or not data_end:
            continue

        for col_letter, period_label in table.time_period_labels.items():
            for row in range(data_start, data_end + 1):
                cell_id = f"{table.sheet}_{row}_{col_letter}"
                cell = graph.cells.get(cell_id)
                # 只标注 value 非空的 cell
                if cell is not None and cell.value is not None:
                    cell.time_period = period_label
                    annotated_count += 1

    return annotated_count
