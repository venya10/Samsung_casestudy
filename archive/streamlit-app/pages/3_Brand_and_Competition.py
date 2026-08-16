"""Brand & competition — awareness, sentiment, share of voice, and paid vs earned."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import theme as T
from data_access import load, market_filter, spine

T.page_setup("Brand & Competition", "🏷️")
st.title("Brand health and competitive position")

df_all = spine()
df, markets = market_filter(df_all, key="brand_market")

# --------------------------------------------------------------------------
# The headline question from the brief
# --------------------------------------------------------------------------
st.markdown("## Why awareness rose while media spend fell")

CUT_START, CUT_END = pd.Timestamp("2026-01-19"), pd.Timestamp("2026-02-23")
before = df[(df["week"] >= CUT_START - pd.Timedelta(weeks=6)) & (df["week"] < CUT_START)]
during = df[(df["week"] >= CUT_START) & (df["week"] <= CUT_END)]

paid_delta = during["paid_spend_usd"].sum() / before["paid_spend_usd"].sum() - 1
infl_delta = during["influencer_spend_usd"].sum() / before["influencer_spend_usd"].sum() - 1
pr_delta = during["pr_mentions"].sum() / before["pr_mentions"].sum() - 1
aw_start = df[df["week"] == CUT_START]["awareness"].mean()
aw_end = df[df["week"] == CUT_END]["awareness"].mean()

T.kpi_tiles([
    {"label": "Paid media", "value": f"{paid_delta:+.0%}", "sub": "vs prior 6 weeks"},
    {"label": "Influencer investment", "value": f"{infl_delta:+.0%}", "sub": "vs prior 6 weeks"},
    {"label": "PR mentions", "value": f"{pr_delta:+.0%}", "sub": "vs prior 6 weeks"},
    {"label": "Awareness", "value": f"{aw_start:.1f} → {aw_end:.1f} pp",
     "sub": "over the cut window"},
])

wk = df.groupby("week", as_index=False).agg(
    paid_spend_usd=("paid_spend_usd", "sum"),
    influencer_spend_usd=("influencer_spend_usd", "sum"),
    awareness=("awareness", "mean"),
    pr_mentions=("pr_mentions", "sum"),
)

c1, c2 = st.columns(2)

with c1:
    fig = go.Figure()
    for i, (col, label) in enumerate(
        [("paid_spend_usd", "Paid media"), ("influencer_spend_usd", "Influencer")]
    ):
        fig.add_trace(go.Scatter(
            x=wk["week"], y=wk[col], mode="lines", name=label,
            line=dict(color=T.SERIES[i], width=2),
            hovertemplate=f"%{{x|%d %b %Y}}<br>{label} $%{{y:,.0f}}<extra></extra>",
        ))
    fig.add_vrect(x0=CUT_START, x1=CUT_END, fillcolor=T.MUTED, opacity=0.09,
                  line_width=0, layer="below")
    fig.add_annotation(x=CUT_START + (CUT_END - CUT_START) / 2, y=1.0, yref="paper",
                       text="Q1 budget cut", showarrow=False,
                       font=dict(size=11, color=T.INK_2), yshift=-6)
    fig.update_layout(title="Investment by type through the cut (USD)")
    fig.update_yaxes(tickprefix="$", tickformat="~s")
    T.chart(fig, table=wk[["week", "paid_spend_usd", "influencer_spend_usd"]])

with c2:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=wk["week"], y=wk["awareness"], mode="lines", name="Awareness",
        line=dict(color=T.SERIES[0], width=2),
        hovertemplate="%{x|%d %b %Y}<br>Awareness %{y:.1f} pp<extra></extra>",
    ))
    fig.add_vrect(x0=CUT_START, x1=CUT_END, fillcolor=T.MUTED, opacity=0.09,
                  line_width=0, layer="below")
    fig.update_layout(title="Prompted awareness (percentage points)", showlegend=False)
    T.chart(fig, table=wk[["week", "awareness", "pr_mentions"]].round(2))

T.note(
    "<b>Three things happened at once, and none of them is 'media stopped mattering'.</b> "
    "First, carryover: the mix model puts the half-life of brand channels at roughly "
    "a week, so the White Friday and December bursts were still working into January. "
    "Second, the mix shifted rather than shrank — influencer investment rose "
    f"{infl_delta:+.0%} and earned PR mentions {pr_delta:+.0%} while paid fell "
    f"{paid_delta:+.0%}. Third, awareness is a slow-moving stock, not a flow; it "
    "responds to accumulated pressure over months. <b>The risk is reading this as "
    "proof that paid media can be cut permanently.</b> Brand equity begins declining "
    "from week 42 — roughly the lag you would expect from a sustained reduction in "
    "brand investment."
)

# --------------------------------------------------------------------------
# Share of voice
# --------------------------------------------------------------------------
st.markdown("## Share of voice")

pr = load("fact_weekly_pr")
pr = pr[pr["market"].isin(markets)]
sov = (
    pr.groupby(["week", "brand"], as_index=False)
    .agg(mentions=("mentions", "sum"))
)
tot = sov.groupby("week", as_index=False)["mentions"].sum().rename(
    columns={"mentions": "total"})
sov = sov.merge(tot, on="week")
sov["sov_pct"] = sov["mentions"] / sov["total"] * 100

fig = go.Figure()
brands = ["Samsung", "Rival A", "Rival B", "Rival C"]
for i, b in enumerate(brands):
    sub = sov[sov["brand"] == b]
    if sub.empty:
        continue
    # Samsung is the subject of the chart; rivals recede to a neutral step so the
    # eye goes to the crossover rather than to four competing hues.
    color = T.SERIES[0] if b == "Samsung" else ("#b8b6ae" if b != "Rival A" else T.SERIES[1])
    fig.add_trace(go.Scatter(
        x=sub["week"], y=sub["sov_pct"], mode="lines", name=b,
        line=dict(color=color, width=2 if b in ("Samsung", "Rival A") else 1.5),
        hovertemplate=f"%{{x|%d %b %Y}}<br>{b} %{{y:.1f}}%<extra></extra>",
    ))
fig.update_layout(title="Share of voice by brand (%)")
fig.update_yaxes(ticksuffix="%")
T.chart(fig, height=380, table=sov[["week", "brand", "sov_pct"]].round(2))

cross = df.groupby("week", as_index=False)["sov_gap_pp"].mean()
neg = cross[cross["sov_gap_pp"] < 0]
first_neg = neg["week"].min() if not neg.empty else None
T.note(
    "Rival A has taken share of voice steadily from week 38 onward"
    + (f", overtaking Samsung from <b>{first_neg.date()}</b>" if first_neg is not None else "")
    + ". Share of voice is a leading indicator for consideration, so this is the "
    "competitive signal to act on before it reaches the sales line. A steady slide "
    "with stable spend points to a weaker earned-media calendar rather than a paid "
    "media problem — buying reach at a premium to close a PR-driven gap is the "
    "expensive way to respond."
)

# --------------------------------------------------------------------------
# Sentiment
# --------------------------------------------------------------------------
st.markdown("## Sentiment")

sent = df.groupby("week", as_index=False).agg(
    sentiment_score=("sentiment_score", "mean"),
    social_engagement_rate=("social_engagement_rate", "mean"),
)
c1, c2 = st.columns(2)
with c1:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sent["week"], y=sent["sentiment_score"], mode="lines", name="Sentiment",
        line=dict(color=T.SERIES[0], width=2),
        hovertemplate="%{x|%d %b %Y}<br>Sentiment %{y:.3f}<extra></extra>",
    ))
    trough = sent.loc[sent["sentiment_score"].idxmin()]
    fig.add_annotation(
        x=trough["week"], y=trough["sentiment_score"],
        text="Post-launch pricing backlash", showarrow=True, arrowhead=0,
        arrowcolor=T.MUTED, ax=0, ay=34, font=dict(size=11, color=T.INK_2),
    )
    fig.add_hline(y=0, line=dict(color=T.BASELINE, width=1))
    fig.update_layout(title="Social sentiment (−1 to +1)", showlegend=False)
    T.chart(fig, table=sent.round(4))

with c2:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sent["week"], y=sent["social_engagement_rate"], mode="lines",
        name="Engagement rate", line=dict(color=T.SERIES[2], width=2),
        hovertemplate="%{x|%d %b %Y}<br>Engagement rate %{y:.2%}<extra></extra>",
    ))
    fig.update_layout(title="Social engagement rate (engagements ÷ reach)",
                      showlegend=False)
    fig.update_yaxes(tickformat=".1%")
    T.chart(fig, table=sent.round(4))

T.note(
    "<b>Engagement rose while sentiment fell.</b> The two charts move in opposite "
    "directions around the launch because outrage is engagement — a spike in "
    "interaction is not automatically good news, and a dashboard that tracked "
    "engagement alone would have read this week as a success."
)

# --------------------------------------------------------------------------
# Paid vs earned
# --------------------------------------------------------------------------
st.markdown("## Paid versus earned")

pve = load("paid_vs_earned")
show = pve[["media_type", "sessions", "session_share", "transactions",
            "conversion_rate", "revenue_usd", "revenue_share",
            "revenue_per_session_usd", "media_cost_usd", "roas"]]
st.dataframe(
    show.style.format({
        "sessions": "{:,.0f}", "session_share": "{:.1%}", "transactions": "{:,.0f}",
        "conversion_rate": "{:.2%}", "revenue_usd": "${:,.0f}",
        "revenue_share": "{:.1%}", "revenue_per_session_usd": "${:,.2f}",
        "media_cost_usd": "${:,.0f}", "roas": "{:.2f}x",
    }),
    use_container_width=True, hide_index=True,
)

earned = pve[pve["media_type"] == "earned"].iloc[0]
paid = pve[pve["media_type"] == "paid"].iloc[0]
T.note(
    f"Earned traffic is <b>{earned['session_share']:.0%}</b> of sessions but "
    f"<b>{earned['revenue_share']:.0%}</b> of online revenue, converting at "
    f"{earned['conversion_rate']:.2%} against paid's {paid['conversion_rate']:.2%} "
    f"and producing ${earned['revenue_per_session_usd']:.2f} per session versus "
    f"${paid['revenue_per_session_usd']:.2f}. "
    "<b>Earned is not free.</b> It has no media cost this week, but it was paid for "
    "by brand investment made in earlier weeks — which is why ROAS is left blank "
    "rather than shown as infinite. The honest read is that brand spending shows up "
    "later as high-intent organic traffic, not that organic traffic is costless."
)
