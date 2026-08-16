"""Channels -- efficiency, statistical significance, and the reallocation case."""
from __future__ import annotations

import streamlit as st

import charts
import data
import kpi
import state
import theme
from data import aed, mult, num, pct

theme.head("Channel performance", "Which channels earn their spend",
           "ROAS, statistical confidence, and where budget should move. TV and PR "
           "carry no attributed sales and are shown separately rather than scored "
           "at zero.")
# Before data.tables() so a dropdown change is reflected in this same run.
state.standard_filter_bar()

t = data.tables()
eff, chan, base = t["channel_efficiency"], t["fact_channel"], t["fact_base"]
realloc = t["reallocation"]
pm = t["panel_model"]          # global-only: fitted once on the full panel
pve = t["paid_vs_earned"]

if not len(base):
    theme.note("No rows match the current filters.", warn=True)
    st.stop()

attributed = eff[eff["revenue_attributed"] & (eff["spend_aed"] > 0)]
unmeasured = eff[~eff["revenue_attributed"]]


def _unmeasured_spend(d):
    return d.loc[~d["revenue_attributed"], "spend_aed"].sum()


def _earned_share(d):
    paid = d.loc[d["media_type"] == "paid", "sales_aed"].sum()
    earned = d.loc[d["media_type"] == "earned", "sales_aed"].sum()
    tot = paid + earned
    return earned / tot * 100 if tot else float("nan")


d_unm, sp_unm = kpi.period_trend(chan, "week", _unmeasured_spend)
d_earn, sp_earn = kpi.period_trend(chan, "week", _earned_share)

kpi.row([
    {"label": "Channels in view", "value": num(len(eff)), "vs": "in this slice"},
    {"label": "Best ROAS", "value": mult(attributed["roas"].max()) if len(attributed) else "—",
     "vs": attributed.loc[attributed["roas"].idxmax(), "channel"] if len(attributed) else ""},
    {"label": "Weakest ROAS", "value": mult(attributed["roas"].min()) if len(attributed) else "—",
     "vs": attributed.loc[attributed["roas"].idxmin(), "channel"] if len(attributed) else ""},
    {"label": "No media cost", "value": f"{pve.loc[pve['media_type'] == 'earned', 'share_of_sales'].sum() * 100:,.1f}"
     if len(pve) else "—", "unit": "%", "change": d_earn, "spark": sp_earn,
     "spark_color": "#0B7A54", "vs": "vs first half"},
    {"label": "Unmeasured spend", "value": aed(unmeasured["spend_aed"].sum()), "unit": "AED",
     "change": d_unm, "invert": True, "spark": sp_unm,
     "spark_color": theme.STATUS["warning"], "vs": "vs first half"},
])

theme.section("Return on ad spend")
c1, c2 = st.columns([3, 2], gap="medium")

with c1.container(border=True):
    theme.card_head("ROAS by channel", "Sorted low to high · extremes highlighted")
    if len(attributed):
        charts.render(
            charts.bar_h(attributed, "channel", "roas", "channel",
                        highlight_extremes=True, value_fmt=lambda v: f"{v:,.1f}x",
                        hover_fn=lambda r: (
                            f"{r.channel}<br>ROAS {r.roas:,.2f}x · "
                            f"{aed(r.spend_aed)} spend → {aed(r.sales_aed)} sales<br>"
                            f"{r.payback}")),
            "ch_roas", "channel", height=340)
    else:
        theme.note("No attributed channels in this slice.")

with c2.container(border=True):
    theme.card_head("Not attributable", "TV and PR: spend without a linked sale")
    if len(unmeasured):
        charts.render(
            charts.bar_h(unmeasured, "channel", "spend_aed", "channel",
                        color=theme.SERIES_MUTED, value_fmt=lambda v: aed(v),
                        hover_fn=lambda r: f"{r.channel}<br>{aed(r.spend_aed)} spend"),
            "ch_unmeasured", "channel", height=340)
        theme.note(f"{pct(unmeasured['spend_aed'].sum() / eff['spend_aed'].sum())} "
                   "of all spend sits here. It isn't wasted -- there is simply no "
                   "sales record this dataset can attribute it to.", warn=True)
    else:
        theme.note("All channels in this slice are attributable.")

theme.section("Statistical confidence")
with st.container(border=True):
    theme.card_head("Panel regression: which channels move sales, holding others fixed",
                    f"R² {pm['r_squared'].iloc[0]:.3f} on {pm['n_observations'].iloc[0]} "
                    "market-weeks · fixed on the full panel regardless of filters, "
                    "since a regression needs the whole sample to mean anything")
    sig = pm[pm["significant_5pct"]]
    charts.render(
        charts.status_bar(
            pm.assign(status=pm["significant_5pct"].map(
                {True: "good", False: "warning"})),
            "channel", "coefficient", "status", "channel",
            value_fmt=lambda v: f"{v:,.2f}",
            hover_fn=lambda r: f"{r.channel}<br>{r.interpretation}"),
        "ch_panel", None, height=260)
    names = ", ".join(sig["channel"]) if len(sig) else "none"
    theme.note(f"<b>Only {names}</b> are distinguishable from zero at the 5% level "
               "with 8 weeks of data. The other coefficients are the model's best "
               "estimate but the confidence interval spans zero -- reported for "
               "completeness, not for reallocation decisions.")

theme.section("Reallocation case")
with st.container(border=True):
    theme.card_head("Moving budget toward the channels that are working",
                    "Donors and receivers are chosen against the full channel set, "
                    "even if one channel is filtered above -- reallocation needs "
                    "the whole group to identify who to move budget from")
    st.dataframe(
        realloc[["channel", "action", "spend_change_aed", "sales_impact_aed",
                "margin_impact_aed"]].rename(columns={
                    "channel": "Channel", "action": "Action",
                    "spend_change_aed": "Spend change (AED)",
                    "sales_impact_aed": "Sales impact (AED)",
                    "margin_impact_aed": "Margin impact (AED)"}),
        use_container_width=True, hide_index=True,
        column_config={
            "Spend change (AED)": st.column_config.NumberColumn(format="%.0f"),
            "Sales impact (AED)": st.column_config.NumberColumn(format="%.0f"),
            "Margin impact (AED)": st.column_config.NumberColumn(format="%.0f")})
    net_sales = realloc["sales_impact_aed"].sum()
    net_margin = realloc["margin_impact_aed"].sum()
    theme.note(f"Net effect of the moves above: <b>{aed(net_sales)}</b> in sales and "
               f"<b>{aed(net_margin)}</b> in gross margin, at zero net change in "
               "total spend.")
