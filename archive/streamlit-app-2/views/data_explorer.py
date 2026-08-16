"""Data -- the cleaned tables themselves, filtered and downloadable."""
from __future__ import annotations

import streamlit as st

import data
import state
import theme

TABLES = {
    "fact_base": "Base fact (week x market x channel x product) -- the finest grain",
    "fact_channel": "Channel performance by week and market",
    "fact_product": "Product performance by week and market",
    "fact_market_week": "Market-week spine -- one row per market per week",
    "fact_influencer": "Influencer campaign performance",
    "fact_brand": "Brand tracking (awareness, intent, sentiment, SOV)",
    "dim_market": "Market dimension",
    "dim_channel": "Channel dimension",
    "dim_product": "Product dimension",
    "dim_influencer": "Influencer roster dimension",
    "dim_week": "Week dimension",
    "data_quality_log": "Every cleaning decision made on the raw files, and why",
}

theme.head("Data", "The cleaned tables behind every chart on this platform",
           "Filters from other pages carry over where the table has a matching "
           "column. Download any table as CSV.")
state.standard_filter_bar()

t = data.tables()
name = st.selectbox("Table", list(TABLES.keys()),
                    format_func=lambda k: f"{k}  ·  {TABLES[k]}")
df = t.get(name)

if df is None or not len(df):
    theme.note("No rows match the current filters for this table.", warn=True)
else:
    theme.note(f"<b>{len(df):,} rows × {len(df.columns)} columns</b> — {TABLES[name]}")
    st.dataframe(df, use_container_width=True, height=560)
    st.download_button("Download CSV", df.to_csv(index=False).encode("utf-8"),
                       file_name=f"{name}.csv", mime="text/csv")

theme.section("Cleaning log")
with st.container(border=True):
    dq = t.get("data_quality_log")
    if dq is not None and len(dq):
        st.dataframe(dq.rename(columns={"check": "Check", "finding": "Finding",
                                        "rows": "Rows", "action": "Action taken"}),
                    use_container_width=True, hide_index=True)
