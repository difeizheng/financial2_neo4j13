"""Page 1: Upload and parse an Excel financial model with enhanced UI."""
from __future__ import annotations
import os
import sys
import time
import uuid
import tempfile
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from financial_kg.parser.excel_reader import read_excel
from financial_kg.parser.cell_extractor import build_cell_graph
from financial_kg.parser.indicator_builder import build_indicators
from financial_kg.parser.relationship_builder import infer_relationships
from financial_kg.parser.time_period_annotator import annotate_cell_time_periods
from financial_kg.storage.json_store import save_graph, verify_cell_count
from financial_kg.storage.task_db import TaskDB

st.set_page_config(page_title="上传解析", layout="wide", page_icon="📁")

db = TaskDB()

st.title("📁 上传 Excel 财务模型")

with st.expander("💡 快速开始指南", expanded=False):
    st.markdown("""
    **使用流程：**
    1. 上传 Excel 文件（支持拖拽）
    2. 查看文件预览信息
    3. 配置解析参数（可选）
    4. 点击开始解析，查看实时进度
    5. 查看解析结果统计
    
    **支持格式：** `.xlsx`, `.xls`
    
    **提示：** 大文件解析可能需要几分钟，请耐心等待进度条完成。
    """)

st.divider()

uploaded_file = st.file_uploader(
    "拖拽或点击上传 Excel 文件",
    type=["xlsx", "xls"],
    help="支持 .xlsx 和 .xls 格式",
)

if uploaded_file:
    file_size_kb = uploaded_file.size / 1024
    file_size_str = f"{file_size_kb:.1f} KB" if file_size_kb < 1024 else f"{file_size_kb / 1024:.2f} MB"
    
    st.success(f"✅ 文件已选择：**{uploaded_file.name}** ({file_size_str})")
    
    with st.spinner("预览文件信息..."):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_preview:
                tmp_preview.write(uploaded_file.getvalue())
                preview_path = tmp_preview.name
            
            preview_data = read_excel(preview_path)
            os.unlink(preview_path)
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Sheet 数量", len(preview_data))
            total_cells_preview = sum(len(v) for v in preview_data.values())
            col2.metric("单元格总数", f"{total_cells_preview:,}")
            col3.metric("预计解析时间", f"{total_cells_preview / 5000:.1f}s")
            
            with st.expander("📋 查看 Sheet 详情", expanded=False):
                sheet_info_data = []
                for sheet_name, cells in preview_data.items():
                    formula_cells = sum(1 for c in cells if c.formula_raw)
                    value_cells = len(cells) - formula_cells
                    sheet_info_data.append({
                        "Sheet": sheet_name,
                        "总单元格": len(cells),
                        "公式单元格": formula_cells,
                        "数值单元格": value_cells,
                    })
                st.dataframe(sheet_info_data, use_container_width=True)
                
        except Exception as e:
            st.warning(f"预览失败：{e}")
    
    st.divider()
    
    st.subheader("⚙️ 解析配置")
    
    with st.container():
        col_left, col_right = st.columns([2, 1])
        
        with col_left:
            task_id_input = st.text_input(
                "任务 ID",
                value="",
                placeholder="留空自动生成",
                help="用于标识本次解析任务，可在历史任务中查看",
            )
            
            output_dir_input = st.text_input(
                "输出目录",
                value="output",
                help="解析结果 JSON 文件的保存目录",
            )
        
        with col_right:
            st.info("**解析流程：**\n1️⃣ 读取 Excel\n2️⃣ 构建 Cell 层\n3️⃣ 构建 Indicator 层\n4️⃣ 构建 Table 层\n5️⃣ 标注时间属性\n6️⃣ 保存结果")
    
    st.divider()
    
    if st.button("🚀 开始解析", type="primary", use_container_width=True):
        task_id = task_id_input.strip() if task_id_input.strip() else str(uuid.uuid4())[:8]
        output_dir = output_dir_input.strip() or "output"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        
        db.create_task(task_id, uploaded_file.name, output_dir)
        db.update_task(task_id, status="running")
        
        st.subheader("📊 解析进度")
        
        progress_bar = st.progress(0, text="准备开始...")
        status_container = st.container()
        
        step_names = [
            "读取 Excel 文件",
            "构建 Cell 层图谱",
            "构建 Indicator 层",
            "构建 Table 层",
            "标注时间属性",
            "保存 JSON 结果",
        ]
        
        step_status = ["⏳ 等待", "⏳ 等待", "⏳ 等待", "⏳ 等待", "⏳ 等待", "⏳ 等待"]
        
        def update_step(idx: int, status: str, detail: str = "") -> None:
            step_status[idx] = status
            with status_container:
                for i, name in enumerate(step_names):
                    st.write(f"{step_status[i]} **{name}**")
                if detail:
                    st.caption(detail)
        
        try:
            t0 = time.time()
            
            update_step(0, "🔄 进行中", f"文件：{uploaded_file.name}")
            sheet_cells = read_excel(tmp_path)
            total_raw = sum(len(v) for v in sheet_cells.values())
            progress_bar.progress(15, text=f"完成：{len(sheet_cells)} 个 sheet，{total_raw:,} 个单元格")
            update_step(0, "✅ 完成", f"{len(sheet_cells)} 个 sheet")
            
            update_step(1, "🔄 进行中", "提取单元格、解析公式...")
            graph = build_cell_graph(sheet_cells)
            progress_bar.progress(35, text="Cell 层构建完成")
            update_step(1, "✅ 完成", f"{len(graph.cells):,} 个 Cell 节点")
            
            update_step(2, "🔄 进行中", "识别财务指标...")
            build_indicators(sheet_cells, graph)
            progress_bar.progress(55, text="Indicator 层构建完成")
            update_step(2, "✅ 完成", f"{len(graph.indicators):,} 个 Indicator")
            
            update_step(3, "🔄 进行中", "构建表格关系...")
            infer_relationships(graph)
            progress_bar.progress(75, text="Table 层构建完成")
            update_step(3, "✅ 完成", f"{len(graph.tables):,} 个 Table")
            
            update_step(4, "🔄 进行中", "标注时间周期...")
            annotated = annotate_cell_time_periods(graph)
            progress_bar.progress(85, text=f"时间标注完成")
            update_step(4, "✅ 完成", f"{annotated:,} 个 Cell 已标注")
            
            update_step(5, "🔄 进行中", "保存到 JSON...")
            paths = save_graph(graph, output_dir, task_id=task_id)
            progress_bar.progress(100, text="保存完成")
            update_step(5, "✅ 完成", "JSON 文件已保存")
            
            stats = graph.stats()
            db.update_task(
                task_id,
                status="done",
                cell_count=stats["total_cells"],
                indicator_count=stats["total_indicators"],
                table_count=stats["total_tables"],
                output_dir=output_dir,
            )
            
            elapsed = time.time() - t0
            
            st.balloons()
            st.success(f"🎉 解析完成！总耗时 **{elapsed:.1f}** 秒")
            
            st.subheader("📈 解析结果统计")
            
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Cell 节点", f"{stats['total_cells']:,}")
            col2.metric("Indicator 节点", f"{stats['total_indicators']:,}")
            col3.metric("Table 节点", f"{stats['total_tables']:,}")
            col4.metric("解析速度", f"{total_raw / elapsed:,.0f} cells/s")
            unlinked = stats.get("unlinked_cells", 0)
            unlinked_pct = f"{unlinked / stats['total_cells'] * 100:.1f}%" if stats['total_cells'] else "0%"
            col5.metric("未关联 Cell", f"{unlinked:,}", delta=unlinked_pct)
            
            with st.expander("📂 输出文件详情", expanded=True):
                for layer, path in paths.items():
                    size_kb = os.path.getsize(path) / 1024
                    size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.2f} MB"
                    st.code(f"{layer}: {path} ({size_str})", language="text")
                
                check = verify_cell_count(graph, total_raw)
                status_str = "✅ 一致" if check["match"] else f"⚠️ 差异 {check['diff']:+d}"
                st.info(f"**Cell 数量验证：** {check['actual']:,} / {check['expected']:,}  {status_str}")
            
            st.session_state["current_task_id"] = task_id
            st.session_state["current_graph"] = graph
            
            st.divider()
            col_nav1, col_nav2 = st.columns(2)
            with col_nav1:
                st.page_link("pages/02_explorer.py", label="🔍 前往图谱浏览", icon="🔍")
            with col_nav2:
                st.page_link("pages/05_qa.py", label="💬 前往智能问答", icon="💬")
            
        except Exception as e:
            db.update_task(task_id, status="error", error_msg=str(e))
            st.error(f"❌ 解析失败：{e}")
            with st.expander("查看错误详情"):
                st.code(str(e), language="text")
        finally:
            os.unlink(tmp_path)