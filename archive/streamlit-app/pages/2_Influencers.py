"""Influencers — who is worth the money, and who is buying an audience."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import theme as T
from data_access import load

T.page_setup("Influencers", "🎤")
st.title("Influencer performance")

sc = load("influencer_scorecard")

markets = st.multiselect("Markets", sorted(sc["market"].unique()),
                         default=sorted(sc["market"].unique()), key="inf_market")
if markets:
    sc = sc[sc["market"].isin(markets)]

suspect = sc[sc["audience_quality"] == "Suspect"]

T.kpi_tiles([
    {"label": "Influencers", "value": f"{len(sc)}"},
    {"label": "Total fees", "value": T.fmt_money(sc["fee_usd"].sum())},
    {"label": "Flagged audience quality", "value": f"{len(suspect)}",
     "sub": f"{T.fmt_money(suspect['fee_usd'].sum())} of fees"},
    {"label": "Excess vs median efficiency", "value": T.fmt_money(sc["excess_cost_usd"].sum()),
     "sub": "recoverable at median CPA"},
    {"label": "Median CPA", "value": f"${sc['cpa_usd'].median():,.2f}"},
])

# --------------------------------------------------------------------------
# The quadrant
# --------------------------------------------------------------------------
st.markdown("## Reach versus efficiency")

med_cpa = sc["cpa_usd"].median()
med_reach = sc["reach"].median()

fig = go.Figure()
# Two colour classes only. On a scatter every pair of points sits adjacent, so the
# palette caps at three; two keeps clear separation under colour-vision deficiency.
# "Suspect" is a state, not a category, so it wears the critical status colour and
# is spelled out in the legend -- never colour alone.
for label, color, symbol in [
    ("OK", T.SERIES[0], "circle"),
    ("Suspect", T.STATUS["critical"], "x"),
]:
    sub = sc[sc["audience_quality"] == label]
    if sub.empty:
        continue
    fig.add_trace(go.Scatter(
        x=sub["reach"], y=sub["cpa_usd"], mode="markers+text",
        name=f"Audience quality: {label}",
        text=sub["influencer"], textposition="top center",
        textfont=dict(size=9, color=T.MUTED),
        marker=dict(
            color=color, symbol=symbol,
            size=(sub["fee_usd"] / sc["fee_usd"].max() * 34 + 10),
            line=dict(color=T.SURFACE, width=2),
        ),
        customdata=sub[["tier", "fee_usd", "conversions", "engagement_rate"]],
        hovertemplate=(
            "<b>%{text}</b><br>Tier %{customdata[0]}<br>"
            "Reach %{x:,.0f}<br>CPA $%{y:,.2f}<br>"
            "Fees $%{customdata[1]:,.0f}<br>Conversions %{customdata[2]:,.0f}<br>"
            "Engagement rate %{customdata[3]:.2%}<extra></extra>"
        ),
    ))

fig.add_hline(y=med_cpa, line=dict(color=T.BASELINE, width=1))
fig.add_vline(x=med_reach, line=dict(color=T.BASELINE, width=1))
fig.add_annotation(x=0.02, y=0.02, xref="paper", yref="paper",
                   text="Hidden gems — cheap, small", showarrow=False,
                   font=dict(size=10, color=T.MUTED), align="left")
fig.add_annotation(x=0.98, y=0.02, xref="paper", yref="paper",
                   text="Scale winners — cheap, big", showarrow=False,
                   font=dict(size=10, color=T.MUTED), align="right")
fig.add_annotation(x=0.98, y=0.97, xref="paper", yref="paper",
                   text="Expensive reach", showarrow=False,
                   font=dict(size=10, color=T.MUTED), align="right")
fig.update_layout(
    title="Cost per acquisition vs total reach · marker size = total fees",
)
fig.update_xaxes(title_text="Total reach", tickformat="~s")
fig.update_yaxes(title_text="Cost per acquisition (USD)", tickprefix="$", type="log")
T.chart(fig, height=520,
        table=sc[["influencer", "tier", "market", "reach", "cpa_usd", "fee_usd",
                  "engagement_rate", "audience_quality", "quadrant"]].round(4))

T.note(
    "The y-axis is logarithmic: the flagged accounts cost so much more per "
    "acquisition than the rest that a linear scale would compress every genuinely "
    "useful influencer into a single band at the bottom. <b>Note the ranking is not "
    "by follower count</b> — the largest accounts on this chart are the worst "
    "investments."
)

# --------------------------------------------------------------------------
# Audience quality diagnostic
# --------------------------------------------------------------------------
st.markdown("## Audience quality diagnostic")

fig = go.Figure()
for label, color, symbol in [
    ("OK", T.SERIES[0], "circle"),
    ("Suspect", T.STATUS["critical"], "x"),
]:
    sub = sc[sc["audience_quality"] == label]
    if sub.empty:
        continue
    fig.add_trace(go.Scatter(
        x=sub["impression_reach_ratio"], y=sub["comment_ratio"], mode="markers+text",
        name=f"Audience quality: {label}", text=sub["influencer"],
        textposition="top center", textfont=dict(size=9, color=T.MUTED),
        marker=dict(color=color, symbol=symbol, size=12,
                    line=dict(color=T.SURFACE, width=2)),
        hovertemplate=("<b>%{text}</b><br>Impressions:reach %{x:.2f}x<br>"
                       "Comment ratio %{y:.2%}<extra></extra>"),
    ))
fig.add_hline(y=0.02, line=dict(color=T.BASELINE, width=1))
fig.add_vline(x=2.0, line=dict(color=T.BASELINE, width=1))
fig.update_layout(title="Impressions-to-reach ratio vs comment ratio")
fig.update_xaxes(title_text="Impressions ÷ reach")
fig.update_yaxes(title_text="Comments ÷ engagements", tickformat=".1%")
T.chart(fig, height=440,
        table=sc[["influencer", "impression_reach_ratio", "comment_ratio",
                  "audience_quality"]].round(4))

T.note(
    "Two signals, both cheap to compute, that together are hard to fake. A healthy "
    "account converts roughly 5–9% of its engagements into comments and shows "
    "impressions within about 1.5x of genuine reach. The flagged accounts sit at "
    "under 2% comments with impressions near 3x reach — the signature of purchased "
    "followers or undisclosed paid amplification. Neither number alone is proof; "
    "together they are enough to withhold the next payment and ask for "
    "platform-native analytics."
)

# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------
st.markdown("## Recommended action by influencer")

show = sc.sort_values("cpa_usd")[[
    "influencer", "market", "tier", "followers", "fee_usd", "reach", "conversions",
    "cpa_usd", "engagement_rate", "audience_quality", "quadrant",
    "excess_cost_usd", "recommended_action",
]]
st.dataframe(
    show.style.format({
        "followers": "{:,.0f}", "fee_usd": "${:,.0f}", "reach": "{:,.0f}",
        "conversions": "{:,.0f}", "cpa_usd": "${:,.2f}",
        "engagement_rate": "{:.2%}", "excess_cost_usd": "${:,.0f}",
    }),
    use_container_width=True, hide_index=True, height=560,
)

sus_fees = sc.loc[sc["audience_quality"] == "Suspect", "fee_usd"].sum()
sus_conv = sc.loc[sc["audience_quality"] == "Suspect", "conversions"].sum()
T.note(
    f"The four flagged accounts take <b>{sus_fees / sc['fee_usd'].sum():.0%}</b> of "
    f"influencer fees ({T.fmt_money(sus_fees)}) and return "
    f"<b>{sus_conv / sc['conversions'].sum():.1%}</b> of influencer conversions, at "
    f"an average ${sc.loc[sc['audience_quality'] == 'Suspect', 'cpa_usd'].mean():,.0f} "
    f"per acquisition against a roster median of ${med_cpa:,.2f}. "
    f"<b>Excess cost against median efficiency: {T.fmt_money(sc['excess_cost_usd'].sum())}.</b><br><br>"
    "That excess figure is the defensible one. Dividing the freed budget by the "
    "median CPA to project additional conversions is <i>not</i> — it assumes the "
    "efficient micro tier absorbs several million dollars at unchanged efficiency, "
    "and it would not. The realistic move is to reallocate progressively and "
    "re-measure, expecting CPA to rise as the tier scales."
)
