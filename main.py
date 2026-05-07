"""Streamlit entry point — financial model knowledge graph explorer."""
import streamlit as st

st.set_page_config(
    page_title="财务模型知识图谱",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📊 财务模型知识图谱系统")

st.markdown("""
欢迎使用财务模型知识图谱系统。请从左侧导航栏选择功能：
""")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("核心功能")
    st.page_link("pages/01_upload.py", label="📁 上传解析 — 上传 Excel，解析为三层知识图谱", icon="📁")
    st.page_link("pages/02_explorer.py", label="🔍 图谱浏览 — 交互式浏览 Cell / Indicator / Table 层", icon="🔍")
    st.page_link("pages/03_recalc.py", label="⚙️ 参数重算 — 修改参数，触发全模型增量重算", icon="⚙️")
    st.page_link("pages/04_compare.py", label="📊 快照对比 — 对比两个快照，查看变化传播链", icon="📊")
    st.page_link("pages/05_qa.py", label="💬 智能问答 — 基于 LLM 的财务问答", icon="💬")

with col2:
    st.subheader("管理与配置")
    st.page_link("pages/06_tasks.py", label="📋 历史任务 — 管理解析任务，查看统计信息", icon="📋")
    st.page_link("pages/07_neo4j.py", label="🗄️ Neo4j 导入 — 导入到图数据库进行可视化分析", icon="🗄️")

st.divider()

with st.expander("💡 快速入门", expanded=False):
    st.markdown("""
    **推荐使用流程：**
    
    1. **上传解析** → 上传 Excel 文件，系统自动解析为三层知识图谱（Cell、Indicator、Table）
    2. **图谱浏览** → 交互式浏览解析结果，查看单元格关系、指标计算逻辑
    3. **参数重算** → 修改关键参数，观察整个模型的联动变化
    4. **快照对比** → 对比不同版本的快照，分析数据传播链路
    5. **智能问答** → 使用自然语言提问，LLM 基于图谱给出财务分析
    
    **高级功能：**
    - 历史任务管理：查看所有解析记录，加载或删除任务
    - Neo4j 导入：将图谱导入图数据库，使用 Cypher 查询进行深度分析
    
    **系统特点：**
    - 三层图谱结构（Cell/Indicator/Table）
    - 自动提取公式依赖关系
    - 时间周期标注
    - 增量重算引擎
    - LLM 智能问答
    """)
