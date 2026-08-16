"""Analytical layer.

WHAT IS NOT HERE, AND WHY.

There is no marketing mix model. Eight weeks cannot identify advertising
carryover: estimating a decay rate needs the response to a spend change observed
over many cycles, and with 8 points per market any adstock parameter would be
fitting noise. A mix model built on this data would produce confident channel ROIs
that are not recoverable from the evidence. Reporting them would be the single
most criticisable thing in this analysis, so they are not reported.

What 64 market-weeks DO support, and what is built instead:

  1. channel_efficiency   observed cost and return per channel, TV handled apart
  2. market_scorecard     8 subsidiaries benchmarked against their own peer set
  3. product_channel      which channel actually sells which device
  4. panel_model          sales on channel spend with market fixed effects,
                          reported WITH confidence intervals so the reader can see
                          how little 8 weeks can conclude
  5. influencer_scorecard efficiency against the whole roster (no follower tier --
                          the source's follower counts are too unstable per
                          creator to support one; see build_dims() in model.py)
  6. paid_vs_earned       PR and Website carry no spend and are the earned side
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import (
    DATA_PROCESSED,
    GROSS_MARGIN,
    NO_REVENUE_ATTRIBUTION,
    REVENUE_ATTRIBUTED,
)


def _div(a, b):
    """Safe divide. Accepts Series or scalars on either side.

    pd.isna() as a function rather than the .isna() method, because a scalar
    denominator (a column total, say) is a numpy float and has no method.
    """
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(pd.isna(a) | pd.isna(b) | (b == 0), np.nan, a / b)


def load_tables() -> dict[str, pd.DataFrame]:
    names = ["fact_base", "fact_channel", "fact_product", "fact_market_week",
             "fact_influencer", "fact_brand", "dim_influencer", "dim_market"]
    return {n: pd.read_parquet(DATA_PROCESSED / f"{n}.parquet") for n in names}


# --------------------------------------------------------------------------
# 1. Channel efficiency
# --------------------------------------------------------------------------
def channel_efficiency(chan: pd.DataFrame) -> pd.DataFrame:
    g = chan.groupby("channel", as_index=False).agg(
        spend_aed=("spend_aed", "sum"),
        sales_aed=("sales_aed", "sum"),
        conversions=("conversions", "sum"),
        impressions=("impressions", "sum"),
        clicks=("clicks", "sum"),
        tv_grp=("tv_grp", "sum"),
        media_type=("media_type", "first"),
        channel_role=("channel_role", "first"),
        revenue_attributed=("revenue_attributed", "first"),
    )
    g["roas"] = _div(g["sales_aed"], g["spend_aed"])
    g["roi_gross_margin"] = g["roas"] * GROSS_MARGIN
    g["cpa_aed"] = _div(g["spend_aed"], g["conversions"])
    g["cpm_aed"] = _div(g["spend_aed"], g["impressions"]) * 1000
    g["cpc_aed"] = _div(g["spend_aed"], g["clicks"])
    g["aov_aed"] = _div(g["sales_aed"], g["conversions"])
    g["cost_per_grp_aed"] = _div(g["spend_aed"], g["tv_grp"])

    g["share_of_spend"] = _div(g["spend_aed"], g["spend_aed"].sum())
    g["share_of_sales"] = _div(g["sales_aed"], g["sales_aed"].sum())

    # Efficiency index compares a channel's share of outcome to its share of
    # budget. It is only meaningful where BOTH sides exist, so channels without
    # revenue attribution are left null rather than scored as zero -- a channel
    # that cannot be measured is not the same as a channel that failed.
    g["efficiency_index"] = np.where(
        g["revenue_attributed"], _div(g["share_of_sales"], g["share_of_spend"]), np.nan
    )
    # Blank the cost ratios wherever they are not meaningful: no attribution, or
    # no media cost at all. A zero-spend channel technically has a CPA of 0.00,
    # which is arithmetically true and reads as a data error.
    meaningful = g["revenue_attributed"] & (g["spend_aed"].fillna(0) > 0)
    for c in ["roas", "roi_gross_margin", "cpa_aed", "cpm_aed", "cpc_aed"]:
        g[c] = np.where(meaningful, g[c], np.nan)

    # Order matters, and NaN must be caught explicitly: `NaN >= 1.0` is False, so
    # without the first two conditions a channel with no spend (Website) would
    # fall through to "below breakeven" -- scoring a channel that was never
    # measured as one that failed.
    g["payback"] = np.select(
        [
            ~g["revenue_attributed"],
            g["spend_aed"].fillna(0) == 0,
            g["roi_gross_margin"].isna(),
            g["roi_gross_margin"] >= 1.0,
        ],
        [
            "not measurable from this data",
            "no media cost — earned",
            "not measurable from this data",
            "profitable on margin",
        ],
        default="below breakeven on margin",
    )
    return g.sort_values("spend_aed", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# 2. Market scorecard
# --------------------------------------------------------------------------
def market_scorecard(spine: pd.DataFrame) -> pd.DataFrame:
    """Benchmark each subsidiary against the peer set.

    With 8 comparable markets running the same 8 channels in the same 8 weeks,
    cross-sectional comparison is the strongest evidence available -- far stronger
    than a trend read off 8 weekly points.
    """
    g = spine.groupby("market", as_index=False).agg(
        spend_aed=("spend_aed", "sum"),
        sales_aed=("sales_aed", "sum"),
        conversions=("conversions", "sum"),
        paid_spend_aed=("paid_spend_aed", "sum"),
        earned_sales_aed=("earned_sales_aed", "sum"),
        tv_spend_aed=("tv_spend_aed", "sum"),
        brand_awareness=("brand_awareness", "mean"),
        purchase_intent=("purchase_intent", "mean"),
        share_of_voice=("share_of_voice", "mean"),
        competitor_sov=("competitor_sov", "mean"),
        sentiment=("sentiment", "mean"),
        sessions=("sessions", "sum"),
    )
    g["mer"] = _div(g["sales_aed"], g["spend_aed"])
    g["cpa_aed"] = _div(g["spend_aed"], g["conversions"])
    g["aov_aed"] = _div(g["sales_aed"], g["conversions"])
    g["earned_sales_share"] = _div(g["earned_sales_aed"], g["sales_aed"])
    g["tv_spend_share"] = _div(g["tv_spend_aed"], g["spend_aed"])
    g["sov_gap"] = g["share_of_voice"] - g["competitor_sov"]
    g["spend_share_of_group"] = _div(g["spend_aed"], g["spend_aed"].sum())
    g["sales_share_of_group"] = _div(g["sales_aed"], g["sales_aed"].sum())

    # Rank against peers, and express the gap in money so it reads as a decision.
    med_mer = g["mer"].median()
    g["mer_vs_peer_median"] = _div(g["mer"], med_mer) - 1
    g["sales_at_peer_median_mer"] = g["spend_aed"] * med_mer
    g["sales_gap_vs_peer_aed"] = g["sales_aed"] - g["sales_at_peer_median_mer"]
    g["mer_rank"] = g["mer"].rank(ascending=False).astype(int)
    # Quartiles need >=4 markets with distinct MER to mean anything; qcut raises
    # on fewer unique values (e.g. a slice that has already been filtered to one
    # or two markets), so fall back to "n/a" rather than crash or fabricate a tier.
    if g["market"].nunique() >= 4 and g["mer"].nunique() >= 4:
        # duplicates="drop" is not combined with fixed `labels`: if ties still
        # collapse the bin count below 4, qcut would raise on the label-length
        # mismatch instead of the edge-uniqueness error this branch exists to avoid.
        try:
            g["quartile"] = pd.qcut(
                g["mer"], 4, labels=["Bottom", "Third", "Second", "Top"]).astype(str)
        except ValueError:
            g["quartile"] = "n/a (too few markets in view)"
    else:
        g["quartile"] = "n/a (too few markets in view)"
    return g.sort_values("mer", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# 3. Product x channel
# --------------------------------------------------------------------------
def product_channel(base: pd.DataFrame) -> pd.DataFrame:
    g = base.groupby(["product", "channel"], as_index=False).agg(
        spend_aed=("spend_aed", "sum"),
        sales_aed=("sales_aed", "sum"),
        conversions=("conversions", "sum"),
    )
    g["roas"] = _div(g["sales_aed"], g["spend_aed"])
    g["cpa_aed"] = _div(g["spend_aed"], g["conversions"])
    g = g[~g["channel"].isin(NO_REVENUE_ATTRIBUTION)]

    # Index each cell against the product's own average, so the read is "which
    # channel over-performs FOR THIS DEVICE" rather than which product sells most.
    prod_roas = g.groupby("product")["roas"].transform("mean")
    g["roas_index_vs_product"] = _div(g["roas"], prod_roas)
    return g.reset_index(drop=True)


def product_summary(prod: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    g = prod.groupby("product", as_index=False).agg(
        spend_aed=("spend_aed", "sum"),
        sales_aed=("sales_aed", "sum"),
        conversions=("conversions", "sum"),
    )
    g["roas"] = _div(g["sales_aed"], g["spend_aed"])
    g["aov_aed"] = _div(g["sales_aed"], g["conversions"])
    g["cpa_aed"] = _div(g["spend_aed"], g["conversions"])
    g["share_of_spend"] = _div(g["spend_aed"], g["spend_aed"].sum())
    g["share_of_sales"] = _div(g["sales_aed"], g["sales_aed"].sum())
    g["support_index"] = _div(g["share_of_spend"], g["share_of_sales"])
    return g.sort_values("sales_aed", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# 4. Panel model -- with the uncertainty left visible
# --------------------------------------------------------------------------
def panel_model(chan: pd.DataFrame) -> pd.DataFrame:
    """Weekly market sales on channel spend, with market fixed effects.

    This is NOT a marketing mix model: no carryover, no saturation, no claim of
    causal contribution. It asks a narrower question that 64 observations can
    speak to -- when a market spends more on channel X in a week, do its sales
    that week differ?

    Coefficients come with 95% confidence intervals and cluster-robust standard
    errors. The intervals are the point: on 8 weeks most channels will not be
    distinguishable from zero, and saying so is more useful than a precise-looking
    number that would not survive another 8 weeks of data.
    """
    import statsmodels.api as sm

    piv = (chan.pivot_table(index=["week", "market"], columns="channel",
                            values="spend_aed", aggfunc="sum")
           .fillna(0.0))
    sales = (chan.groupby(["week", "market"])["sales_aed"].sum())
    df = piv.join(sales.rename("sales_aed")).reset_index()

    spend_cols = [c for c in piv.columns if c not in NO_REVENUE_ATTRIBUTION
                  or c == "TV"]
    spend_cols = [c for c in spend_cols if df[c].std() > 0]

    X = df[spend_cols].copy()
    dummies = pd.get_dummies(df["market"], prefix="mkt", drop_first=True, dtype=float)
    X = pd.concat([X, dummies], axis=1)
    X = sm.add_constant(X)
    y = df["sales_aed"]

    fit = sm.OLS(y, X).fit(cov_type="cluster",
                           cov_kwds={"groups": df["market"]})
    ci = fit.conf_int(alpha=0.05)

    rows = []
    for c in spend_cols:
        rows.append({
            "channel": c,
            "coefficient": fit.params[c],
            "std_error": fit.bse[c],
            "p_value": fit.pvalues[c],
            "ci_low": ci.loc[c, 0],
            "ci_high": ci.loc[c, 1],
            "significant_5pct": bool(fit.pvalues[c] < 0.05),
            "interpretation": (
                f"1 AED more on {c} associates with "
                f"{fit.params[c]:+,.2f} AED of weekly sales"
            ),
        })
    out = pd.DataFrame(rows).sort_values("coefficient", ascending=False)
    out["r_squared"] = fit.rsquared
    out["n_observations"] = int(fit.nobs)
    out["model_note"] = (
        "Association only. No carryover or saturation modelled; 8 weeks cannot "
        "identify either. Read the confidence interval, not the point estimate."
    )
    return out.reset_index(drop=True)


# --------------------------------------------------------------------------
# 5. Relationships between metrics
# --------------------------------------------------------------------------
CORR_METRICS = [
    "spend_aed", "sales_aed", "conversions", "aov_aed", "cpa_aed",
    "brand_awareness", "purchase_intent", "sentiment", "share_of_voice",
    "sessions",
]


def metric_correlations(spine: pd.DataFrame,
                        metrics: list[str] | None = None) -> pd.DataFrame:
    """Pairwise correlation across the 64 market-weeks, in long form.

    A caveat travels with this: pooling all 64 rows mixes BETWEEN-market variation
    (a large subsidiary always spends and sells more) with WITHIN-market variation
    (a market spending more in a given week). The first inflates any spend-to-sales
    correlation for reasons of size alone, so a strong coefficient here is a prompt
    to look, not evidence of an effect. The panel model, which carries market fixed
    effects, is the one that removes size.
    """
    metrics = [m for m in (metrics or CORR_METRICS) if m in spine.columns]
    sub = spine[metrics].astype(float)
    c = sub.corr(method="pearson")

    rows = []
    for a in metrics:
        for b in metrics:
            rows.append({"metric_a": a, "metric_b": b,
                         "correlation": float(c.loc[a, b])})
    out = pd.DataFrame(rows)
    out["n_observations"] = len(sub)
    out["note"] = ("Pooled across markets; mixes between-market size differences "
                   "with within-market movement. Screening only.")
    return out


# --------------------------------------------------------------------------
# 6. Influencer scorecard
# --------------------------------------------------------------------------
def influencer_scorecard(infl: pd.DataFrame, dim: pd.DataFrame) -> pd.DataFrame:
    # No follower-tier comparison here -- see build_dims() in model.py for why:
    # the source's `followers` value is not stable per influencer (the same
    # creator's row-level value swings by hundreds of thousands within a
    # single week), so it cannot support a reliable size-based peer group.
    # Engagement is judged against the whole roster instead; `followers` here
    # is the median of a noisy field, kept as a descriptive best estimate, not
    # a classification input. `followers_unstable` (from dim_influencer) says
    # so explicitly rather than silently.
    g = infl.groupby(["influencer", "market"], as_index=False).agg(
        followers=("followers", "median"),
        engagement_rate=("engagement_rate", "mean"),
        spend_aed=("spend_aed", "sum"),
        conversions=("conversions", "sum"),
        sales_aed=("sales_aed", "sum"),
        weeks_active=("week", "nunique"),
        products=("product", "nunique"),
    )
    g = g.merge(dim[["influencer", "followers_unstable"]], on="influencer", how="left")
    g["cpa_aed"] = _div(g["spend_aed"], g["conversions"])
    g["roas"] = _div(g["sales_aed"], g["spend_aed"])
    g["roi_gross_margin"] = g["roas"] * GROSS_MARGIN
    g["aov_aed"] = _div(g["sales_aed"], g["conversions"])
    g["cost_per_follower"] = _div(g["spend_aed"], g["followers"])

    roster_median_er = g["engagement_rate"].median()
    g["er_vs_roster"] = _div(g["engagement_rate"], roster_median_er) - 1

    med_cpa = g["cpa_aed"].median()
    med_roas = g["roas"].median()
    g["cpa_vs_roster"] = _div(g["cpa_aed"], med_cpa) - 1

    g["flag"] = np.select(
        [
            (g["er_vs_roster"] < -0.25) & (g["cpa_aed"] > med_cpa),
            g["cpa_aed"] > med_cpa * 1.5,
            (g["roas"] > med_roas * 1.25) & (g["cpa_aed"] < med_cpa),
        ],
        ["Underperforming — weak engagement and costly",
         "Costly — CPA well above roster",
         "Strong — scale candidate"],
        default="On par",
    )
    g["recommended_action"] = np.select(
        [
            g["flag"].str.startswith("Underperforming"),
            g["flag"].str.startswith("Costly"),
            g["flag"].str.startswith("Strong"),
        ],
        ["Renegotiate to performance-weighted fee, or exit at term",
         "Renegotiate rate; retest at lower fee before renewing",
         "Increase budget and brief across more products"],
        default="Maintain; review next cycle",
    )

    # Money left on the table against roster-median efficiency.
    g["spend_at_median_cpa"] = g["conversions"] * med_cpa
    g["excess_spend_aed"] = (g["spend_aed"] - g["spend_at_median_cpa"]).clip(lower=0)
    return g.sort_values("cpa_aed").reset_index(drop=True)


# --------------------------------------------------------------------------
# 7. Paid vs earned
# --------------------------------------------------------------------------
def paid_vs_earned(chan: pd.DataFrame) -> pd.DataFrame:
    g = chan.groupby("media_type", as_index=False).agg(
        spend_aed=("spend_aed", "sum"),
        sales_aed=("sales_aed", "sum"),
        conversions=("conversions", "sum"),
    )
    g["share_of_spend"] = _div(g["spend_aed"], g["spend_aed"].sum())
    g["share_of_sales"] = _div(g["sales_aed"], g["sales_aed"].sum())
    g["aov_aed"] = _div(g["sales_aed"], g["conversions"])
    g["roas"] = np.where(g["spend_aed"] > 0, _div(g["sales_aed"], g["spend_aed"]), np.nan)
    return g.sort_values("sales_aed", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# 8. Reallocation -- directional, explicitly not an optimum
# --------------------------------------------------------------------------
def reallocation(eff: pd.DataFrame, move_share: float = 0.15) -> pd.DataFrame:
    """Shift budget from the weakest measurable channels to the strongest.

    Without a response curve there is no way to estimate diminishing returns, so
    this cannot be an optimisation and is not presented as one. It is a
    test-and-learn direction: move a bounded share, measure, repeat. The projected
    impact assumes the receiving channel holds its observed efficiency on
    incremental budget, which is the assumption most likely to be wrong.
    """
    m = eff[eff["revenue_attributed"] & eff["roas"].notna()].copy()
    if m.empty:
        return m
    med = m["roas"].median()
    m["action"] = np.select(
        [m["roas"] >= med * 1.2, m["roas"] <= med * 0.8],
        ["INCREASE", "REDUCE"], default="HOLD",
    )
    donors = m[m["action"] == "REDUCE"]
    receivers = m[m["action"] == "INCREASE"]
    pot = float((donors["spend_aed"] * move_share).sum())

    m["spend_change_aed"] = 0.0
    if not donors.empty:
        m.loc[donors.index, "spend_change_aed"] = -(donors["spend_aed"] * move_share)
    if not receivers.empty and pot > 0:
        w = receivers["roas"] / receivers["roas"].sum()
        m.loc[receivers.index, "spend_change_aed"] = pot * w

    m["sales_impact_aed"] = m["spend_change_aed"] * m["roas"]
    m["margin_impact_aed"] = m["sales_impact_aed"] * GROSS_MARGIN
    return m.sort_values("roas", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
if __name__ == "__main__":
    t = load_tables()
    eff = channel_efficiency(t["fact_channel"])
    print("=" * 78, "\nCHANNEL EFFICIENCY\n", "=" * 78, sep="")
    print(eff[["channel", "spend_aed", "share_of_spend", "sales_aed", "roas",
               "roi_gross_margin", "efficiency_index", "payback"]]
          .round(3).to_string(index=False))

    print("\n" + "=" * 78, "\nMARKET SCORECARD\n", "=" * 78, sep="")
    ms = market_scorecard(t["fact_market_week"])
    print(ms[["market", "mer_rank", "spend_aed", "sales_aed", "mer",
              "mer_vs_peer_median", "sales_gap_vs_peer_aed", "quartile"]]
          .round(2).to_string(index=False))

    print("\n" + "=" * 78, "\nPANEL MODEL\n", "=" * 78, sep="")
    pm = panel_model(t["fact_channel"])
    print(pm[["channel", "coefficient", "ci_low", "ci_high", "p_value",
              "significant_5pct"]].round(3).to_string(index=False))
    print(f"\nR2 {pm['r_squared'].iloc[0]:.3f} on {pm['n_observations'].iloc[0]} obs")

    print("\n" + "=" * 78, "\nPRODUCTS\n", "=" * 78, sep="")
    print(product_summary(product_channel(t["fact_base"]), t["fact_base"])
          .round(3).to_string(index=False))

    print("\n" + "=" * 78, "\nINFLUENCERS (worst 6 by CPA)\n", "=" * 78, sep="")
    sc = influencer_scorecard(t["fact_influencer"], t["dim_influencer"])
    print(sc.tail(6)[["influencer", "followers", "followers_unstable",
                      "engagement_rate", "er_vs_roster", "spend_aed", "conversions",
                      "cpa_aed", "flag"]]
          .round(3).to_string(index=False))

    print("\n" + "=" * 78, "\nPAID VS EARNED\n", "=" * 78, sep="")
    print(paid_vs_earned(t["fact_channel"]).round(3).to_string(index=False))
