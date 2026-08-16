"""Build the analytical model from the cleaned source.

The source is one long table at week x market x channel x product. This reshapes
it into the facts and dimensions everything downstream reads:

    fact_base            week x market x channel x product   (the cleaned grain)
    fact_channel         week x market x channel
    fact_product         week x market x product
    fact_market_week     week x market                       <- the spine
    fact_influencer      influencer x week x market x product
    fact_brand           week x market   (brand metrics, averaged -- indicative)
    dim_*                lookups for the star schema

KPI definitions live here and nowhere else. The site and the AI assistant's
system prompt both restate these, so a number cannot disagree between them.
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from common import (
    CHANNEL_ROLE,
    CURRENCY,
    DATA_PBI,
    DATA_PROCESSED,
    DUCKDB_PATH,
    MARKET_LABEL,
    MEDIA_TYPE,
    NO_REVENUE_ATTRIBUTION,
    N_WEEKS,
    format_export_df,
)
from ingest import DQ, load


def _div(a, b):
    """Safe divide -- returns NaN rather than inf where the denominator is zero."""
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    return np.where((b == 0) | b.isna() | a.isna(), np.nan, a / b)


# --------------------------------------------------------------------------
# Facts
# --------------------------------------------------------------------------
def build_base(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["media_type"] = out["channel"].map(MEDIA_TYPE)
    out["channel_role"] = out["channel"].map(CHANNEL_ROLE)
    out["revenue_attributed"] = ~out["channel"].isin(NO_REVENUE_ATTRIBUTION)

    out["cpm_aed"] = _div(out["spend_aed"], out["impressions"]) * 1000
    out["cpc_aed"] = _div(out["spend_aed"], out["clicks"])
    out["ctr"] = _div(out["clicks"], out["impressions"])
    out["cpa_aed"] = _div(out["spend_aed"], out["conversions"])
    out["roas"] = _div(out["sales_aed"], out["spend_aed"])
    out["aov_aed"] = _div(out["sales_aed"], out["conversions"])
    out["cost_per_grp_aed"] = _div(out["spend_aed"], out["tv_grp"])
    return out


def build_channel_fact(base: pd.DataFrame) -> pd.DataFrame:
    g = base.groupby(["week", "market", "channel"], as_index=False).agg(
        spend_aed=("spend_aed", "sum"),
        impressions=("impressions", "sum"),
        clicks=("clicks", "sum"),
        conversions=("conversions", "sum"),
        sales_aed=("sales_aed", "sum"),
        tv_grp=("tv_grp", "sum"),
        engagement_rate=("engagement_rate", "mean"),
        sessions=("sessions", "sum"),
        pr_mentions=("pr_mentions", "sum"),
        pr_share_of_voice=("pr_share_of_voice", "mean"),
        products_active=("product", "nunique"),
    )
    # A summed column of all-NaN comes back as 0; restore the distinction between
    # "zero" and "this channel does not carry this measure".
    for col, src in [("impressions", "impressions"), ("clicks", "clicks"),
                     ("sales_aed", "sales_aed"), ("conversions", "conversions"),
                     ("tv_grp", "tv_grp"), ("sessions", "sessions"),
                     ("pr_mentions", "pr_mentions"), ("spend_aed", "spend_aed")]:
        present = base.groupby(["week", "market", "channel"])[src].apply(
            lambda s: s.notna().any()
        ).rename("has").reset_index()
        g = g.merge(present, on=["week", "market", "channel"], how="left")
        g.loc[~g["has"], col] = np.nan
        g = g.drop(columns=["has"])

    g["media_type"] = g["channel"].map(MEDIA_TYPE)
    g["channel_role"] = g["channel"].map(CHANNEL_ROLE)
    g["revenue_attributed"] = ~g["channel"].isin(NO_REVENUE_ATTRIBUTION)

    g["cpm_aed"] = _div(g["spend_aed"], g["impressions"]) * 1000
    g["cpc_aed"] = _div(g["spend_aed"], g["clicks"])
    g["ctr"] = _div(g["clicks"], g["impressions"])
    g["cvr"] = _div(g["conversions"], g["clicks"])
    g["cpa_aed"] = _div(g["spend_aed"], g["conversions"])
    g["roas"] = _div(g["sales_aed"], g["spend_aed"])
    g["aov_aed"] = _div(g["sales_aed"], g["conversions"])
    g["cost_per_grp_aed"] = _div(g["spend_aed"], g["tv_grp"])
    return g


def build_product_fact(base: pd.DataFrame) -> pd.DataFrame:
    g = base.groupby(["week", "market", "product"], as_index=False).agg(
        spend_aed=("spend_aed", "sum"),
        conversions=("conversions", "sum"),
        sales_aed=("sales_aed", "sum"),
        impressions=("impressions", "sum"),
        channels_active=("channel", "nunique"),
    )
    g["roas"] = _div(g["sales_aed"], g["spend_aed"])
    g["aov_aed"] = _div(g["sales_aed"], g["conversions"])
    g["cpa_aed"] = _div(g["spend_aed"], g["conversions"])
    return g


def build_brand_fact(base: pd.DataFrame) -> pd.DataFrame:
    """Brand metrics averaged to market-week.

    They arrive per row and vary by up to ~39 points inside one market-week, so
    they cannot be a market-level tracker. Averaging across the ~37 rows in each
    market-week is the best available estimate; the spread is carried alongside so
    the uncertainty travels with the number instead of being quietly dropped.
    """
    g = base.groupby(["week", "market"], as_index=False).agg(
        brand_awareness=("brand_awareness", "mean"),
        brand_awareness_sd=("brand_awareness", "std"),
        purchase_intent=("purchase_intent", "mean"),
        purchase_intent_sd=("purchase_intent", "std"),
        competitor_sov=("competitor_sov", "mean"),
        sentiment=("sentiment", "mean"),
        sentiment_sd=("sentiment", "std"),
        n_observations=("brand_awareness", "size"),
    )
    g["is_indicative"] = True
    g["intent_to_awareness"] = _div(g["purchase_intent"], g["brand_awareness"])
    return g


def build_influencer_fact(base: pd.DataFrame) -> pd.DataFrame:
    inf = base[base["channel"] == "Influencer"].copy()
    return inf[["week", "market", "product", "influencer", "followers",
                "engagement_rate", "spend_aed", "conversions", "sales_aed",
                "cpa_aed", "roas"]]


def build_spine(base: pd.DataFrame, chan: pd.DataFrame,
                brand: pd.DataFrame) -> pd.DataFrame:
    """One row per week x market -- the table most questions start from."""
    keys = ["week", "market"]

    total = base.groupby(keys, as_index=False).agg(
        spend_aed=("spend_aed", "sum"),
        sales_aed=("sales_aed", "sum"),
        conversions=("conversions", "sum"),
        impressions=("impressions", "sum"),
        clicks=("clicks", "sum"),
    )

    paid = (chan[chan["media_type"] == "paid"].groupby(keys, as_index=False)
            .agg(paid_spend_aed=("spend_aed", "sum"),
                 paid_sales_aed=("sales_aed", "sum"),
                 paid_conversions=("conversions", "sum")))
    earned = (chan[chan["media_type"] == "earned"].groupby(keys, as_index=False)
              .agg(earned_sales_aed=("sales_aed", "sum"),
                   earned_conversions=("conversions", "sum")))

    def channel_col(name: str, col: str, out: str) -> pd.DataFrame:
        return (chan[chan["channel"] == name].groupby(keys, as_index=False)
                .agg(**{out: (col, "sum")}))

    tv_spend = channel_col("TV", "spend_aed", "tv_spend_aed")
    tv_grp = channel_col("TV", "tv_grp", "tv_grp")
    web_sessions = channel_col("Website", "sessions", "sessions")
    web_sales = channel_col("Website", "sales_aed", "website_sales_aed")
    pr_mentions = channel_col("PR", "pr_mentions", "pr_mentions")
    pr_sov = (chan[chan["channel"] == "PR"].groupby(keys, as_index=False)
              .agg(share_of_voice=("pr_share_of_voice", "mean")))
    infl_spend = channel_col("Influencer", "spend_aed", "influencer_spend_aed")

    web_quality = (chan[chan["channel"] == "Website"]
                   .groupby(keys, as_index=False)
                   .agg(website_conversions=("conversions", "sum")))

    spine = total
    for frame in [paid, earned, tv_spend, tv_grp, web_sessions, web_sales,
                  pr_mentions, pr_sov, infl_spend, web_quality, brand]:
        spine = spine.merge(frame, on=keys, how="left")

    # ---- derived KPIs (the semantic layer) ------------------------------
    spine["mer"] = _div(spine["sales_aed"], spine["spend_aed"])
    spine["paid_roas"] = _div(spine["paid_sales_aed"], spine["paid_spend_aed"])
    spine["cpa_aed"] = _div(spine["spend_aed"], spine["conversions"])
    spine["aov_aed"] = _div(spine["sales_aed"], spine["conversions"])
    spine["cpm_aed"] = _div(spine["spend_aed"], spine["impressions"]) * 1000
    spine["cpc_aed"] = _div(spine["spend_aed"], spine["clicks"])
    spine["earned_sales_share"] = _div(spine["earned_sales_aed"], spine["sales_aed"])
    spine["tv_spend_share"] = _div(spine["tv_spend_aed"], spine["spend_aed"])
    spine["cost_per_grp_aed"] = _div(spine["tv_spend_aed"], spine["tv_grp"])
    spine["sov_gap"] = spine["share_of_voice"] - spine["competitor_sov"]
    spine["web_conversion_rate"] = _div(spine["website_conversions"], spine["sessions"])

    spine = spine.sort_values(["market", "week"]).reset_index(drop=True)

    # Week-on-week deltas. With 8 weeks these are movements, not trends -- the
    # naming keeps that honest.
    for c in ["sales_aed", "spend_aed", "conversions", "brand_awareness",
              "purchase_intent", "sentiment", "share_of_voice", "mer"]:
        spine[f"{c}_wow"] = spine.groupby("market")[c].pct_change()
    return spine


# --------------------------------------------------------------------------
# Dimensions
# --------------------------------------------------------------------------
def build_dims(base: pd.DataFrame, chan: pd.DataFrame) -> dict[str, pd.DataFrame]:
    dim_week = pd.DataFrame({"week": sorted(base["week"].dropna().unique())})
    dim_week["week_label"] = "Wk " + dim_week["week"].astype(str)

    dim_market = pd.DataFrame({"market": sorted(base["market"].unique())})
    dim_market["market_label"] = dim_market["market"].map(MARKET_LABEL).fillna("")
    dim_market["label_confirmed"] = False

    dim_channel = pd.DataFrame({"channel": sorted(base["channel"].unique())})
    dim_channel["media_type"] = dim_channel["channel"].map(MEDIA_TYPE)
    dim_channel["channel_role"] = dim_channel["channel"].map(CHANNEL_ROLE)
    dim_channel["revenue_attributed"] = ~dim_channel["channel"].isin(
        NO_REVENUE_ATTRIBUTION)

    dim_product = pd.DataFrame({"product": sorted(base["product"].unique())})
    dim_product["family"] = dim_product["product"].str.extract(
        r"Galaxy (Z Fold|Z Flip|S\d|Tab|Watch|Buds)")[0].fillna("Other")

    # No follower tier here. The source's `followers` value is not stable per
    # influencer -- the same creator's row-level value swings by up to ~780k
    # (e.g. 860k on one product in a week, 320k on a different product the
    # SAME week), which an audience size does not do. Taking the max of that
    # noise (the previous approach) pushed every influencer into "Mega" by
    # construction; the median or mean just relabels everyone into a
    # different single bucket instead -- the field can't support a tier split
    # under any aggregation. `followers_unstable` flags the instability
    # itself as a data-quality fact rather than asserting a tier from it.
    inf = base[base["channel"] == "Influencer"]
    dim_influencer = (inf.groupby(["influencer", "market"], as_index=False)
                      ["followers"].agg(followers_median="median", followers_min="min",
                                        followers_max="max")
                      .sort_values("followers_median", ascending=False))
    spread = dim_influencer["followers_max"] - dim_influencer["followers_min"]
    dim_influencer["followers_unstable"] = spread > dim_influencer["followers_median"]

    return {"dim_week": dim_week, "dim_market": dim_market,
            "dim_channel": dim_channel, "dim_product": dim_product,
            "dim_influencer": dim_influencer}


# --------------------------------------------------------------------------
def build_all() -> dict[str, pd.DataFrame]:
    df = load()
    base = build_base(df)
    chan = build_channel_fact(base)
    prod = build_product_fact(base)
    brand = build_brand_fact(base)
    infl = build_influencer_fact(base)
    spine = build_spine(base, chan, brand)
    dims = build_dims(base, chan)

    # Record the constraint that shapes the whole analysis.
    tv = chan[chan["channel"] == "TV"]
    tv_share = tv["spend_aed"].sum() / chan["spend_aed"].sum()
    DQ.log(
        "Attribution",
        f"TV carries {tv_share:.0%} of all media spend but no attributed sales "
        f"or conversions",
        int(len(tv)),
        "TV excluded from every ROI/ROAS/CPA ranking; evaluated on cost per GRP "
        "and brand association instead",
    )

    return {
        "fact_base": base, "fact_channel": chan, "fact_product": prod,
        "fact_market_week": spine, "fact_influencer": infl, "fact_brand": brand,
        "data_quality_log": DQ.to_frame(), **dims,
    }


def persist(tables: dict[str, pd.DataFrame]) -> None:
    for name, t in tables.items():
        t.to_parquet(DATA_PROCESSED / f"{name}.parquet", index=False)

    if DUCKDB_PATH.exists():
        DUCKDB_PATH.unlink()
    con = duckdb.connect(str(DUCKDB_PATH))
    for name, t in tables.items():
        con.register("tmp", t)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp")
        con.unregister("tmp")
    con.close()

    for name in ["fact_base", "fact_market_week", "fact_channel", "fact_product",
                 "fact_influencer", "fact_brand", "dim_week", "dim_market",
                 "dim_channel", "dim_product", "dim_influencer"]:
        format_export_df(tables[name]).to_csv(DATA_PBI / f"{name}.csv", index=False)


def main() -> None:
    tables = build_all()
    persist(tables)
    print(f"Built {len(tables)} tables ({CURRENCY}) -> {DATA_PROCESSED}\n")
    for name, t in tables.items():
        print(f"  {name:22s} {len(t):6,d} rows x {len(t.columns):3d} cols")
    print("\n--- Data quality log ---")
    print(tables["data_quality_log"].to_string(index=False))


if __name__ == "__main__":
    main()
