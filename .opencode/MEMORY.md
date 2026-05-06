# Financial KG Session Memory

## Project
Financial model Excel parser → 3-layer knowledge graph (Cell/Indicator/Table) with Neo4j.
Streamlit UI on port 8534 via `./run_streamlit.bat`.

## Key Architecture
- `financial_kg/parser/table_detector.py` — core table detection logic
- `financial_kg/parser/header_inheritance.py` — header inheritance for sub-tables
- `financial_kg/parser/time_period_annotator.py` — cell time_period annotation
- `financial_kg/models/cell.py` — Cell model with `time_period` field
- `pages/01_upload.py` — parse pipeline: cells → indicators → relationships → time annotate
- `pages/02_explorer.py` — table list shows: name, type, row range, header rows, time cols, indicators

## 8 Issues Fixed
1. **L-table split**: `_expand_l_table` now stops at new anchor's start_row
2. **data_start fix**: `_raw_to_table_info` scans 1-2 rows above for header keywords
3. **Overlap merge**: `_merge_overlapping_table_infos` merges same row_range TableInfo objects
4. **Table split fix**: BFS blocks title-only rows from absorbing next row's header
5. **Header inheritance**: BFS small tables inherit header from previous proper table
6. **Double-header detection**: `TableInfo.is_double_header` set when header_row has keywords + next row has sequences
7. **Table list columns**: explorer shows row range, header rows, time series count
8. **Time column detection**: `_is_time_value()` covers 9 formats (year, date serial, YYYY-MM, quarter, FY, etc.)

## Critical Gotchas
- `detect_tables` returns `TableInfo` objects; `indicator_builder` converts them to `Table` nodes
- Double-header tables store `header_rows=[row, row+1]` in Table model
- `_has_proper_header` requires >=3 header keywords to qualify
- BFS header blocking only applies when BFS started from a pure title row (<=2 cells, all text, no numbers)
- `time_period_labels` dict maps col_letter → standardized label like "2024", "2024-01", "2024-Q1"
- Test file: `数字化系统财务模型边界【抽水蓄能】v15(亏损弥补+分红预提税+净资产税+折旧摊销优化）.xlsx`
