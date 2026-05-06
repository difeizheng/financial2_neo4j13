"""Page 2: Interactive graph explorer — hierarchical navigation with search and breadcrumb."""
from __future__ import annotations
import os
import sys

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from financial_kg.storage.json_store import load_graph
from financial_kg.storage.task_db import TaskDB
from financial_kg.viz.graph_viz import (
    build_cell_subgraph,
    build_indicator_cell_graph,
    build_indicator_subgraph,
    build_table_graph,
    build_indicator_graph,
)

st.set_page_config(page_title="图谱浏览", layout="wide")
st.title("🔍 图谱浏览")

# ── Task selector ─────────────────────────────────────────────────────────────
db = TaskDB()
tasks = [t for t in db.list_tasks() if t.status == "done"]

if not tasks:
    st.warning("暂无已解析的任务，请先在「上传解析」页面上传 Excel。")
    st.stop()

task_options = {f"{t.id} — {t.filename}": t for t in tasks}
selected_label = st.selectbox("选择任务", list(task_options.keys()))
task = task_options[selected_label]


@st.cache_resource(show_spinner="加载图谱...")
def _load(task_id: str, output_dir: str):
    cells_path = os.path.join(output_dir, f"{task_id}_cells.json")
    return load_graph(cells_path)


graph = _load(task.id, task.output_dir)
stats = graph.stats()

# ── Create hidden input for receiving graph clicks ─────────────────────────────
st.markdown("""
<input type="hidden" id="kg_clicked_node" value="" />
<script>
// Listen for changes on the hidden input
document.getElementById('kg_clicked_node').addEventListener('change', function(e) {
    // The value will be picked up by Streamlit via st.text_input below
    console.log('Hidden input changed:', e.target.value);
});
</script>
""", unsafe_allow_html=True)

# Invisible text_input to receive node click (key must match hidden input id)
clicked_node_input = st.text_input("", "", key="kg_clicked_node", label_visibility="collapsed")

# ── Handle graph node click ────────────────────────────────────────────────
clicked_node_id = None

# Check hidden input value
if clicked_node_input and clicked_node_input.strip():
    clicked_node_id = clicked_node_input.strip()
    st.session_state["kg_clicked_node"] = ""  # Clear after handling

# Fallback: check URL parameters
elif "kg_node_click" in st.query_params:
    clicked_node_id = st.query_params["kg_node_click"]

if clicked_node_id:
    
    # Determine node type and navigate
    if clicked_node_id in graph.cells:
        cell = graph.cells[clicked_node_id]
        # Find parent indicator and table
        parent_ind = None
        parent_tbl = None
        for ind_id, ind in graph.indicators.items():
            if clicked_node_id in ind.cell_ids:
                parent_ind = ind_id
                for tbl_id, tbl in graph.tables.items():
                    if ind_id in tbl.indicator_ids:
                        parent_tbl = tbl_id
                        break
                break
        
        nav.update({
            "sheet": cell.sheet,
            "table": parent_tbl,
            "indicator": parent_ind,
            "cell": clicked_node_id
        })
    
    elif clicked_node_id in graph.indicators:
        ind = graph.indicators[clicked_node_id]
        # Find parent table
        parent_tbl = None
        for tbl_id, tbl in graph.tables.items():
            if clicked_node_id in tbl.indicator_ids:
                parent_tbl = tbl_id
                break
        
        nav.update({
            "sheet": ind.sheet,
            "table": parent_tbl,
            "indicator": clicked_node_id,
            "cell": None
        })
    
    elif clicked_node_id in graph.tables:
        tbl = graph.tables[clicked_node_id]
        nav.update({
            "sheet": tbl.sheet,
            "table": clicked_node_id,
            "indicator": None,
            "cell": None
        })
    
    # Clear URL parameter to avoid repeated navigation
    st.query_params.clear()
    st.rerun()

# ── Overview metrics ──────────────────────────────────────────────────────────
m_cols = st.columns(6)
m_cols[0].metric("Sheets", len(stats["sheets"]))
m_cols[1].metric("Tables", stats["total_tables"])
m_cols[2].metric("Indicators", stats["total_indicators"])
m_cols[3].metric("Cells", stats["total_cells"])
m_cols[4].metric("公式 Cells", stats["formula_cells"])
unlinked = stats.get("unlinked_cells", 0)
m_cols[5].metric("未关联 Table", f"{unlinked:,}", delta=f"{unlinked/stats['total_cells']*100:.1f}%" if stats["total_cells"] else "")

st.divider()

# ── Navigation state ──────────────────────────────────────────────────────────
_NAV_KEY = f"nav_{task.id}"
if _NAV_KEY not in st.session_state:
    st.session_state[_NAV_KEY] = {"sheet": None, "table": None, "indicator": None, "cell": None}

nav = st.session_state[_NAV_KEY]

# ── Global Search ─────────────────────────────────────────────────────────────
search_query = st.text_input("🔍 全局搜索 (支持 Sheet/Table/Indicator 名称或 Cell ID)", "", key="global_search")

if search_query and len(search_query) >= 2:
    st.markdown("### 📋 搜索结果")
    
    # Search Sheets
    sheet_matches = [s for s in stats["sheets"] if search_query.lower() in s.lower()]
    
    # Search Tables
    table_matches = []
    for tbl_id, tbl in graph.tables.items():
        if search_query.lower() in tbl.name.lower():
            table_matches.append({"id": tbl_id, "name": tbl.name, "sheet": tbl.sheet})
    
    # Search Indicators
    indicator_matches = []
    for ind_id, ind in graph.indicators.items():
        if search_query.lower() in ind.name.lower() or search_query.lower() in ind_id.lower():
            indicator_matches.append({"id": ind_id, "name": ind.name, "sheet": ind.sheet})
    
    # Search Cells
    cell_matches = []
    for cell_id in graph.cells.keys():
        if search_query.lower() in cell_id.lower():
            cell_matches.append(cell_id)
    
    # Display results with clickable buttons
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if sheet_matches:
            st.markdown(f"**Sheets ({len(sheet_matches)})**")
            for sheet in sheet_matches[:10]:
                if st.button(sheet, key=f"search_sheet_{sheet}"):
                    nav.update({"sheet": sheet, "table": None, "indicator": None, "cell": None})
                    st.rerun()
    
    with col2:
        if table_matches:
            st.markdown(f"**Tables ({len(table_matches)})**")
            for match in table_matches[:10]:
                btn_label = f"{match['name'][:25]} ({match['sheet'][:10]})"
                if st.button(btn_label, key=f"search_table_{match['id']}"):
                    nav.update({"sheet": match['sheet'], "table": match['id'], "indicator": None, "cell": None})
                    st.rerun()
    
    with col3:
        if indicator_matches:
            st.markdown(f"**Indicators ({len(indicator_matches)})**")
            for match in indicator_matches[:10]:
                btn_label = f"{match['name'][:25]} ({match['sheet'][:10]})"
                if st.button(btn_label, key=f"search_ind_{match['id']}"):
                    tbl = None
                    for t in graph.tables.values():
                        if match['id'] in t.indicator_ids:
                            tbl = t.id
                            break
                    nav.update({"sheet": match['sheet'], "table": tbl, "indicator": match['id'], "cell": None})
                    st.rerun()
    
    with col4:
        if cell_matches:
            st.markdown(f"**Cells ({len(cell_matches)})**")
            for cell_id in cell_matches[:10]:
                cell = graph.cells.get(cell_id)
                if cell:
                    btn_label = f"{cell_id[-20:]}"
                    if st.button(btn_label, key=f"search_cell_{cell_id}"):
                        nav.update({"sheet": cell.sheet, "cell": cell_id})
                        st.rerun()
    
    if not any([sheet_matches, table_matches, indicator_matches, cell_matches]):
        st.info("未找到匹配的节点")
    
    st.divider()

# ── Breadcrumb Navigation ─────────────────────────────────────────────────────
breadcrumb_parts = []
if nav["sheet"]:
    breadcrumb_parts.append(f"Sheet: {nav['sheet']}")
if nav["table"]:
    tbl = graph.tables.get(nav["table"])
    tbl_name = tbl.name[:20] if tbl else nav["table"][-20:]
    breadcrumb_parts.append(f"Table: {tbl_name}")
if nav["indicator"]:
    ind = graph.indicators.get(nav["indicator"])
    ind_name = ind.name[:20] if ind else nav["indicator"][-20:]
    breadcrumb_parts.append(f"Indicator: {ind_name}")
if nav["cell"]:
    breadcrumb_parts.append(f"Cell: {nav['cell'][-20:]}")

if breadcrumb_parts:
    st.markdown(f"📍 当前位置: **{' > '.join(breadcrumb_parts)}**")
    
    # Quick navigation buttons
    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)
    
    if nav["cell"]:
        if btn_col1.button("⬆️ 返回 Indicator 层", key="nav_up_cell"):
            nav["cell"] = None
            st.rerun()
    
    if nav["indicator"]:
        if btn_col2.button("⬆️ 返回 Table 层", key="nav_up_ind"):
            nav.update({"indicator": None, "cell": None})
            st.rerun()
    
    if nav["table"]:
        if btn_col3.button("⬆️ 返回 Sheet 层", key="nav_up_table"):
            nav.update({"table": None, "indicator": None, "cell": None})
            st.rerun()
    
    if nav["sheet"]:
        if btn_col4.button("⬆️ 返回总览", key="nav_up_sheet"):
            nav.update({"sheet": None, "table": None, "indicator": None, "cell": None})
            st.rerun()
    
    st.divider()

# ── Sidebar navigation ────────────────────────────────────────────────────────
st.sidebar.header("层级导航")
max_nodes = st.sidebar.slider("最大节点数", 50, 2000, 500, 50)

sheets = sorted(stats["sheets"])
sheet_opts = ["(选择 Sheet)"] + sheets
sheet_idx = (sheets.index(nav["sheet"]) + 1) if nav["sheet"] in sheets else 0
new_sheet_raw = st.sidebar.selectbox("Sheet", sheet_opts, index=sheet_idx)
new_sheet = None if new_sheet_raw == "(选择 Sheet)" else new_sheet_raw
if new_sheet != nav["sheet"]:
    nav.update({"sheet": new_sheet, "table": None, "indicator": None, "cell": None})
    st.rerun()

if nav["sheet"]:
    tables_in_sheet = [t for t in graph.tables.values() if t.sheet == nav["sheet"]]
    tbl_ids = [t.id for t in tables_in_sheet]
    tbl_names = [t.name[:30] for t in tables_in_sheet]
    tbl_opts = ["(选择 Table)"] + tbl_names
    tbl_idx = (tbl_ids.index(nav["table"]) + 1) if nav["table"] in tbl_ids else 0
    new_tbl_name = st.sidebar.selectbox("Table", tbl_opts, index=tbl_idx)
    new_tbl = None
    if new_tbl_name != "(选择 Table)":
        matched = [t for t in tables_in_sheet if t.name[:30] == new_tbl_name]
        new_tbl = matched[0].id if matched else None
    if new_tbl != nav["table"]:
        nav.update({"table": new_tbl, "indicator": None, "cell": None})
        st.rerun()

if nav["table"]:
    tbl_obj = graph.tables.get(nav["table"])
    inds_in_table = [graph.indicators[i] for i in (tbl_obj.indicator_ids if tbl_obj else []) if i in graph.indicators]
    ind_ids = [i.id for i in inds_in_table]
    ind_names = [i.name[:30] for i in inds_in_table]
    ind_opts = ["(选择 Indicator)"] + ind_names
    ind_idx = (ind_ids.index(nav["indicator"]) + 1) if nav["indicator"] in ind_ids else 0
    new_ind_name = st.sidebar.selectbox("Indicator", ind_opts, index=ind_idx)
    new_ind = None
    if new_ind_name != "(选择 Indicator)":
        matched = [i for i in inds_in_table if i.name[:30] == new_ind_name]
        new_ind = matched[0].id if matched else None
    if new_ind != nav["indicator"]:
        nav.update({"indicator": new_ind, "cell": None})
        st.rerun()

if nav["indicator"]:
    ind_obj = graph.indicators.get(nav["indicator"])
    cells_in_ind = [graph.cells[c] for c in (ind_obj.cell_ids if ind_obj else []) if c in graph.cells]
    cell_ids = [c.id for c in cells_in_ind]
    cell_opts = ["(选择 Cell)"] + cell_ids
    cell_idx = (cell_ids.index(nav["cell"]) + 1) if nav["cell"] in cell_ids else 0
    new_cell = st.sidebar.selectbox("Cell", cell_opts, index=cell_idx)
    if new_cell == "(选择 Cell)":
        new_cell = None
    if new_cell != nav["cell"]:
        nav["cell"] = new_cell
        st.rerun()

# ── Main area ─────────────────────────────────────────────────────────────────

def _render_html(path: str, height: int = 640) -> None:
    with open(path, encoding="utf-8") as f:
        components.html(f.read(), height=height, scrolling=False)


# Cell level
if nav["cell"]:
    cell = graph.cells[nav["cell"]]
    st.subheader(f"Cell: {nav['cell']}")
    c1, c2, c3 = st.columns(3)
    c1.metric("值", str(cell.value))
    c2.metric("上游依赖", len(cell.dependencies))
    c3.metric("下游被依赖", len(cell.dependents))
    st.write(f"**公式**: `{cell.formula_raw or '无'}`")
    
    # Auto-generate graph
    depth = st.slider("展开深度", 1, 5, 2, key="cell_depth")
    st.caption("💡 **提示**: 点击图谱中的节点可直接跳转到详情页")
    with st.spinner("渲染依赖子图..."):
        _render_html(build_cell_subgraph(graph, nav["cell"], depth=depth), height=500)
    
    # Optional refresh button
    if st.button("🔄 刷新图谱", key="refresh_cell_graph"):
        with st.spinner("重新渲染..."):
            _render_html(build_cell_subgraph(graph, nav["cell"], depth=depth), height=500)

# Indicator level
elif nav["indicator"]:
    ind = graph.indicators[nav["indicator"]]
    st.subheader(f"Indicator: {ind.name}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("分类", ind.category or "—")
    c2.metric("单位", ind.unit or "—")
    val_str = ind.display_value if ind.display_value is not None else str(ind.summary_value or "—")
    c3.metric("汇总值", val_str)
    c4.metric("时间序列点数", len(ind.time_series))
    if ind.formula_readable:
        st.write(f"**公式**: `{ind.formula_readable}`")
    if ind.description:
        st.caption(ind.description)

    # Auto-generate Cell graph
    ind_obj = graph.indicators.get(nav["indicator"])
    cells_in_ind = [graph.cells[c] for c in (ind_obj.cell_ids if ind_obj else []) if c in graph.cells]
    
    cell_count = len(cells_in_ind)
    if cell_count > 100:
        st.info(f"检测到 {cell_count} 个 Cell，已启用增强稳定化模式")
    
    st.caption("💡 **提示**: 点击图谱中的节点可直接跳转到详情页")
    with st.spinner("渲染 Cell 关系图..."):
        _render_html(build_indicator_cell_graph(graph, nav["indicator"]), height=500)
    
    if st.button("🔄 刷新图谱", key="refresh_ind_graph"):
        with st.spinner("重新渲染..."):
            _render_html(build_indicator_cell_graph(graph, nav["indicator"]), height=500)
    
    # Show cell list below the graph
    if cells_in_ind:
        st.divider()
        st.subheader(f"Cell 列表（{len(cells_in_ind)} 个）")
        rows = [
            {
                "ID": c.id,
                "值": c.value,
                "公式": c.formula_raw or "",
                "上游依赖": len(c.dependencies),
                "下游被依赖": len(c.dependents),
            }
            for c in cells_in_ind
        ]
        st.dataframe(rows, use_container_width=True)

# Table level
elif nav["table"]:
    tbl = graph.tables[nav["table"]]
    st.subheader(f"Table: {tbl.name}")
    c1, c2, c3 = st.columns(3)
    c1.metric("类型", tbl.table_type)
    row_range = f"{tbl.data_row_range[0]}–{tbl.data_row_range[-1]}" if tbl.data_row_range else "—"
    c2.metric("行范围", row_range)
    c3.metric("Indicator 数", len(tbl.indicator_ids))

    # Auto-generate Indicator graph
    inds_in_table = [graph.indicators[i] for i in tbl.indicator_ids if i in graph.indicators]
    node_count = len(inds_in_table)
    
    if node_count > 200:
        st.info(f"检测到 {node_count} 个指标，已启用增强稳定化模式")
    
    st.caption("💡 **提示**: 点击图谱中的节点可直接跳转到详情页")
    with st.spinner("渲染指标关系图..."):
        _render_html(build_indicator_subgraph(graph, nav["table"], node_count=node_count), height=500)
    
    if st.button("🔄 刷新图谱", key="refresh_table_graph"):
        with st.spinner("重新渲染..."):
            _render_html(build_indicator_subgraph(graph, nav["table"], node_count=node_count), height=500)
    
    # Show indicator list below the graph
    if inds_in_table:
        st.divider()
        st.subheader(f"Indicator 列表（{len(inds_in_table)} 个）")
        rows = []
        for ind in inds_in_table:
            val_str = ind.display_value if ind.display_value is not None else (
                f"{ind.summary_value:.2f}" if isinstance(ind.summary_value, float)
                else str(ind.summary_value or "")
            )
            rows.append({
                "名称": ind.name,
                "分类": ind.category or "",
                "单位": ind.unit or "",
                "汇总值": val_str,
                "公式": ind.formula_readable or "",
                "时间序列点数": len(ind.time_series),
            })
        st.dataframe(rows, use_container_width=True)

# Sheet level
elif nav["sheet"]:
    st.subheader(f"Sheet: {nav['sheet']}")
    tables_in_sheet = [t for t in graph.tables.values() if t.sheet == nav["sheet"]]
    unlinked_by_sheet = graph.get_unlinked_cells()
    orphan_cells = len(unlinked_by_sheet.get(nav["sheet"], []))

    # Auto-generate Table graph
    if tables_in_sheet:
        st.caption("💡 **提示**: 点击图谱中的节点可直接跳转到详情页")
        with st.spinner("渲染表间关系图..."):
            _render_html(build_table_graph(graph, nav["sheet"]), height=500)
        
        if st.button("🔄 刷新图谱", key="refresh_sheet_graph"):
            with st.spinner("重新渲染..."):
                _render_html(build_table_graph(graph, nav["sheet"]), height=500)
        
        st.divider()
        st.subheader(f"Table 列表（{len(tables_in_sheet)} 个）")
        rows = []
        for tbl in tables_in_sheet:
            row_range = f"{tbl.data_row_range[0]}–{tbl.data_row_range[1]}" if len(tbl.data_row_range) == 2 else "—"
            header_rows_str = ", ".join(str(r) for r in tbl.header_rows) if tbl.header_rows else "—"
            time_col_count = len(tbl.time_period_labels)
            rows.append({
                "名称": tbl.name,
                "类型": tbl.table_type,
                "行范围": row_range,
                "表头行": header_rows_str,
                "时间序列列数": time_col_count,
                "Indicator 数": len(tbl.indicator_ids),
                "上游 Table 数": len(tbl.fed_by),
                "下游 Table 数": len(tbl.feeds_into),
            })
        st.dataframe(rows, use_container_width=True)

    if orphan_cells > 0:
        st.caption(f"未归属 Cell（无 Indicator）: {orphan_cells} 个")

# Overview (no selection)
else:
    # Global graph overview
    st.subheader("📊 全局图谱概览")
    
    with st.expander("展开查看全局图谱（建议最多200节点）", expanded=False):
        st.caption("💡 **提示**: 点击图谱中的节点可直接跳转到详情页")
        col1, col2 = st.columns([3, 1])
        with col1:
            overview_nodes = st.slider("概览节点数", 50, 300, 150, 50, key="overview_nodes")
        with col2:
            if st.button("生成概览图谱", key="gen_overview"):
                with st.spinner("渲染全局图谱（可能需要10-20秒）..."):
                    _render_html(build_indicator_graph(graph, max_nodes=overview_nodes), height=400)
    
    st.divider()
    
    # Quick layer switch buttons
    st.markdown("### 🎯 快速跳转到层级图谱")
    col1, col2 = st.columns(2)
    
    sheets_for_btn = sorted(stats["sheets"])
    if sheets_for_btn:
        selected_sheet_btn = col1.selectbox("选择 Sheet 查看表间关系", sheets_for_btn, key="quick_sheet")
        if col1.button("📊 查看 Sheet 图谱", key="quick_sheet_btn"):
            nav["sheet"] = selected_sheet_btn
            st.rerun()
    
    tables_for_btn = list(graph.tables.keys())[:20]
    if tables_for_btn:
        table_names_btn = [graph.tables[t].name[:30] for t in tables_for_btn]
        selected_table_idx = col2.selectbox("选择 Table 查看指标关系", range(len(tables_for_btn)), format_func=lambda i: table_names_btn[i] if i < len(table_names_btn) else "", key="quick_table")
        if col2.button("📊 查看 Table 图谱", key="quick_table_btn"):
            selected_table_id = tables_for_btn[selected_table_idx]
            tbl = graph.tables[selected_table_id]
            nav.update({"sheet": tbl.sheet, "table": selected_table_id})
            st.rerun()
    
    st.divider()
    
    # Indicator list with pagination
    st.subheader("全量 Indicator 列表")
    
    # Pagination controls
    page_size = 100
    total_inds = len(graph.indicators)
    total_pages = (total_inds // page_size) + 1
    
    col1, col2, col3 = st.columns([2, 1, 1])
    current_page = col1.number_input("页码", min_value=1, max_value=total_pages, value=1, key="ind_page")
    col2.metric("总条数", f"{total_inds:,}")
    col3.metric("当前页", f"{(current_page-1)*page_size+1}-{min(current_page*page_size, total_inds)}")
    
    rows = []
    ind_list = list(graph.indicators.values())
    start_idx = (current_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_inds)
    
    for ind in ind_list[start_idx:end_idx]:
        val_str = ind.display_value if ind.display_value is not None else (
            f"{ind.summary_value:.2f}" if isinstance(ind.summary_value, float)
            else str(ind.summary_value or "")
        )
        rows.append({
            "ID": ind.id,
            "名称": ind.name,
            "分类": ind.category or "",
            "单位": ind.unit or "",
            "汇总值": val_str,
            "Sheet": ind.sheet,
            "时间序列点数": len(ind.time_series),
        })
    
    if rows:
        st.dataframe(rows, use_container_width=True)
        
        # Click indicator to navigate
        st.caption("💡 点击上方表格中的 Indicator ID 可跳转到详情页（功能待实现）")
    else:
        st.info("该任务暂无 Indicator 数据。")

    # Orphan cells summary
    unlinked = graph.get_unlinked_cells()
    total_unlinked = graph.unlinked_cell_count()
    if total_unlinked > 0:
        st.divider()
        st.subheader(f"未关联 Table 的 Cell（共 {total_unlinked:,} 个）")
        orphan_rows = []
        for sheet, cell_ids in sorted(unlinked.items(), key=lambda x: -len(x[1])):
            orphan_rows.append({
                "Sheet": sheet,
                "数量": len(cell_ids),
                "占该 Sheet Cell 比例": f"{len(cell_ids) / sum(1 for c in graph.cells.values() if c.sheet == sheet) * 100:.1f}%",
            })
        st.dataframe(orphan_rows, use_container_width=True)

        if st.checkbox("展开查看孤儿 Cell ID"):
            for sheet, cell_ids in sorted(unlinked.items(), key=lambda x: -len(x[1])):
                st.caption(f"**{sheet}** ({len(cell_ids)} 个)")
                st.text(", ".join(cell_ids[:200]))
                if len(cell_ids) > 200:
                    st.caption(f"... 及其他 {len(cell_ids) - 200} 个")