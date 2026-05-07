"""Page 3: Parameter modification and incremental recalculation - Complete refactor."""
from __future__ import annotations
import os
import sys
import uuid
import streamlit as st
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from financial_kg.storage.json_store import load_graph
from financial_kg.storage.task_db import TaskDB
from financial_kg.engine.recalculator import recalculate
from financial_kg.engine.snapshot import create_snapshot
from financial_kg.llm.category_classifier import INDICATOR_CATEGORIES

st.set_page_config(page_title="参数重算", layout="wide")
st.title("⚙️ 参数修改 & 增量重算")

# ── Initialize database (BEFORE function definitions) ─────────────────────────────
db = TaskDB()

# ── Helper functions (defined BEFORE use) ────────────────────────────────────────
def _execute_recalc(graph, task, updates, snap_before_name, snap_after_name):
    """Execute recalculation with snapshots and display results."""
    
    # Snapshot before
    if snap_before_name.strip():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        snap_name_auto = f"{snap_before_name.strip()}-{timestamp}"
        snap_b = create_snapshot(graph, task.id, snap_name_auto)
        db.save_snapshot(str(uuid.uuid4())[:8], task.id, snap_name_auto, snap_b.filepath)
        st.toast(f"快照「{snap_name_auto}」已保存", icon="📸")
    
    # Recalculate
    with st.spinner("重算中..."):
        result = recalculate(graph, updates)
    
    # Snapshot after
    if snap_after_name.strip():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        snap_name_auto = f"{snap_after_name.strip()}-{timestamp}"
        snap_a = create_snapshot(graph, task.id, snap_name_auto)
        db.save_snapshot(str(uuid.uuid4())[:8], task.id, snap_name_auto, snap_a.filepath)
        st.toast(f"快照「{snap_name_auto}」已保存", icon="📸")
    
    # Save result to session state
    st.session_state["last_recalc_result"] = result
    
    # Show success message
    st.success(f"✅ 重算完成：{result.affected_count} 个单元格变化，{len(result.error_cells)} 个求值失败")
    
    # Rerun to refresh comparison tab
    st.rerun()

def _get_downstream_chain(graph, cell_id, depth=3):
    """Get downstream dependency chain with depth limit."""
    chain = []
    visited = set()
    
    def traverse(cid, level):
        if level > depth or cid in visited:
            return
        visited.add(cid)
        
        cell = graph.cells.get(cid)
        if cell and cell.dependents:
            for dep_id in cell.dependents:
                chain.append((dep_id, level))
                traverse(dep_id, level + 1)
    
    traverse(cell_id, 1)
    return chain

# ── Task selection ─────────────────────────────────────────────────────────────
tasks = [t for t in db.list_tasks() if t.status == "done"]

if not tasks:
    st.warning("暂无已解析的任务。")
    st.stop()

task_options = {f"{t.id} — {t.filename}": t for t in tasks}
selected_label = st.selectbox("选择任务", list(task_options.keys()), key="task_select")
task = task_options[selected_label]

@st.cache_resource(show_spinner="加载图谱...")
def _load(task_id: str, output_dir: str):
    cells_path = os.path.join(output_dir, f"{task_id}_cells.json")
    return load_graph(cells_path)

graph = _load(task.id, task.output_dir)

# ── Identify ALL cells (not just parameters) for filtering ─────────────────────
def get_all_cells_with_filters():
    """Get all cells with metadata for filtering (name, value_type, formula status)."""
    cells_data = []
    
    for cell_id, cell in graph.cells.items():
        # Determine value type
        value_type = "数值型" if isinstance(cell.value, (int, float)) else "文本型"
        
        # Get indicator name
        ind_name = ""
        if cell.indicator_id:
            ind = graph.indicators.get(cell.indicator_id)
            ind_name = ind.name if ind else ""
        
        cells_data.append({
            "cell_id": cell_id,
            "indicator_name": ind_name,
            "value": cell.value,
            "value_type": value_type,
            "has_formula": bool(cell.formula_raw),
            "formula": cell.formula_raw,
            "sheet": cell.sheet,
            "row": cell.row,
            "col": cell.col,
            "unit": "",
        })
        
        # Add unit from indicator
        if cell.indicator_id:
            ind = graph.indicators.get(cell.indicator_id)
            if ind:
                cells_data[-1]["unit"] = ind.unit or ""
    
    return cells_data

all_cells_data = get_all_cells_with_filters()

# ── Categorize cells for display ────────────────────────────────────────────────
def categorize_cell_by_indicator(cell_data):
    """Assign cell to category based on its indicator name."""
    ind_name = cell_data["indicator_name"]
    for category, keywords in INDICATOR_CATEGORIES.items():
        for kw in keywords:
            if kw.lower() in (ind_name or "").lower():
                return category
    return "其他类"

# ── Left panel: Parameter quick view with filters ───────────────────────────────
st.markdown("---")
st.markdown("### 📋 参数快览 & 快速修改")

col_left, col_right = st.columns([1, 2])

with col_left:
    st.markdown("**筛选参数单元格**")
    
    # Compact filter controls in one row
    col_search, col_type1, col_type2 = st.columns([2, 1, 1])
    
    with col_search:
        name_filter = st.text_input(
            "名称搜索",
            placeholder="如：营业成本、利率",
            key="param_name_filter",
            label_visibility="collapsed"
        )
    
    with col_type1:
        value_type_filter = st.selectbox(
            "值类型",
            ["全部", "数值型", "文本型"],
            key="param_value_type_filter",
            label_visibility="collapsed"
        )
    
    with col_type2:
        formula_filter = st.selectbox(
            "公式类型",
            ["全部", "无公式(参数)", "有公式(计算)"],
            key="param_formula_filter",
            label_visibility="collapsed"
        )
    
    # Category filter (below the row filters)
    filter_cat = st.selectbox(
        "分类筛选",
        ["全部"] + list(INDICATOR_CATEGORIES.keys()),
        key="param_cat_filter"
    )
    
    # Apply filters to cells
    filtered_cells = []
    for cell_data in all_cells_data:
        # Name filter
        if name_filter and len(name_filter) >= 2:
            search_lower = name_filter.lower()
            if search_lower not in (cell_data["indicator_name"] or "").lower() and \
               search_lower not in cell_data["cell_id"].lower() and \
               search_lower not in str(cell_data["value"]).lower():
                continue
        
        # Value type filter
        if value_type_filter != "全部" and cell_data["value_type"] != value_type_filter:
            continue
        
        # Formula filter
        if formula_filter == "无公式(参数)" and cell_data["has_formula"]:
            continue
        if formula_filter == "有公式(计算)" and not cell_data["has_formula"]:
            continue
        
        # Category filter
        if filter_cat != "全部":
            cell_category = categorize_cell_by_indicator(cell_data)
            if cell_category != filter_cat:
                continue
        
        filtered_cells.append(cell_data)
    
    # Display filtered cells grouped by category
    st.markdown(f"**找到 {len(filtered_cells)} 个单元格**")
    
    # Group filtered cells by category for display
    categorized_filtered = {}
    for cell_data in filtered_cells:
        category = categorize_cell_by_indicator(cell_data)
        if category not in categorized_filtered:
            categorized_filtered[category] = []
        categorized_filtered[category].append(cell_data)
    
    selected_params = st.session_state.get("selected_params", {})
    
    for category, cells in sorted(categorized_filtered.items()):
        with st.expander(f"📊 {category} ({len(cells)}个)", expanded=(len(cells) <= 5)):
            for cell_data in cells[:10]:
                cell_id = cell_data["cell_id"]
                current_val = cell_data["value"]
                ind_name = cell_data["indicator_name"]
                unit = cell_data["unit"]
                has_formula = cell_data["has_formula"]
                
                # Show cell info
                st.markdown(f"**{ind_name or cell_id}** ({unit})")
                st.caption(f"Cell: {cell_id} | 类型: {cell_data['value_type']} | 公式: {'是' if has_formula else '无'}")
                
                # Only allow modification for non-formula cells
                if not has_formula:
                    # Input for quick modification
                    new_val_input = st.text_input(
                        f"当前值: {current_val}",
                        value=str(current_val) if current_val is not None else "",
                        key=f"param_{cell_id}",
                        placeholder="输入新值",
                    )
                    
                    # Checkbox for batch selection
                    batch_select = st.checkbox(
                        "批量修改",
                        key=f"batch_{cell_id}",
                        value=selected_params.get(cell_id, False),
                    )
                    if batch_select:
                        selected_params[cell_id] = new_val_input
                    else:
                        selected_params.pop(cell_id, None)
                else:
                    # Formula cells: show formula but no modification
                    st.info(f"公式: `{cell_data['formula']}`")
                    st.caption("⚠️ 公式单元格不建议直接修改，请在右侧搜索标签页查看依赖关系")
                
                st.session_state["selected_params"] = selected_params
    
    # Batch modification button
    st.markdown("---")
    batch_count = len(selected_params)
    st.markdown(f"**已选择 {batch_count} 个参数用于批量修改**")
    
    if batch_count > 0:
        with st.form("batch_recalc"):
            batch_mode = st.radio("批量修改模式", ["逐个输入值", "统一变化幅度 (%)"], horizontal=True)
            
            if batch_mode == "统一变化幅度 (%)":
                batch_change_pct = st.number_input("变化幅度 (%)", value=10.0, step=5.0)
            
            batch_snap_before = st.text_input("快照名称（修改前）", value="batch_before")
            batch_snap_after = st.text_input("快照名称（修改后）", value="batch_after")
            
            batch_submit = st.form_submit_button("🚀 执行批量重算", type="primary")
            
            if batch_submit:
                updates = {}
                for cell_id, new_val_str in selected_params.items():
                    if batch_mode == "逐个输入值":
                        try:
                            new_val = float(new_val_str) if "." in new_val_str else int(new_val_str)
                            updates[cell_id] = new_val
                        except ValueError:
                            updates[cell_id] = new_val_str
                    else:
                        cell = graph.cells.get(cell_id)
                        if cell and isinstance(cell.value, (int, float)):
                            updates[cell_id] = cell.value * (1 + batch_change_pct / 100)
                
                # Execute batch recalculation
                if updates:
                    _execute_recalc(graph, task, updates, batch_snap_before, batch_snap_after)
                    st.session_state["selected_params"] = {}

# ── Right panel: Search & Compare ───────────────────────────────────────────────
with col_right:
    st.markdown("### 🔍 搜索 & 对比视图")
    
    tab_search, tab_compare = st.tabs(["搜索参数", "对比结果"])
    
    # ── Tab: Search ──────────────────────────────────────────────────────────────
    with tab_search:
        search_mode = st.radio("搜索方式", ["按指标名称", "按单元格ID/值"], horizontal=True, key="search_mode")
        search_kw = st.text_input("搜索关键词", placeholder="如：营业收入、row:380、建设期", key="search_input")
        
        if search_kw and len(search_kw) >= 2:
            search_lower = search_kw.lower()
            matching_results = []
            
            if search_mode == "按指标名称":
                for ind_id, ind in graph.indicators.items():
                    if search_lower in (ind.name or "").lower():
                        for cell_id in ind.cell_ids:
                            cell = graph.cells.get(cell_id)
                            if cell and not cell.formula_raw:
                                matching_results.append({
                                    "cell_id": cell_id,
                                    "indicator": ind.name,
                                    "value": cell.value,
                                    "sheet": cell.sheet,
                                    "row": cell.row,
                                })
            else:
                for cid, cell in graph.cells.items():
                    if not cell.formula_raw:
                        match_score = 0
                        
                        if search_lower in cell.sheet.lower():
                            match_score += 3
                        if "row:" in search_lower:
                            row_kw = search_lower.replace("row:", "").strip()
                            if row_kw.isdigit() and cell.row == int(row_kw):
                                match_score += 5
                        cell_val_str = str(cell.value) if cell.value is not None else ""
                        if search_lower in cell_val_str.lower():
                            match_score += 2
                        if cell.indicator_id:
                            ind = graph.indicators.get(cell.indicator_id)
                            if ind and search_lower in (ind.name or "").lower():
                                match_score += 4
                        
                        if match_score > 0:
                            ind_name = ""
                            if cell.indicator_id:
                                ind = graph.indicators.get(cell.indicator_id)
                                ind_name = ind.name if ind else ""
                            matching_results.append({
                                "cell_id": cid,
                                "indicator": ind_name,
                                "value": cell.value,
                                "sheet": cell.sheet,
                                "row": cell.row,
                                "score": match_score,
                            })
                
                matching_results.sort(key=lambda x: -x.get("score", 0))
            
            if matching_results:
                st.markdown(f"找到 **{len(matching_results)}** 个参数单元格")
                
                # Pagination
                page_size = 20
                total_pages = (len(matching_results) - 1) // page_size + 1
                page_num = st.number_input("页码", min_value=1, max_value=total_pages, value=1, key="search_page")
                
                start_idx = (page_num - 1) * page_size
                end_idx = start_idx + page_size
                
                for result in matching_results[start_idx:end_idx]:
                    with st.container():
                        col_info, col_action = st.columns([3, 1])
                        
                        with col_info:
                            st.markdown(f"**{result['indicator']}** — {result['cell_id']}")
                            st.caption(f"Sheet: {result['sheet']} | Row: {result['row']} | 当前值: {result['value']}")
                        
                        with col_action:
                            quick_modify = st.button("修改", key=f"modify_{result['cell_id']}")
                            if quick_modify:
                                st.session_state["quick_modify_cell"] = result['cell_id']
                                st.rerun()
            else:
                st.info("未找到匹配的参数单元格")
        
        # Quick modify modal
        if "quick_modify_cell" in st.session_state:
            cell_id = st.session_state["quick_modify_cell"]
            cell = graph.cells.get(cell_id)
            
            if cell:
                st.markdown("---")
                st.markdown(f"### 快速修改: {cell_id}")
                st.markdown(f"**当前值**: {cell.value}")
                
                with st.form("quick_recalc_form"):
                    quick_new_val = st.text_input("新值", placeholder="输入新值", key="quick_new_val_input")
                    quick_snap_before = st.text_input("快照（修改前）", value="quick_before")
                    quick_snap_after = st.text_input("快照（修改后）", value="quick_after")
                    
                    quick_submit = st.form_submit_button("✅ 执行修改", type="primary")
                    quick_cancel = st.form_submit_button("❌ 取消")
                    
                    if quick_submit and quick_new_val:
                        try:
                            new_val = float(quick_new_val) if "." in quick_new_val else int(quick_new_val)
                        except ValueError:
                            new_val = quick_new_val
                        
                        updates = {cell_id: new_val}
                        _execute_recalc(graph, task, updates, quick_snap_before, quick_snap_after)
                        st.session_state.pop("quick_modify_cell", None)
                    
                    if quick_cancel:
                        st.session_state.pop("quick_modify_cell", None)
    
    # ── Tab: Compare ─────────────────────────────────────────────────────────────
    with tab_compare:
        if "last_recalc_result" in st.session_state:
            result = st.session_state["last_recalc_result"]
            
            # Statistics
            st.markdown("#### 📊 变化统计")
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            with col_stat1:
                st.metric("影响单元格", result.affected_count)
            with col_stat2:
                st.metric("求值失败", len(result.error_cells))
            with col_stat3:
                st.metric("成功率", f"{result.affected_count / max(1, result.affected_count + len(result.error_cells)) * 100:.1f}%")
            
            st.markdown("---")
            
            # Before/After comparison table
            if result.changed_cells:
                st.markdown("#### 📝 Before/After 对比表")
                
                comparison_rows = []
                for change in result.changed_cells[:50]:
                    change_pct = ""
                    if isinstance(change.old_value, (int, float)) and isinstance(change.new_value, (int, float)) and change.old_value != 0:
                        change_pct = f"{((change.new_value - change.old_value) / abs(change.old_value) * 100):.1f}%"
                    
                    comparison_rows.append({
                        "Cell ID": change.cell_id,
                        "旧值": change.old_value,
                        "新值": change.new_value,
                        "变化": change_pct,
                        "公式": change.formula or "",
                    })
                
                st.dataframe(comparison_rows, use_container_width=True, hide_index=True)
                
                # Color-coded highlight
                st.markdown("**变化幅度标记**: 绿色(>5%增长) | 红色(>5%下降) | 灰色(小幅变化)")
            
            # Error cells
            if result.error_cells:
                with st.expander(f"⚠️ 求值失败的单元格 ({len(result.error_cells)})"):
                    for err_cell_id in result.error_cells[:20]:
                        cell = graph.cells.get(err_cell_id)
                        if cell:
                            st.markdown(f"- **{err_cell_id}** | 公式: `{cell.formula_raw}`")
            
            # Dependency propagation (simplified tree view)
            st.markdown("---")
            st.markdown("#### 🌊 依赖传播路径（简化）")
            st.info("点击对比表中的单元格，查看其下游影响链")
            
            selected_cell_for_tree = st.selectbox(
                "选择单元格查看影响链",
                ["(选择)"] + [change.cell_id for change in result.changed_cells[:20]],
                key="tree_cell_select"
            )
            
            if selected_cell_for_tree != "(选择)":
                downstream = _get_downstream_chain(graph, selected_cell_for_tree, depth=3)
                
                if downstream:
                    st.markdown(f"**{selected_cell_for_tree}** → 影响以下单元格:")
                    for i, (cell_id, level) in enumerate(downstream):
                        indent = "　" * level
                        cell = graph.cells.get(cell_id)
                        ind_name = ""
                        if cell and cell.indicator_id:
                            ind = graph.indicators.get(cell.indicator_id)
                            ind_name = ind.name if ind else ""
                        st.markdown(f"{indent}→ **{cell_id}** ({ind_name})")
                else:
                    st.info("该单元格无下游依赖")
        
        else:
            st.info("尚未执行重算，请在左侧面板或搜索标签页修改参数")