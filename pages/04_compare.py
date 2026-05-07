"""Page 4: Snapshot comparison with enhanced visualization."""
from __future__ import annotations
import json
import os
import sys

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from financial_kg.storage.json_store import load_graph
from financial_kg.storage.task_db import TaskDB
from financial_kg.engine.snapshot import load_snapshot, diff_snapshots
from financial_kg.viz.propagation_graph import build_propagation_data
from financial_kg.viz.echarts_template import render_propagation_html
from financial_kg.viz.stats_charts import (
    build_sheet_distribution_pie,
    build_indicator_distribution_pie,
    build_change_magnitude_bar,
    build_change_category_histogram,
    build_combined_stats_dashboard,
    create_styled_dataframe,
)
from financial_kg.analysis.change_ranker import (
    rank_changes_by_impact,
    rank_indicator_changes_by_impact,
    get_change_category,
    get_change_color,
)

st.set_page_config(page_title="快照对比", layout="wide")
st.title("📊 快照对比 - 增强版")

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

snaps = db.list_snapshots(task.id)
if len(snaps) < 2:
    st.info("该任务快照不足 2 个，请先在「参数重算」页面创建快照。")
    st.stop()

snap_options = {f"{s.name} ({s.created_at[:19]})": s for s in snaps}

st.markdown("### 🎯 选择快照")
col1, col2 = st.columns(2)
with col1:
    label_a = st.selectbox("快照 A（基准）", list(snap_options.keys()), index=len(snaps) - 1)
with col2:
    label_b = st.selectbox("快照 B（对比）", list(snap_options.keys()), index=0)

rec_a = snap_options[label_a]
rec_b = snap_options[label_b]

auto_compare = st.checkbox("自动对比（选择快照后立即执行）", value=True)

if rec_a.id == rec_b.id:
    st.warning("请选择两个不同的快照")
    st.stop()

if auto_compare or st.button("执行对比", type="primary"):
    with st.spinner("对比中..."):
        snap_a = load_snapshot(rec_a.filepath)
        snap_b = load_snapshot(rec_b.filepath)
        diff = diff_snapshots(snap_a, snap_b, graph)
    
    st.session_state["diff"] = diff
    st.session_state["diff_task_id"] = task.id
    st.session_state["snap_a_name"] = snap_a.name
    st.session_state["snap_b_name"] = snap_b.name

diff = st.session_state.get("diff")
if diff is None or st.session_state.get("diff_task_id") != task.id:
    st.stop()

snap_a_name = st.session_state.get("snap_a_name", "快照A")
snap_b_name = st.session_state.get("snap_b_name", "快照B")

st.success(f"✅ 对比完成：{snap_a_name} vs {snap_b_name}")

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 汇总概览",
    "🎯 关键变化",
    "📈 统计分析",
    "🔍 详细分析"
])

with tab1:
    st.markdown("### 📊 变化汇总")
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("变化单元格数", diff.summary["total_changed_cells"])
    c2.metric("受影响 Indicator", diff.summary["total_changed_indicators"])
    c3.metric("涉及 Sheet", len(diff.summary["sheets_affected"]))
    c4.metric("平均影响深度", "待计算")
    
    if diff.summary["sheets_affected"]:
        st.markdown("**涉及 Sheet：**")
        st.write("、".join(diff.summary["sheets_affected"]))
    
    st.markdown("---")
    
    col_pie1, col_pie2 = st.columns(2)
    with col_pie1:
        fig_sheet = build_sheet_distribution_pie(diff)
        if fig_sheet.data:
            st.plotly_chart(fig_sheet, use_container_width=True)
        else:
            st.info("暂无Sheet分布数据")
    
    with col_pie2:
        fig_ind = build_indicator_distribution_pie(diff)
        if fig_ind.data:
            st.plotly_chart(fig_ind, use_container_width=True)
        else:
            st.info("暂无Indicator分布数据")

with tab2:
    st.markdown("### 🎯 关键变化点（按影响范围排序）")
    
    ranked_cells = rank_changes_by_impact(diff, graph, top_n=20)
    ranked_indicators = rank_indicator_changes_by_impact(diff, graph, top_n=20)
    
    st.markdown("#### 📌 Top 10 变化单元格")
    cell_rows = []
    for r in ranked_cells[:10]:
        downstream_info = f"影响 {r.downstream_count} 个下游单元格"
        pct_info = f"{r.change_pct:.1f}%" if r.change_pct else "N/A"
        cat = get_change_category(r.change_pct)
        cat_label = {"critical": "关键", "major": "重大", "moderate": "中等", "minor": "轻微"}
        
        cell_rows.append({
            "Cell ID": r.cell_id.split("_", 1)[-1] if "_" in r.cell_id else r.cell_id,
            "Sheet": r.sheet,
            "旧值": r.old_value,
            "新值": r.new_value,
            "变化幅度": pct_info,
            "影响程度": cat_label.get(cat, "轻微"),
            "下游影响": downstream_info,
            "Indicator": r.indicator_name or "",
        })
    
    if cell_rows:
        df_cells = pd.DataFrame(cell_rows)
        st.dataframe(
            df_cells,
            use_container_width=True,
            height=300,
        )
    else:
        st.info("暂无关键变化单元格")
    
    st.markdown("#### 📌 Top 10 变化 Indicator")
    ind_rows = []
    for r in ranked_indicators[:10]:
        pct_info = f"{r.change_pct:.1f}%" if r.change_pct else "N/A"
        cat = get_change_category(r.change_pct)
        cat_label = {"critical": "关键", "major": "重大", "moderate": "中等", "minor": "轻微"}
        
        ind_rows.append({
            "Indicator": r.indicator_name[:50],
            "Sheet": r.sheet,
            "旧汇总值": r.old_summary,
            "新汇总值": r.new_summary,
            "变化幅度": pct_info,
            "影响程度": cat_label.get(cat, "轻微"),
            "变化单元格数": r.changed_cell_count,
            "影响评分": f"{r.impact_score:.1f}",
        })
    
    if ind_rows:
        df_ind = pd.DataFrame(ind_rows)
        st.dataframe(
            df_ind,
            use_container_width=True,
            height=300,
        )
    else:
        st.info("暂无关键变化Indicator")

with tab3:
    st.markdown("### 📈 统计分析图表")
    
    col_bar1, col_bar2 = st.columns(2)
    with col_bar1:
        st.markdown("#### 变化幅度 Top 10 (Indicator)")
        fig_bar_ind = build_change_magnitude_bar(diff, top_n=10, by_indicator=True)
        if fig_bar_ind.data:
            st.plotly_chart(fig_bar_ind, use_container_width=True)
    
    with col_bar2:
        st.markdown("#### 变化幅度 Top 10 (Cell)")
        fig_bar_cell = build_change_magnitude_bar(diff, top_n=10, by_indicator=False)
        if fig_bar_cell.data:
            st.plotly_chart(fig_bar_cell, use_container_width=True)
    
    st.markdown("---")
    st.markdown("#### 变化类别分布")
    fig_hist = build_change_category_histogram(diff)
    if fig_hist.data:
        st.plotly_chart(fig_hist, use_container_width=True)
    
    st.markdown("---")
    st.markdown("#### 综合统计仪表板")
    fig_combined = build_combined_stats_dashboard(diff)
    if fig_combined.data:
        st.plotly_chart(fig_combined, use_container_width=True)

with tab4:
    st.markdown("### 🔍 详细变化分析")
    
    if diff.affected_indicators:
        st.markdown("#### 📋 受影响 Indicator（完整列表）")
        
        col_sheet, col_name, col_cat = st.columns(3)
        with col_sheet:
            all_sheets = sorted({i["sheet"] for i in diff.affected_indicators if i.get("sheet")})
            selected_sheets = st.multiselect("按 Sheet 筛选", all_sheets, default=[])
        with col_name:
            ind_search = st.text_input("搜索名称", placeholder="输入关键词...")
        with col_cat:
            cat_options = ["全部", "关键", "重大", "中等", "轻微"]
            selected_cat = st.selectbox("按影响程度筛选", cat_options)
        
        filtered_indicators = diff.affected_indicators
        if selected_sheets:
            filtered_indicators = [i for i in filtered_indicators if i["sheet"] in selected_sheets]
        if ind_search:
            keyword = ind_search.lower()
            filtered_indicators = [i for i in filtered_indicators if keyword in i["name"].lower()]
        if selected_cat != "全部":
            cat_map = {"关键": "critical", "重大": "major", "中等": "moderate", "轻微": "minor"}
            target_cat = cat_map[selected_cat]
            filtered_indicators = [
                i for i in filtered_indicators
                if get_change_category(
                    rank_indicator_changes_by_impact(diff, graph).__getitem__(0).change_pct
                ) == target_cat
            ]
        
        rows = []
        ranked_all = rank_indicator_changes_by_impact(diff, graph)
        ranked_dict = {r.indicator_id: r for r in ranked_all}
        
        for i in filtered_indicators:
            r = ranked_dict.get(i["id"])
            if r:
                pct_info = f"{r.change_pct:.1f}%" if r.change_pct else "N/A"
                cat = get_change_category(r.change_pct)
                cat_label = {"critical": "关键", "major": "重大", "moderate": "中等", "minor": "轻微"}
            else:
                pct_info = "N/A"
                cat_label_val = "轻微"
            
            rows.append({
                "Indicator": i["name"],
                "Sheet": i["sheet"],
                "旧汇总值": i["old_summary"],
                "新汇总值": i["new_summary"],
                "变化幅度": pct_info,
                "影响程度": cat_label.get(cat, "轻微") if r else "轻微",
                "变化单元格数": i["changed_cell_count"],
            })
        
        if rows:
            df_ind_full = pd.DataFrame(rows)
            st.dataframe(df_ind_full, use_container_width=True)
            st.caption(f"筛选结果：{len(rows)} / {len(diff.affected_indicators)} 个 Indicator")
        else:
            st.info("无匹配的Indicator")
    
    if diff.changed_cells:
        with st.expander(f"📄 变化单元格明细（共 {len(diff.changed_cells)} 条，显示前 200）"):
            rows = []
            ranked_cells_all = rank_changes_by_impact(diff, graph)
            ranked_dict_cells = {r.cell_id: r for r in ranked_cells_all}
            
            for c in diff.changed_cells[:200]:
                r = ranked_dict_cells.get(c["id"])
                if r:
                    pct_info = f"{r.change_pct:.1f}%" if r.change_pct else "N/A"
                    cat = get_change_category(r.change_pct)
                    cat_label = {"critical": "关键", "major": "重大", "moderate": "中等", "minor": "轻微"}
                else:
                    pct_info = "N/A"
                    cat_label_val = "轻微"
                
                rows.append({
                    "Cell ID": c["id"].split("_", 1)[-1] if "_" in c["id"] else c["id"],
                    "Sheet": c["sheet"],
                    "旧值": c["old"],
                    "新值": c["new"],
                    "变化幅度": pct_info,
                    "影响程度": cat_label.get(cat, "轻微") if r else "轻微",
                    "公式": c["formula"] or "",
                })
            
            if rows:
                df_cells_full = pd.DataFrame(rows)
                st.dataframe(df_cells_full, use_container_width=True)
    
    st.markdown("---")
    st.markdown("### 🔗 变化传播图")
    
    if diff.changed_cells:
        ranked_for_prop = rank_changes_by_impact(diff, graph, top_n=50)
        
        cell_search = st.text_input("搜索传播起点", placeholder="输入 Cell ID、Sheet 名或值...")
        if cell_search:
            kw = cell_search.lower()
            candidates = [
                r for r in ranked_for_prop
                if kw in r.cell_id.lower()
                or kw in r.sheet.lower()
                or kw in str(r.old_value).lower()
                or kw in str(r.new_value).lower()
            ]
        else:
            candidates = ranked_for_prop
        
        cell_options = {
            f"{r.cell_id.split('_', 1)[-1]} ({r.sheet}) {r.old_value} → {r.new_value} | 影响{r.downstream_count}个": r.cell_id
            for r in candidates[:50]
        }
        
        if not cell_options:
            st.warning("无匹配的变化单元格，请调整搜索条件")
        else:
            root_id = cell_options[st.selectbox("选择传播起点", list(cell_options.keys()))]
            if cell_search and len(candidates) > 50:
                st.caption(f"匹配 {len(candidates)} 个，显示前 50 个")
            
            col_d, col_s = st.columns(2)
            max_depth = col_d.slider("最大传播深度", 1, 15, 8)
            max_nodes = col_s.slider("最大节点数", 100, 2000, 500, 100)
            
            if st.button("生成传播图", type="primary"):
                with st.spinner("构建传播图..."):
                    data = build_propagation_data(graph, diff, root_id, max_depth, max_nodes)
                    html = render_propagation_html(
                        json.dumps(data, ensure_ascii=False, default=str)
                    )
                st.session_state["prop_html"] = html
                st.session_state["prop_truncated"] = data["stats"]["truncated"]
                st.session_state["prop_nodes"] = data["stats"]["total_nodes"]
            
            if "prop_html" in st.session_state:
                if st.session_state.get("prop_truncated"):
                    st.warning(f"图谱已截断至 {st.session_state['prop_nodes']} 个节点（下游更多）")
                components.html(st.session_state["prop_html"], height=780, scrolling=False)