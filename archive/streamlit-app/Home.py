"""Overview — the page a Marketing Director opens first."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import theme as T
from data_access import load, market_filter, spine

T.page_setup("Overview", "📊")

st.title("Samsung MENA — Marketing Performance")
T.synthetic_banner()

df_all = spine()
df, markets = market_filter(df_all)

latest = df["week"].max()
prev = latest - pd.Timedelta(weeks=1)
cur_wk = df[df["week"] == latest]
prv_wk = df[df["week"] == prev]


def delta(col: str) -> float | None:
    a, b = cur_wk[col].sum(), prv_wk[col].sum()
    return None if b == 0 else a / b - 1


# --------------------------------------------------------------------------
# Headline KPIs
# --------------------------------------------------------------------------
st.markdown(f"### Week commencing {latest.date()}")

alerts_cur = load("alerts_current")
alerts_cur = alerts_cur[alerts_cur["market"].isin(markets)]
n_critical = int((alerts_cur["severity"] == "critical").sum())

T.kpi_tiles([
    {
        "label": "Sales revenue",
        "value": T.fmt_money(cur_wk["sales_revenue_usd"].sum()),
        "delta": delta("sales_revenue_usd"),
        "sub": f"{T.fmt_num(cur_wk['units_sold'].sum())} units",
    },
    {
        "label": "Media spend",
        "value": T.fmt_money(cur_wk["total_media_spend_usd"].sum()),
        "delta": delta("total_media_spend_usd"),
        "good_when_up": False,
        "sub": "paid + influencer",
    },
    {
        "label": "MER",
        "value": f"{cur_wk['sales_revenue_usd'].sum() / max(cur_wk['total_media_spend_usd'].sum(), 1):,.1f}x",
        "sub": "revenue per media dollar",
    },
    {
        "label": "CPC",
        "value": f"${cur_wk['paid_spend_usd'].sum() / max(cur_wk['paid_clicks'].sum(), 1):,.2f}",
        "delta": delta("paid_clicks") and None,
        "good_when_up": False,
        "sub": "blended paid",
    },
    {
        "label": "Brand equity",
        "value": f"{cur_wk['brand_equity_index'].mean():,.1f}",
        "sub": "index, interpolated",
    },
    {
        "label": "SOV gap",
        "value": f"{cur_wk['sov_gap_pp'].mean():+,.1f} pp",
        "sub": "vs largest competitor",
    },
    {
        "label": "Open alerts",
        "value": f"{len(alerts_cur)}",
        "sub": f"{n_critical} critical",
    },
])

if n_critical:
    T.note(
        f"<b>{n_critical} critical alert(s) this week.</b> Samsung's share of voice has "
        "fallen behind its largest competitor in every market, and brand equity is "
        "declining. See the Alerts page for owners and recommended actions."
    )

# --------------------------------------------------------------------------
# Trends -- two charts, never a dual axis
# --------------------------------------------------------------------------
st.markdown("## Sales and media investment")
T.note(
    "Shown as two charts rather than one with two y-axes: revenue and spend are on "
    "different scales, and overlaying them on a shared plot invents a visual "
    "correlation that the alignment of the two axes, not the data, produced."
)

wk = df.groupby("week", as_index=False).agg(
    sales_revenue_usd=("sales_revenue_usd", "sum"),
    total_media_spend_usd=("total_media_spend_usd", "sum"),
    paid_spend_usd=("paid_spend_usd", "sum"),
    influencer_spend_usd=("influencer_spend_usd", "sum"),
    units_sold=("units_sold", "sum"),
)

c1, c2 = st.columns(2)

with c1:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=wk["week"], y=wk["sales_revenue_usd"], mode="lines",
        line=dict(color=T.SERIES[0], width=2), name="Sales revenue",
        hovertemplate="%{x|%d %b %Y}<br>Revenue $%{y:,.0f}<extra></extra>",
    ))
    peak = wk.loc[wk["sales_revenue_usd"].idxmax()]
    fig.add_annotation(
        x=peak["week"], y=peak["sales_revenue_usd"], text="White Friday peak",
        showarrow=True, arrowhead=0, arrowcolor=T.MUTED, ax=0, ay=-28,
        font=dict(size=11, color=T.INK_2),
    )
    fig.update_layout(title="Weekly sales revenue (USD)", showlegend=False)
    fig.update_yaxes(tickprefix="$", tickformat="~s")
    T.chart(fig, table=wk[["week", "sales_revenue_usd", "units_sold"]])

with c2:
    fig = go.Figure()
    for i, (col, label) in enumerate(
        [("paid_spend_usd", "Paid media"), ("influencer_spend_usd", "Influencer")]
    ):
        fig.add_trace(go.Scatter(
            x=wk["week"], y=wk[col], mode="lines", name=label,
            line=dict(color=T.SERIES[i], width=2),
            hovertemplate=f"%{{x|%d %b %Y}}<br>{label} $%{{y:,.0f}}<extra></extra>",
        ))
    fig.update_layout(title="Weekly media spend by type (USD)")
    fig.update_yaxes(tickprefix="$", tickformat="~s")
    T.chart(fig, table=wk[["week", "paid_spend_usd", "influencer_spend_usd"]])

# --------------------------------------------------------------------------
# Market comparison
# --------------------------------------------------------------------------
st.markdown("## Market performance")

by_mkt = df.groupby(["week", "market"], as_index=False).agg(
    sales_revenue_usd=("sales_revenue_usd", "sum"),
    units_sold=("units_sold", "sum"),
    brand_equity_index=("brand_equity_index", "mean"),
)

c1, c2 = st.columns(2)

with c1:
    # Indexed to week 1 = 100 so three markets of very different absolute size
    # can share one axis honestly.
    base = by_mkt[by_mkt["week"] == by_mkt["week"].min()].set_index("market")["units_sold"]
    idx = by_mkt.copy()
    idx["indexed"] = idx.apply(lambda r: 100 * r["units_sold"] / base[r["market"]], axis=1)
    fig = go.Figure()
    for m in markets:
        sub = idx[idx["market"] == m]
        fig.add_trace(go.Scatter(
            x=sub["week"], y=sub["indexed"], mode="lines", name=m,
            line=dict(color=T.MARKET_COLOR.get(m, T.SERIES[0]), width=2),
            hovertemplate=f"%{{x|%d %b %Y}}<br>{m} %{{y:,.0f}}<extra></extra>",
        ))
    fig.add_hline(y=100, line=dict(color=T.BASELINE, width=1))
    fig.update_layout(title="Unit volume, indexed to week 1 = 100")
    T.chart(fig, table=idx[["week", "market", "units_sold", "indexed"]].round(1))

with c2:
    fig = go.Figure()
    for m in markets:
        sub = by_mkt[by_mkt["market"] == m]
        fig.add_trace(go.Scatter(
            x=sub["week"], y=sub["brand_equity_index"], mode="lines", name=m,
            line=dict(color=T.MARKET_COLOR.get(m, T.SERIES[0]), width=2),
            hovertemplate=f"%{{x|%d %b %Y}}<br>{m} %{{y:,.1f}}<extra></extra>",
        ))
    fig.update_layout(title="Brand equity index (modelled from monthly waves)")
    T.chart(fig, table=by_mkt[["week", "market", "brand_equity_index"]].round(2))

T.note(
    "Brand equity is measured monthly and interpolated to the weekly grain, so "
    "week-on-week movement here is a modelled estimate rather than a measurement. "
    "Read the direction of travel, not individual weeks."
)

# --------------------------------------------------------------------------
# Where the money went
# --------------------------------------------------------------------------
st.markdown("## Where the budget went, and what it returned")

roi = load("mmm_channel_roi").sort_values("marginal_roi", ascending=False)

c1, c2 = st.columns(2)

with c1:
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=roi["channel"], x=roi["share_of_spend"], orientation="h", name="Share of spend",
        marker=dict(color="#a9c8ee"),
        hovertemplate="%{y}<br>Share of working spend %{x:.1%}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=roi["channel"], x=roi["share_of_contribution"], orientation="h",
        name="Share of contribution", marker=dict(color=T.SERIES[0]),
        hovertemplate="%{y}<br>Share of contribution %{x:.1%}<extra></extra>",
    ))
    fig.update_layout(title="Share of spend vs share of modelled contribution",
                      barmode="group", bargap=0.28, bargroupgap=0.08)
    fig.update_xaxes(tickformat=".0%")
    fig.update_yaxes(autorange="reversed")
    T.chart(fig, height=380,
            table=roi[["channel", "share_of_spend", "share_of_contribution",
                       "efficiency_index"]].round(3))

with c2:
    vals = roi["efficiency_index"].tolist()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=roi["channel"], x=roi["efficiency_index"], orientation="h",
        marker=dict(color=T.emphasis_colors(vals, 1, 1)),
        text=[f"{v:.2f}" for v in vals], textposition="outside",
        textfont=dict(color=T.INK_2, size=11),
        hovertemplate="%{y}<br>Efficiency index %{x:.2f}<extra></extra>",
    ))
    fig.add_vline(x=1.0, line=dict(color=T.BASELINE, width=1))
    fig.add_annotation(x=1.0, y=-0.6, text="parity", showarrow=False,
                       font=dict(size=10, color=T.MUTED), yref="y")
    fig.update_layout(title="Efficiency index (contribution share ÷ spend share)",
                      showlegend=False)
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(range=[0, max(vals) * 1.22])
    T.chart(fig, height=380, table=roi[["channel", "efficiency_index", "roi",
                                        "marginal_roi"]].round(3))

T.note(
    "An efficiency index above 1.0 means the channel earns a larger share of "
    "modelled sales than it takes of working budget. Below 1.0 it is buying less "
    "than its share. This is the cleanest single read on where the money is "
    "misallocated — the Channels page turns it into a specific reallocation."
)

st.caption(
    f"Weeks {df['week'].min().date()} to {df['week'].max().date()} · "
    f"markets: {', '.join(markets)} · all figures USD at fixed period-average FX"
)
