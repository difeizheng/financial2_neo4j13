"""Page 5: LLM-powered financial Q&A."""
from __future__ import annotations
import os
import sys
import re
import io

import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from financial_kg.storage.json_store import load_graph
from financial_kg.storage.task_db import TaskDB
from financial_kg.storage.chat_history_db import ChatHistoryDB
from financial_kg.llm import QAEngine
from financial_kg.config import (
    LLM_BASE_URL, LLM_API_KEY, LLM_MODEL,
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    save_config,
)

st.set_page_config(page_title="智能问答", layout="wide")
st.title("💬 财务模型智能问答")

db = TaskDB()
chat_db = ChatHistoryDB()
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

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("LLM 配置")
    base_url = st.text_input("Base URL", value=LLM_BASE_URL or "https://api.openai.com/v1")
    api_key = st.text_input("API Key", value=LLM_API_KEY or "", type="password")
    model = st.text_input("Model", value=LLM_MODEL or "gpt-4o-mini")
    top_k = st.slider("检索 Indicator 数量 (top-k)", 3, 20, 8)

    st.divider()
    st.header("Neo4j 配置")
    use_neo4j = st.checkbox("启用 Neo4j 图遍历", value=False)
    neo4j_uri = st.text_input("URI", value=NEO4J_URI)
    neo4j_user = st.text_input("User", value=NEO4J_USER)
    neo4j_pwd = st.text_input("Password", value=NEO4J_PASSWORD, type="password")

    st.divider()
    if st.button("保存配置到 .env", type="secondary"):
        save_config(
            llm_base_url=base_url,
            llm_api_key=api_key,
            llm_model=model,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_pwd,
        )
        st.success("配置已保存到 .env 文件")


@st.cache_resource(show_spinner="连接 Neo4j...")
def _get_neo4j(uri: str, user: str, pwd: str):
    try:
        from financial_kg.storage.neo4j_store import Neo4jStore
        return Neo4jStore(uri, user, pwd)
    except Exception as e:
        st.warning(f"Neo4j 连接失败：{e}")
        return None


neo4j_store = None
if use_neo4j and neo4j_pwd.strip():
    neo4j_store = _get_neo4j(neo4j_uri, neo4j_user, neo4j_pwd)


@st.cache_resource(show_spinner="初始化问答引擎...")
def _get_engine(task_id: str, _graph, _neo4j, base_url: str, api_key: str, model: str):
    return QAEngine(
        graph=_graph,
        neo4j_store=_neo4j,
        llm_base_url=base_url,
        llm_api_key=api_key,
        llm_model=model,
        task_id=task_id,
    )


engine = _get_engine(task.id, graph, neo4j_store, base_url, api_key, model)

# ── Chat History Persistence ────────────────────────────────────────────────────
if "qa_session_id" not in st.session_state:
    st.session_state.qa_session_id = os.urandom(8).hex()

if "qa_history_loaded" not in st.session_state:
    saved_messages = chat_db.load_history(task.id, limit=50, session_id=st.session_state.qa_session_id)
    st.session_state.qa_history = chat_db.format_for_llm(saved_messages)
    st.session_state.qa_history_loaded = True

# ── Sidebar: History Control ─────────────────────────────────────────────────────
with st.sidebar:
    st.divider()
    st.header("对话历史")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("清空当前对话", type="secondary"):
            st.session_state.qa_history = []
            chat_db.clear_history(task.id, session_id=st.session_state.qa_session_id)
            st.rerun()
    with col2:
        if st.button("清空所有历史", type="secondary"):
            st.session_state.qa_history = []
            chat_db.clear_history(task.id)
            st.rerun()
    
    history_count = len(st.session_state.qa_history)
    st.caption(f"当前对话: {history_count} 条消息")

# ── Chat ──────────────────────────────────────────────────────────────────────────
if "qa_history" not in st.session_state:
    st.session_state.qa_history = []

# Render existing chat history
for msg in st.session_state.qa_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

question = st.chat_input("请输入财务问题，如：204年管理费用是多少？")

if question:
    # Show user message immediately
    with st.chat_message("user"):
        st.markdown(question)
    st.session_state.qa_history.append({"role": "user", "content": question})
    
    # Save user message to database
    chat_db.save_message(
        task_id=task.id,
        role="user",
        content=question,
        session_id=st.session_state.qa_session_id,
    )

    # Stream assistant response
    with st.chat_message("assistant"):
        # Use a mutable container so the generator can write back to outer scope
        state = {
            "full_answer": "",
            "retrieval": None,
            "cypher": None,
            "metadata": None,
            "confidence": 0.0,
        }

        def _stream():
            # Get retrieval metadata first (if available)
            try:
                candidates, metadata = engine._retriever.search_hybrid(question, top_k_candidates=30)
                state["metadata"] = metadata
                
                for event_type, data in engine.ask_stream(
                    question,
                    chat_history=st.session_state.qa_history,
                    top_k=top_k,
                ):
                    if event_type == "retrieval":
                        state["retrieval"] = data
                        
                        # Calculate confidence score
                        if data and data.contexts:
                            avg_score = sum(ctx.match_score for ctx in data.contexts) / len(data.contexts)
                            state["confidence"] = min(avg_score * 10, 100)
                        
                    elif event_type == "cypher":
                        state["cypher"] = data
                    elif event_type == "chunk":
                        state["full_answer"] += data
                        yield data
                    elif event_type in ("answer", "error"):
                        state["full_answer"] = data
                        yield data
            except:
                # Fallback if search_hybrid not available
                for event_type, data in engine.ask_stream(
                    question,
                    chat_history=st.session_state.qa_history,
                    top_k=top_k,
                ):
                    if event_type == "retrieval":
                        state["retrieval"] = data
                    elif event_type == "cypher":
                        state["cypher"] = data
                    elif event_type == "chunk":
                        state["full_answer"] += data
                        yield data
                    elif event_type in ("answer", "error"):
                        state["full_answer"] = data
                        yield data

        st.write_stream(_stream())
    
    # ── Phase 2.1: Confidence Display ───────────────────────────────────────
    if state["confidence"] > 0:
        confidence_color = "green" if state["confidence"] > 70 else "orange" if state["confidence"] > 50 else "red"
        st.markdown(
            f"<span style='color:{confidence_color}; font-size: 12px;'>"
            f"📊 回答置信度: {state['confidence']:.1f}% "
            f"({'高' if state['confidence'] > 70 else '中' if state['confidence'] > 50 else '低'})"
            f"</span>",
            unsafe_allow_html=True
        )
    
    # ── Phase 1.3: Debug Panel ─────────────────────────────────────────────────
    if state["metadata"]:
        with st.expander("🔍 检索过程追踪"):
            st.subheader("Phase 1: 关键词+类别粗筛")
            col1, col2 = st.columns(2)
            with col1:
                st.write("**提取关键词**:", state["metadata"].get("keywords", []))
                st.write("**推断年份**:", state["metadata"].get("years", []))
            with col2:
                st.write("**推断类别**:", state["metadata"].get("category", "未分类"))
                st.write("**候选数量**:", state["metadata"].get("total_candidates", 0))
            
            if state["retrieval"] and state["retrieval"].contexts:
                st.subheader("Phase 2: 最终选择")
                st.write(f"**最终选择**: {len(state['retrieval'].contexts)}个指标")
                
                for idx, ctx in enumerate(state["retrieval"].contexts[:5], 1):
                    st.markdown(f"{idx}. **{ctx.indicator.name}** (匹配分数: {ctx.match_score:.2f})")
    
    # ── Phase 2.2: User Feedback ───────────────────────────────────────────────
    st.markdown("**回答质量评价**:")
    feedback_cols = st.columns(4)
    with feedback_cols[0]:
        thumbs_up = st.button("👍 好", key=f"good_{len(st.session_state.qa_history)}")
    with feedback_cols[1]:
        thumbs_down = st.button("👎 差", key=f"bad_{len(st.session_state.qa_history)}")
    with feedback_cols[2]:
        neutral = st.button("😐 一般", key=f"neutral_{len(st.session_state.qa_history)}")
    with feedback_cols[3]:
        report_issue = st.button("⚠️ 报告问题", key=f"issue_{len(st.session_state.qa_history)}")
    
    # Save feedback
    feedback_value = None
    if thumbs_up:
        feedback_value = "good"
    elif thumbs_down:
        feedback_value = "bad"
    elif neutral:
        feedback_value = "neutral"
    elif report_issue:
        feedback_value = "issue"
    
    if feedback_value:
        chat_db.save_message(
            task_id=task.id,
            role="feedback",
            content=feedback_value,
            metadata={
                "question": question,
                "answer": state["full_answer"],
                "confidence": state["confidence"],
            },
            session_id=st.session_state.qa_session_id,
        )
        st.toast(f"已记录反馈: {feedback_value}", icon="✅")

    st.session_state.qa_history.append({"role": "assistant", "content": state["full_answer"]})
    
    # Save assistant message to database
    chat_db.save_message(
        task_id=task.id,
        role="assistant",
        content=state["full_answer"],
        metadata={
            "retrieval": [ctx.indicator.id for ctx in state["retrieval"].contexts[:3]] if state["retrieval"] else None,
            "confidence": state["confidence"],
            "keywords": state["metadata"].get("keywords") if state["metadata"] else None,
        },
        session_id=st.session_state.qa_session_id,
    )
    
    st.session_state["_last_retrieval"] = state["retrieval"]
    st.session_state["_last_cypher"] = state["cypher"]
    st.session_state["_last_metadata"] = state["metadata"]
    st.session_state["_last_confidence"] = state["confidence"]

# Show retrieval context for the last response
last_retrieval = st.session_state.get("_last_retrieval")
if last_retrieval and last_retrieval.contexts:
    with st.expander(f"检索上下文（{len(last_retrieval.contexts)} 个指标）"):
        for ctx in last_retrieval.contexts:
            ind = ctx.indicator
            st.markdown(
                f"**{ind.name}** — 匹配方式: `{ctx.match_reason}` 分数: {ctx.match_score:.2f}"
            )
            if ind.time_series:
                ts_items = list(ind.time_series.items())
                query_years = getattr(last_retrieval, "query_years", [])
                if query_years:
                    hits = [(k, v) for k, v in ts_items if any(y in str(k) for y in query_years)]
                    if hits:
                        st.caption("查询年份: " + "  ".join(f"{k}={v}" for k, v in hits))
                st.caption("  ".join(f"{p}={v}" for p, v in ts_items[:5]))
            if ctx.upstream:
                st.caption("上游: " + ", ".join(u.name for u in ctx.upstream))
            if ctx.downstream:
                st.caption("被依赖: " + ", ".join(d.name for d in ctx.downstream))
            st.divider()

last_cypher = st.session_state.get("_last_cypher")
if last_cypher and last_cypher[0]:
    with st.expander("Cypher 查询"):
        st.code(last_cypher[0], language="cypher")
        if last_cypher[1]:
            st.text(last_cypher[1])

if st.button("清空对话", key="clear_chat_btn"):
    st.session_state.qa_history = []
    st.session_state.pop("_last_retrieval", None)
    st.session_state.pop("_last_cypher", None)
    st.session_state.pop("_last_metadata", None)
    st.session_state.pop("_last_confidence", None)
    chat_db.clear_history(task.id, session_id=st.session_state.qa_session_id)
    st.rerun()

# ── Phase 1.4: Export Chat History ──────────────────────────────────────────────
if st.button("导出问答记录", key="export_chat", type="secondary"):
    chat_history = chat_db.load_history(task.id, limit=100, session_id=st.session_state.qa_session_id)
    
    if chat_history:
        # Prepare data for export
        export_data = []
        for msg in chat_history:
            export_data.append({
                "时间": msg.created_at,
                "角色": msg.role,
                "内容": msg.content[:200] if len(msg.content) > 200 else msg.content,
                "元数据": str(msg.metadata) if msg.metadata else ""
            })
        
        df = pd.DataFrame(export_data)
        
        # Convert to CSV
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
        csv_data = csv_buffer.getvalue()
        
        st.download_button(
            label="下载CSV文件",
            data=csv_data,
            file_name=f"chat_history_{task.id}_{st.session_state.qa_session_id}.csv",
            mime="text/csv",
            key="download_csv"
        )
        
        st.success(f"已准备{len(export_data)}条记录导出")
    else:
        st.warning("暂无对话历史可导出")

# ── Phase 2.4: Chart Generation ─────────────────────────────────────────────────
if st.button("生成数据图表", key="generate_chart", type="secondary"):
    last_retrieval = st.session_state.get("_last_retrieval")
    
    if last_retrieval and last_retrieval.contexts:
        # Prepare chart data from retrieved indicators
        chart_data = []
        for ctx in last_retrieval.contexts:
            ind = ctx.indicator
            if ind.time_series:
                for period, value in ind.time_series.items():
                    try:
                        numeric_value = float(value)
                        chart_data.append({
                            "指标": ind.name,
                            "时期": period,
                            "数值": numeric_value
                        })
                    except (ValueError, TypeError):
                        pass
        
        if chart_data:
            df_chart = pd.DataFrame(chart_data)
            
            st.subheader("趋势图")
            st.line_chart(df_chart.pivot_table(
                values="数值",
                index="时期",
                columns="指标"
            ))
            
            st.subheader("对比图")
            st.bar_chart(df_chart.groupby("指标")["数值"].mean())
            
            st.success(f"已生成{len(chart_data)}个数据点图表")
        else:
            st.warning("检索数据无数值型时间序列，无法生成图表")
    else:
        st.warning("暂无检索数据可图表化")

# ── Phase 2.3: Quick Filters Sidebar ────────────────────────────────────────────
with st.sidebar:
    st.divider()
    st.header("快捷筛选")
    
    if graph and graph.indicators:
        all_years = set()
        for ind in graph.indicators.values():
            if ind.time_series:
                for key in ind.time_series.keys():
                    years_in_key = re.findall(r"\d{4}", str(key))
                    all_years.update(years_in_key)
        
        available_years = sorted(list(all_years), reverse=True)
        selected_years = st.multiselect(
            "选择年份",
            available_years,
            default=available_years[:3] if available_years else []
        )
    else:
        selected_years = []
    
    from financial_kg.llm.category_classifier import INDICATOR_CATEGORIES
    selected_category = st.selectbox(
        "选择类别",
        ["全部"] + list(INDICATOR_CATEGORIES.keys())
    )
    
    indicator_type = st.radio(
        "指标类型",
        ["全部", "数值型", "趋势型", "计算型"],
        horizontal=True
    )

# ── Example Questions ──────────────────────────────────────────────────────────────
st.divider()
st.subheader("💡 示例问题")
example_questions = [
    "2040年管理费用是多少？",
    "营业收入近5年的变化趋势？",
    "营业成本和营业费用的差异？",
    "哪些指标影响净利润？",
]

cols = st.columns(len(example_questions))
for idx, example in enumerate(example_questions):
    with cols[idx]:
        if st.button(example, key=f"example_{idx}"):
            st.session_state["_example_question"] = example
            st.rerun()

# Handle example question click
if "_example_question" in st.session_state:
    example_q = st.session_state.pop("_example_question")
    st.session_state["_auto_question"] = example_q
