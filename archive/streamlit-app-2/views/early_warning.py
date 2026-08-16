"""Early Warning -- the rule engine's live alert feed."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import charts
import data
import kpi
import state
import theme
from common import market_label
from data import num

theme.head("Early warning system", "13 rules watching spend, ROI, and peer variance",
           "Every alert traces back to a specific threshold in config/rules.yaml. "
           "Filters here narrow which alerts are shown, not which rules fired -- "
           "the engine always evaluates against the full panel.")
state.standard_filter_bar()

t = data.tables()
alerts, current = t["alerts"], t["alerts_current"]     # global-only: rule engine
                                                         # runs on the unfiltered
                                                         # panel; filters narrow
                                                         # which rows are SHOWN

SEV_STATUS = {"critical": "critical", "high": "serious", "medium": "warning",
             "low": "good"}


def _display(df):
    """Week is float64 NaN for rules that aren't week-scoped (peer/global rules).
    st.dataframe's grid renderer shows a bare float NaN as the literal text
    "None" rather than a blank cell, so it's rendered explicitly here instead."""
    df = df.copy()
    df["week"] = df["week"].apply(lambda w: "—" if pd.isna(w) else f"{int(w)}")
    return df


def _apply(df):
    a = state.active()
    for dim, vals in a.items():
        if dim in df.columns:
            df = df[df[dim].astype(str).isin([str(v) for v in vals])]
    return df


shown = _apply(alerts)
shown_current = _apply(current)

kpi.row([
    {"label": "Alerts in view", "value": num(len(shown)), "vs": f"of {len(alerts)} total"},
    {"label": "Open (current week)", "value": num(len(shown_current)), "vs": "in this slice"},
    {"label": "Critical", "value": num((shown["severity"] == "critical").sum()),
     "vs": "in this slice"},
    {"label": "High", "value": num((shown["severity"] == "high").sum()), "vs": "in this slice"},
    {"label": "Rules with hits", "value": num(shown["rule_id"].nunique()),
     "vs": "of 13 rules"},
])

if not len(shown):
    theme.note("No alerts match the current filters.")
    st.stop()

theme.section("By severity")
c1, c2 = st.columns([2, 3], gap="medium")

with c1.container(border=True):
    theme.card_head("Alert count by severity", "")
    sc = (shown["severity"].value_counts()
          .reindex(["critical", "high", "medium", "low"]).fillna(0).astype(int)
          .rename_axis("severity").reset_index(name="n"))
    sc = sc[sc["n"] > 0]
    charts.render(
        charts.status_bar(sc.assign(status=sc["severity"].map(SEV_STATUS)),
                          "severity", "n", "status", "severity",
                          value_fmt=lambda v: f"{v:,.0f}"),
        "ew_sev", None, height=220)

with c2.container(border=True):
    theme.card_head("Alert count by market", "Click a bar to filter the page")
    mc = (shown.groupby("market", as_index=False).size()
          .rename(columns={"size": "n"}))
    if len(mc):
        charts.render(
            charts.bar_h(mc, "market", "n", "market", value_fmt=lambda v: f"{v:,.0f}",
                        hover_fn=lambda r: f"{market_label(r.market)}<br>{r.n:.0f} alerts"),
            "ew_market", "market", height=220)
    else:
        theme.note("No market-scoped alerts in this slice.")

theme.section("Open alerts")
with st.container(border=True):
    theme.card_head(f"{len(shown_current)} currently open",
                    "Filtered to the latest week each rule was evaluated")
    if len(shown_current):
        sort_col = "severity_rank" if "severity_rank" in shown_current.columns else "severity"
        st.dataframe(
            _display(shown_current.sort_values(sort_col))
            [["week", "market", "entity", "severity", "rule", "metric",
             "value", "detail", "owner", "action"]]
            .rename(columns={"week": "Week", "market": "Market", "entity": "Entity",
                             "severity": "Severity", "rule": "Rule", "metric": "Metric",
                             "value": "Value", "detail": "Detail", "owner": "Owner",
                             "action": "Recommended action"}),
            use_container_width=True, hide_index=True)
    else:
        theme.note("Nothing currently open in this slice.")

theme.section("Full alert history")
with st.container(border=True):
    st.dataframe(
        _display(shown)
        [["week", "market", "entity", "severity", "rule", "category", "metric",
         "value", "detail", "owner", "action"]]
        .rename(columns={"week": "Week", "market": "Market", "entity": "Entity",
                         "severity": "Severity", "rule": "Rule", "category": "Category",
                         "metric": "Metric", "value": "Value", "detail": "Detail",
                         "owner": "Owner", "action": "Recommended action"}),
        use_container_width=True, hide_index=True)
