"""Shared KPI card component.

Structure and CSS are a direct port of the reference dashboard's kpiCard() /
sparkline() (samsung-marketing-intelligence/dashboard/app_pages.js,app_core.js):
container -> label (+ optional flag badge) -> value (+ optional unit) -> delta
badge -> "vs" caption -> sparkline SVG. One "hero" variant (a dark gradient
fill) for a page's single primary/composite metric, where one exists.

This module only renders. It never fetches, filters, or aggregates data --
`period_trend()` re-applies a caller-supplied aggregation function (the same
one already used to produce the page's headline number) across the first vs.
second half of the filtered weeks, and per week for the sparkline. That is
presentation of already-computed results, not new business logic: every value
it returns is something the calling page could already compute for its
headline KPI, just sliced narrower.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

DEFAULT_SPARK_COLOR = "#2B6DEF"
HERO_SPARK_COLOR = "#9FC0FF"


def _sparkline_svg(values: list[float], color: str) -> str:
    """Gradient-filled line with an end-point dot -- same construction as the
    reference's sparkline(): W=120 H=26, viewBox scaled, no axes."""
    vals = [float(v) for v in values if v is not None and pd.notna(v)]
    if len(vals) < 2:
        return ""
    w, h, pad = 120, 26, 2
    mn, mx = min(vals), max(vals)
    rg = (mx - mn) or 1

    def x(i: int) -> float:
        return pad + i * (w - pad * 2) / (len(vals) - 1)

    def y(v: float) -> float:
        return h - pad - (v - mn) / rg * (h - pad * 2)

    pts = [(x(i), y(v)) for i, v in enumerate(vals)]
    line = " ".join(f'{"M" if i == 0 else "L"}{px:.1f} {py:.1f}'
                    for i, (px, py) in enumerate(pts))
    area = f"{line} L{pts[-1][0]:.1f} {h} L{pts[0][0]:.1f} {h} Z"
    gid = f"sg{abs(hash(tuple(vals))) % 100_000}"
    lx, ly = pts[-1]
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity=".24"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/>'
        f'</linearGradient></defs>'
        f'<path d="{area}" fill="url(#{gid})"/>'
        f'<path d="{line}" fill="none" stroke="{color}" stroke-width="1.6" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.4" fill="{color}"/></svg>'
    )


def row(items: list[dict]) -> None:
    """One KPI card per item. Each item accepts:

    label (str) -- required.
    value (str) -- required, pre-formatted (this module does no number formatting).
    unit (str, optional) -- e.g. "AED", "/100"; rendered smaller, after value.
    change (float | None) -- percent change for the delta badge. None renders a
        flat "--" badge (used for a hero/composite card with no single prior
        period to compare against).
    invert (bool) -- True for "lower is better" metrics (spend, CPA), so a
        decrease still renders green/up rather than red/down.
    vs (str) -- caption next to the delta badge, e.g. "vs first half".
    spark (list[float] | None) -- week-by-week values for the sparkline.
    spark_color (str, optional) -- overrides the default line colour.
    flag / flag_tip (str, optional) -- small badge next to the label, e.g. "excl. TV".
    hero (bool) -- dark gradient "primary metric" card treatment.
    """
    html = ['<div class="kpirow">']
    for it in items:
        hero = bool(it.get("hero"))
        change = it.get("change")
        invert = bool(it.get("invert"))

        if change is None:
            cls, arrow, delta_txt = "flat", "·", "—"
        else:
            up = change >= 0
            good = (not up) if invert else up
            cls = "up" if good else "down"
            arrow = "▲" if up else "▼"
            delta_txt = f"{change:+.1f}%"

        flag_html = (f'<span class="flag" title="{it.get("flag_tip", "")}">'
                     f'{it["flag"]}</span>' if it.get("flag") else "")
        unit_html = f'<span class="u"> {it["unit"]}</span>' if it.get("unit") else ""

        spark_html = ""
        if it.get("spark"):
            color = HERO_SPARK_COLOR if hero else it.get("spark_color", DEFAULT_SPARK_COLOR)
            spark_html = _sparkline_svg(it["spark"], color)

        html.append(
            f'<div class="kpi{" hero" if hero else ""}">'
            f'<div class="lab">{it["label"]}{flag_html}</div>'
            f'<div class="val">{it["value"]}{unit_html}</div>'
            f'<div class="foot"><span class="delta {cls}">{arrow} {delta_txt}</span>'
            f'<span class="vs">{it.get("vs", "vs prior period")}</span></div>'
            f'{spark_html}</div>'
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def period_trend(df: pd.DataFrame, week_col: str, value_fn, weeks: list[int] | None = None
                 ) -> tuple[float | None, list[float]]:
    """(change_pct, weekly_trend) for a KPI's delta badge and sparkline.

    `value_fn(sub_df) -> float | None` is the SAME aggregation the caller
    already uses to compute its headline number (e.g. ``lambda d:
    d.sales_aed.sum() / d.spend_aed.sum()``) -- this just re-applies it to the
    first vs. second half of `weeks` (default: every week present in `df`) and
    to each week individually, mirroring the reference's periodSplit()/chg().
    """
    all_weeks = sorted(weeks) if weeks else sorted(df[week_col].dropna().unique())
    if len(all_weeks) < 2:
        return None, []

    mid = -(-len(all_weeks) // 2)  # ceil(len/2)
    prior_weeks, current_weeks = all_weeks[:mid], all_weeks[mid:]
    prior_val = value_fn(df[df[week_col].isin(prior_weeks)])
    current_val = value_fn(df[df[week_col].isin(current_weeks)])

    change = None
    if (prior_val not in (None, 0) and pd.notna(prior_val)
            and current_val is not None and pd.notna(current_val)):
        change = (current_val / prior_val - 1) * 100

    trend = [value_fn(df[df[week_col] == w]) for w in all_weeks]
    return change, trend
