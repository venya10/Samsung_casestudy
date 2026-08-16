"""Brand & Share -- awareness, intent, share of voice, and how they actually relate."""
from __future__ import annotations

import streamlit as st

import charts
import data
import kpi
import state
import theme
from common import market_label
from data import aed, num, pp

theme.head("Brand & share of voice", "Perception metrics, and what actually moves sales",
           "Samsung's share of voice against tracked competitors, plus a direct "
           "check on whether brand-tracking metrics predict sales in this dataset.")
# Before data.tables() so a dropdown change is reflected in this same run.
state.standard_filter_bar()

t = data.tables()
spine, ms = t["fact_market_week"], t["market_scorecard"]
corr = t["metric_correlations"]          # global-only: needs the full panel

if not len(spine):
    theme.note("No rows match the current filters.", warn=True)
    st.stop()

awareness = spine["brand_awareness"].mean()
intent = spine["purchase_intent"].mean()
sov = spine["share_of_voice"].mean()
comp_sov = spine["competitor_sov"].mean()
sentiment = spine["sentiment"].mean()


def _mean(col):
    return lambda d: d[col].mean()


d_aw, sp_aw = kpi.period_trend(spine, "week", _mean("brand_awareness"))
d_in, sp_in = kpi.period_trend(spine, "week", _mean("purchase_intent"))
d_sov, sp_sov = kpi.period_trend(spine, "week", _mean("share_of_voice"))
d_sent, sp_sent = kpi.period_trend(spine, "week", _mean("sentiment"))

kpi.row([
    {"label": "Brand awareness", "value": pp(awareness).rstrip("%"), "unit": "%",
     "change": d_aw, "spark": sp_aw, "vs": "vs first half"},
    {"label": "Purchase intent", "value": pp(intent).rstrip("%"), "unit": "%",
     "change": d_in, "spark": sp_in, "spark_color": "#0B7A54", "vs": "vs first half"},
    {"label": "Share of voice", "value": pp(sov).rstrip("%"), "unit": "%",
     "change": d_sov, "spark": sp_sov, "vs": f"vs. {pp(comp_sov)} competitor"},
    {"label": "SOV gap", "value": f"{sov - comp_sov:+.1f}", "unit": "pp",
     "vs": "Samsung minus competitor"},
    {"label": "Sentiment", "value": f"{sentiment:,.2f}", "change": d_sent,
     "spark": sp_sent, "spark_color": "#0B7A54", "vs": "index, -1 to +1"},
])

theme.section("Share of voice by market")
c1, c2 = st.columns([3, 2], gap="medium")

with c1.container(border=True):
    theme.card_head("Samsung vs. competitor share of voice",
                    "Click a bar to filter the page to that market")
    if len(ms):
        charts.render(
            charts.bar_h(ms, "market", "share_of_voice", "market",
                        value_fmt=lambda v: pp(v, 0),
                        hover_fn=lambda r: (f"{market_label(r.market)}<br>"
                                            f"Samsung {pp(r.share_of_voice)} vs. "
                                            f"competitor {pp(r.competitor_sov)}")),
            "br_sov", "market", height=300)
    else:
        theme.note("No market rows in this slice.")

with c2.container(border=True):
    theme.card_head("Sentiment by market", "-1 (negative) to +1 (positive)")
    if len(ms):
        charts.render(
            charts.bar_h(ms, "market", "sentiment", "market",
                        highlight_extremes=True, value_fmt=lambda v: f"{v:,.2f}",
                        hover_fn=lambda r: f"{market_label(r.market)}<br>sentiment {r.sentiment:,.2f}"),
            "br_sent", "market", height=300)

theme.section("Does brand tracking predict sales?")
with st.container(border=True):
    theme.card_head("Correlation with weekly sales",
                    "Computed on the full 64 market-weeks regardless of filters -- "
                    "a correlation needs the whole sample to mean anything")
    sales_corr = corr[(corr["metric_a"] == "sales_aed") | (corr["metric_b"] == "sales_aed")].copy()
    sales_corr["other"] = sales_corr.apply(
        lambda r: r["metric_b"] if r["metric_a"] == "sales_aed" else r["metric_a"], axis=1)
    sales_corr = sales_corr[sales_corr["other"] != "sales_aed"].sort_values("correlation")
    charts.render(
        charts.status_bar(
            sales_corr.assign(status=(sales_corr["correlation"] >= 0)
                              .map({True: "good", False: "critical"})),
            "other", "correlation", "status", "other",
            value_fmt=lambda v: f"{v:+.2f}",
            hover_fn=lambda r: f"{r.other}<br>r = {r.correlation:+.2f}<br>{r.note}"),
        "br_corr", None, height=340)
    weak = sales_corr[sales_corr["correlation"].abs() < 0.3]
    if len(weak):
        theme.note(f"<b>{', '.join(weak['other'])}</b> show weak or inverse "
                   "correlation with sales in this dataset. That does not mean "
                   "brand tracking is worthless -- 8 weeks is a short window for a "
                   "lagged effect -- but it means this dataset alone cannot be used "
                   "to justify brand spend on a sales basis.", warn=True)

theme.section("Awareness and intent over time")
with st.container(border=True):
    theme.card_head("Weekly brand awareness by market", "")
    charts.render(
        charts.line(spine, "week", "brand_awareness", "market", "market",
                    hover_fmt=pp, label_fn=market_label),
        "br_line", "market", height=320)
