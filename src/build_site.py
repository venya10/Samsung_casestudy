"""Generate the static HTML dashboard.

Reads the processed tables and writes a self-contained site into `site/`. No
server needed to view it: open `site/index.html`. `src/serve.py` adds only the
live AI assistant.
"""
from __future__ import annotations

import json
import re
import shutil

import numpy as np
import pandas as pd

import ingest
import site_charts as C
from alerts import load_rules as load_alert_rules
from common import (
    ASSETS,
    CURRENCY,
    DATA_PBI,
    DATA_PROCESSED,
    GROSS_MARGIN,
    MARKET_LABEL,
    SITE,
    SOURCE_FILE,
    market_label,
)

# (file, label, nav group, icon glyph). Grouped and glyphed the way the visual
# reference groups its own nav (Performance / Decide / Foundation) -- this
# project has 8 pages where the reference has 10, so the grouping is mapped by
# content rather than copied wholesale (no "Campaign Performance" or "Next Best
# Actions" page exists here to group).
def _nav_icon(inner: str, color: str) -> str:
    """One outlined, pastel-tinted glyph per nav item -- same hand-rolled
    stroke-SVG style as the KPI icons (_ICONS below), but each carries its
    own colour instead of `currentColor` so the sidebar reads as a set of
    distinct, softly-coloured marks rather than plain monochrome glyphs."""
    return (f'<svg width="15" height="15" viewBox="0 0 18 18" fill="none" stroke="{color}" '
            f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{inner}</svg>')


PAGES = [
    ("index.html", "Overview", "Performance",
     _nav_icon('<path d="M3 14V9M9 14V4M15 14V7"/>', "#7FA8FF")),
    ("channels.html", "Channels", "Performance",
     _nav_icon('<circle cx="9" cy="9" r="6"/><path d="M9 3v6l5.2-3"/>', "#62C4C2")),
    ("portfolio.html", "Markets &amp; Products", "Performance",
     _nav_icon('<rect x="2.5" y="2.5" width="5.5" height="5.5" rx="1"/>'
               '<rect x="10" y="2.5" width="5.5" height="5.5" rx="1"/>'
               '<rect x="2.5" y="10" width="5.5" height="5.5" rx="1"/>'
               '<rect x="10" y="10" width="5.5" height="5.5" rx="1"/>', "#6FCFA0")),
    ("influencers.html", "Influencers", "Performance",
     _nav_icon('<circle cx="9" cy="6" r="2.3"/><path d="M4 15c0-3 2.3-5 5-5s5 2 5 5"/>', "#F291B7")),
    ("brand.html", "Brand &amp; Competition", "Performance",
     _nav_icon('<path d="M9 2.5l5.5 2v4c0 4-2.3 6.7-5.5 8-3.2-1.3-5.5-4-5.5-8v-4z"/>', "#B39BF0")),
    ("insights.html", "Insights &amp; Actions", "Decide",
     _nav_icon('<path d="M9 2.8a4.2 4.2 0 00-2.4 7.6c.5.4.9 1 .9 1.7v.4h3v-.4c0-.7.4-1.3.9-1.7A4.2 4.2 0 009 2.8z"/>'
               '<path d="M7.3 15h3.4M7.8 16.6h2.4"/>', "#F2D98A")),
    ("alerts.html", "Early Warning", "Decide",
     _nav_icon('<path d="M9 3 16 15H2Z"/><path d="M9 7.5v3"/>'
               '<circle cx="9" cy="12.3" r=".9" fill="#F2A6A6" stroke="none"/>', "#F2A6A6")),
    ("assistant.html", "Ask AI", "Decide",
     _nav_icon('<path d="M9 2.5l1.2 3.3L13.5 7l-3.3 1.2L9 11.5l-1.2-3.3L4.5 7l3.3-1.2z"/>'
               '<path d="M14 11.3l.6 1.6 1.6.6-1.6.6-.6 1.6-.6-1.6-1.6-.6 1.6-.6z"/>', "#F2AD5C")),
    ("data.html", "Data", "Foundation",
     _nav_icon('<rect x="2.5" y="2.5" width="13" height="13" rx="1.5"/><path d="M2.5 9h13M9 2.5v13"/>', "#7FA8FF")),
]

# Every table the pipeline models -- used only to state the true total on the
# Data page's "Modelled tables" KPI. Browsing and download are scoped to
# FACT_TABLES below; the rest (analysis outputs, lookups) are still computed
# and still power their own page's charts, just not re-exposed as raw sheets
# here -- 19 browsable tables was clutter, not transparency.
EXPLORER_TABLES = [
    ("fact_base", "The cleaned source, at its original grain: week x market x channel x product"),
    ("fact_market_week", "The spine — one row per week per market, everything joined"),
    ("fact_channel", "week x market x channel"),
    ("fact_product", "week x market x product"),
    ("fact_influencer", "Every influencer placement"),
    ("fact_brand", "Brand metrics averaged to market-week (indicative index)"),
    ("channel_efficiency", "Analysis: cost and return per channel"),
    ("market_scorecard", "Analysis: the 8 subsidiaries benchmarked"),
    ("product_summary", "Analysis: the 6 devices"),
    ("influencer_scorecard", "Analysis: the 24 creators scored"),
    ("panel_model", "Analysis: association model with confidence intervals"),
    ("paid_vs_earned", "Analysis: paid against earned"),
    ("reallocation", "Analysis: the directional budget shift"),
    ("alerts", "Every alert fired across the 8 weeks"),
    ("dim_market", "Lookup: subsidiary codes"),
    ("dim_channel", "Lookup: channel classification"),
    ("dim_product", "Lookup: devices"),
    ("dim_influencer", "Lookup: creators and follower-count reliability"),
    ("dim_week", "Lookup: weeks"),
]

# (table, display name, description). The 6 fact tables -- the cleaned data
# itself -- are what the Data page browses and downloads. Plain business
# names, not the internal fact_ prefix.
FACT_TABLES = [
    ("fact_base", "Master Table",
     "The cleaned source, at its original grain: week x market x channel x product"),
    ("fact_market_week", "Markets", "The spine — one row per week per market"),
    ("fact_channel", "Channels", "week x market x channel"),
    ("fact_product", "Products", "week x market x product"),
    ("fact_influencer", "Influencers", "Every influencer placement"),
    ("fact_brand", "Brand", "Brand metrics averaged to market-week (indicative index)"),
]

LOGO = (ASSETS / "samsung-wordmark.svg").read_text(encoding="utf-8")


def load(name: str) -> pd.DataFrame:
    return pd.read_parquet(DATA_PROCESSED / f"{name}.parquet")


def aed(v, dp: int = 0) -> str:
    if v is None or (isinstance(v, float) and (np.isnan(v))):
        return "—"
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1e9:
        return f"{sign}{a/1e9:,.2f}bn AED"
    if a >= 1e6:
        return f"{sign}{a/1e6:,.1f}m AED"
    if a >= 1e3:
        return f"{sign}{a/1e3:,.0f}k AED"
    return f"{sign}{a:,.{dp}f} AED"


def aed_short(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1e6:
        return f"{sign}{a/1e6:,.1f}m"
    if a >= 1e3:
        return f"{sign}{a/1e3:,.0f}k"
    return f"{sign}{a:,.0f}"


def x_fmt(v) -> str:
    return "—" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:,.2f}x"


def int_fmt(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)) or v == 0:
        return "—"
    return f"{v:,.0f}"


def ctr_fmt(v) -> str:
    return "—" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.2f}%"


def attribution_pill(attributed: bool) -> str:
    return (f'<span class="pill ok">Measured</span>' if attributed
            else f'<span class="pill bad">Gap</span>')


def flag_pill(flag: str) -> str:
    """Colour-codes insights.py's influencer `flag` -- green for the scale
    candidates, amber for the on-par majority, red for the two costly/
    underperforming tiers. The short label goes in the pill; the full flag
    text (e.g. "Costly — CPA well above roster") is kept as a hover tooltip
    so nothing is lost, just compressed."""
    if flag.startswith("Strong"):
        cls, label = "ok", "Scale"
    elif flag.startswith("Costly"):
        cls, label = "bad", "Costly"
    elif flag.startswith("Underperforming"):
        cls, label = "bad", "Underperforming"
    else:
        cls, label = "warn", "On par"
    return f'<span class="pill {cls}" title="{C.esc(flag)}">{label}</span>'


def severity_pill(sev: str) -> str:
    """Red/orange/yellow, matching the Early Warning page's KPI cards, alert
    borders and history chart -- one severity palette, everywhere it appears."""
    return f'<span class="pill sev-{C.esc(sev)}">{C.esc(sev)}</span>'


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------
def shell(active: str, title: str, body: str, period: str, *,
          crit_count: int = 0) -> str:
    nav_parts = []
    last_group = None
    for href, label, group, icon in PAGES:
        if group != last_group:
            nav_parts.append(f'<div class="sb-nav-label">{group}</div>')
            last_group = group
        badge = (f'<span class="badge">{crit_count}</span>'
                 if href == "alerts.html" and crit_count else "")
        on = ' class="on"' if href == active else ""
        nav_parts.append(
            f'<a href="{href}"{on}><span class="ic">{icon}</span>'
            f'<span class="lbl">{label}</span>{badge}</a>'
        )
    nav = "".join(nav_parts)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Samsung MENA Marketing Intelligence</title>
<link rel="stylesheet" href="assets/app.css">
<script>(function(){{try{{if(localStorage.getItem('sb-collapsed')==='1')document.documentElement.classList.add('sb-collapsed');}}catch(e){{}}}})();</script>
</head>
<body>
<div class="app">
<aside class="sidebar" id="sidebar">
  <div class="sb-top"><button class="sb-toggle" id="sbToggle" aria-label="Collapse sidebar" title="Collapse sidebar">
    <svg viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 2.5 4 7.5l5.5 5"/></svg>
  </button></div>
  <div class="sb-brand"><a href="index.html">{LOGO.replace('<svg ', '<svg class="sb-logo" ', 1)}<span class="sb-name">Marketing Intelligence</span><span class="sb-meta">MENA · {period}</span></a></div>
  <nav class="sb-nav">{nav}</nav>
</aside>
<div class="main">
<main class="wrap">
{body}
</main>
<footer><div class="footer-inner">
  <span>Samsung MENA Marketing Intelligence · generated from the weekly pipeline</span>
  <span>All figures in AED · 8 weeks · 8 markets · 8 channels · 6 products</span>
</div></footer>
</div>
</div>
<script src="assets/app_charts.js"></script>
<script src="assets/app_filter.js"></script>
<script src="assets/app_pages.js"></script>
<script src="assets/app.js"></script>
</body>
</html>"""


def head(eyebrow: str, h1: str, filter_page: str | None = None,
         kpis_html: str | None = None) -> str:
    """Sticky page-header bar: title + cross-filter controls on one row
    (when `filter_page` is given), with the page's KPI row (when given)
    stacked directly beneath -- title, filters and KPI tiles all stay
    pinned together while only the charts below scroll. `eyebrow` is kept
    for screen readers as page context, not shown visually -- the sticky
    bar only has room for one clean line of title."""
    filterbar = f'<div id="mount-filterbar" data-page="{filter_page}"></div>' if filter_page else ''
    kpis_block = kpis_html or ""
    return (
        '<div class="page-header-bar">'
        '<div class="page-header-top">'
        f'<div class="page-head"><span class="sr-only">{eyebrow}</span><h1>{h1}</h1></div>'
        f'{filterbar}'
        "</div>"
        f'{kpis_block}'
        '</div>'
    )


def _sparkline_svg(values: list[float], color: str) -> str:
    """Gradient-filled line with an end-point dot. W=120 H=26, viewBox
    scaled, no axes -- a shape, not a chart to be read precisely."""
    vals = [float(v) for v in values if v is not None and not (isinstance(v, float) and np.isnan(v))]
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
    line = " ".join(f'{"M" if i == 0 else "L"}{px:.1f} {py:.1f}' for i, (px, py) in enumerate(pts))
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


# One small outline-icon vocabulary for every KPI tile on the site, so a
# reviewer learns the shapes once and reads every page's KPI row the same
# way. Colour comes from the card's own --k-accent (currentColor), not baked
# into the icon -- tiles themselves are plain now; the icon carries the
# pastel instead. stroke-linecap/join set once at the <svg> level.
_ICON_ATTRS = ('width="15" height="15" viewBox="0 0 18 18" fill="none" '
               'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
               'stroke-linejoin="round" class="kpi-icon"')
_ICONS = {
    "currency": f'<svg {_ICON_ATTRS}><rect x="2" y="5" width="14" height="8" rx="1.5"/>'
                '<circle cx="9" cy="9" r="1.8"/></svg>',
    "percent": f'<svg {_ICON_ATTRS}><circle cx="5.5" cy="5.5" r="1.6"/>'
               '<circle cx="12.5" cy="12.5" r="1.6"/><path d="M13 5 5 13"/></svg>',
    "trend": f'<svg {_ICON_ATTRS}><path d="M3 13l4-4 3 3 6-7"/>'
             '<path d="M12.5 4.5H16v3.5"/></svg>',
    "alert": f'<svg {_ICON_ATTRS}><path d="M9 3 16 15H2Z"/><path d="M9 7.5v3"/>'
             '<circle cx="9" cy="12.3" r=".9" fill="currentColor" stroke="none"/></svg>',
    "people": f'<svg {_ICON_ATTRS}><circle cx="9" cy="6" r="2.3"/>'
              '<path d="M4 15c0-3 2.3-5 5-5s5 2 5 5"/></svg>',
    "table": f'<svg {_ICON_ATTRS}><rect x="2.5" y="2.5" width="13" height="13" rx="1.5"/>'
             '<path d="M2.5 9h13M9 2.5v13"/></svg>',
    "check": f'<svg {_ICON_ATTRS}><circle cx="9" cy="9" r="6.5"/>'
             '<path d="M5.8 9.2l2.1 2.1 4.3-4.6"/></svg>',
    "rows": f'<svg {_ICON_ATTRS}><path d="M3 5h12M3 9h12M3 13h12"/></svg>',
    "broadcast": f'<svg {_ICON_ATTRS}><circle cx="9" cy="12" r="1.6"/>'
                 '<path d="M5.5 10.5a5 5 0 017 0M3 7.8a9 9 0 0112 0"/></svg>',
    "hash": f'<svg {_ICON_ATTRS}><path d="M6.2 3 4.6 15M13.4 3 11.8 15M3 7.3h12M2.4 10.7h12"/></svg>',
}


def _kpi_icon(label: str, value: str, unit: str) -> str:
    """Best-effort icon, matched by what the number actually is (an AED
    amount, a ratio, a percentage) first, then by a few labels specific
    enough to deserve their own picture, falling back to a generic count."""
    if "AED" in value:
        return _ICONS["currency"]
    if unit == "x":
        return _ICONS["trend"]
    if unit == "%":
        return _ICONS["percent"]
    low = label.lower()
    if "influencer" in low:
        return _ICONS["people"]
    if "table" in low:
        return _ICONS["table"]
    if "check" in low:
        return _ICONS["check"]
    if "row" in low:
        return _ICONS["rows"]
    if "grp" in low:
        return _ICONS["broadcast"]
    if "alert" in low or "fired" in low or low in ("critical", "high", "medium", "open now"):
        return _ICONS["alert"]
    return _ICONS["hash"]


def kpi(label: str, value: str, unit: str = "", delta: float | None = None,
        good_up: bool = True, vs: str = "vs prior period",
        spark: list[float] | None = None, spark_color: str | None = None) -> str:
    """One KPI card: an auto-picked icon, header label, the number, and --
    only where a call site opts in -- a trend badge and a sparkline. Most
    pages still just pass label/value/unit; the Overview page's KPI row is
    the one that uses the rest. `delta` is a fraction (0.023 == +2.3%);
    `good_up=False` marks a lower-is-better metric so a decrease still
    renders as the "up"/green badge."""
    foot = ""
    if delta is not None and pd.notna(delta):
        up = delta >= 0
        cls = "up" if (up == good_up) else "down"
        arrow = "▲" if up else "▼"
        foot = (f'<div class="foot"><span class="delta {cls}">{arrow} '
                f'{abs(delta)*100:,.1f}%</span><span class="vs">{vs}</span></div>')
    unit_html = f'<span class="u"> {unit}</span>' if unit else ""
    spark_html = _sparkline_svg(spark, spark_color or C.SERIES[0]) if spark else ""
    icon = _kpi_icon(label, value, unit)
    return (f'<div class="kpi"><div class="lab">{icon}{label}</div>'
            f'<div class="val">{value}{unit_html}</div>{foot}{spark_html}</div>')


def kpi_link(target: str, kpi_html: str, external: bool = False) -> str:
    """Wraps a kpi() card as a plain link -- used where nothing on this page
    answers the KPI itself (Open alerts links straight to the page that
    does). A KPI whose chart pair lives on this page uses kpi_select()
    instead, which selects in place rather than navigating."""
    href = target if external else f"#{target}"
    return f'<a class="kpi-link" href="{href}">{kpi_html}</a>'


def kpi_select(key: str, kpi_html: str, selected: bool = False) -> str:
    """Wraps a kpi() card as a click-to-select target (the Overview page's
    KPI-driven chart pair) instead of kpi_link's jump-to-anchor -- same
    display:contents trick so the button adds no box of its own, just a
    data-kpi hook for assets/app_pages.js's click handler and a .selected
    modifier for the highlighted-card outline."""
    cls = "kpi-link" + (" selected" if selected else "")
    return f'<button type="button" class="{cls}" data-kpi="{key}">{kpi_html}</button>'


def kpis(items: list[str]) -> str:
    return '<div class="kpis">' + "".join(items) + "</div>"


def card(title: str, sub: str, content: str, extra: str = "") -> str:
    s = f'<div class="card-sub">{sub}</div>' if sub else ""
    return (f'<div class="card"><div class="card-head"><h3>{title}</h3>{s}</div>'
            f"{content}{extra}</div>")


def note(text: str, kind: str = "") -> str:
    cls = "note" + (f" {kind}" if kind else "")
    return f'<div class="{cls}">{text}</div>'


def table(df: pd.DataFrame, formats: dict | None = None,
          classes: dict | None = None, sortable: bool = False) -> str:
    formats = formats or {}
    classes = classes or {}
    # `sortable` adds a `data-sort` attribute per cell carrying the raw,
    # unformatted value -- assets/app.js's click-to-sort reads that instead
    # of re-parsing "24,908" or "1.28x" back out of the display text.
    ths = "".join(
        f'<th class="{"num" if c in formats else ""}'
        f'{" sort-h" if sortable else ""}"'
        + (f' data-i="{i}"' if sortable else "")
        + f'>{c.replace("_", " ")}</th>'
        for i, c in enumerate(df.columns))
    rows = []
    for _, r in df.iterrows():
        tds = []
        for c in df.columns:
            v = r[c]
            sort_attr = f' data-sort="{C.esc(v)}"' if sortable and not pd.isna(v) else ""
            # Catch missing values here rather than in every formatter. A NaN that
            # reaches a format string renders as the literal "nan", which looks
            # like a broken pipeline; an em dash reads as "not applicable", which
            # is what it means -- these columns are null because the measure does
            # not exist for that row, not because a calculation failed.
            if c in formats:
                cls = "num" + (" " + classes[c](v) if c in classes else "")
                txt = "—" if pd.isna(v) else formats[c](v)
                tds.append(f'<td class="{cls}"{sort_attr}>{txt}</td>')
            else:
                tds.append(f"<td{sort_attr}>{'—' if pd.isna(v) else C.esc(v)}</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")
    wrap_cls = "table-wrap" + (" sortable-table" if sortable else "")
    return (f'<div class="{wrap_cls}"><table><thead><tr>{ths}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def table_view(df: pd.DataFrame, formats: dict | None = None,
               label: str = "View as table") -> str:
    return (f'<details class="table-view"><summary>{label}</summary>'
            f"{table(df, formats)}</details>")


WK = [f"Wk {i}" for i in range(1, 9)]


def _wow(vals: list[float]) -> float | None:
    """First half of the series vs the second half -- the one definition of
    week-over-week movement this project uses, shared by every page that
    needs a trend direction rather than each recomputing its own."""
    mid = -(-len(vals) // 2)
    prior, cur = sum(vals[:mid]) / mid, sum(vals[mid:]) / (len(vals) - mid)
    return (cur / prior - 1) if prior else None


# ==========================================================================
# Page 1 — Overview
# ==========================================================================
def page_overview(d: dict) -> str:
    spine, eff, ms, ps, base = d["spine"], d["eff"], d["ms"], d["ps"], d["base"]
    alerts = d["alerts_current"]

    total_spend = spine["spend_aed"].sum()
    total_sales = spine["sales_aed"].sum()
    tv = eff[eff["channel"] == "TV"].iloc[0]
    earned = d["pve"][d["pve"]["media_type"] == "earned"]
    earned_share = float(earned["share_of_sales"].iloc[0]) if len(earned) else np.nan
    measurable = eff[eff["revenue_attributed"] & eff["roas"].notna()]

    # Weekly series for the KPI sparklines AND each KPI's trend chart --
    # ratios of weekly sums, never a mean of weekly ratios, matching the
    # project's one-definition-per-KPI rule. Unchanged from before this
    # redesign; the trend chart reuses these exact series rather than
    # recomputing anything.
    wk_kpi = spine.groupby("week", as_index=False).agg(
        sales_aed=("sales_aed", "sum"), spend_aed=("spend_aed", "sum"),
        earned_sales_aed=("earned_sales_aed", "sum"), tv_spend_aed=("tv_spend_aed", "sum"))
    sales_trend = wk_kpi["sales_aed"].tolist()
    spend_trend = wk_kpi["spend_aed"].tolist()
    mer_trend = (wk_kpi["sales_aed"] / wk_kpi["spend_aed"]).tolist()
    earned_trend = (wk_kpi["earned_sales_aed"] / wk_kpi["sales_aed"] * 100).tolist()
    tv_share_trend = (wk_kpi["tv_spend_aed"] / wk_kpi["spend_aed"] * 100).tolist()

    # Same six hues as the pastel cycle each card already tints itself with
    # (.kpis .kpi:nth-child(6n+N) in app.css) -- the sparkline (and now each
    # KPI's own trend chart) matches its own card's accent.
    KPI_ACCENTS = ["#7FA8FF", "#6FCFA0", "#F2AD5C", "#B39BF0", "#F291B7", "#62C4C2"]

    # --- breakdown series, by channel / market / product -- read straight
    # off eff/ms/ps/base, the exact tables the rest of the site already uses
    # for these numbers. No new KPI definition anywhere below: "earned share
    # by product" and "unmeasured spend by market" aren't precomputed
    # columns, so they're aggregated here from fact_base's own row-level
    # media_type/revenue_attributed/spend_aed/sales_aed -- a page-assembly
    # grouping, the same thing _channel_drilldown() already does for the
    # Channels page, not a new backend metric.
    def _rows(labels, values, fvals=None) -> list[dict]:
        fvals = list(fvals) if fvals is not None else list(labels)
        return [
            {"label": lab, "fval": fv,
             "value": None if (v is None or (isinstance(v, float) and pd.isna(v))) else float(v)}
            for lab, v, fv in zip(labels, values, fvals)
        ]

    def _mkt_rows(df: pd.DataFrame, col: str) -> list[dict]:
        s = df.sort_values(col, ascending=False)
        return _rows([market_label(mk) for mk in s["market"]], s[col], s["market"])

    eff_sales = eff.sort_values("sales_aed", ascending=False)
    eff_spend = eff.sort_values("spend_aed", ascending=False)
    ps_sales = ps.sort_values("sales_aed", ascending=False)
    ps_spend = ps.sort_values("spend_aed", ascending=False)
    m_mer = measurable.sort_values("roas", ascending=False)
    ps_mer = ps[ps["roas"].notna()].sort_values("roas", ascending=False)

    # Earned share by product: fact_base's own media_type tags each row paid
    # or earned already (the same tag channel_efficiency's "media_type"
    # column carries) -- pivot sales by product x media_type and take the
    # earned fraction, exactly what the KPI itself does at the whole-dataset
    # grain via paid_vs_earned.
    prod_media = (base.groupby(["product", "media_type"], as_index=False)["sales_aed"].sum()
                  .pivot(index="product", columns="media_type", values="sales_aed").fillna(0))
    for col in ("paid", "earned"):
        if col not in prod_media.columns:
            prod_media[col] = 0.0
    prod_media["total"] = prod_media["paid"] + prod_media["earned"]
    prod_media["earned_share"] = np.where(
        prod_media["total"] > 0, prod_media["earned"] / prod_media["total"] * 100, np.nan)
    prod_earned = prod_media.reset_index().sort_values("earned_share", ascending=False)

    # Unmeasured spend by market / by channel: spend on channels without an
    # attributed return (TV; PR too, though PR carries no spend at all) --
    # the same revenue_attributed flag channel_efficiency already carries,
    # just summed by a different dimension.
    unmeas_channels = eff.loc[~eff["revenue_attributed"], "channel"].tolist()
    mkt_unmeas = (base[base["channel"].isin(unmeas_channels)]
                  .groupby("market", as_index=False)["spend_aed"].sum())
    mkt_unmeas = (ms[["market"]].merge(mkt_unmeas, on="market", how="left").fillna(0)
                  .sort_values("spend_aed", ascending=False))
    chan_unmeas = eff.assign(
        unmeasured_spend_aed=np.where(~eff["revenue_attributed"], eff["spend_aed"], 0.0)
    ).sort_values("unmeasured_spend_aed", ascending=False)

    breakdown = {
        "sales": {
            "channel": _rows(eff_sales["channel"], eff_sales["sales_aed"]),
            "market": _mkt_rows(ms, "sales_aed"),
            "product": _rows(ps_sales["product"], ps_sales["sales_aed"]),
        },
        "spend": {
            "channel": _rows(eff_spend["channel"], eff_spend["spend_aed"]),
            "market": _mkt_rows(ms, "spend_aed"),
            "product": _rows(ps_spend["product"], ps_spend["spend_aed"]),
        },
        # TV (and PR, also unattributed) fall out of the "measurable"/notna
        # filters here -- carried as a note under the chart instead of a
        # literal 0 bar, per the "don't score a measurement gap as a zero"
        # rule this project already applies to every other ROAS ranking.
        "mer": {
            "channel": _rows(m_mer["channel"], m_mer["roas"]),
            "market": _mkt_rows(ms, "mer"),
            "product": _rows(ps_mer["product"], ps_mer["roas"]),
        },
        "earned_share": {
            "market": _mkt_rows(ms, "earned_sales_share"),
            "product": _rows(prod_earned["product"], prod_earned["earned_share"]),
        },
        "unmeasured": {
            "market": _rows([market_label(mk) for mk in mkt_unmeas["market"]],
                             mkt_unmeas["spend_aed"], mkt_unmeas["market"]),
            "channel": _rows(chan_unmeas["channel"], chan_unmeas["unmeasured_spend_aed"]),
        },
    }
    # market_scorecard's shares are fractions (0-1), matching the KPI's own
    # earned_share -- the breakdown above carries the same 0-1 scale, scaled
    # to a percent only at render time (both here and in assets/app_pages.js).
    for r in breakdown["earned_share"]["market"]:
        if r["value"] is not None:
            r["value"] *= 100

    pve_sales = d["pve"].set_index("media_type")["sales_aed"]
    earned_contrib = _rows(["Paid", "Earned"],
                            [pve_sales.get("paid"), pve_sales.get("earned")])
    measured_split = _rows(["Measured", "Unmeasured"],
                            [total_spend - tv["spend_aed"], tv["spend_aed"]])

    ov_data = {
        "weeks": WK,
        "trend": {"sales": sales_trend, "spend": spend_trend, "mer": mer_trend,
                  "earned_share": earned_trend, "unmeasured_share": tv_share_trend},
        "breakdown": breakdown,
        "earned_contrib": earned_contrib,
        "measured_split": measured_split,
        "totals": {"sales": float(total_sales), "spend": float(total_spend)},
        "tv_share_of_spend": float(tv["share_of_spend"]),
    }

    def _ov_bar(rows: list[dict], v_fmt, filter_dim: str, chart_id: str) -> str:
        labels = [r["label"] for r in rows]
        values = [r["value"] if r["value"] is not None else 0 for r in rows]
        fvals = [r["fval"] for r in rows]
        return C.bar_chart_h(labels, values, colors=[C.SERIES_PASTEL[0]] * len(labels),
                              v_fmt=v_fmt, filter_dim=filter_dim, filter_vals=fvals,
                              chart_id=chart_id)

    def _ov_lollipop(rows: list[dict], v_fmt, filter_dim: str, chart_id: str) -> str:
        labels = [r["label"] for r in rows]
        values = [r["value"] if r["value"] is not None else 0 for r in rows]
        fvals = [r["fval"] for r in rows]
        return C.lollipop_chart(labels, values, colors=[C.SERIES_PASTEL[5]] * len(labels),
                                 v_fmt=v_fmt, filter_dim=filter_dim, filter_vals=fvals,
                                 chart_id=chart_id)

    def _ov_donut(rows: list[dict], v_fmt, filter_dim: str, chart_id: str,
                  center_label: str, center_sub: str) -> str:
        labels = [r["label"] for r in rows]
        values = [r["value"] if r["value"] is not None else 0 for r in rows]
        fvals = [r["fval"] for r in rows]
        colors = [C.SERIES_PASTEL[i % len(C.SERIES_PASTEL)] for i in range(len(labels))]
        return C.donut_chart(labels, values, colors=colors, v_fmt=v_fmt,
                              filter_dim=filter_dim, filter_vals=fvals, chart_id=chart_id,
                              center_label=center_label, center_sub=center_sub)

    def _ov_line(values: list[float], v_fmt, color: str, chart_id: str) -> str:
        return C.line_chart(WK, [C.Series("", values, color)], y_fmt=v_fmt,
                             hover_fmt=v_fmt, chart_id=chart_id)

    ov_kpis_html = '<div id="mount-kpis">' + kpis([
        kpi_select("sales", kpi(
            "Sales", aed(total_sales), delta=_wow(sales_trend), vs="vs first half",
            spark=sales_trend, spark_color=KPI_ACCENTS[0]), selected=True),
        kpi_select("spend", kpi(
            "Media spend", aed(total_spend), delta=_wow(spend_trend), good_up=False,
            vs="vs first half", spark=spend_trend, spark_color=KPI_ACCENTS[1])),
        kpi_select("mer", kpi(
            "MER", f"{total_sales/total_spend:,.1f}", unit="x", delta=_wow(mer_trend),
            vs="vs first half", spark=mer_trend, spark_color=KPI_ACCENTS[2])),
        kpi_select("earned", kpi(
            "Earned share of sales", f"{earned_share*100:.0f}", unit="%",
            delta=_wow(earned_trend), vs="vs first half", spark=earned_trend,
            spark_color=KPI_ACCENTS[3])),
        kpi_select("unmeasured", kpi(
            "Unmeasured spend", f"{tv['share_of_spend']*100:.0f}", unit="%",
            delta=_wow(tv_share_trend), good_up=False, vs="vs first half",
            spark=tv_share_trend, spark_color=KPI_ACCENTS[4])),
        kpi_link("alerts.html", kpi("Open alerts", str(len(alerts))), external=True),
    ]) + '</div>'

    body = [
        head("Executive overview", "Marketing Performance", "overview", kpis_html=ov_kpis_html),
    ]

    # --- the four charts the selected KPI explains -------------------------
    body.append('<div class="grid-2" id="ov-charts">')
    body.append(
        '<div id="ov-chart-1">'
        + card("Sales across the 8-week cycle", "Total measured sales, week by week",
               _ov_line(sales_trend, aed_short, KPI_ACCENTS[0], "ov-trend-sales"))
        + "</div>"
    )
    body.append(
        '<div id="ov-chart-2">'
        + card("Which channel earns the sales", "Sales attributed by channel",
               _ov_bar(breakdown["sales"]["channel"], aed_short, "channel", "ov-sales-channel"),
               table_view(eff_sales[["channel", "sales_aed"]], {"sales_aed": aed_short}))
        + "</div>"
    )
    body.append(
        '<div id="ov-chart-3">'
        + card("How sales split across products", "Share of total sales, 6 devices",
               _ov_donut(breakdown["sales"]["product"], aed_short, "product", "ov-sales-product",
                         aed_short(total_sales), "Total sales"))
        + "</div>"
    )
    body.append(
        '<div id="ov-chart-4">'
        + card("Which market earns the sales", "Sales attributed by market",
               _ov_lollipop(breakdown["sales"]["market"], aed_short, "market", "ov-sales-market"))
        + "</div>"
    )
    body.append("</div>")  # #ov-charts

    body.append(
        "<script>window.__OVERVIEW_DATA__ = "
        + json.dumps(ov_data, separators=(",", ":"))
        + ";</script>"
    )
    return "".join(body)


def page_insights(d: dict) -> str:
    spine = d["spine"]
    total_sales, total_spend = spine["sales_aed"].sum(), spine["spend_aed"].sum()
    blended_mer = (total_sales / total_spend) if total_spend else float("nan")

    insights_kpis_html = '<div id="mount-insights-kpis">' + kpis([
        kpi("Sales", aed(total_sales)),
        kpi("Media spend", aed(total_spend)),
        kpi("Blended MER", f"{blended_mer:,.1f}", unit="x"),
    ]) + '</div>'

    body = [head("Insights & actions", "Insights & Actions", "insights",
                 kpis_html=insights_kpis_html)]

    # No formula-based write-up baked in any more -- the narrative and
    # recommended actions are generated live by the AI assistant, scoped to
    # the current filter, on demand. Offline (no server / no API key) the
    # button just disables itself with a note; there is no static fallback
    # text to fall back to.
    body.append(
        '<div id="mount-ai-insights" class="card" style="margin-top:22px">'
        '<div class="sens-row">'
        '<button type="button" id="ai-insights-btn" class="btn-dl">'
        "✨ Generate AI insights</button>"
        "</div>"
        '<div class="fbar-note" id="ai-insights-note"></div>'
        '<div id="mount-ai-body" style="display:none">'
        '<h3 class="ai-section-h">Insights</h3>'
        '<div id="mount-ai-perf"></div>'
        '<h3 class="ai-section-h">Recommended actions</h3>'
        '<div id="mount-ai-actions"></div>'
        "</div>"
        "</div>"
    )

    return "".join(body)


# ==========================================================================
# Page 2 — Channels
# ==========================================================================

def _channel_drilldown(base: pd.DataFrame, eff: pd.DataFrame,
                        channels: list[str]) -> dict:
    """Per-channel product/market breakdown for the Channels page's
    click-a-slice drill-down, keyed by channel and embedded as JSON --
    assets/app_pages.js groups fact_base the same way (channel -> product /
    market, sum spend/sales/conversions, drop rows with neither) so the
    server-rendered default and a live-filtered redraw never disagree."""
    out = {}
    for ch in channels:
        sub = base[base["channel"] == ch]
        row = eff[eff["channel"] == ch]
        r = row.iloc[0] if len(row) else None

        def _agg(dim: str) -> list[dict]:
            g = (sub.groupby(dim, as_index=False)
                 .agg(spend_aed=("spend_aed", "sum"), sales_aed=("sales_aed", "sum"),
                      conversions=("conversions", "sum")))
            g = g[(g["spend_aed"] > 0) | (g["sales_aed"] > 0)]
            return g.sort_values("sales_aed", ascending=False).to_dict(orient="records")

        out[ch] = {
            "kpis": {
                "spend_aed": float(r["spend_aed"]) if r is not None else float(sub["spend_aed"].sum()),
                "sales_aed": float(r["sales_aed"]) if r is not None else float(sub["sales_aed"].sum()),
                "conversions": float(r["conversions"]) if r is not None else float(sub["conversions"].sum()),
                "roas": None if r is None or pd.isna(r["roas"]) else float(r["roas"]),
            },
            "by_product": _agg("product"),
            "by_market": _agg("market"),
        }
    return out


def _channel_detail_kpis(k: dict) -> str:
    return kpis([
        kpi("Spend", aed(k["spend_aed"])),
        kpi("Sales", aed(k["sales_aed"])),
        kpi("Conversions", f"{k['conversions']:,.0f}"),
        kpi("ROAS", x_fmt(k["roas"])),
    ])


def _channel_detail_card(title: str, rows: list[dict], dim: str) -> str:
    labels = [market_label(r[dim]) if dim == "market" else r[dim] for r in rows]
    return card(
        title, "",
        C.legend([("Spend", C.SERIES_PASTEL[0]), ("Sales", C.SERIES_PASTEL[1])], symbol="dot")
        + C.grouped_bar_h(
            labels,
            [("Spend", [r["spend_aed"] for r in rows], C.SERIES_PASTEL[0]),
             ("Sales", [r["sales_aed"] for r in rows], C.SERIES_PASTEL[1])],
            v_fmt=aed_short, label_series=1, chart_id=f"ch-detail-{dim}",
        ),
    )


def page_channels(d: dict) -> str:
    eff, base = d["eff"], d["base"]

    # --- channel summary: KPIs common to every channel, not TV alone -----
    total_spend, total_sales = eff["spend_aed"].sum(), eff["sales_aed"].sum()
    total_conv = eff["conversions"].sum()
    blended_mer = (total_sales / total_spend) if total_spend else float("nan")
    channel_kpis_html = '<div id="mount-channel-kpis">' + kpis([
        kpi("Total spend", aed(total_spend)),
        kpi("Total sales", aed(total_sales)),
        kpi("Total conversions", f"{total_conv:,.0f}"),
        kpi("Blended MER", f"{blended_mer:,.1f}", unit="x"),
    ]) + '</div>'

    body = [
        head("Channels", "Channels", "channels", kpis_html=channel_kpis_html),
    ]

    # --- return by channel: pie (left) + channel legend/selector (right), --
    # full page width now that the reallocation chart that used to share
    # this row is gone.
    body.append("<h2>Return by channel</h2>")
    meas = eff[eff["revenue_attributed"] & eff["roas"].notna()]
    econ = eff.sort_values("spend_aed", ascending=False).copy()
    econ["ctr_pct"] = np.where(econ["impressions"] > 0,
                                econ["clicks"] / econ["impressions"] * 100, np.nan)

    pie_src = meas.sort_values("sales_aed", ascending=False).reset_index(drop=True)
    default_channel = pie_src.iloc[0]["channel"] if len(pie_src) else None

    body.append('<div id="mount-eff-table">' + card(
        "Measured return by channel",
        "Each slice is a channel's share of measured sales — TV, PR and "
        "Website aren't sliced here, a measurement gap rather than a zero.",
        C.pie_chart(pie_src["channel"].tolist(), pie_src["sales_aed"].tolist(),
                    v_fmt=aed_short, chart_id="ch-roas", select_dim="channel",
                    selected=default_channel,
                    subs=[f"ROAS {v:,.2f}x" for v in pie_src["roas"]]),
        table_view(
            econ[["channel", "media_type", "spend_aed", "share_of_spend",
                  "impressions", "clicks", "ctr_pct", "conversions", "sales_aed",
                  "roas", "roi_gross_margin", "revenue_attributed"]],
            {"spend_aed": aed_short, "share_of_spend": lambda v: f"{v:.0%}",
             "impressions": int_fmt, "clicks": int_fmt, "ctr_pct": ctr_fmt,
             "conversions": int_fmt, "sales_aed": aed_short, "roas": x_fmt,
             "roi_gross_margin": x_fmt, "revenue_attributed": attribution_pill},
            label="View channel economics",
        ),
    ) + "</div>")

    # --- channel detail: click a slice (or a legend entry) to drill in ----
    channel_list = pie_src["channel"].tolist()
    drilldown = _channel_drilldown(base, eff, channel_list)
    if default_channel:
        dd = drilldown[default_channel]
        body.append('<div id="mount-channel-detail-kpis">'
                     + _channel_detail_kpis(dd["kpis"]) + "</div>")
        body.append('<div class="grid-2">')
        body.append('<div id="mount-channel-detail-product">'
                     + _channel_detail_card("By product", dd["by_product"], "product")
                     + "</div>")
        body.append('<div id="mount-channel-detail-market">'
                     + _channel_detail_card("By market", dd["by_market"], "market")
                     + "</div>")
        body.append("</div>")
    else:
        body.append('<div id="mount-channel-detail-kpis"></div><div class="grid-2">'
                     '<div id="mount-channel-detail-product"></div>'
                     '<div id="mount-channel-detail-market"></div></div>')
    body.append(
        "<script>window.__CHANNEL_DRILLDOWN__ = "
        + json.dumps(drilldown, separators=(",", ":"))
        + f"; window.__CHANNEL_DEFAULT__ = {json.dumps(default_channel)};</script>"
    )

    return "".join(body)


# ==========================================================================
# Page 3 — Markets & Products
# ==========================================================================
def page_portfolio(d: dict) -> str:
    ms, ps, spine, base = d["ms"], d["ps"], d["spine"], d["base"]

    # --- KPIs --------------------------------------------------------------
    total_conv = spine["conversions"].sum()
    total_spend = spine["spend_aed"].sum()
    cpa = (total_spend / total_conv) if total_conv else float("nan")
    portfolio_kpis_html = '<div id="mount-portfolio-kpis">' + kpis([
        kpi("Conversions", f"{total_conv:,.0f}"),
        kpi("CPA", aed(cpa, 0)),
        kpi("Products", str(len(ps))),
        kpi("Markets", str(len(ms))),
    ]) + '</div>'

    body = [
        head("Portfolio", "Market & Products", "portfolio", kpis_html=portfolio_kpis_html),
    ]

    # --- weekly sales across markets + product-by-market split, side by --
    # side -- pastel, one colour per market, shared between both charts.
    wm_piv = (spine.pivot(index="week", columns="market", values="sales_aed")
              .reindex(range(1, 9)).fillna(0))
    wm_piv = wm_piv[wm_piv.sum().sort_values(ascending=False).index]
    market_order = wm_piv.columns.tolist()
    market_colors = {mk: C.SERIES_PASTEL[i % len(C.SERIES_PASTEL)]
                      for i, mk in enumerate(market_order)}

    sales_by_market = [
        C.Series(market_label(mk), wm_piv[mk].tolist(), market_colors[mk], filter_val=mk)
        for mk in market_order
    ]

    products_order = ps.sort_values("sales_aed", ascending=False)["product"].tolist()
    pm_piv = (base.groupby(["product", "market"], as_index=False)["sales_aed"].sum()
              .pivot(index="product", columns="market", values="sales_aed")
              .reindex(products_order).fillna(0))
    product_by_market = [
        (market_label(mk), pm_piv[mk].tolist() if mk in pm_piv.columns
         else [0.0] * len(products_order), market_colors[mk])
        for mk in market_order
    ]
    market_legend = C.legend([(market_label(mk), market_colors[mk], mk) for mk in market_order],
                              filter_dim="market")

    body.append("<h2>Weekly sales across markets</h2>")
    body.append('<div class="grid-2">')
    body.append(
        '<div id="mount-sales-week-market">' + card(
            "Sales by week across markets",
            "Click a line, a point, or the legend to filter",
            market_legend
            + C.line_chart(WK, sales_by_market, y_fmt=aed_short, hover_fmt=aed,
                           filter_dim="market", chart_id="pf-sales-week"),
            table_view(wm_piv.reset_index(), {c: aed_short for c in wm_piv.columns}),
        ) + "</div>"
    )
    body.append(
        '<div id="mount-sales-product-market">' + card(
            "Sales by product, stacked by market",
            "Each segment is a market's contribution to that product's sales — "
            "click the legend to filter",
            market_legend
            + C.stacked_columns(products_order, product_by_market, v_fmt=aed_short,
                                chart_id="pf-sales-product"),
            table_view(pm_piv.reset_index(), {c: aed_short for c in pm_piv.columns}),
        ) + "</div>"
    )
    body.append("</div>")  # .grid-2

    # --- products -------------------------------------------------------
    body.append("<h2>Product portfolio</h2>")
    ps_sorted = ps.sort_values("sales_aed", ascending=False).reset_index(drop=True)
    body.append('<div id="mount-product-table" class="card">' + table(
        ps_sorted[["product", "spend_aed", "sales_aed", "conversions", "roas",
                   "aov_aed", "share_of_spend", "share_of_sales", "support_index"]],
        {"spend_aed": aed_short, "sales_aed": aed_short,
         "conversions": lambda v: f"{v:,.0f}", "roas": x_fmt,
         "aov_aed": lambda v: f"{v:,.0f}", "share_of_spend": C.pct,
         "share_of_sales": C.pct, "support_index": lambda v: f"{v:,.2f}"},
        sortable=True) + "</div>")
    body.append(note(
        "Support index = share of spend ÷ share of sales; 1.00 is proportionate. "
        "<b>Every device sits between 0.95 and 1.04</b> — no misallocation to "
        "correct."))
    return "".join(body)


# ==========================================================================
# Page 4 — Influencers
# ==========================================================================
INF_GRADE_COLORS = {"good": "#8FD9AE", "mid": "#F2D97A", "bad": "#F2A6A6"}


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = p * (len(sorted_vals) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def _grade_colors(values: list[float]) -> list[str]:
    """Pastel traffic-light per bar: green at/above the 80th percentile of
    THIS metric's own values, red below the 20th, yellow between -- a band,
    not a fixed threshold, so it re-grades sensibly whichever metric (ROAS,
    CPA, spend...) is currently on the axis."""
    ranked = sorted(values)
    p20, p80 = _percentile(ranked, 0.2), _percentile(ranked, 0.8)
    return [
        INF_GRADE_COLORS["good"] if v >= p80
        else INF_GRADE_COLORS["bad"] if v < p20
        else INF_GRADE_COLORS["mid"]
        for v in values
    ]


def _inf_number(name: str) -> str:
    return str(name).rsplit("_", 1)[-1]


def page_influencers(d: dict) -> str:
    sc = d["sc"]
    med_cpa = sc["cpa_aed"].median()
    med_roas = sc["roas"].median()
    best_margin = (sc["roas"] * GROSS_MARGIN).max()

    inf_kpis_html = '<div id="mount-inf-kpis">' + kpis([
        kpi("Influencers", str(len(sc))),
        kpi("Total fees", aed(sc["spend_aed"].sum())),
        kpi("Median CPA", aed(med_cpa, 0)),
        kpi("Median ROAS", f"{med_roas:,.2f}x"),
        kpi("Best on margin", f"{best_margin:,.2f}x"),
    ]) + '</div>'

    body = [
        head("Influencer performance", "Influencer Performance", "influencers", kpis_html=inf_kpis_html),
    ]

    # --- influencer comparison: one metric at a time, switchable ---------
    # X axis is every influencer (just its number); Y axis is whichever
    # metric the tab picks. Bars sort highest-to-lowest and are graded
    # green/yellow/red by percentile within that metric, so the chart reads
    # as a ranking at a glance. window.__INF_SCORECARD__ below carries every
    # field the hover needs, for all five metrics, so a tab click redraws
    # client-side without a server round-trip; app_pages.js's influencers()
    # redraws it again from live-filtered data when a filter changes.
    INF_METRICS = [
        ("roas", "ROAS", lambda v: f"{v:,.2f}x"),
        ("cpa_aed", "CPA (AED)", lambda v: aed(v, 0)),
        ("spend_aed", "Spend (AED)", aed_short),
        ("engagement_rate", "Engagement rate (%)", lambda v: f"{v:,.1f}%"),
        ("followers", "Followers", lambda v: f"{v:,.0f}"),
    ]
    default_metric = "roas"
    sc_bar = sc.sort_values(default_metric, ascending=False).reset_index(drop=True)
    bar_values = sc_bar[default_metric].tolist()
    tooltip_titles = [f"Influencer {_inf_number(name)} · {mkt}"
                       for name, mkt in zip(sc_bar["influencer"], sc_bar["market"])]
    tooltip_bodies = [
        '<ul class="tip-list">'
        f"<li>Followers: {f:,.0f}</li>"
        f"<li>Engagement: {e:,.1f}%</li>"
        f"<li>Spend: {aed(s)}</li>"
        f"<li>CPA: {aed(c, 0)}</li>"
        f"<li>ROAS: {r:,.2f}x</li>"
        "</ul>"
        for f, e, s, c, r in zip(sc_bar["followers"], sc_bar["engagement_rate"],
                                  sc_bar["spend_aed"], sc_bar["cpa_aed"], sc_bar["roas"])
    ]
    bar_svg = C.bar_chart_graded(
        [_inf_number(n) for n in sc_bar["influencer"]], bar_values,
        _grade_colors(bar_values), tooltip_titles, tooltip_bodies,
        v_fmt=lambda v: f"{v:,.1f}", chart_id="inf-bar")
    metric_tabs = "".join(
        f'<button type="button" class="tab{" active" if key == default_metric else ""}" '
        f'data-metric="{key}">{label}</button>'
        for key, label, _ in INF_METRICS)
    body.append("<h2>Influencer comparison</h2>")
    body.append(card(
        "Compare influencers by metric",
        "Bars sorted highest to lowest and graded green/yellow/red by "
        "percentile. Hover a bar for the full picture.",
        f'<div class="tabs" id="inf-metric-tabs" role="tablist">{metric_tabs}</div>'
        f'<div id="inf-bar-chart">{bar_svg}</div>'
    ))
    body.append(
        "<script>window.__INF_SCORECARD__ = "
        + json.dumps(
            sc[["influencer", "market", "roas", "cpa_aed", "spend_aed",
                "engagement_rate", "followers"]].to_dict(orient="records"),
            separators=(",", ":"))
        + ";</script>"
    )

    body.append("<h2>Recommended action</h2>")
    body.append('<div id="mount-inf-table" class="card">' + table(
        sc.sort_values("cpa_aed")[["influencer", "market", "followers",
                                   "engagement_rate", "er_vs_roster", "spend_aed",
                                   "cpa_aed", "roas", "flag", "recommended_action"]],
        {"followers": lambda v: f"{v:,.0f}",
         "engagement_rate": lambda v: f"{v:,.2f}%",
         "er_vs_roster": lambda v: f"{v:+.0%}", "spend_aed": aed_short,
         "cpa_aed": lambda v: f"{v:,.0f}", "roas": x_fmt,
         "flag": flag_pill}, sortable=True) + "</div>")
    body.append(note(
        "Click a column header to sort — again for descending."))
    return "".join(body)


# ==========================================================================
# Page 5 — Brand & competition
# ==========================================================================
def page_brand(d: dict) -> str:
    spine, ms = d["spine"], d["ms"]

    # --- KPIs: group-level mean across every market-week in scope, same ---
    # "average, not a measurement" basis the per-market charts below already
    # use (ms itself is markets averaged across weeks) -- one definition,
    # just rolled up one level further for a single headline number.
    brand_kpis_html = '<div id="mount-brand-kpis">' + kpis([
        kpi("Brand awareness score", f"{spine['brand_awareness'].mean():,.1f}"),
        kpi("Purchase intent score", f"{spine['purchase_intent'].mean():,.1f}"),
        kpi("Sentiment score", f"{spine['sentiment'].mean():,.2f}"),
        kpi("PR share of voice", f"{spine['share_of_voice'].mean():,.1f}"),
        kpi("Competitor SOV", f"{spine['competitor_sov'].mean():,.1f}"),
    ]) + '</div>'

    body = [
        head("Brand & competition", "Brand & Competition", "brand", kpis_html=brand_kpis_html),
        note(
            "<b>Brand metrics are indicative, not exact measurements</b> — the "
            "source values vary by up to 39 points inside a single market-week. "
            "Compare markets, don't read week-to-week movement."),
    ]

    # --- four charts, 2x2 ---------------------------------------------------
    wk = spine.groupby("week", as_index=False).agg(
        brand_awareness=("brand_awareness", "mean"),
        purchase_intent=("purchase_intent", "mean"))

    ms_aware = ms.sort_values("brand_awareness", ascending=False).reset_index(drop=True)
    aware_labels = [market_label(m) for m in ms_aware["market"]]

    ms_sent = ms.sort_values("sentiment", ascending=False).reset_index(drop=True)
    sent_labels = [market_label(m) for m in ms_sent["market"]]

    ms_sov = ms.sort_values("share_of_voice", ascending=False).reset_index(drop=True)
    sov_labels = [market_label(m) for m in ms_sov["market"]]

    body.append('<div id="mount-brand-charts">')
    body.append(
        '<div id="mount-brand-weekly">' + card(
            "Brand awareness & purchase intent over week",
            "Group average, indicative index",
            C.legend([("Awareness", C.SERIES_PASTEL[0]), ("Purchase intent", C.SERIES_PASTEL[1])])
            + C.line_chart(WK, [
                C.Series("Awareness", wk["brand_awareness"].tolist(), C.SERIES_PASTEL[0]),
                C.Series("Purchase intent", wk["purchase_intent"].tolist(), C.SERIES_PASTEL[1]),
            ], y_fmt=lambda v: f"{v:,.0f}", chart_id="br-wk"),
        ) + "</div>"
    )
    body.append(
        '<div id="mount-brand-sentiment">' + card(
            "Sentiment by market", "Averaged across the weeks in scope",
            C.lollipop_chart(sent_labels, ms_sent["sentiment"].tolist(),
                             colors=[C.SERIES_PASTEL[2]] * len(sent_labels),
                             v_fmt=lambda v: f"{v:,.2f}", filter_dim="market",
                             filter_vals=ms_sent["market"].tolist(), chart_id="br-sent-mkt"),
        ) + "</div>"
    )
    body.append(
        '<div id="mount-brand-sov">' + card(
            "Samsung PR SOV vs competitor SOV", "Percentage points, by market",
            C.legend([("Samsung", C.SERIES_PASTEL[0]), ("Competitor", C.SERIES_PASTEL[3])])
            + C.grouped_bar_h(sov_labels, [
                ("Samsung", ms_sov["share_of_voice"].tolist(), C.SERIES_PASTEL[0]),
                ("Competitor", ms_sov["competitor_sov"].tolist(), C.SERIES_PASTEL[3]),
            ], v_fmt=lambda v: f"{v:,.1f}", label_series=0, chart_id="br-sov-grp"),
            table_view(ms_sov[["market", "share_of_voice", "competitor_sov", "sov_gap"]],
                       {"share_of_voice": lambda v: f"{v:,.1f}",
                        "competitor_sov": lambda v: f"{v:,.1f}",
                        "sov_gap": lambda v: f"{v:+,.1f}"}),
        ) + "</div>"
    )
    body.append(
        '<div id="mount-brand-awareness-market">' + card(
            "Brand awareness by market", "Averaged across the weeks in scope",
            C.bar_chart_h(aware_labels, ms_aware["brand_awareness"].tolist(),
                          colors=[C.SERIES_PASTEL[0]] * len(aware_labels),
                          filter_dim="market", filter_vals=ms_aware["market"].tolist(),
                          v_fmt=lambda v: f"{v:,.1f}", chart_id="br-aware-mkt"),
        ) + "</div>"
    )
    body.append("</div>")  # #mount-brand-charts

    behind = ms[ms["sov_gap"] < 0]
    if len(behind):
        body.append(note(
            f"<b>{len(behind)} of {len(ms)} markets sit behind the leading "
            "competitor on share of voice</b> — act before it reaches sales. A "
            "PR-driven gap is cheaper to close with earned activity than paid reach."))
    else:
        body.append(note(
            "<b>Samsung leads on share of voice in every market.</b> PR carries no "
            "media cost, so protecting this lead is one of the cheapest wins here."))
    return "".join(body)


# ==========================================================================
# Page 6 — Alerts
# ==========================================================================
def _sensitivity_card() -> str:
    """The manager-adjustable practical-significance floor. Static render shows
    the config file's default (8%); the slider only works live (src/serve.py's
    /api/alerts) -- same honest offline-degradation pattern as the filter bar,
    wired up in assets/app_pages.js."""
    default_gap = load_alert_rules().get("settings", {}).get("min_relative_gap", 0.08)
    pct = round(default_gap * 100)
    return (
        '<div id="mount-ew-sensitivity" class="card">'
        '<div class="card-head"><h3>Detection sensitivity</h3>'
        '<div class="card-sub">How different a market must be from its peers '
        "before a comparison rule fires. Sentiment keeps its own fixed floor, "
        "regardless of this control.</div></div>"
        '<div class="sens-row">'
        f'<input type="range" id="sens-slider" min="1" max="25" step="1" value="{pct}">'
        f'<span class="sens-value" id="sens-value">{pct}%</span>'
        '<button type="button" id="sens-apply" class="btn-dl">Apply</button>'
        "</div>"
        '<div class="fbar-note" id="sens-note"></div>'
        "</div>"
    )


def page_alerts(d: dict) -> str:
    alerts, current = d["alerts"], d["alerts_current"]
    counts = current["severity"].value_counts().to_dict()
    # Page-local severity palette (red/orange/yellow), not the shared
    # C.STATUS tokens -- scoped to this page only, per request. Kept vivid
    # for the alert list itself (small text/border needs the contrast); the
    # standalone "Alerts fired per week" chart below uses the pastel twin
    # instead, matching the SERIES_PASTEL register every other chart uses.
    sev_color = {"critical": "#DC2626", "high": "#EA580C", "medium": "#EAB308"}
    sev_color_pastel = {"critical": "#F2A6A6", "high": "#F2AD5C", "medium": "#F2D98A"}
    glyph = {"critical": "●", "high": "▲", "medium": "■"}

    n_rules = len(load_alert_rules()["rules"])
    n_categories = len({r["category"] for r in load_alert_rules()["rules"]})
    ew_kpis_html = '<div id="mount-ew-kpis">' + kpis([
        kpi("Open now", str(len(current))),
        kpi("Critical", str(counts.get("critical", 0))),
        kpi("High", str(counts.get("high", 0))),
        kpi("Medium", str(counts.get("medium", 0))),
        kpi("Fired across 8 weeks", str(len(alerts))),
    ]) + '</div>'

    body = [
        head("Risk & alerts", "Early Warning System", "alerts", kpis_html=ew_kpis_html),
        note(
            "<b>This system compares markets, not weeks</b> — the primary "
            "detector asks <i>is this market unlike its peers this week?</i> "
            "The controls above narrow which alerts are shown, not which rules fired."),
        _sensitivity_card(),
        "<h2>Open alerts</h2>",
        '<div id="mount-ew-open">',
    ]

    if current.empty:
        body.append('<div class="card">No alerts open.</div>')
    else:
        for (rid, rule, sev, cat, owner, action), grp in current.groupby(
            ["rule_id", "rule", "severity", "category", "owner", "action"], sort=False
        ):
            c = sev_color.get(sev, C.MUTED)
            lines = []
            for _, r in grp.iterrows():
                wk = "" if pd.isna(r["week"]) else f" · week {int(r['week'])}"
                lines.append(f'<div style="margin-top:4px"><b>{C.esc(r["entity"])}</b>'
                             f'{wk} — {C.esc(r["detail"])}</div>')
            scope = f'<span class="alert-scope">{len(grp)} affected</span>' if len(grp) > 1 else ""
            body.append(
                f'<details class="alert" style="border-left-color:{c}">'
                f'<summary class="alert-summary">'
                f'<span class="alert-sev" style="color:{c}">{glyph.get(sev,"•")} {C.esc(sev)}</span>'
                f'<span class="alert-title">{C.esc(rule)}</span>{scope}</summary>'
                f'<div class="alert-body">'
                f'<div class="alert-meta">{C.esc(cat)} · {C.esc(rid)}</div>'
                f'<div class="alert-detail">{"".join(lines)}</div>'
                f'<div class="alert-foot"><b>Owner:</b> {C.esc(owner)}<br>'
                f'<b>Action:</b> {C.esc(action)}</div></div></details>')
    body.append('</div>')

    # --- back-test -------------------------------------------------------
    dated = alerts[alerts["week"].notna()]
    body.append('<div id="mount-ew-history">')
    if not dated.empty:
        piv = (dated.groupby(["week", "severity"]).size().unstack(fill_value=0)
               .reindex(range(1, 9), fill_value=0))
        for s in ["critical", "high", "medium"]:
            if s not in piv.columns:
                piv[s] = 0
        body.append("<h2>What the rules would have caught</h2>")
        body.append(card(
            "Alerts fired per week", "Back-tested across all 8 weeks",
            C.legend([("Critical", sev_color_pastel["critical"]), ("High", sev_color_pastel["high"]),
                      ("Medium", sev_color_pastel["medium"])], symbol="dot")
            + C.stacked_columns(
                WK,
                [("Critical", piv["critical"].tolist(), sev_color_pastel["critical"]),
                 ("High", piv["high"].tolist(), sev_color_pastel["high"]),
                 ("Medium", piv["medium"].tolist(), sev_color_pastel["medium"])],
                chart_id="al-hist"),
            table_view(dated.groupby(["week", "severity"]).size()
                       .reset_index(name="alerts"),
                       {"severity": severity_pill})))
    body.append('</div>')

    # --- catalogue -------------------------------------------------------
    cat = (alerts.groupby(["rule_id", "rule", "category", "severity", "owner"],
                          as_index=False).size()
           .rename(columns={"size": "times_fired"})
           .sort_values(["severity", "times_fired"], ascending=[True, False]))
    body.append("<h2>Rule catalogue</h2>")
    body.append('<div id="mount-ew-catalogue" class="card">'
                + table(cat, {"times_fired": lambda v: f"{v:,.0f}",
                              "severity": severity_pill}) + "</div>")
    body.append(note(
        "<b>A statistical outlier isn't automatically a problem.</b> Rules also "
        "require a minimum practical gap before firing — that floor alone cut "
        "eight noise alerts a cycle."))

    body.append("<h2>How this works</h2>")
    body.append(note(
        "<b>Data sources:</b> the same weekly subsidiary extract every other page "
        "reads."))
    body.append(note(
        f"<b>Alert logic:</b> {n_rules} rules in <code>config/rules.yaml</code>. "
        "Most compare a market to its 7 peers via robust z-scores plus a minimum "
        "gap; one watches the group total instead."))
    body.append(note(
        "<b>Recommended actions:</b> every alert carries an owner and a next step "
        "— route critical/high the same day, fold medium into a weekly digest."))
    return "".join(body)


# ==========================================================================
# Page 7 — Data
# ==========================================================================
def _order_columns(df: pd.DataFrame, reference_cols: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Columns already present in `reference_cols` come first, in that
    table's order; everything new to this table follows. Returns the
    reordered frame plus the list of "new" column names, so the caller can
    mark those headers as derived."""
    shared = [c for c in reference_cols if c in df.columns]
    extra = [c for c in df.columns if c not in shared]
    return df[shared + extra], extra


def _json_table(df: pd.DataFrame, note: str, label: str, derived: list[str] | None = None) -> dict:
    """Serialise a frame for the browser explorer.

    Column-oriented would be smaller, but row-oriented keeps the JS trivial and
    these tables are small. NaN becomes null so the explorer can render an em
    dash rather than the string "NaN". `label` is the business-friendly tab
    name ("Master Table") -- the JS tab bar and download filename both read
    it, so the internal fact_ name never reaches the screen. `derived` names
    the columns that aren't carried over unchanged from their source (see
    `_order_columns`) -- the JS tab bar tints those headers.
    """
    clean = df.where(pd.notna(df), None)
    rows = []
    for rec in clean.itertuples(index=False, name=None):
        rows.append([
            None if (isinstance(v, float) and np.isnan(v)) else
            (round(v, 2) if isinstance(v, float) else
             (int(v) if isinstance(v, (np.integer,)) else
              (bool(v) if isinstance(v, (np.bool_, bool)) else v)))
            for v in rec
        ])
    return {"cols": list(df.columns), "rows": rows, "note": note, "label": label,
            "derived": derived or []}


def page_data(d: dict) -> str:
    raw = d["raw_shape"]
    dq = d["dq"]
    base = d["base"]

    data_kpis_html = kpis([
        kpi("Source rows", f"{raw['rows']:,}"),
        kpi("Modelled tables", str(len(EXPLORER_TABLES))),
        kpi("Cleaning checks", str(len(dq))),
        kpi("Duplicate keys", "0"),
        kpi("Values imputed", "0"),
    ])

    body = [
        head("Part 1", "Data Processing", kpis_html=data_kpis_html),
        note("<b>Nulls are structural, not missing</b> — each row is one channel "
             "with only its own measures populated. Nothing was imputed."),
    ]

    # --- the data: tabs + download, first and up top ---------------------
    # Only the 6 fact tables -- the cleaned data itself. Business names
    # (Master Table, Channels, ...), not the internal fact_ prefix. Columns
    # are reordered so anything carried straight from the source (Master
    # Table for fact_base itself, or Master Table's own columns for the
    # other five) comes first, in that order -- new/computed columns follow
    # and get their header tinted in the explorer.
    raw_cols = list(dict.fromkeys(ingest.RENAME.values()))
    base_cols: list[str] = []
    tables = {}
    for name, label, desc in FACT_TABLES:
        try:
            df = load(name)
        except FileNotFoundError:
            continue
        ordered, derived = _order_columns(df, raw_cols if name == "fact_base" else base_cols)
        if name == "fact_base":
            base_cols = list(ordered.columns)
        tables[name] = _json_table(ordered, desc, label, derived)

    body.append("<h2>The data</h2>")
    body.append(
        '<div class="tbl-toolbar">'
        '<div class="tabs" id="tbl-tabs" role="tablist"></div>'
        '<a class="btn-dl" href="data/samsung_mena_all_tables.xlsx" download>'
        f"↓ Download all ({len(FACT_TABLES)} tables, .xlsx)</a>"
        "</div>"
    )
    body.append(
        '<div class="card">'
        '<div class="tbl-bar">'
        '<input id="tbl-search" type="search" placeholder="Filter rows…" '
        'autocomplete="off">'
        # Downloads whichever tab is open, so the file you take is the one
        # you were just looking at.
        '<a id="tbl-download" class="btn-dl" download>↓ Download CSV</a>'
        "</div>"
        '<div id="tbl-meta"></div><div id="explorer"><div id="tbl-host"></div></div>'
        '<button id="tbl-more">Show more</button>'
        "</div>"
    )
    body.append(note(
        "Click a tab to switch tables, a column header to sort, or type to "
        "filter. <span class=\"tbl-h-swatch derived\"></span> marks a "
        "computed or aggregated column, not carried over as-is. "
        "<b>Download</b> takes the full table; <b>Download all</b> gets "
        "every table as its own sheet in one workbook."))

    body.append(
        f"<script>window.__TABLES__ = {json.dumps(tables, separators=(',', ':'))};</script>"
    )

    # --- modelling structure ----------------------------------------------
    def _n(id_: str, label: str | None = None, kind: str = "fact") -> dict:
        return {"id": id_, "label": label or id_, "kind": kind}

    fact_label = {name: label for name, label, _ in FACT_TABLES}
    lineage_tiers = [
        [_n("source", "raw CSV", "source")],
        [_n("fact_base", fact_label["fact_base"])],
        [_n("fact_channel", fact_label["fact_channel"]),
         _n("fact_product", fact_label["fact_product"]),
         _n("fact_influencer", fact_label["fact_influencer"]),
         _n("fact_brand", fact_label["fact_brand"])],
        [_n("fact_market_week", fact_label["fact_market_week"])],
    ]
    lineage_edges = [
        ("source", "fact_base"),
        ("fact_base", "fact_channel"), ("fact_base", "fact_product"),
        ("fact_base", "fact_influencer"), ("fact_base", "fact_brand"),
        ("fact_base", "fact_market_week"), ("fact_channel", "fact_market_week"),
        ("fact_brand", "fact_market_week"),
    ]
    body.append("<h2>Modelling structure</h2>")
    body.append(
        '<div class="card">'
        '<div class="card-head"><h3>How the fact tables are derived</h3>'
        '<div class="card-sub">Source → facts → spine.</div></div>'
        + C.legend([("Source file", C.LINEAGE_KIND_COLOR["source"]),
                    ("Fact", C.LINEAGE_KIND_COLOR["fact"])], symbol="dot")
        + C.lineage_graph(lineage_tiers, lineage_edges, chart_id="data-lineage")
        + "</div>"
    )

    # --- the cleaning log, compact and last -------------------------------
    # Rows with the same check that only differ by which measure/metric they
    # cover (structural sparsity, brand grain, taxonomy) are folded into one
    # line each -- otherwise near-identical findings pad the log to 18 rows.
    # Collapsed by default (details.table-view, same pattern as every chart's
    # "view as table" toggle) and rendered as a compact table rather than a
    # stack of cards -- ten checks fit in the space four used to take.
    def _spread(finding: str) -> float:
        m = re.search(r"spread inside a market-week is ([\d.]+) points", finding)
        return float(m.group(1)) if m else 0.0

    def _channel_count(finding: str) -> int:
        return str(finding).count("'") // 2

    def _cls(check: str) -> str:
        if check in ("Attribution", "Brand metric grain"):
            return "crit"
        if check in ("Redundancy", "Zero values"):
            return "flag"
        return ""

    rows_by_check: dict[str, list] = {}
    for _, r in dq.iterrows():
        rows_by_check.setdefault(r["check"], []).append(r)

    entries = []  # (check, finding, action)
    for check, rows in rows_by_check.items():
        if check == "Taxonomy" and len(rows) > 1:
            entries.append((check, "market, channel and product values all recognised",
                             rows[0]["action"]))
        elif check == "Structural sparsity" and len(rows) > 1:
            parts = [f"{str(r['finding']).split(' present on')[0]} on "
                     f"{_channel_count(r['finding'])}/8" for r in rows]
            entries.append((check, ", ".join(parts) + " channels", "left as null"))
        elif check == "Brand metric grain" and len(rows) > 1:
            metrics = [str(r["finding"]).split(" is constant")[0] for r in rows]
            max_spread = max(_spread(str(r["finding"])) for r in rows)
            entries.append((check, f"{', '.join(metrics)} vary up to "
                             f"{max_spread:.1f} pts within a market-week", rows[0]["action"]))
        else:
            entries.extend((check, r["finding"], r["action"]) for r in rows)

    n_crit = sum(1 for c, *_ in entries if _cls(c) == "crit")
    n_flag = sum(1 for c, *_ in entries if _cls(c) == "flag")
    tail = ", ".join(p for p in (f"{n_crit} critical" if n_crit else "",
                                  f"{n_flag} flagged" if n_flag else "") if p)
    summary = f"{len(entries)} checks" + (f" — {tail}" if tail else "")
    rows_html = "".join(
        f'<tr class="{_cls(c)}"><td>{C.esc(c)}</td>'
        f'<td>{C.esc(f)} <span class="dq-act">→ {C.esc(a)}</span></td></tr>'
        for c, f, a in entries)
    body.append("<h2>Cleaning log</h2>")
    body.append(
        f'<details class="table-view"><summary>{summary}</summary>'
        f'<div class="card"><table class="dq-tbl"><tbody>{rows_html}'
        "</tbody></table></div></details>")

    return "".join(body)


# ==========================================================================
# Page 8 — Assistant
# ==========================================================================
def canned_answers(d: dict) -> dict[str, str]:
    eff, ms, sc, pve, pm = d["eff"], d["ms"], d["sc"], d["pve"], d["pm"]
    re_, ps = d["realloc"], d["ps"]
    tv = eff[eff["channel"] == "TV"].iloc[0]
    measurable = eff[eff["revenue_attributed"] & eff["roas"].notna()]
    best = measurable.sort_values("roas", ascending=False).iloc[0]
    med_cpa = sc["cpa_aed"].median()

    eff_tbl = table(
        eff[["channel", "spend_aed", "sales_aed", "roas", "roi_gross_margin", "payback"]],
        {"spend_aed": aed_short, "sales_aed": aed_short, "roas": x_fmt,
         "roi_gross_margin": x_fmt})
    inf_tbl = table(
        sc.sort_values("cpa_aed", ascending=False).head(6)[
            ["influencer", "followers", "spend_aed", "conversions", "cpa_aed", "roas"]],
        {"followers": lambda v: f"{v:,.0f}", "spend_aed": aed_short,
         "conversions": lambda v: f"{v:,.0f}", "cpa_aed": lambda v: f"{v:,.0f}",
         "roas": x_fmt})
    pve_tbl = table(
        pve[["media_type", "spend_aed", "sales_aed", "share_of_sales", "roas"]],
        {"spend_aed": aed_short, "sales_aed": aed_short, "share_of_sales": C.pct,
         "roas": x_fmt})
    sig = pm[pm["significant_5pct"]]["channel"].tolist()

    return {
        "Which channel delivered the highest ROI?":
            f"<p><b>{best['channel']} is the strongest measurable channel</b> at "
            f"{best['roas']:,.1f}x on revenue, or {best['roi_gross_margin']:,.2f}x "
            f"once the {GROSS_MARGIN:.0%} gross margin is applied. It takes "
            f"{best['share_of_spend']:.0%} of media spend and returns "
            f"{best['share_of_sales']:.0%} of sales.</p>{eff_tbl}"
            f"<p><b>Caveat:</b> TV holds {tv['share_of_spend']:.0%} of budget with "
            "no attributed sales, so it's absent from this ranking, not last in "
            "it. Any TV ROI quoted here would be invented.</p>",

        "Which influencers underperformed?":
            f"<p><b>No influencer clears breakeven on gross margin.</b> Median "
            f"{sc['roas'].median()*GROSS_MARGIN:,.2f}x, best "
            f"{(sc['roas'].max()*GROSS_MARGIN):,.2f}x. Weakest by CPA:</p>{inf_tbl}"
            f"<p>Roster median CPA is {aed(med_cpa,0)}. Follower counts in this "
            "source are too unstable per creator to support tier classification "
            "— evaluate on cost and engagement instead, and confirm audience "
            "size before testing smaller creators.</p>",

        "Why did brand awareness change despite spend?":
            "<p><b>This data can't support that question.</b></p>"
            "<p>Brand values vary by up to <b>39 points inside a single "
            "market-week</b> — too noisy to be a real tracker reading, and "
            "averaging them to an indicative index supports comparing markets, not "
            "attributing a weekly move to spend.</p>"
            "<p>Answering it properly needs market-week-grain brand tracking and "
            "enough weeks to see a metric actually move.</p>",

        "Compare paid media versus earned media.":
            f"{pve_tbl}"
            f"<p><b>Earned produces "
            f"{pve[pve['media_type']=='earned']['share_of_sales'].iloc[0]:.0%} of "
            "sales at no media cost</b> — no ROAS shown rather than an infinite "
            "one.</p>"
            "<p><b>Earned isn't free</b> — it's bought by brand investment made "
            "earlier. Cutting reach spend to chase measurable channels risks "
            "eroding it.</p>",

        "What should be optimised next month?":
            "<p><b>One measurement fix, one budget move, one test.</b></p>"
            f"<p><b>1. Put a number on TV.</b> {tv['share_of_spend']:.0%} of budget "
            f"({aed(tv['spend_aed'])}) has no attributed return. A geo holdout or "
            "incrementality test is the highest-value analytics investment "
            "available.</p>"
            f"<p><b>2. Move budget toward the measurable winners.</b> "
            f"{table(re_[['channel','action','spend_change_aed','sales_impact_aed']], {'spend_change_aed': aed_short, 'sales_impact_aed': aed_short}) if not re_.empty else ''}"
            "Directional, not an optimum — move a bounded share and re-measure.</p>"
            "<p><b>3. Test smaller-scale influencer partnerships.</b> No creator "
            "clears breakeven, and this source's follower data isn't reliable "
            "enough to size the current roster.</p>"
            "<p>What <i>not</i> to do: re-plan by market or product — both sit "
            f"within {(ms['mer'].max()/ms['mer'].min()-1):.0%} and "
            f"{(ps['roas'].max()/ps['roas'].min()-1):.0%} of each other. No "
            "material misallocation to correct.</p>",
    }


def page_assistant(d: dict) -> str:
    canned = canned_answers(d)
    chips = "".join(f'<button class="chip">{C.esc(q)}</button>' for q in canned)
    return "".join([
        head("Part 2", "Ask AI"),
        '<div id="chat-status" class="card-sub" style="margin-bottom:16px"></div>',
        '<div class="chat-shell"><div>',
        f'<div class="suggestions">{chips}</div>',
        '<div id="chat-log" class="chat-log"></div>',
        '<div class="composer">',
        '<input id="chat-input" type="text" autocomplete="off" '
        'placeholder="Ask about channels, markets, products, influencers or budget…">',
        '<button id="chat-send">Ask</button></div></div>',
        '<aside class="side-note"><h3>How it works</h3>',
        "<p>Four tools: <code>run_sql</code> (read-only DuckDB), "
        "<code>describe_schema</code>, <code>get_alerts</code>, "
        "<code>get_analysis</code>.</p>",
        "<p>Deliberately <b>not</b> retrieval over the CSV — RAG on tabular data "
        "is exactly where models invent figures. SQL means DuckDB computes every "
        "number; the model only explains the rows.</p>",
        "<p><b>Guardrails:</b> read-only, only <code>SELECT</code>/"
        "<code>WITH</code> pass validation, results row-capped, 12-round limit.</p>",
        "<p>Briefed on this dataset's limits — 8 weeks, TV unattributed, brand "
        "metrics indicative — so it declines what the data can't answer.</p>",
        "</aside></div>",
        f"<script>window.__CANNED__ = {json.dumps(canned)};</script>",
    ])


# ==========================================================================
def build() -> None:
    d = {
        "spine": load("fact_market_week"), "chan": load("fact_channel"),
        "base": load("fact_base"), "eff": load("channel_efficiency"),
        "ms": load("market_scorecard"), "ps": load("product_summary"),
        "pm": load("panel_model"),
        "sc": load("influencer_scorecard"), "pve": load("paid_vs_earned"),
        "realloc": load("reallocation"), "alerts": load("alerts"),
        "alerts_current": load("alerts_current"),
        "dq": load("data_quality_log"),
    }
    d["raw_shape"] = {"rows": 2360, "cols": 24}
    src = pd.read_csv(SOURCE_FILE) if SOURCE_FILE.exists() else None
    if src is not None:
        d["raw_shape"] = {"rows": len(src), "cols": len(src.columns)}
    period = "8 weeks"

    crit_count = int((d["alerts_current"]["severity"] == "critical").sum())
    # Two independently-aggregated tables -- the market-week spine and the
    # per-channel rollup -- should agree on totals. No longer shown in the
    # sidebar, but still worth failing loudly on if the pipeline ever drifts.
    reconciled = (
        abs(d["spine"]["spend_aed"].sum() - d["eff"]["spend_aed"].sum()) < 1.0
        and abs(d["spine"]["sales_aed"].sum() - d["eff"]["sales_aed"].sum()) < 1.0
    )
    if not reconciled:
        print("  WARNING: spine and channel-efficiency totals do not reconcile")

    SITE.mkdir(parents=True, exist_ok=True)
    out_assets = SITE / "assets"
    if out_assets.exists():
        shutil.rmtree(out_assets)
    shutil.copytree(ASSETS, out_assets)

    # Ship the fact-table CSVs alongside the site so the Data page's per-table
    # download resolves offline. Only FACT_TABLES -- that is everything the
    # Data page browses now, so nothing else needs to ship as a loose CSV.
    out_data = SITE / "data"
    if out_data.exists():
        shutil.rmtree(out_data)
    out_data.mkdir(parents=True)
    for name, _, _ in FACT_TABLES:
        csv = DATA_PBI / f"{name}.csv"
        if csv.exists():
            shutil.copy2(csv, out_data / csv.name)

    # One workbook, every fact table as its own sheet under its business
    # name -- reads straight from the parquet (not the DATA_PBI CSVs above),
    # so it can never go stale against whatever the CSV export list includes.
    xlsx_path = out_data / "samsung_mena_all_tables.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        for name, label, _ in FACT_TABLES:
            try:
                load(name).to_excel(writer, sheet_name=label, index=False)
            except FileNotFoundError:
                continue

    builders = {
        "index.html": ("Overview", page_overview),
        "channels.html": ("Channels", page_channels),
        "portfolio.html": ("Markets & Products", page_portfolio),
        "influencers.html": ("Influencers", page_influencers),
        "brand.html": ("Brand & Competition", page_brand),
        "insights.html": ("Insights & Actions", page_insights),
        "alerts.html": ("Early Warning", page_alerts),
        "data.html": ("Data", page_data),
        "assistant.html": ("Ask AI", page_assistant),
    }
    for fname, (title, fn) in builders.items():
        html = shell(fname, title, fn(d), period, crit_count=crit_count)
        (SITE / fname).write_text(html, encoding="utf-8")
        print(f"  {fname:20s} {len(html)/1024:7.1f} KB")

    print(f"\nSite written to {SITE}")
    print("  open site/index.html      (static, works offline)")
    print("  python src/serve.py       (adds the live AI assistant)")


if __name__ == "__main__":
    build()
