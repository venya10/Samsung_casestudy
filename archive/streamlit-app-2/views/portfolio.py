"""Portfolio -- product performance and which channel carries which product."""
from __future__ import annotations

import streamlit as st

import charts
import data
import kpi
import state
import theme
from data import aed, mult, num, pct

theme.head("Product portfolio", "What's selling, and through what",
           "Six products across eight channels. Support index compares each "
           "product's channel spread against the portfolio average.")
# Before data.tables() so a dropdown change is reflected in this same run.
state.standard_filter_bar()

t = data.tables()
psum, pchan, base = t["product_summary"], t["product_channel"], t["fact_base"]

if not len(psum):
    theme.note("No rows match the current filters.", warn=True)
    st.stop()

lead = psum.loc[psum["sales_aed"].idxmax()]


def _total_sales(d):
    return d["sales_aed"].sum()


def _total_aov(d):
    c = d["conversions"].sum()
    return d["sales_aed"].sum() / c if c else float("nan")


d_sales, sp_sales = kpi.period_trend(base, "week", _total_sales)
d_aov, sp_aov = kpi.period_trend(base, "week", _total_aov)

kpi.row([
    {"label": "Products in view", "value": num(len(psum)), "vs": "in this slice"},
    {"label": "Lead product", "value": lead["product"], "vs": aed(lead["sales_aed"])},
    {"label": "Best ROAS", "value": mult(psum["roas"].max()),
     "vs": psum.loc[psum["roas"].idxmax(), "product"]},
    {"label": "Total sales", "value": aed(psum["sales_aed"].sum()), "unit": "AED",
     "change": d_sales, "spark": sp_sales, "spark_color": "#0B7A54", "vs": "vs first half"},
    {"label": "Total AOV", "value": aed(base["sales_aed"].sum() / base["conversions"].sum()
                                        if base["conversions"].sum() else float("nan")),
     "unit": "AED", "change": d_aov, "spark": sp_aov, "vs": "vs first half"},
])

theme.section("Product performance")
c1, c2 = st.columns([3, 2], gap="medium")

with c1.container(border=True):
    theme.card_head("Sales by product", "Click a bar to filter the page to that product")
    charts.render(
        charts.bar_h(psum, "product", "sales_aed", "product",
                    value_fmt=lambda v: aed(v),
                    hover_fn=lambda r: (f"{r.product}<br>{aed(r.sales_aed)} sales · "
                                        f"ROAS {r.roas:,.1f}x")),
        "pf_sales", "product", height=300)

with c2.container(border=True):
    theme.card_head("ROAS by product", "")
    charts.render(
        charts.bar_h(psum, "product", "roas", "product", highlight_extremes=True,
                    value_fmt=lambda v: f"{v:,.1f}x",
                    hover_fn=lambda r: f"{r.product}<br>ROAS {r.roas:,.2f}x"),
        "pf_roas", "product", height=300)

theme.section("Product x channel")
with st.container(border=True):
    theme.card_head("Sales by product and channel",
                    "Click a cell to filter to that channel")
    pv = pchan.pivot_table(index="product", columns="channel", values="sales_aed",
                           fill_value=0)
    charts.render(charts.heatmap(pv, "channel", on="columns",
                                 fmt=lambda v: f"{v/1e6:,.1f}m" if v >= 1e5 else f"{v:,.0f}"),
                  "pf_grid", "channel", height=280)
    theme.note("Read down a column to see whether a channel is a generalist "
               "(spread across products) or is really only working for one line. "
               "Read across a row to see how concentrated a product's sales are "
               "in one channel versus spread across several.")

theme.section("Support index")
with st.container(border=True):
    theme.card_head("How many channels carry each product",
                    "support_index: 1.0 = average channel spread for this portfolio")
    st.dataframe(
        psum[["product", "spend_aed", "sales_aed", "roas", "aov_aed", "cpa_aed",
             "share_of_spend", "share_of_sales", "support_index"]]
        .rename(columns={"product": "Product", "spend_aed": "Spend (AED)",
                         "sales_aed": "Sales (AED)", "roas": "ROAS",
                         "aov_aed": "AOV (AED)", "cpa_aed": "CPA (AED)",
                         "share_of_spend": "Share of spend",
                         "share_of_sales": "Share of sales",
                         "support_index": "Support index"}),
        use_container_width=True, hide_index=True,
        column_config={
            "Spend (AED)": st.column_config.NumberColumn(format="%.0f"),
            "Sales (AED)": st.column_config.NumberColumn(format="%.0f"),
            "ROAS": st.column_config.NumberColumn(format="%.2fx"),
            "AOV (AED)": st.column_config.NumberColumn(format="%.0f"),
            "CPA (AED)": st.column_config.NumberColumn(format="%.0f"),
            "Share of spend": st.column_config.NumberColumn(format="percent"),
            "Share of sales": st.column_config.NumberColumn(format="percent"),
            "Support index": st.column_config.NumberColumn(format="%.2f")})
