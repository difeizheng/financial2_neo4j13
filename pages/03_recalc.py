"""Page 3: Parameter modification and incremental recalculation."""
from __future__ import annotations
import os
import sys
import uuid

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from financial_kg.storage.json_store import load_graph
from financial_kg.storage.task_db import TaskDB
from financial_kg.engine.recalculator import recalculate
from financial_kg.engine.snapshot import create_snapshot

st.set_page_config(page_title="参数重算", layout="wide")
st.title("⚙️ 参数修改 & 增量重算")

db = TaskDB()
tasks = [t for t in db.list_tasks() if t.status == "done"]

if not tasks:
    st.warning("暂无已解析的任务。")
    st.stop()

task_options = {f"{t.id} — {t.filename}": t for t in tasks}
selected_label = st.selectbox("选择任务", list(task_options.keys()))
task = task_options[selected_label]

@st.cache_resource(show_spinner="加载图谱...")
def _load(task_id: str, output_dir: str):
    cells_path = os.path.join(output_dir, f"{task_id}_cells.json")
    return load_graph(cells_path)

graph = _load(task.id, task.output_dir)

st.info("修改参数单元格的值，系统将自动传播计算所有下游受影响单元格。")

# ── Parameter search ─────────────────────────────────────────────────────────
st.subheader("搜索参数单元格")

search_mode = st.radio("搜索方式", ["按 Indicator 名称", "按 Cell ID/值"], horizontal=True)

cell_id = None

if search_mode == "按 Indicator 名称":
    search_kw = st.text_input("关键词（Indicator 名称）", placeholder="如：建设期")
    
    if search_kw:
        matching_inds = [
            ind for ind in graph.indicators.values()
            if search_kw.lower() in (ind.name or "").lower()
        ]
        if matching_inds:
            st.write(f"找到 {len(matching_inds)} 个匹配 Indicator：")
            
            # Create clickable list with selectbox
            ind_options = ["(选择 Indicator)"] + [f"{ind.name} — {ind.id}" for ind in matching_inds[:50]]
            selected_ind_option = st.selectbox("选择 Indicator", ind_options)
            
            if selected_ind_option != "(选择 Indicator)":
                # Extract indicator ID
                ind_id = selected_ind_option.split(" — ")[-1]
                ind = graph.indicators.get(ind_id)
                
                if ind and ind.cell_ids:
                    # Show indicator details
                    st.write(f"**Indicator**: {ind.name}")
                    st.write(f"**值**: {ind.summary_value}  **单位**: {ind.unit or ''}")
                    
                    # Select from indicator's cells
                    cell_options = ["(选择 Cell)"] + ind.cell_ids[:10]
                    selected_cell_option = st.selectbox(f"选择 Cell（{len(ind.cell_ids)}个）", cell_options)
                    
                    if selected_cell_option != "(选择 Cell)":
                        cell_id = selected_cell_option
                        cell = graph.cells.get(cell_id)
                        if cell:
                            st.info(f"Cell值: {cell.value} | 公式: {cell.formula_raw or '无'}")
        else:
            st.write("未找到匹配项")

else:  # 按 Cell ID/值
    cell_search = st.text_input(
        "搜索 Cell（支持：sheet名、row号、value值、formula关键词）", 
        placeholder="如：成本费用 或 row:380 或 建设期"
    )
    
    if cell_search and len(cell_search) >= 2:
        # Parse search keywords
        search_lower = cell_search.lower()
        
        # Filter cells by multiple criteria
        filtered_cells = []
        for cid, cell in graph.cells.items():
            match_score = 0
            
            # 1. Match sheet name
            if search_lower in cell.sheet.lower():
                match_score += 3
            
            # 2. Match row number (if user types "row:380")
            if "row:" in search_lower:
                row_kw = search_lower.replace("row:", "").strip()
                if row_kw.isdigit() and cell.row == int(row_kw):
                    match_score += 5
            
            # 3. Match cell value
            cell_val_str = str(cell.value) if cell.value is not None else ""
            if search_lower in cell_val_str.lower():
                match_score += 2
            
            # 4. Match formula
            if cell.formula_raw and search_lower in cell.formula_raw.lower():
                match_score += 1
            
            # 5. Match indicator name (via cell.indicator_id)
            if cell.indicator_id:
                ind = graph.indicators.get(cell.indicator_id)
                if ind and search_lower in (ind.name or "").lower():
                    match_score += 4
            
            if match_score > 0:
                filtered_cells.append((match_score, cid, cell))
        
        # Sort by match score
        filtered_cells.sort(key=lambda x: -x[0])
        
        if filtered_cells:
            st.write(f"找到 {len(filtered_cells)} 个匹配 Cell（按相关性排序）")
            
            # Display as dataframe for better UX
            display_limit = min(50, len(filtered_cells))
            cell_rows = []
            for score, cid, cell in filtered_cells[:display_limit]:
                ind_name = ""
                if cell.indicator_id:
                    ind = graph.indicators.get(cell.indicator_id)
                    ind_name = ind.name[:30] if ind else ""
                
                cell_rows.append({
                    "Cell ID": cid,
                    "值": str(cell.value)[:20] if cell.value is not None else "",
                    "公式": (cell.formula_raw[:30] if cell.formula_raw else ""),
                    "指标": ind_name,
                    "相关性": score,
                })
            
            st.dataframe(cell_rows, use_container_width=True, hide_index=True)
            
            # Select from filtered cells
            cell_options = ["(选择 Cell)"] + [cid for _, cid, _ in filtered_cells[:display_limit]]
            selected_cell_option = st.selectbox("选择 Cell ID", cell_options)
            
            if selected_cell_option != "(选择 Cell)":
                cell_id = selected_cell_option
                cell = graph.cells.get(cell_id)
                if cell:
                    # Show full cell details
                    ind_name = ""
                    if cell.indicator_id:
                        ind = graph.indicators.get(cell.indicator_id)
                        ind_name = ind.name if ind else ""
                    st.info(f"**Cell**: {cell_id} | **值**: {cell.value} | **公式**: {cell.formula_raw or '无'} | **指标**: {ind_name}")
        else:
            st.write("未找到匹配 Cell")

# ── Manual cell edit ─────────────────────────────────────────────────────────
st.subheader("修改单元格值")

if not cell_id:
    # Allow manual input if no cell selected
    with st.expander("手动输入 Cell ID"):
        cell_id = st.text_input("Cell ID", placeholder="参数输入表_4_I")
        if cell_id:
            cell = graph.cells.get(cell_id)
            if cell:
                st.info(f"Cell值: {cell.value} | 公式: {cell.formula_raw or '无'}")

with st.form("recalc_form"):
    new_value_str = st.text_input("新值", placeholder="5")
    snap_before_name = st.text_input("保存「修改前」快照名称（留空跳过）", value="before")
    snap_after_name = st.text_input("保存「修改后」快照名称（留空跳过）", value="after")
    submitted = st.form_submit_button("执行重算", type="primary")

if submitted and cell_id:
    cell = graph.cells.get(cell_id)
    if cell is None:
        st.error(f"Cell {cell_id!r} 不存在")
    else:
        # Parse new value
        try:
            new_val = float(new_value_str) if "." in new_value_str else int(new_value_str)
        except ValueError:
            new_val = new_value_str

        # Snapshot before
        if snap_before_name.strip():
            snap_b = create_snapshot(graph, task.id, snap_before_name.strip())
            db.save_snapshot(str(uuid.uuid4())[:8], task.id, snap_before_name.strip(), snap_b.filepath)
            st.write(f"快照「{snap_before_name}」已保存：`{snap_b.filepath}`")

        with st.spinner("重算中..."):
            result = recalculate(graph, {cell_id: new_val})

        # Snapshot after
        if snap_after_name.strip():
            snap_a = create_snapshot(graph, task.id, snap_after_name.strip())
            db.save_snapshot(str(uuid.uuid4())[:8], task.id, snap_after_name.strip(), snap_a.filepath)
            st.write(f"快照「{snap_after_name}」已保存：`{snap_a.filepath}`")

        st.success(f"重算完成：{result.affected_count} 个单元格发生变化，{len(result.error_cells)} 个求值失败")

        if result.changed_cells:
            st.subheader("变化单元格（前 100 条）")
            rows = [
                {"Cell ID": c.cell_id, "旧值": c.old_value, "新值": c.new_value, "公式": c.formula or ""}
                for c in result.changed_cells[:100]
            ]
            st.dataframe(rows, use_container_width=True)

        if result.error_cells:
            with st.expander(f"求值失败的单元格 ({len(result.error_cells)})"):
                st.write(result.error_cells[:50])
