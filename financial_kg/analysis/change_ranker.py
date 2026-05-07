"""Change analysis and ranking utilities for snapshot comparison."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional

from financial_kg.models.graph import FinancialGraph
from financial_kg.engine.snapshot import SnapshotDiff


@dataclass
class RankedChange:
    cell_id: str
    sheet: str
    old_value: Any
    new_value: Any
    formula: Optional[str]
    downstream_count: int
    change_pct: Optional[float]
    impact_score: float
    indicator_name: Optional[str]


@dataclass
class RankedIndicatorChange:
    indicator_id: str
    indicator_name: str
    sheet: str
    old_summary: Any
    new_summary: Any
    changed_cell_count: int
    change_pct: Optional[float]
    impact_score: float


def calculate_change_pct(old_val: Any, new_val: Any) -> Optional[float]:
    """Calculate percentage change between two numeric values."""
    if old_val is None or new_val is None:
        return None
    try:
        old_f = float(old_val)
        new_f = float(new_val)
        if old_f == 0:
            return 100.0 if new_f != 0 else 0.0
        return abs((new_f - old_f) / old_f * 100)
    except (TypeError, ValueError):
        return None


def calculate_impact_score(downstream_count: int, change_pct: Optional[float]) -> float:
    """Calculate composite impact score combining downstream influence and change magnitude."""
    downstream_weight = downstream_count * 10
    change_weight = (change_pct or 0) / 10
    return downstream_weight + change_weight


def rank_changes_by_impact(
    diff: SnapshotDiff,
    graph: FinancialGraph,
    top_n: Optional[int] = None
) -> list[RankedChange]:
    """Rank changed cells by their impact on downstream cells and change magnitude."""
    ranked: list[RankedChange] = []
    
    for cell_entry in diff.changed_cells:
        cell_id = cell_entry["id"]
        cell = graph.cells.get(cell_id)
        
        downstream_count = 0
        if cell_id in graph.cell_graph:
            downstream_count = len(list(graph.cell_graph.predecessors(cell_id)))
        
        change_pct = calculate_change_pct(cell_entry["old"], cell_entry["new"])
        impact_score = calculate_impact_score(downstream_count, change_pct)
        
        indicator_name = None
        if cell and cell.indicator_id:
            ind = graph.indicators.get(cell.indicator_id)
            indicator_name = ind.name if ind else None
        
        ranked.append(RankedChange(
            cell_id=cell_id,
            sheet=cell_entry.get("sheet", ""),
            old_value=cell_entry["old"],
            new_value=cell_entry["new"],
            formula=cell_entry.get("formula"),
            downstream_count=downstream_count,
            change_pct=change_pct,
            impact_score=impact_score,
            indicator_name=indicator_name,
        ))
    
    ranked.sort(key=lambda x: x.impact_score, reverse=True)
    
    if top_n:
        return ranked[:top_n]
    
    return ranked


def rank_indicator_changes_by_impact(
    diff: SnapshotDiff,
    graph: FinancialGraph,
    top_n: Optional[int] = None
) -> list[RankedIndicatorChange]:
    """Rank indicator-level changes by impact score."""
    ranked: list[RankedIndicatorChange] = []
    
    for ind_entry in diff.affected_indicators:
        ind_id = ind_entry["id"]
        indicator = graph.indicators.get(ind_id)
        
        downstream_total = 0
        if indicator and indicator.cell_ids:
            for cell_id in indicator.cell_ids:
                if cell_id in graph.cell_graph:
                    downstream_total += len(list(graph.cell_graph.predecessors(cell_id)))
        
        change_pct = calculate_change_pct(ind_entry["old_summary"], ind_entry["new_summary"])
        impact_score = calculate_impact_score(downstream_total, change_pct)
        
        ranked.append(RankedIndicatorChange(
            indicator_id=ind_id,
            indicator_name=ind_entry["name"],
            sheet=ind_entry.get("sheet", ""),
            old_summary=ind_entry["old_summary"],
            new_summary=ind_entry["new_summary"],
            changed_cell_count=ind_entry["changed_cell_count"],
            change_pct=change_pct,
            impact_score=impact_score,
        ))
    
    ranked.sort(key=lambda x: x.impact_score, reverse=True)
    
    if top_n:
        return ranked[:top_n]
    
    return ranked


def get_change_category(change_pct: Optional[float]) -> str:
    """Classify change magnitude into categories for color coding."""
    if change_pct is None:
        return "minor"
    if change_pct > 50:
        return "critical"
    elif change_pct > 20:
        return "major"
    elif change_pct > 5:
        return "moderate"
    else:
        return "minor"


def get_change_color(category: str) -> str:
    """Return color hex code for change category."""
    colors = {
        "critical": "#FFCCCC",  # Light red
        "major": "#FFFFCC",     # Light yellow
        "moderate": "#CCFFCC",  # Light green
        "minor": "#FFFFFF",     # White (no highlight)
    }
    return colors.get(category, "#FFFFFF")