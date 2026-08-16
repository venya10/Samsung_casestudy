"""Influencers -- roster economics, follower-data reliability, and the breakeven line."""
from __future__ import annotations

import streamlit as st

import charts
import data
import kpi
import state
import theme
from common import market_label
from data import aed, mult, num, pct

theme.head("Influencer roster", "Creator-level economics against margin breakeven",
           "24 creators. ROI is measured on gross margin, not revenue -- a ROAS "
           "above 1x can still lose money once cost of goods is paid.")
# Before data.tables() so a dropdown change is reflected in this same run.
state.standard_filter_bar()

t = data.tables()
inf = t["influencer_scorecard"]

if not len(inf):
    theme.note("No influencer rows match the current filters.", warn=True)
    st.stop()

profitable = inf[inf["roi_gross_margin"] >= 1.0]
# No follower tier -- the source's follower count swings by hundreds of
# thousands for the same creator within a single week, so no aggregation of
# it (max, median, mean) supports a reliable tier split. See build_dims() in
# src/model.py. `followers_unstable` flags the instability itself.
n_unstable = int(inf["followers_unstable"].fillna(False).sum()) if "followers_unstable" in inf else 0
mostly_unstable = len(inf) > 0 and n_unstable / len(inf) >= 0.5

# influencer_scorecard is aggregated to one row per creator across the whole
# window (no week column), so its spend trend comes from fact_influencer
# instead -- same total, just still broken out by week.
fi = t["fact_influencer"]


def _spend(d):
    return d["spend_aed"].sum()


d_spend, sp_spend = kpi.period_trend(fi, "week", _spend) if len(fi) else (None, [])

kpi.row([
    {"label": "Creators in view", "value": num(len(inf)), "vs": "in this slice"},
    {"label": "Above margin breakeven", "value": f"{len(profitable)} / {len(inf)}",
     "vs": pct(len(profitable) / len(inf)) if len(inf) else "—"},
    {"label": "Best ROI (margin)", "value": mult(inf["roi_gross_margin"].max()),
     "vs": inf.loc[inf["roi_gross_margin"].idxmax(), "influencer"]},
    {"label": "Total spend", "value": aed(inf["spend_aed"].sum()), "unit": "AED",
     "change": d_spend, "invert": True, "spark": sp_spend,
     "spark_color": theme.STATUS["warning"], "vs": "vs first half"},
    {"label": "Follower data unreliable", "value": f"{n_unstable} / {len(inf)}" if len(inf) else "—",
     "vs": "swings by more than its own median"},
])

if mostly_unstable:
    theme.note("<b>Most creators in this slice have a follower count that swings by "
               "more than its own median across rows in the source.</b> The same "
               "influencer shows very different values week to week, sometimes even "
               "product to product in the same week -- so follower-tier "
               "classification is not reliable here. Engagement is benchmarked "
               "against the whole roster instead, not a follower-size peer group.",
               warn=True)

theme.section("Return on margin")
with st.container(border=True):
    theme.card_head("ROI on gross margin, by creator",
                    "1.0x = breakeven after cost of goods. Below the line: losing "
                    "money on margin despite a ROAS above 1x.")
    inf_sorted = inf.sort_values("roi_gross_margin")
    charts.render(
        charts.status_bar(
            inf_sorted.assign(status=(inf_sorted["roi_gross_margin"] >= 1.0)
                              .map({True: "good", False: "critical"})),
            "influencer", "roi_gross_margin", "status", "influencer",
            value_fmt=lambda v: f"{v:,.2f}x",
            hover_fn=lambda r: (f"{r.influencer} · {market_label(r.market)}<br>"
                                f"ROI {r.roi_gross_margin:,.2f}x on margin · "
                                f"ROAS {r.roas:,.2f}x<br>{r.recommended_action}")),
        "inf_roi", None, height=560)

theme.section("Efficiency vs. reach")
c1, c2 = st.columns(2, gap="medium")

with c1.container(border=True):
    theme.card_head("Cost per follower vs. ROI",
                    "Bubble size = spend")
    charts.render(
        charts.scatter(inf, "cost_per_follower", "roi_gross_margin", "influencer",
                       "influencer", size="spend_aed",
                       hover_fn=lambda r: (f"{r.influencer}<br>"
                                           f"{r.cost_per_follower:,.3f} AED/follower · "
                                           f"ROI {r.roi_gross_margin:,.2f}x")),
        "inf_scatter", None, height=320)

with c2.container(border=True):
    theme.card_head("Engagement vs. roster median", "er_vs_roster: positive = outperforming the roster")
    e = inf.sort_values("er_vs_roster")
    charts.render(
        charts.status_bar(
            e.assign(status=(e["er_vs_roster"] >= 0).map({True: "good", False: "warning"})),
            "influencer", "er_vs_roster", "status", "influencer",
            value_fmt=lambda v: f"{v:+.1%}",
            hover_fn=lambda r: f"{r.influencer}<br>{r.er_vs_roster:+.1%} vs. roster median"),
        "inf_er", None, height=560)

theme.section("Full roster")
with st.container(border=True):
    st.dataframe(
        inf[["influencer", "market", "followers", "spend_aed", "sales_aed",
            "roas", "roi_gross_margin", "cpa_aed", "flag", "recommended_action"]]
        .rename(columns={"influencer": "Creator", "market": "Market",
                         "followers": "Followers (median)", "spend_aed": "Spend (AED)",
                         "sales_aed": "Sales (AED)", "roas": "ROAS",
                         "roi_gross_margin": "ROI (margin)", "cpa_aed": "CPA (AED)",
                         "flag": "Flag", "recommended_action": "Recommended action"}),
        use_container_width=True, hide_index=True,
        column_config={
            "Spend (AED)": st.column_config.NumberColumn(format="%.0f"),
            "Sales (AED)": st.column_config.NumberColumn(format="%.0f"),
            "ROAS": st.column_config.NumberColumn(format="%.2fx"),
            "ROI (margin)": st.column_config.NumberColumn(format="%.2fx"),
            "CPA (AED)": st.column_config.NumberColumn(format="%.0f")})
