"""Page 7: Neo4j import and management."""
from __future__ import annotations
import os
import sys
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from financial_kg.storage.task_db import TaskDB
from financial_kg.storage.json_store import load_graph
from financial_kg.storage.neo4j_store import Neo4jStore
from financial_kg.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, save_config

st.set_page_config(page_title="Neo4j 导入", layout="wide", page_icon="🗄️")

db = TaskDB()

st.title("🗄️ Neo4j 数据导入")

st.markdown("将已解析的知识图谱导入到 Neo4j 图数据库进行可视化分析。")

st.divider()

tasks = db.list_tasks()
done_tasks = [t for t in tasks if t.status == "done"]

if not done_tasks:
    st.info("📭 暂无已完成的任务可导入，请先上传并解析 Excel 文件。")
    st.page_link("pages/01_upload.py", label="前往上传页面", icon="📁")
else:
    st.subheader("1️⃣ 选择任务")
    
    selected_task_label = st.selectbox(
        "选择要导入的任务",
        [f"{t.id} — {t.filename} ({t.cell_count:,} cells)" for t in done_tasks],
        help="仅显示已完成的任务",
    )
    
    selected_task = next(
        t for t in done_tasks 
        if f"{t.id} — {t.filename} ({t.cell_count:,} cells)" == selected_task_label
    )
    
    st.divider()
    
    st.subheader("2️⃣ Neo4j 连接配置")
    
    with st.container():
        col_uri, col_user, col_pwd = st.columns(3)
        
        neo4j_uri = col_uri.text_input(
            "Neo4j URI",
            value=NEO4J_URI,
            placeholder="bolt://localhost:7687",
            help="Neo4j 服务地址，通常是 bolt://localhost:7687",
        )
        
        neo4j_user = col_user.text_input(
            "用户名",
            value=NEO4J_USER,
            placeholder="neo4j",
        )
        
        neo4j_pwd = col_pwd.text_input(
            "密码",
            value=NEO4J_PASSWORD,
            type="password",
            placeholder="输入密码",
        )
        
        col_save, col_test = st.columns(2)
        
        if col_save.button("💾 保存配置到 .env", use_container_width=True):
            save_config(neo4j_uri=neo4j_uri, neo4j_user=neo4j_user, neo4j_password=neo4j_pwd)
            st.success("✅ 配置已保存到 .env 文件")
        
        if col_test.button("🔌 测试连接", use_container_width=True):
            if not neo4j_pwd.strip():
                st.error("请输入 Neo4j 密码")
            else:
                try:
                    with Neo4jStore(neo4j_uri, neo4j_user, neo4j_pwd) as store:
                        st.success("✅ 连接成功")
                except Exception as e:
                    st.error(f"❌ 连接失败：{e}")
    
    st.divider()
    
    st.subheader("3️⃣ 导入操作")
    
    col_import, col_clear = st.columns(2)
    
    with col_import:
        if st.button("📤 导入到 Neo4j", type="primary", use_container_width=True):
            if not neo4j_pwd.strip():
                st.error("请输入 Neo4j 密码")
            else:
                cells_path = os.path.join(
                    selected_task.output_dir or "output",
                    f"{selected_task.id}_cells.json",
                )
                
                if not os.path.exists(cells_path):
                    st.error(f"❌ 文件不存在：{cells_path}")
                else:
                    try:
                        with st.spinner("加载图谱数据..."):
                            graph = load_graph(cells_path)
                        
                        st.info(f"📊 已加载：{len(graph.cells):,} 个 Cell，{len(graph.indicators):,} 个 Indicator，{len(graph.tables):,} 个 Table")
                        
                        progress_bar = st.progress(0, text="连接 Neo4j...")
                        status_box = st.empty()
                        
                        step_msgs = [
                            "导入 Cell 节点...",
                            "导入 Indicator 节点...",
                            "导入 Table 节点...",
                            "导入 DEPENDS_ON 关系...",
                            "导入 CALCULATES_FROM 关系...",
                            "导入 FEEDS_INTO 关系...",
                            "导入 BELONGS_TO 关系...",
                        ]
                        step_idx = [0]
                        
                        def progress_callback(msg: str) -> None:
                            pct = int((step_idx[0] / len(step_msgs)) * 100)
                            progress_bar.progress(pct, text=msg)
                            status_box.info(f"**步骤 {step_idx[0] + 1}/{len(step_msgs)}：** {msg}")
                            step_idx[0] += 1
                        
                        with Neo4jStore(neo4j_uri, neo4j_user, neo4j_pwd) as store:
                            counts = store.import_graph(
                                graph,
                                task_id=selected_task.id,
                                progress_callback=progress_callback,
                            )
                        
                        progress_bar.progress(100, text="导入完成！")
                        
                        st.balloons()
                        st.success("🎉 Neo4j 导入成功！")
                        
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("Cell 节点", f"{counts.get('cells', 0):,}")
                        col2.metric("Indicator 节点", f"{counts.get('indicators', 0):,}")
                        col3.metric("Table 节点", f"{counts.get('tables', 0):,}")
                        col4.metric("DEPENDS_ON 关系", f"{counts.get('depends_on', 0):,}")
                        
                        st.info(f"💡 提示：你可以在 Neo4j Browser 中查看图谱，访问 {neo4j_uri.replace('bolt://', 'http://').replace('7687', '7474')}")
                        
                    except Exception as e:
                        st.error(f"❌ 导入失败：{e}")
                        with st.expander("查看错误详情"):
                            st.code(str(e), language="text")
    
    with col_clear:
        if st.button("🗑️ 清空数据库", type="secondary", use_container_width=True):
            if not neo4j_pwd.strip():
                st.error("请输入 Neo4j 密码")
            else:
                st.session_state["_neo4j_clear_stage"] = st.session_state.get("_neo4j_clear_stage", 0) + 1
                
                if st.session_state["_neo4j_clear_stage"] == 1:
                    st.warning("⚠️ 第一次确认：此操作将清空 Neo4j 数据库中的所有数据，不可恢复！")
                elif st.session_state["_neo4j_clear_stage"] == 2:
                    st.error("🚨 第二次确认：再次点击将**立即清空数据库**！")
                elif st.session_state["_neo4j_clear_stage"] >= 3:
                    try:
                        with Neo4jStore(neo4j_uri, neo4j_user, neo4j_pwd) as store:
                            store.clear_database()
                        st.success("✅ Neo4j 数据库已清空")
                        st.session_state["_neo4j_clear_stage"] = 0
                    except Exception as e:
                        st.error(f"❌ 清空失败：{e}")
                        st.session_state["_neo4j_clear_stage"] = 0
        
        if st.session_state.get("_neo4j_clear_stage", 0) > 0:
            st.caption(f"确认进度：{st.session_state['_neo4j_clear_stage']}/3")
    
    st.divider()
    
    with st.expander("📚 Neo4j 使用指南", expanded=False):
        st.markdown("""
        **导入后的操作：**
        
        1. **访问 Neo4j Browser**  
           打开 http://localhost:7474，登录后可查看图谱
        
        2. **常用 Cypher 查询**
           ```cypher
           // 查看所有 Cell 节点
           MATCH (c:Cell) RETURN c LIMIT 100
           
           // 查看某个指标的计算依赖
           MATCH (i:Indicator)-[:CALCULATES_FROM]->(c:Cell) 
           WHERE i.name CONTAINS '收入' 
           RETURN i, c
           
           // 查看数据传播链
           MATCH path = (c1:Cell)-[:DEPENDS_ON*]->(c2:Cell) 
           WHERE c1.address = 'Sheet1!A1' 
           RETURN path
           ```
        
        3. **导出图谱可视化**  
           在 Neo4j Browser 中点击节点，右侧可导出为 PNG/JSON
        
        4. **性能优化**  
           - 大图谱建议创建索引：`CREATE INDEX FOR (c:Cell) ON c.address`
           - 查询时添加 LIMIT 避免加载过多数据
        """)