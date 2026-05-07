from __future__ import annotations
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from ..models.indicator import Indicator
from ..models.graph import FinancialGraph
from .category_classifier import (
    extract_keywords,
    classify_category,
    classify_question_type,
    match_indicator_category,
    calculate_keyword_match_score,
)


@dataclass
class IndicatorContext:
    indicator: Indicator
    match_score: float
    match_reason: str  # "exact_name" | "fuzzy_name" | "category" | "time_period"
    upstream: list[Indicator] = field(default_factory=list)
    downstream: list[Indicator] = field(default_factory=list)


@dataclass
class RetrievalResult:
    contexts: list[IndicatorContext]
    query_tokens: list[str]
    query_years: list[str]
    total_candidates: int


def _fuzzy_score(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _extract_years(text: str) -> list[str]:
    return re.findall(r"\d{4}", text)


class IndicatorRetriever:
    """Structured indicator retrieval with fuzzy matching and graph context."""

    def __init__(
        self,
        graph: FinancialGraph,
        neo4j_store=None,  # Optional[Neo4jStore] — avoid circular import
        task_id: str = "",  # Required for Neo4j queries
    ) -> None:
        self._graph = graph
        self._neo4j = neo4j_store
        self._task_id = task_id
        self._indicators = list(graph.indicators.values())

    def search(self, question: str, top_k: int = 8) -> RetrievalResult:
        tokens = self._tokenize(question)
        years = _extract_years(question)
        scored: list[tuple[float, str, Indicator]] = []

        for ind in self._indicators:
            score, reason = self._score(ind, tokens, years)
            if score > 0:
                scored.append((score, reason, ind))

        scored.sort(key=lambda x: -x[0])
        top = scored[:top_k]

        contexts = [
            IndicatorContext(
                indicator=ind,
                match_score=score,
                match_reason=reason,
            )
            for score, reason, ind in top
        ]
        self._enrich_with_graph_context(contexts)

        return RetrievalResult(
            contexts=contexts,
            query_tokens=tokens,
            query_years=years,
            total_candidates=len(scored),
        )

    def search_hybrid(
        self,
        question: str,
        top_k_candidates: int = 30,
    ) -> tuple[list[Indicator], dict]:
        """Phase 1: Hybrid retrieval using keywords + category filtering.
        
        Returns candidates for Phase 2 LLM filtering.
        
        Args:
            question: User question
            top_k_candidates: Number of candidates to return (default 30)
            
        Returns:
            tuple: (candidate_indicators, metadata_dict)
        """
        keywords = extract_keywords(question)
        category = classify_category(question)
        question_type = classify_question_type(question)
        years = _extract_years(question)
        
        candidates = []
        seen_ids = set()
        
        for ind in self._indicators:
            ind_name = ind.name or ""
            ind_category = match_indicator_category(ind_name)
            
            score = 0.0
            reasons = []
            
            kw_score = calculate_keyword_match_score(question, ind_name, keywords)
            if kw_score > 0:
                score += kw_score
                reasons.append("keyword_match")
            
            if category and ind_category == category:
                score += 0.4
                reasons.append("category_match")
            
            for kw in keywords:
                if kw in ind_name or kw in (ind.category or ""):
                    score += 0.3
                    if kw not in reasons:
                        reasons.append("keyword_exact")
            
            if years and ind.time_series:
                year_match = any(y in str(k) for y in years for k in ind.time_series.keys())
                if year_match:
                    score += 0.2
                    reasons.append("year_match")
            
            if score > 0 and ind.id not in seen_ids:
                candidates.append((score, reasons, ind))
                seen_ids.add(ind.id)
        
        candidates.sort(key=lambda x: -x[0])
        top_candidates = [c[2] for c in candidates[:top_k_candidates]]
        
        metadata = {
            "keywords": keywords,
            "category": category,
            "question_type": question_type,
            "years": years,
            "total_candidates": len(candidates),
            "candidate_scores": [(c[2].id, c[0], c[1]) for c in candidates[:top_k_candidates]],
        }
        
        return top_candidates, metadata

    def get_candidates_for_llm(
        self,
        candidates: list[Indicator],
        metadata: dict,
    ) -> str:
        """Format candidate indicators for LLM filtering prompt.
        
        Args:
            candidates: List of candidate indicators from Phase 1
            metadata: Metadata from Phase 1
            
        Returns:
            Formatted text for LLM prompt
        """
        lines = []
        for idx, ind in enumerate(candidates, 1):
            time_series_str = ""
            if ind.time_series:
                ts_items = list(ind.time_series.items())[:3]
                time_series_str = " | ".join(f"{k}={v}" for k, v in ts_items)
            
            category_str = ind.category or "未分类"
            formula_str = ind.formula_raw or "无公式"
            
            line = f"{idx}. {ind.id}\n"
            line += f"   名称: {ind.name}\n"
            line += f"   类别: {category_str}\n"
            line += f"   时间序列: {time_series_str}\n"
            line += f"   公式: {formula_str[:50]}...\n"
            
            lines.append(line)
        
        return "\n".join(lines)

    def _tokenize(self, question: str) -> list[str]:
        # Strip stop words and punctuation that carry no indicator meaning
        cleaned = re.sub(r"[？?！!，,。.：:；;（）()【】\[\]「」""''、的是了吗呢吧啊哪些跟和与在到从对于]", "", question)
        tokens: list[str] = []
        # Split into Chinese and ASCII segments
        for seg in re.findall(r"[一-鿿]+|[a-zA-Z0-9]+", cleaned):
            if re.match(r"[一-鿿]", seg):
                # Chinese: sliding-window n-grams (2–4 chars) to cover all substrings
                for n in range(2, min(len(seg) + 1, 5)):
                    for i in range(len(seg) - n + 1):
                        tokens.append(seg[i : i + n])
            elif len(seg) >= 2:
                tokens.append(seg)
        # Deduplicate while preserving order, then sort longest-first for better exact matching
        seen: set[str] = set()
        result: list[str] = []
        for t in tokens:
            if t not in seen:
                seen.add(t)
                result.append(t)
        result.sort(key=len, reverse=True)
        return result

    def _score(
        self, ind: Indicator, tokens: list[str], years: list[str]
    ) -> tuple[float, str]:
        name = ind.name or ""
        category = ind.category or ""
        combined = name + category

        # Exact name match — highest priority
        for token in tokens:
            if token == name:
                score = 10.0
                if years and any(y in str(k) for y in years for k in ind.time_series):
                    score += 2.0
                return score, "exact_name"

        # Substring match — bidirectional: token-in-name OR name-in-token
        for token in tokens:
            if token in name:
                score = 5.0 + len(token) / max(len(name), 1)
                if years and any(y in str(k) for y in years for k in ind.time_series):
                    score += 2.0
                return score, "fuzzy_name"
            if len(name) >= 2 and name in token:
                score = 5.0 + len(name) / max(len(token), 1)
                if years and any(y in str(k) for y in years for k in ind.time_series):
                    score += 2.0
                return score, "fuzzy_name"

        # Fuzzy match on name
        best_fuzzy = 0.0
        for token in tokens:
            if len(token) >= 2:
                ratio = _fuzzy_score(token, name)
                if ratio > best_fuzzy:
                    best_fuzzy = ratio
        if best_fuzzy >= 0.6:
            return best_fuzzy * 4.0, "fuzzy_name"

        # Category match
        for token in tokens:
            if token in category:
                score = 2.0
                # Boost if also has time series data for the queried year
                if years and any(y in str(k) for y in years for k in ind.time_series):
                    score += 1.0
                return score, "category"

        # Time period filter — if question mentions a year and indicator has it
        if years and ind.time_series:
            for y in years:
                if any(y in str(k) for k in ind.time_series):
                    return 1.0, "time_period"

        return 0.0, ""

    def _enrich_with_graph_context(
        self, contexts: list[IndicatorContext], depth: int = 1
    ) -> None:
        for ctx in contexts:
            ind = ctx.indicator
            if self._neo4j and self._task_id:
                try:
                    up_dicts = self._neo4j.get_upstream_indicators(self._task_id, ind.id, depth)
                    down_dicts = self._neo4j.get_downstream_indicators(self._task_id, ind.id, depth)
                    # Strip task_id prefix from returned IDs to match in-memory graph
                    ctx.upstream = [
                        self._graph.indicators[d.get("orig_id", d.get("id", "").split("_", 1)[-1])]
                        for d in up_dicts
                        if (d.get("orig_id") or d.get("id", "").split("_", 1)[-1]) in self._graph.indicators
                    ]
                    ctx.downstream = [
                        self._graph.indicators[d.get("orig_id", d.get("id", "").split("_", 1)[-1])]
                        for d in down_dicts
                        if (d.get("orig_id") or d.get("id", "").split("_", 1)[-1]) in self._graph.indicators
                    ]
                    continue
                except Exception:
                    pass  # fall through to in-memory

            # In-memory fallback
            ctx.upstream = [
                self._graph.indicators[dep_id]
                for dep_id in ind.depends_on_indicators[:5]
                if dep_id in self._graph.indicators
            ]
            ctx.downstream = [
                self._graph.indicators[dep_id]
                for dep_id in ind.depended_by_indicators[:5]
                if dep_id in self._graph.indicators
            ]
