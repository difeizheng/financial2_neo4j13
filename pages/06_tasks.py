"""Page 6: Task history management."""
from __future__ import annotations
import os
import sys
import shutil
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from financial_kg.storage.task_db import TaskDB
from financial_kg.storage.json_store import load_graph

st.set_page_config(page_title="历史任务", layout="wide", page_icon="📋")

db = TaskDB()

st.title("📋 历史任务管理")

st.markdown("管理所有解析任务，查看详情、删除任务、加载到内存。")

st.divider()

tasks = db.list_tasks()

if not tasks:
    st.info("📭 暂无历史任务，请先上传并解析 Excel 文件。")
    st.page_link("pages/01_upload.py", label="前往上传页面", icon="📁")
else:
    status_counts = {"done": 0, "running": 0, "error": 0, "pending": 0}
    for t in tasks:
        status_counts[t.status] = status_counts.get(t.status, 0) + 1
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("✅ 已完成", status_counts["done"])
    col2.metric("⏳ 运行中", status_counts["running"])
    col3.metric("❌ 失败", status_counts["error"])
    col4.metric("🕐 待处理", status_counts["pending"])
    
    st.divider()
    
    status_filter = st.selectbox(
        "筛选状态",
        ["全部", "done", "running", "error", "pending"],
        format_func=lambda x: {"全部": "全部", "done": "✅ 已完成", "running": "⏳ 运行中", "error": "❌ 失败", "pending": "🕐 待处理"}.get(x, x),
    )
    
    filtered_tasks = tasks if status_filter == "全部" else [t for t in tasks if t.status == status_filter]
    
    if filtered_tasks:
        for t in filtered_tasks:
            icon = {"done": "✅", "running": "⏳", "error": "❌", "pending": "🕐"}.get(t.status, "?")
            
            with st.container():
                col_info, col_actions = st.columns([5, 2])
                
                with col_info:
                    st.subheader(f"{icon} {t.id}")
                    st.caption(f"文件：{t.filename} | 创建时间：{t.created_at[:19]}")
                    
                    if t.status == "done":
                        col_a, col_b, col_c = st.columns(3)
                        col_a.metric("Cell 节点", f"{t.cell_count:,}")
                        col_b.metric("Indicator 节点", f"{t.indicator_count:,}")
                        col_c.metric("Table 节点", f"{t.table_count:,}")
                    elif t.status == "error":
                        st.error(f"错误：{t.error_msg}")
                
                with col_actions:
                    st.markdown("#### 操作")
                    
                    if t.status == "done":
                        if st.button("🔍 加载并浏览图谱", key=f"load_{t.id}", use_container_width=True, type="primary"):
                            cells_path = os.path.join(t.output_dir or "output", f"{t.id}_cells.json")
                            if os.path.exists(cells_path):
                                with st.spinner("加载图谱..."):
                                    graph = load_graph(cells_path)
                                    st.session_state["current_graph"] = graph
                                    st.session_state["current_task_id"] = t.id
                                st.success("✅ 已加载到内存")
                                st.page_link("pages/02_explorer.py", label="前往图谱浏览 →", icon="🔍")
                            else:
                                st.error(f"文件不存在：{cells_path}")
                    
                    if st.button("🗑️ 删除任务", key=f"del_{t.id}", type="secondary", use_container_width=True):
                        st.session_state[f"_confirm_del_{t.id}"] = True
                        st.rerun()
                
                if st.session_state.get(f"_confirm_del_{t.id}"):
                    st.warning(f"⚠️ 确认删除任务 **{t.id}**（{t.filename}）？所有输出文件和快照将被永久删除。")
                    col_c1, col_c2, col_c3 = st.columns([1, 1, 4])
                    if col_c1.button("✅ 确认删除", key=f"confirm_{t.id}", type="primary"):
                        output_dir = t.output_dir or "output"
                        prefix = t.id
                        snapshots_dir = os.path.join("snapshots", t.id)
                        deleted_count = 0
                        
                        for suffix in ["_cells.json", "_indicators.json", "_tables.json"]:
                            fp = os.path.join(output_dir, f"{prefix}{suffix}")
                            if os.path.isfile(fp):
                                os.remove(fp)
                                deleted_count += 1
                        
                        for fp in db.list_snapshot_files(t.id):
                            if os.path.isfile(fp):
                                os.remove(fp)
                                deleted_count += 1
                        
                        if os.path.isdir(snapshots_dir):
                            try:
                                shutil.rmtree(snapshots_dir)
                                deleted_count += 1
                            except OSError:
                                pass
                        
                        db.delete_task(t.id)
                        st.session_state[f"_confirm_del_{t.id}"] = False
                        st.success(f"✅ 已删除任务 {t.id}（{deleted_count} 个文件）")
                        st.rerun()
                    
                    if col_c2.button("❌ 取消", key=f"cancel_{t.id}"):
                        st.session_state[f"_confirm_del_{t.id}"] = False
                        st.rerun()
                
                st.divider()
    else:
        st.info(f"没有符合筛选条件的任务。")