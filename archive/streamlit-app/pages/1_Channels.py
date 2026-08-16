"""Channels — what each channel returns, and where the next dollar should go."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import theme as T
from data_access import load, market_filter, spine

T.page_setup("Channels", "📈")
st.title("Channel performance")

df_all = spine()
df, markets = market_filter(df_all, key="ch_market")

chan = load("fact_weekly_channel")
chan = chan[chan["market"].isin(markets)]
roi = load("mmm_channel_roi")
plan = load("reallocation_plan")
fit = load("mmm_fit").iloc[0]

# --------------------------------------------------------------------------
# Model transparency first -- a director should see the fit before the answer
# --------------------------------------------------------------------------
st.markdown("## The model behind these numbers")
T.kpi_tiles([
    {"label": "Holdout R²", "value": f"{fit['holdout_r2']:.2f}",
     "sub": "on the last 8 weeks, unseen"},
    {"label": "In-sample R²", "value": f"{fit['r2']:.2f}", "sub": f"MAPE {fit['mape']:.1%}"},
    {"label": "Working media", "value": f"{fit['media_share_of_volume']:.0%}",
     "sub": "of volume, above the always-on floor"},
    {"label": "Brand half-life", "value": f"{-0.693/__import__('math').log(fit['brand_decay']):.1f} wk",
     "sub": "TV, YouTube, OOH, display"},
    {"label": "Performance half-life",
     "value": f"{-0.693/__import__('math').log(fit['perf_decay']):.1f} wk",
     "sub": "Search, Meta, TikTok"},
])

T.note(
    "Contribution is measured against a counterfactual of <b>every channel held at "
    "its leanest observed week</b>, not zero spend. Nothing in this data ever goes "
    "to zero — every channel runs always-on — so a zero-spend baseline would "
    "extrapolate far outside what was observed and credit media with volume that "
    "would have happened anyway. ROI below therefore divides uplift revenue by "
    "<i>working</i> spend: the money above the always-on floor."
)

# --------------------------------------------------------------------------
# ROI table
# --------------------------------------------------------------------------
st.markdown("## Return by channel")

show = roi[[
    "channel", "spend_usd", "working_spend_usd", "contribution_revenue_usd",
    "efficiency_index", "roi", "roi_gross_margin", "marginal_roi",
    "marginal_roi_gross_margin", "payback",
]].copy()
st.dataframe(
    show.style.format({
        "spend_usd": "${:,.0f}", "working_spend_usd": "${:,.0f}",
        "contribution_revenue_usd": "${:,.0f}", "efficiency_index": "{:.2f}",
        "roi": "{:.1f}x", "roi_gross_margin": "{:.2f}x",
        "marginal_roi": "{:.1f}x", "marginal_roi_gross_margin": "{:.2f}x",
    }),
    use_container_width=True, hide_index=True,
)
T.note(
    "<b>ROI on revenue flatters every channel.</b> The gross-margin columns apply a "
    "22% blended margin — the number a budget decision actually turns on. "
    "<b>Marginal</b> ROI, not average, is what should drive reallocation: average "
    "says what a channel earned historically, marginal says what the next dollar "
    "into it returns once diminishing returns are accounted for."
)

# --------------------------------------------------------------------------
# Reallocation
# --------------------------------------------------------------------------
st.markdown("## Recommended reallocation")

p = plan.sort_values("spend_change_usd")
colors = [T.STATUS["critical"] if v < 0 else T.SERIES[0] for v in p["spend_change_usd"]]
fig = go.Figure()
fig.add_trace(go.Bar(
    y=p["channel"], x=p["spend_change_usd"], orientation="h",
    marker=dict(color=colors),
    text=[f"{'−' if v < 0 else '+'}{T.fmt_money(abs(v))}" for v in p["spend_change_usd"]],
    textposition="outside", textfont=dict(color=T.INK_2, size=11),
    hovertemplate="%{y}<br>Change %{x:$,.0f}<extra></extra>",
))
fig.add_vline(x=0, line=dict(color=T.BASELINE, width=1))
span = max(abs(p["spend_change_usd"].min()), abs(p["spend_change_usd"].max())) * 1.45
fig.update_layout(title="Proposed annualised budget shift (USD)", showlegend=False)
fig.update_xaxes(range=[-span, span], tickprefix="$", tickformat="~s")
T.chart(fig, height=380, table=p[["channel", "action", "spend_usd", "spend_change_usd",
                                  "revenue_impact_usd", "marginal_roi"]].round(0))

net = plan["revenue_impact_usd"].sum()
from common import GROSS_MARGIN  # noqa: E402  (path is set by data_access)

T.kpi_tiles([
    {"label": "Budget moved", "value": T.fmt_money(
        plan.loc[plan["spend_change_usd"] > 0, "spend_change_usd"].sum())},
    {"label": "Modelled revenue impact", "value": T.fmt_money(net),
     "sub": "net, annualised"},
    {"label": "Modelled margin impact", "value": T.fmt_money(net * GROSS_MARGIN),
     "sub": f"at {GROSS_MARGIN:.0%} gross margin"},
])
T.note(
    "This shifts 15% of the budget of every below-median channel into the "
    "above-median ones, weighted by marginal ROI. It is a direction and an order of "
    "magnitude, not a media plan — it assumes response curves hold outside the "
    "observed spend range, which is exactly where they are least reliable. Treat it "
    "as the opening position for a planning conversation."
)

# --------------------------------------------------------------------------
# Cost inflation
# --------------------------------------------------------------------------
st.markdown("## Media cost inflation")

perf = chan[chan["channel"].isin(["Paid Search", "Meta"])]
cpc = (
    perf.groupby(["week", "channel"], as_index=False)
    .agg(spend=("spend_usd", "sum"), clicks=("clicks", "sum"))
)
cpc["cpc_usd"] = cpc["spend"] / cpc["clicks"].replace(0, pd.NA)

fig = go.Figure()
for i, ch in enumerate(["Paid Search", "Meta"]):
    sub = cpc[cpc["channel"] == ch]
    fig.add_trace(go.Scatter(
        x=sub["week"], y=sub["cpc_usd"], mode="lines", name=ch,
        line=dict(color=T.SERIES[i], width=2),
        hovertemplate=f"%{{x|%d %b %Y}}<br>{ch} $%{{y:,.2f}}<extra></extra>",
    ))
fig.update_layout(title="Cost per click on the two largest performance channels (USD)")
fig.update_yaxes(tickprefix="$")
T.chart(fig, table=cpc[["week", "channel", "cpc_usd"]].round(3))

first8 = cpc[cpc["week"] <= cpc["week"].min() + pd.Timedelta(weeks=8)]
last8 = cpc[cpc["week"] >= cpc["week"].max() - pd.Timedelta(weeks=8)]
lift = (last8["spend"].sum() / last8["clicks"].sum()) / (
    first8["spend"].sum() / first8["clicks"].sum()) - 1
T.note(
    f"Blended cost per click on Search and Meta is <b>{lift:+.0%}</b> across the "
    "year and has not come back down. Rising click cost with flat conversion volume "
    "is competitive pressure, not a creative problem — adding budget into a hot "
    "auction accelerates the loss rather than defending share."
)

# --------------------------------------------------------------------------
# Lag structure
# --------------------------------------------------------------------------
st.markdown("## How delayed are the effects?")

lag = load("lag_correlation")
lag = lag[lag["target"] == "sales_revenue_usd"]
top = (
    lag.drop_duplicates("driver")
    .assign(abs_corr=lambda d: d["best_correlation"].abs())
    .nlargest(10, "abs_corr")
)
fig = go.Figure()
fig.add_trace(go.Bar(
    y=top["driver"], x=top["best_correlation"], orientation="h",
    marker=dict(color=[T.SERIES[0] if v >= 0 else T.STATUS["critical"]
                       for v in top["best_correlation"]]),
    text=[f"lag {int(l)}w" for l in top["best_lag_weeks"]],
    textposition="outside", textfont=dict(color=T.MUTED, size=10),
    hovertemplate="%{y}<br>r = %{x:.2f}<extra></extra>",
))
fig.add_vline(x=0, line=dict(color=T.BASELINE, width=1))
fig.update_layout(title="Strongest correlation with weekly sales, and the lag at which it peaks",
                  showlegend=False)
fig.update_yaxes(autorange="reversed")
T.chart(fig, height=380,
        table=top[["driver", "best_lag_weeks", "best_correlation"]].round(3))

T.note(
    "Both series are de-seasonalised before correlating. Without that step every "
    "marketing metric correlates about 0.9 with sales purely because both peak at "
    "White Friday and Ramadan — a true statement about the calendar that says "
    "nothing about marketing effectiveness. This is a screening step: it tells the "
    "mix model which relationships to test and how delayed they are, not what caused what."
)
