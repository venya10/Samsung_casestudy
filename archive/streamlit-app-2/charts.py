"""Clickable Plotly figures in the Samsung palette.

Every builder returns a ``Chart``: the figure plus a lookup that maps a clicked
point back to the dimension value it represents.

Two Streamlit behaviours shape this module and are worth stating plainly, because
both are invisible until a click silently does nothing:

1.  **Only scatter traces emit click selections.** Verified against
    streamlit 1.41 / plotly 5.24: clicking a ``go.Bar`` or ``go.Heatmap`` mark
    fires ``plotly_selected`` in the browser but never reaches Python, with or
    without ``dragmode="select"``. Bars and heatmaps therefore carry a
    transparent scatter *hit layer* -- invisible markers laid over the marks so a
    click anywhere on a bar lands on a real, selectable point.

2.  **The selection payload has no trace name**, only ``curve_number``,
    ``point_index``, ``x`` and ``y``. On a horizontal bar the category happens to
    be ``y``, but on a multi-series line or stacked column the series identity
    exists only as the trace, so every builder returns a lookup indexed by
    ``values[curve_number][point_index]``.

Do not pass a ``config=`` kwarg to ``st.plotly_chart``: Streamlit forwards
**kwargs as the Plotly.js config, and overriding it stops selections reaching
Python entirely. The modebar is hidden in CSS instead.
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import state
from theme import BASELINE, GRID, INK, MUTED, SERIES, SERIES_MUTED, STATUS

HOVER = "%{customdata}<extra></extra>"
HIT_DENSITY = 26  # markers laid along each bar


class Chart(NamedTuple):
    fig: go.Figure
    values: list[list] | None = None  # values[curve_number][point_index] -> dim value
    field: str | None = None          # fallback: read the value straight off the point


def _emphasis(cats, dim: str, base_colors) -> list[str]:
    """Dim marks outside the active filter, the way Power BI highlights."""
    sel = state.active().get(dim)
    if isinstance(base_colors, str):
        base_colors = [base_colors] * len(cats)
    if not sel:
        return list(base_colors)
    keep = {str(v) for v in sel}
    return [c if str(x) in keep else SERIES_MUTED for x, c in zip(cats, base_colors)]


def _hit_size(n: int) -> float:
    """Big enough to catch a click, small enough not to bleed into the next row."""
    return float(np.clip(340 / max(n, 1), 9, 26))


def _add_hit(fig: go.Figure, xs, ys, size: float, hide_legend: bool = True) -> None:
    """Overlay invisible, clickable markers.

    A second trace flips Plotly's legend on, which would print a meaningless
    "trace 0" on every single-series chart, so the legend is suppressed unless
    the chart genuinely has series to label.
    """
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers", hoverinfo="none", showlegend=False,
        marker=dict(size=size, color="rgba(0,0,0,0)")))
    if hide_legend:
        fig.update_layout(showlegend=False)


def render(chart: Chart, key: str, dim: str | None = None, height: int = 320) -> None:
    fig = chart.fig
    fig.update_layout(height=height)
    if dim is None:
        st.plotly_chart(fig, use_container_width=True, key=key)
        return
    st.plotly_chart(fig, use_container_width=True,
                    key=state.bind(key, dim, chart.values, chart.field),
                    on_select="rerun", selection_mode="points")


# --------------------------------------------------------------------------
def bar_h(df: pd.DataFrame, cat: str, val: str, dim: str, hover_fn=None,
          color: str | list = SERIES[0], highlight_extremes: bool = False,
          value_fmt=None) -> Chart:
    """Horizontal bars, sorted. One measure across categories gets one hue.

    ``hover_fn`` takes a row and returns its tooltip. It is applied *after* the
    sort -- a pre-built list would pair each bar with a different row's numbers.
    """
    d = df.sort_values(val)
    cats, vals = d[cat].astype(str).tolist(), d[val].tolist()

    if highlight_extremes and len(vals) > 2:
        color = [SERIES_MUTED] * len(vals)
        color[-1], color[0] = SERIES[0], SERIES[1]
    colors = _emphasis(cats, dim, color)

    text = [value_fmt(v) if value_fmt else f"{v:,.0f}" for v in vals]
    hover = [hover_fn(r) for r in d.itertuples()] if hover_fn else text
    fig = go.Figure(go.Bar(
        x=vals, y=cats, orientation="h", marker_color=colors,
        marker_line_width=0, text=text, textposition="outside",
        textfont=dict(size=11.5, color=INK), cliponaxis=False,
        customdata=hover, hovertemplate=HOVER))
    fig.update_layout(xaxis=dict(showgrid=True, gridcolor=GRID, showline=False,
                                 ticks="", showticklabels=False),
                      yaxis=dict(showgrid=False, linecolor=BASELINE, showline=True,
                                 tickfont=dict(size=12, color=INK)),
                      margin=dict(l=8, r=54, t=8, b=8), bargap=0.34)

    hx, hy, hv = [], [], []
    for c, v in zip(cats, vals):
        for t in np.linspace(0.03, 0.97, HIT_DENSITY):
            hx.append(v * t), hy.append(c), hv.append(c)
    _add_hit(fig, hx, hy, _hit_size(len(cats)))
    return Chart(fig, [cats, hv])


def line(df: pd.DataFrame, x: str, y: str, series: str, dim: str,
         hover_fmt=None, label_fn=None) -> Chart:
    """One line per series member; the filtered members stay saturated.

    Scatter traces are natively clickable, so no hit layer is needed -- clicking
    any marker on a line filters to that series member.
    """
    fig = go.Figure()
    sel = state.active().get(dim)
    keep = {str(v) for v in sel} if sel else None
    members = list(dict.fromkeys(df[series].astype(str)))
    lookup = []

    for i, m in enumerate(members):
        d = df[df[series].astype(str) == m].sort_values(x)
        on = keep is None or m in keep
        vals = d[y].tolist()
        name = label_fn(m) if label_fn else m
        fig.add_trace(go.Scatter(
            x=d[x].tolist(), y=vals, name=name, mode="lines+markers",
            line=dict(color=SERIES[i % len(SERIES)] if on else SERIES_MUTED,
                      width=2.2 if on else 1.2),
            marker=dict(size=8 if on else 6),
            opacity=1.0 if on else 0.5,
            customdata=[f"{name} · Week {a}<br>"
                        f"{hover_fmt(v) if hover_fmt else f'{v:,.0f}'}"
                        for a, v in zip(d[x], vals)],
            hovertemplate=HOVER))
        lookup.append([m] * len(vals))

    fig.update_layout(xaxis=dict(title="", dtick=1), hovermode="closest")
    return Chart(fig, lookup)


def scatter(df: pd.DataFrame, x: str, y: str, label: str, dim: str,
            size: str | None = None, hover_fn=None) -> Chart:
    d = df.dropna(subset=[x, y])  # hover_fn runs on `d`, after any rows are dropped
    cats = d[label].astype(str).tolist()
    colors = _emphasis(cats, dim, SERIES[0])
    sizes = 11
    if size and d[size].max() > 0:
        sizes = 9 + 26 * (d[size] / d[size].max()) ** 0.5

    fig = go.Figure(go.Scatter(
        x=d[x], y=d[y], mode="markers+text", text=cats, textposition="top center",
        textfont=dict(size=10.5, color=MUTED),
        marker=dict(color=colors, size=sizes, line=dict(width=1, color="#fff"),
                    opacity=0.9),
        customdata=[hover_fn(r) for r in d.itertuples()] if hover_fn else cats,
        hovertemplate=HOVER))
    fig.update_layout(xaxis=dict(showgrid=True, gridcolor=GRID),
                      margin=dict(l=8, r=24, t=22, b=8))
    return Chart(fig, [cats])


def stacked(df: pd.DataFrame, x: str, series: str, val: str, dim: str,
            hover_fmt=None) -> Chart:
    """Composition over time. Clicking a segment filters on the series member."""
    fig = go.Figure()
    sel = state.active().get(dim)
    keep = {str(v) for v in sel} if sel else None
    members = list(dict.fromkeys(df[series].astype(str)))
    xs = sorted(df[x].unique())
    lookup = []

    base = {k: 0.0 for k in xs}          # running stack height, for the hit layer
    hx, hy, hv = [], [], []
    for m in members:
        d = df[df[series].astype(str) == m].set_index(x).reindex(xs).fillna(0)
        on = keep is None or m in keep
        vals = d[val].tolist()
        fig.add_trace(go.Bar(
            x=xs, y=vals, name=m,
            marker_color=SERIES[members.index(m) % len(SERIES)] if on else SERIES_MUTED,
            marker_line_width=0, opacity=1.0 if on else 0.45,
            customdata=[f"{m} · Week {a}<br>"
                        f"{hover_fmt(v) if hover_fmt else f'{v:,.0f}'}"
                        for a, v in zip(xs, vals)],
            hovertemplate=HOVER))
        lookup.append([m] * len(xs))
        for k, v in zip(xs, vals):
            if v > 0:
                for t in np.linspace(0.2, 0.8, 3):
                    hx.append(k), hy.append(base[k] + v * t), hv.append(m)
            base[k] += v

    _add_hit(fig, hx, hy, 13, hide_legend=False)
    fig.update_layout(barmode="stack", bargap=0.3, xaxis=dict(dtick=1, title=""))
    return Chart(fig, lookup + [hv])


def columns(df: pd.DataFrame, x: str, val: str, dim: str, hover_fn=None,
            value_fmt=None) -> Chart:
    """Single-series vertical columns; the x value is the dimension value."""
    d = df.sort_values(x)
    cats = d[x].astype(str).tolist()
    colors = _emphasis(cats, dim, SERIES[0])
    vals = d[val].tolist()
    hover = ([hover_fn(r) for r in d.itertuples()] if hover_fn
             else [f"{v:,.0f}" for v in vals])
    fig = go.Figure(go.Bar(
        x=d[x].tolist(), y=vals, marker_color=colors, marker_line_width=0,
        text=[value_fmt(v) if value_fmt else f"{v:,.0f}" for v in vals],
        textposition="outside", textfont=dict(size=11, color=INK), cliponaxis=False,
        customdata=hover, hovertemplate=HOVER))
    fig.update_layout(bargap=0.4, xaxis=dict(dtick=1, title=""))

    hx, hy, hv = [], [], []
    for k, c, v in zip(d[x].tolist(), cats, vals):
        for t in np.linspace(0.05, 0.95, HIT_DENSITY):
            hx.append(k), hy.append(v * t), hv.append(c)
    _add_hit(fig, hx, hy, _hit_size(len(cats)))
    return Chart(fig, [cats, hv])


def heatmap(pivot: pd.DataFrame, dim: str, on: str = "columns", fmt=None,
            diverging: bool = False, center: float = 0.0) -> Chart:
    """Rows = index, cols = columns. ``on`` picks which axis carries the filter."""
    z = pivot.values
    if diverging:
        scale = [[0, "#c2422e"], [0.5, "#f2efe9"], [1, "#2f4bd4"]]
        s = _span(z, center)
        lo, hi = center - s, center + s
    else:
        scale = [[0, "#eef1fc"], [0.5, "#7f93e3"], [1, "#1428A0"]]
        lo = hi = None

    cols = [str(c) for c in pivot.columns]
    rows = [str(i) for i in pivot.index]
    text = [[("—" if pd.isna(v) else (fmt(v) if fmt else f"{v:,.1f}")) for v in row]
            for row in z]
    fig = go.Figure(go.Heatmap(
        z=z, x=cols, y=rows, colorscale=scale, zmin=lo, zmax=hi, showscale=False,
        xgap=2, ygap=2, text=text, texttemplate="%{text}",
        textfont=dict(size=11), hovertemplate="%{y} · %{x}<br>%{text}<extra></extra>"))
    fig.update_layout(xaxis=dict(side="top", showgrid=False, ticks="",
                                 showline=False, tickfont=dict(size=11.5, color=INK)),
                      yaxis=dict(showgrid=False, autorange="reversed",
                                 tickfont=dict(size=11.5, color=INK)),
                      margin=dict(l=8, r=8, t=8, b=8))

    hx, hy, hv = [], [], []
    for r in rows:
        for c in cols:
            hx.append(c), hy.append(r), hv.append(c if on == "columns" else r)
    _add_hit(fig, hx, hy, 22)
    return Chart(fig, [[], hv])


def _span(z, center) -> float:
    d = np.nanmax(np.abs(np.asarray(z, dtype=float) - center))
    return float(d) if d and d == d else 1.0


def status_bar(df: pd.DataFrame, cat: str, val: str, status: str, dim: str,
               hover_fn=None, value_fmt=None) -> Chart:
    """Bars coloured by state. Status colour always ships alongside a word."""
    d = df.sort_values(val)
    cats, vals = d[cat].astype(str).tolist(), d[val].tolist()
    base = [STATUS.get(s, SERIES[0]) for s in d[status]]
    colors = _emphasis(cats, dim, base)
    text = [value_fmt(v) if value_fmt else f"{v:,.2f}" for v in vals]
    fig = go.Figure(go.Bar(
        x=vals, y=cats, orientation="h", marker_color=colors, marker_line_width=0,
        text=text, textposition="outside", textfont=dict(size=11.5, color=INK),
        cliponaxis=False,
        customdata=[hover_fn(r) for r in d.itertuples()] if hover_fn else text,
        hovertemplate=HOVER))
    fig.update_layout(xaxis=dict(showgrid=True, gridcolor=GRID, showline=False,
                                 ticks="", showticklabels=False),
                      yaxis=dict(showgrid=False, linecolor=BASELINE, showline=True,
                                 tickfont=dict(size=12, color=INK)),
                      margin=dict(l=8, r=54, t=8, b=8), bargap=0.34)

    hx, hy, hv = [], [], []
    for c, v in zip(cats, vals):
        for t in np.linspace(0.03, 0.97, HIT_DENSITY):
            hx.append(v * t), hy.append(c), hv.append(c)
    _add_hit(fig, hx, hy, _hit_size(len(cats)))
    return Chart(fig, [cats, hv])
