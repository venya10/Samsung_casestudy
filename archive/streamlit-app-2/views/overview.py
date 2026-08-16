"""Overview -- where the money went and what came back."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import charts
import data
import kpi
import state
import theme
from common import market_label
from data import aed, mult, num, pct

theme.head("Executive overview", "Where the money went, and what came back",
           "Eight MENA markets over eight weeks. Every figure below responds to the "
           "filters — click a bar, a line or a column segment, or use the dropdowns "
           "below, and the whole page re-runs on that slice.")

# Called before data.tables() so a dropdown change is reflected in this same
# run's numbers, rather than looking like it needs a second click to take --
# the filter bar writes into `xf` directly, it doesn't wait on a rerun.
state.standard_filter_bar()

t = data.tables()
chan, base = t["fact_channel"], t["fact_base"]
eff, ms = t["channel_efficiency"], t["market_scorecard"]

if not len(base):
    theme.note("No rows match the current filters.", warn=True)
    st.stop()

# ---------------------------------------------------------------- KPI strip
# Summed from `base` (fact_base), the only table carrying market, channel,
# product AND week -- so this is the one place every filter actually moves the
# numbers. fact_market_week has no channel column, so a KPI strip built from it
# would silently ignore a channel-level filter.
sales, spend = base["sales_aed"].sum(), base["spend_aed"].sum()
conv = base["conversions"].sum()
earned = base.loc[base["media_type"] == "earned", "sales_aed"].sum()
tv = base.loc[base["channel"] == "TV", "spend_aed"].sum()


def _sales(d):
    return d["sales_aed"].sum()


def _spend(d):
    return d["spend_aed"].sum()


def _mer(d):
    s = d["spend_aed"].sum()
    return d["sales_aed"].sum() / s if s else float("nan")


def _earned_pct(d):
    s = d["sales_aed"].sum()
    return d.loc[d["media_type"] == "earned", "sales_aed"].sum() / s * 100 if s else float("nan")


def _tv_pct(d):
    s = d["spend_aed"].sum()
    return d.loc[d["channel"] == "TV", "spend_aed"].sum() / s * 100 if s else float("nan")


def _aov(d):
    c = d["conversions"].sum()
    return d["sales_aed"].sum() / c if c else float("nan")


# Every delta/sparkline below re-applies the SAME aggregation already used for
# that KPI's headline value, split across the first vs. second half of the
# filtered weeks (kpi.period_trend) -- no new metric, only a narrower slice of
# what the page already computes.
d_sales, sp_sales = kpi.period_trend(base, "week", _sales)
d_spend, sp_spend = kpi.period_trend(base, "week", _spend)
d_mer, sp_mer = kpi.period_trend(base, "week", _mer)
d_earned, sp_earned = kpi.period_trend(base, "week", _earned_pct)
d_tv, sp_tv = kpi.period_trend(base, "week", _tv_pct)
d_aov, sp_aov = kpi.period_trend(base, "week", _aov)

kpi.row([
    {"label": "Media spend", "value": aed(spend), "unit": "AED", "change": d_spend,
     "invert": True, "spark": sp_spend, "spark_color": "#eb6834", "vs": "vs first half"},
    {"label": "Sales", "value": aed(sales), "unit": "AED", "change": d_sales,
     "spark": sp_sales, "spark_color": "#0B7A54", "vs": "vs first half"},
    {"label": "MER", "value": mult(sales / spend if spend else float("nan")),
     "change": d_mer, "spark": sp_mer, "vs": "vs first half",
     "hero": True},
    {"label": "Earned sales", "value": f"{earned / sales * 100:,.1f}" if sales else "—",
     "unit": "%", "change": d_earned, "spark": sp_earned, "vs": "vs first half"},
    {"label": "TV spend", "value": f"{tv / spend * 100:,.1f}" if spend else "—",
     "unit": "%", "change": d_tv, "invert": True, "spark": sp_tv,
     "spark_color": theme.STATUS["warning"], "flag": "excl. sales",
     "flag_tip": "TV carries spend but no attributed sales.", "vs": "vs first half"},
    {"label": "AOV", "value": aed(sales / conv if conv else float("nan")), "unit": "AED",
     "change": d_aov, "spark": sp_aov, "vs": "vs first half"},
])

# ------------------------------------------------------------- the headline
if len(eff):
    paid = eff[eff["revenue_attributed"] & (eff["spend_aed"] > 0)]
    if len(paid) > 1:
        hi, lo = paid.loc[paid["roas"].idxmax()], paid.loc[paid["roas"].idxmin()]
        span = hi["roas"] / lo["roas"] if lo["roas"] else float("nan")
        theme.note(
            f"<b>The variation that matters is between channels, not between "
            f"markets.</b> Attributed channels run from {mult(lo['roas'])} "
            f"({lo['channel']}) to {mult(hi['roas'])} ({hi['channel']}) — a "
            f"{span:,.0f}-fold spread. Markets sit within a few percent of each "
            f"other on MER. Budget decisions therefore belong at channel level.")

# ------------------------------------------------------------------ trend
theme.section("Trajectory")
c1, c2 = st.columns([3, 2], gap="medium")

with c1.container(border=True):
    theme.card_head("Weekly sales by market",
                    "Click a line to filter the page to that market")
    # Grouped from `base` rather than the market-week spine so a channel or
    # product filter (which fact_market_week can't represent) also narrows this.
    wm = base.groupby(["week", "market"], as_index=False)["sales_aed"].sum()
    charts.render(
        charts.line(wm, "week", "sales_aed", "market", "market",
                    hover_fmt=aed, label_fn=market_label),
        "ov_sales_line", "market", height=310)

with c2.container(border=True):
    theme.card_head("Weekly spend by channel", "Click a segment to filter")
    cw = chan.groupby(["week", "channel"], as_index=False)["spend_aed"].sum()
    charts.render(
        charts.stacked(cw, "week", "channel", "spend_aed", "channel",
                       hover_fmt=aed),
        "ov_spend_stack", "channel", height=310)

# --------------------------------------------------------------- efficiency
theme.section("Efficiency")
c3, c4 = st.columns(2, gap="medium")

with c3.container(border=True):
    theme.card_head("Return on ad spend by channel",
                    "TV and PR carry no attributed sales and are excluded")
    e = eff[eff["revenue_attributed"] & (eff["spend_aed"] > 0)]
    charts.render(
        charts.bar_h(e, "channel", "roas", "channel", highlight_extremes=True,
                     value_fmt=lambda v: f"{v:,.1f}x",
                     hover_fn=lambda r: (
                         f"{r.channel}<br>ROAS {r.roas:,.2f}x · "
                         f"{aed(r.spend_aed)} spend → {aed(r.sales_aed)} sales")),
        "ov_roas", "channel", height=300)

with c4.container(border=True):
    theme.card_head("Marketing efficiency ratio by market",
                    "Sales per AED of total spend")
    charts.render(
        charts.bar_h(ms, "market", "mer", "market", highlight_extremes=True,
                     value_fmt=lambda v: f"{v:,.2f}x",
                     hover_fn=lambda r: (f"{market_label(r.market)}<br>"
                                         f"MER {r.mer:,.2f}x · "
                                         f"{aed(r.sales_aed)} sales")),
        "ov_mer", "market", height=300)

# ------------------------------------------------------------ contribution
theme.section("Contribution")
c5, c6 = st.columns([2, 3], gap="medium")

with c5.container(border=True):
    theme.card_head("Spend share vs sales share",
                    "Above the line: earning more than it costs")
    e2 = eff[eff["spend_aed"] > 0].copy()
    sc = charts.scatter(e2, "share_of_spend", "share_of_sales", "channel", "channel",
                        size="spend_aed",
                        hover_fn=lambda r: (
                            f"{r.channel}<br>{pct(r.share_of_spend)} of spend → "
                            f"{pct(r.share_of_sales)} of sales"))
    lim = max(e2["share_of_spend"].max(), e2["share_of_sales"].max()) * 1.15
    sc.fig.update_xaxes(title="Share of spend", tickformat=".0%")
    sc.fig.update_yaxes(title="Share of sales", tickformat=".0%")
    sc.fig.add_shape(type="line", x0=0, y0=0, x1=lim, y1=lim, layer="below",
                     line=dict(color=theme.BASELINE, width=1, dash="dot"))
    charts.render(sc, "ov_share", "channel", height=330)

with c6.container(border=True):
    theme.card_head("Sales by market and channel",
                    "Click a cell to filter to that channel")
    pv = (base.groupby(["market", "channel"])["sales_aed"].sum()
          .unstack(fill_value=0))
    charts.render(charts.heatmap(pv, "channel", on="columns",
                                 fmt=lambda v: f"{v/1e6:,.1f}m"),
                  "ov_grid", "channel", height=330)

theme.note(
    "Read the grid across a row to see how one market splits its sales, and down a "
    "column to see whether a channel works everywhere or only somewhere. Channel "
    "columns are near-uniform across markets, which is why the reallocation case is "
    "made at channel level rather than market by market.")
