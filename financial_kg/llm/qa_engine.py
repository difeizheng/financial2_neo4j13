from __future__ import annotations
from dataclasses import dataclass, field
import json
from typing import Optional

from .retriever import IndicatorRetriever, IndicatorContext, RetrievalResult
from .prompt_builder import PromptBuilder
from .cypher_gen import CypherGenerator
from .category_classifier import classify_question_type
from ..models.graph import FinancialGraph


@dataclass
class QAResponse:
    answer: str
    retrieved_contexts: list[IndicatorContext] = field(default_factory=list)
    cypher_query: Optional[str] = None
    cypher_results: Optional[str] = None
    error: Optional[str] = None


class QAEngine:
    """Orchestrates retrieval, context building, and LLM calls for Q&A."""

    def __init__(
        self,
        graph: FinancialGraph,
        neo4j_store=None,
        llm_base_url: str = "",
        llm_api_key: str = "",
        llm_model: str = "gpt-4o",
        task_id: str = "",  # Required for Neo4j queries
    ) -> None:
        self._graph = graph
        self._neo4j = neo4j_store
        self._task_id = task_id
        self._model = llm_model
        self._retriever = IndicatorRetriever(graph, neo4j_store, task_id)
        self._prompt_builder = PromptBuilder(graph, task_id)
        self._client = None
        self._cypher_gen = None

        if llm_api_key.strip():
            try:
                from openai import OpenAI
                self._client = OpenAI(base_url=llm_base_url or None, api_key=llm_api_key)
                if neo4j_store:
                    self._cypher_gen = CypherGenerator(self._client, llm_model, neo4j_store, task_id)
            except ImportError:
                pass

    def ask(
        self,
        question: str,
        chat_history: Optional[list[dict]] = None,
        top_k: int = 8,
    ) -> QAResponse:
        retrieval = self._retriever.search(question, top_k)

        if not self._client:
            return self._retrieval_only_response(retrieval)

        schema = ""
        if self._neo4j and self._task_id:
            try:
                schema = self._neo4j.get_graph_schema(self._task_id)
            except Exception:
                pass

        system_prompt = self._prompt_builder.build_system_prompt(retrieval, schema)

        cypher_query: Optional[str] = None
        cypher_results: Optional[str] = None
        if self._cypher_gen and self._cypher_gen.should_use_cypher(question):
            cypher_prompt = self._prompt_builder.build_cypher_prompt(question, schema)
            try:
                cypher_query, cypher_results = self._cypher_gen.generate_and_execute(
                    question, schema, cypher_prompt
                )
                system_prompt += f"\n\n## 图遍历查询结果\n{cypher_results}"
            except Exception as e:
                cypher_results = f"（Cypher 生成失败：{e}）"

        messages = [{"role": "system", "content": system_prompt}]
        for h in (chat_history or [])[:-1]:
            messages.append(h)
        messages.append({"role": "user", "content": question})

        try:
            resp = self._client.chat.completions.create(
                model=self._model, messages=messages, max_tokens=1024
            )
            answer = resp.choices[0].message.content
        except Exception as e:
            answer = f"LLM 调用失败：{e}"
            return QAResponse(
                answer=answer,
                retrieved_contexts=retrieval.contexts,
                cypher_query=cypher_query,
                cypher_results=cypher_results,
                error=str(e),
            )

        return QAResponse(
            answer=answer,
            retrieved_contexts=retrieval.contexts,
            cypher_query=cypher_query,
            cypher_results=cypher_results,
        )

    def _retrieval_only_response(self, retrieval: RetrievalResult) -> QAResponse:
        """Format retrieval results as a readable answer when no LLM is configured."""
        if not retrieval.contexts:
            return QAResponse(answer="未找到相关指标数据。", retrieved_contexts=[])
        lines = ["以下是检索到的相关指标数据（未配置 LLM，仅展示原始数据）：\n"]
        for ctx in retrieval.contexts:
            ind = ctx.indicator
            line = f"- **{ind.name}**"
            if ind.unit:
                line += f" [{ind.unit}]"
            if retrieval.query_years and ind.time_series:
                hits = [(k, v) for k, v in ind.time_series.items() if any(y in str(k) for y in retrieval.query_years)]
                for k, v in hits:
                    line += f"\n  {k}: {v}"
            elif ind.summary_value is not None:
                line += f": {ind.summary_value}"
            lines.append(line)
        return QAResponse(answer="\n".join(lines), retrieved_contexts=retrieval.contexts)

    def ask_hybrid(
        self,
        question: str,
        chat_history: Optional[list[dict]] = None,
        top_k: int = 8,
        top_k_candidates: int = 30,
    ) -> QAResponse:
        """Hybrid retrieval: Phase 1 (keyword+category) + Phase 2 (LLM filtering).
        
        Args:
            question: User question
            chat_history: Chat history
            top_k: Final number of indicators (default 8)
            top_k_candidates: Phase 1 candidates (default 30)
            
        Returns:
            QAResponse with answer and contexts
        """
        candidates, metadata = self._retriever.search_hybrid(question, top_k_candidates)
        
        if not candidates:
            return QAResponse(answer="未找到相关指标数据。", retrieved_contexts=[])
        
        if not self._client:
            contexts = self._build_contexts_from_indicators(candidates[:top_k])
            retrieval = RetrievalResult(
                contexts=contexts,
                query_tokens=metadata.get("keywords", []),
                query_years=metadata.get("years", []),
                total_candidates=len(candidates),
            )
            return self._retrieval_only_response(retrieval)
        
        scored_indicators = self._llm_filter_candidates(question, candidates, metadata)
        
        top_indicators = scored_indicators[:top_k]
        contexts = self._build_contexts_from_indicators(top_indicators)
        
        retrieval = RetrievalResult(
            contexts=contexts,
            query_tokens=metadata.get("keywords", []),
            query_years=metadata.get("years", []),
            total_candidates=len(candidates),
        )
        
        schema = ""
        if self._neo4j and self._task_id:
            try:
                schema = self._neo4j.get_graph_schema(self._task_id)
            except Exception:
                pass
        
        system_prompt = self._prompt_builder.build_system_prompt(retrieval, schema)
        
        cypher_query: Optional[str] = None
        cypher_results: Optional[str] = None
        if self._cypher_gen and self._cypher_gen.should_use_cypher(question):
            cypher_prompt = self._prompt_builder.build_cypher_prompt(question, schema)
            try:
                cypher_query, cypher_results = self._cypher_gen.generate_and_execute(
                    question, schema, cypher_prompt
                )
                system_prompt += f"\n\n## 图遍历查询结果\n{cypher_results}"
            except Exception as e:
                cypher_results = f"（Cypher 生成失败：{e}）"
        
        messages = [{"role": "system", "content": system_prompt}]
        for h in (chat_history or [])[:-1]:
            messages.append(h)
        messages.append({"role": "user", "content": question})
        
        try:
            resp = self._client.chat.completions.create(
                model=self._model, messages=messages, max_tokens=1024
            )
            answer = resp.choices[0].message.content
        except Exception as e:
            answer = f"LLM 调用失败：{e}"
            return QAResponse(
                answer=answer,
                retrieved_contexts=contexts,
                cypher_query=cypher_query,
                cypher_results=cypher_results,
                error=str(e),
            )
        
        return QAResponse(
            answer=answer,
            retrieved_contexts=contexts,
            cypher_query=cypher_query,
            cypher_results=cypher_results,
        )

    def _llm_filter_candidates(
        self,
        question: str,
        candidates: list,
        metadata: dict,
    ) -> list:
        """Phase 2: Use LLM to filter and score candidates.
        
        Args:
            question: User question
            candidates: Candidate indicators from Phase 1
            metadata: Metadata from Phase 1
            
        Returns:
            List of scored Indicator objects
        """
        candidates_text = self._retriever.get_candidates_for_llm(candidates, metadata)
        
        filter_prompt = self._prompt_builder.build_llm_filter_prompt(
            question,
            candidates_text,
            metadata.get("question_type", "通用查询"),
            metadata.get("category", ""),
            metadata.get("years", []),
        )
        
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": filter_prompt}],
                max_tokens=1500,
                temperature=0.3,
            )
            llm_output = resp.choices[0].message.content
            
            scored_data = json.loads(llm_output)
            
            scored_indicators = []
            for item in scored_data:
                ind_id = item.get("id")
                score = item.get("score", 0)
                
                if score >= 6:
                    indicator = self._graph.indicators.get(ind_id)
                    if indicator:
                        scored_indicators.append(indicator)
            
            return scored_indicators
            
        except (json.JSONDecodeError, Exception) as e:
            return candidates[:8]

    def _build_contexts_from_indicators(self, indicators: list) -> list[IndicatorContext]:
        """Build IndicatorContext objects from indicator list."""
        contexts = []
        for ind in indicators:
            ctx = IndicatorContext(
                indicator=ind,
                match_score=0.8,
                match_reason="llm_filtered",
            )
            contexts.append(ctx)
        
        self._retriever._enrich_with_graph_context(contexts)
        return contexts

    def ask_stream(
        self,
        question: str,
        chat_history: Optional[list[dict]] = None,
        top_k: int = 8,
    ):
        """Generator yielding (event_type, data) for streaming UI.

        Event types:
          ("retrieval", RetrievalResult)
          ("cypher", (query_str, results_str))
          ("chunk", str)          — LLM token chunk
          ("answer", str)         — full answer (retrieval-only mode)
          ("error", str)
        """
        candidates, metadata = self._retriever.search_hybrid(question, top_k_candidates=30)
        
        if not candidates:
            yield ("error", "未找到相关指标数据")
            return
        
        if not self._client:
            contexts = self._build_contexts_from_indicators(candidates[:top_k])
            retrieval = RetrievalResult(
                contexts=contexts,
                query_tokens=metadata.get("keywords", []),
                query_years=metadata.get("years", []),
                total_candidates=len(candidates),
            )
            yield ("retrieval", retrieval)
            yield ("answer", self._retrieval_only_response(retrieval).answer)
            return
        
        scored_indicators = self._llm_filter_candidates(question, candidates, metadata)
        top_indicators = scored_indicators[:top_k]
        contexts = self._build_contexts_from_indicators(top_indicators)
        
        retrieval = RetrievalResult(
            contexts=contexts,
            query_tokens=metadata.get("keywords", []),
            query_years=metadata.get("years", []),
            total_candidates=len(candidates),
        )
        yield ("retrieval", retrieval)

        schema = ""
        if self._neo4j and self._task_id:
            try:
                schema = self._neo4j.get_graph_schema(self._task_id)
            except Exception:
                pass

        system_prompt = self._prompt_builder.build_system_prompt(retrieval, schema)

        if self._cypher_gen and self._cypher_gen.should_use_cypher(question):
            cypher_prompt = self._prompt_builder.build_cypher_prompt(question, schema)
            try:
                cypher_query, cypher_results = self._cypher_gen.generate_and_execute(
                    question, schema, cypher_prompt
                )
                system_prompt += f"\n\n## 图遍历查询结果\n{cypher_results}"
                yield ("cypher", (cypher_query, cypher_results))
            except Exception as e:
                yield ("cypher", (None, f"（Cypher 生成失败：{e}）"))

        messages = [{"role": "system", "content": system_prompt}]
        for h in (chat_history or [])[:-1]:
            messages.append(h)
        messages.append({"role": "user", "content": question})

        try:
            stream = self._client.chat.completions.create(
                model=self._model, messages=messages, max_tokens=1024, stream=True
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield ("chunk", delta)
        except Exception as e:
            yield ("error", f"LLM 调用失败：{e}")
