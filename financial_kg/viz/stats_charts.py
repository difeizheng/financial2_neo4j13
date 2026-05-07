"""Statistical charts for snapshot comparison visualization."""
from __future__ import annotations
from collections import Counter
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from financial_kg.engine.snapshot import SnapshotDiff
from financial_kg.analysis.change_ranker import (
    calculate_change_pct,
    get_change_category,
    get_change_color,
)


def build_sheet_distribution_pie(diff: SnapshotDiff) -> go.Figure:
    """Build pie chart showing distribution of changes across sheets."""
    sheet_counts: dict[str, int] = {}
    for cell in diff.changed_cells:
        sheet = cell.get("sheet", "Unknown")
        sheet_counts[sheet] = sheet_counts.get(sheet, 0) + 1
    
    if not sheet_counts:
        return go.Figure()
    
    fig = px.pie(
        values=list(sheet_counts.values()),
        names=list(sheet_counts.keys()),
        title="变化分布 - 按Sheet",
        hole=0.4,
    )
    fig.update_traces(
        textposition='inside',
        textinfo='percent+label',
    )
    fig.update_layout(
        showlegend=True,
        height=400,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    
    return fig


def build_indicator_distribution_pie(diff: SnapshotDiff) -> go.Figure:
    """Build pie chart showing distribution of changes across indicators."""
    ind_counts: dict[str, int] = {}
    for ind in diff.affected_indicators:
        ind_name = ind.get("name", "Unknown")
        ind_counts[ind_name] = ind_counts.get(ind_name, 0) + 1
    
    if not ind_counts:
        return go.Figure()
    
    if len(ind_counts) > 10:
        sorted_items = sorted(ind_counts.items(), key=lambda x: x[1], reverse=True)
        top_10 = dict(sorted_items[:10])
        other_count = sum(v for k, v in sorted_items[10:])
        top_10["其他"] = other_count
        ind_counts = top_10
    
    fig = px.pie(
        values=list(ind_counts.values()),
        names=list(ind_counts.keys()),
        title="变化分布 - Indicator",
        hole=0.4,
    )
    fig.update_traces(
        textposition='inside',
        textinfo='percent+label',
    )
    fig.update_layout(
        showlegend=True,
        height=400,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    
    return fig


def build_change_magnitude_bar(
    diff: SnapshotDiff,
    top_n: int = 10,
    by_indicator: bool = True
) -> go.Figure:
    """Build bar chart showing top changes by magnitude."""
    data_points: list[dict[str, Any]] = []
    
    if by_indicator:
        items = diff.affected_indicators[:top_n]
        for ind in items:
            pct = calculate_change_pct(ind["old_summary"], ind["new_summary"])
            if pct is not None:
                data_points.append({
                    "name": ind["name"][:30],
                    "change_pct": pct,
                    "old": ind["old_summary"],
                    "new": ind["new_summary"],
                })
        title = f"Top {top_n} Indicator变化幅度"
    else:
        items = diff.changed_cells[:top_n]
        for cell in items:
            pct = calculate_change_pct(cell["old"], cell["new"])
            if pct is not None:
                label = cell["id"].split("_", 1)[-1] if "_" in cell["id"] else cell["id"]
                data_points.append({
                    "name": label[:30],
                    "change_pct": pct,
                    "old": cell["old"],
                    "new": cell["new"],
                })
        title = f"Top {top_n} Cell变化幅度"
    
    if not data_points:
        return go.Figure()
    
    df = pd.DataFrame(data_points)
    
    fig = px.bar(
        df,
        x="name",
        y="change_pct",
        title=title,
        labels={"change_pct": "变化幅度 (%)", "name": "名称"},
        color="change_pct",
        color_continuous_scale="Reds",
    )
    
    fig.update_layout(
        xaxis_tickangle=-45,
        height=400,
        margin=dict(l=20, r=20, t=40, b=60),
        coloraxis_colorbar=dict(title="变化%"),
    )
    
    return fig


def build_change_category_histogram(diff: SnapshotDiff) -> go.Figure:
    """Build histogram showing distribution of change categories."""
    categories: list[str] = []
    for cell in diff.changed_cells:
        pct = calculate_change_pct(cell["old"], cell["new"])
        cat = get_change_category(pct)
        categories.append(cat)
    
    if not categories:
        return go.Figure()
    
    cat_counter = Counter(categories)
    cat_order = ["minor", "moderate", "major", "critical"]
    
    fig = go.Figure(data=[
        go.Bar(
            x=cat_order,
            y=[cat_counter.get(cat, 0) for cat in cat_order],
            marker_color=[
                "#FFFFFF",
                "#CCFFCC",
                "#FFFFCC",
                "#FFCCCC",
            ],
            text=[cat_counter.get(cat, 0) for cat in cat_order],
            textposition='auto',
        )
    ])
    
    fig.update_layout(
        title="变化幅度分布",
        xaxis_title="变化类别",
        yaxis_title="数量",
        height=400,
        margin=dict(l=20, r=20, t=40, b=20),
        xaxis=dict(
            tickmode='array',
            tickvals=cat_order,
            ticktext=["轻微 (<5%)", "中等 (5-20%)", "重大 (20-50%)", "关键 (>50%)"]
        ),
    )
    
    return fig


def build_combined_stats_dashboard(diff: SnapshotDiff) -> go.Figure:
    """Build combined dashboard with multiple charts."""
    if not diff or not diff.changed_cells:
        fig = go.Figure()
        fig.update_layout(
            title="无变化数据",
            height=800,
        )
        return fig
    
    fig = make_subplots(
        rows=2, cols=2,
        specs=[[{"type": "domain"}, {"type": "domain"}],
               [{"type": "xy"}, {"type": "xy"}]],
        subplot_titles=("Sheet分布", "Indicator分布", "变化幅度Top10", "变化类别分布"),
        vertical_spacing=0.2,
        horizontal_spacing=0.1,
    )
    
    sheet_counts: dict[str, int] = {}
    for cell in diff.changed_cells:
        sheet = cell.get("sheet", "Unknown")
        if sheet and sheet.strip():
            sheet_counts[sheet] = sheet_counts.get(sheet, 0) + 1
    
    if sheet_counts and len(sheet_counts) > 0:
        fig.add_trace(
            go.Pie(
                values=list(sheet_counts.values()),
                labels=list(sheet_counts.keys()),
                hole=0.4,
                textinfo='percent+label',
                name="Sheet",
            ),
            row=1, col=1,
        )
    
    ind_counts: dict[str, int] = {}
    for ind in diff.affected_indicators:
        ind_name = ind.get("name", "Unknown")
        if ind_name and ind_name.strip():
            ind_counts[ind_name] = ind_counts.get(ind_name, 0) + 1
    
    if len(ind_counts) > 8:
        sorted_items = sorted(ind_counts.items(), key=lambda x: x[1], reverse=True)
        top_8 = dict(sorted_items[:8])
        other_count = sum(v for k, v in sorted_items[8:])
        top_8["其他"] = other_count
        ind_counts = top_8
    
    if ind_counts and len(ind_counts) > 0:
        fig.add_trace(
            go.Pie(
                values=list(ind_counts.values()),
                labels=list(ind_counts.keys()),
                hole=0.4,
                textinfo='percent+label',
                name="Indicator",
            ),
            row=1, col=2,
        )
    
    ind_pcts: list[float] = []
    ind_names: list[str] = []
    for ind in diff.affected_indicators[:10]:
        pct = calculate_change_pct(ind["old_summary"], ind["new_summary"])
        if pct is not None:
            ind_pcts.append(pct)
            ind_names.append(ind["name"][:20])
    
    if ind_pcts:
        fig.add_trace(
            go.Bar(
                x=ind_names,
                y=ind_pcts,
                marker_color='coral',
            ),
            row=2, col=1,
        )
    
    categories: list[str] = []
    for cell in diff.changed_cells:
        pct = calculate_change_pct(cell["old"], cell["new"])
        cat = get_change_category(pct)
        categories.append(cat)
    
    if categories:
        cat_counter = Counter(categories)
        cat_order = ["minor", "moderate", "major", "critical"]
        fig.add_trace(
            go.Bar(
                x=cat_order,
                y=[cat_counter.get(cat, 0) for cat in cat_order],
                marker_color=["#E0E0E0", "#CCFFCC", "#FFFFCC", "#FFCCCC"],
            ),
            row=2, col=2,
        )
    
    fig.update_layout(
        height=800,
        showlegend=False,
        title_text="快照对比统计分析",
        title_x=0.5,
    )
    
    return fig


def create_styled_dataframe(
    diff: SnapshotDiff,
    df: pd.DataFrame,
    highlight_column: str = "变化幅度%"
) -> pd.DataFrame:
    """Apply conditional styling to dataframe based on change magnitude."""
    def highlight_row(row):
        styles = [''] * len(row)
        if highlight_column in row.index:
            try:
                pct = float(row[highlight_column])
                cat = get_change_category(pct)
                color = get_change_color(cat)
                styles = [f'background-color: {color}' for _ in range(len(row))]
            except (TypeError, ValueError):
                pass
        return styles
    
    return df.style.apply(highlight_row, axis=1)