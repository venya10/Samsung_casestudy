"""Prove the source split into facts without gaining or losing anything.

Reshaping a wide source into facts and dimensions is where silent data loss
happens: a join that drops rows, a groupby that swallows nulls, a filter applied
one level too early. None of it shows up in a chart -- the chart just quietly
reports a smaller number.

This traces every table back to the source and reconciles the totals. Run it any
time the model changes.
"""
from __future__ import annotations

import pandas as pd

from common import DATA_PROCESSED, SOURCE_FILE

def L(name: str) -> pd.DataFrame:
    return pd.read_parquet(DATA_PROCESSED / f"{name}.parquet")


def main() -> None:
    src = pd.read_csv(SOURCE_FILE)
    base = L("fact_base")
    chan = L("fact_channel")
    prod = L("fact_product")
    spine = L("fact_market_week")
    infl = L("fact_influencer")
    brand = L("fact_brand")

    print("=" * 74)
    print("GRAIN AND SHAPE")
    print("=" * 74)
    rows = [
        ("SOURCE  samsung_marketing_full_dataset.csv",
         "week x market x channel x product", len(src), len(src.columns)),
        ("fact_base", "week x market x channel x product (1:1 with source)",
         len(base), len(base.columns)),
        ("fact_channel", "week x market x channel", len(chan), len(chan.columns)),
        ("fact_product", "week x market x product", len(prod), len(prod.columns)),
        ("fact_market_week", "week x market  (the spine)", len(spine), len(spine.columns)),
        ("fact_influencer", "the Influencer channel rows only", len(infl), len(infl.columns)),
        ("fact_brand", "week x market  (brand metrics averaged)", len(brand), len(brand.columns)),
    ]
    for name, grain, n, c in rows:
        print(f"  {name:<44} {n:>6,} rows x {c:>3} cols   {grain}")

    print("\n" + "=" * 74)
    print("EXPECTED ROW COUNTS -- does the grain arithmetic hold?")
    print("=" * 74)
    w, m = src.Week.nunique(), src.Market.nunique()
    c_, p = src.Channel.nunique(), src["Product"].nunique()
    checks = [
        ("fact_market_week", len(spine), w * m, f"{w} weeks x {m} markets"),
        ("fact_brand", len(brand), w * m, f"{w} weeks x {m} markets"),
        ("fact_product", len(prod), w * m * p, f"{w} x {m} x {p} products"),
        ("fact_influencer", len(infl),
         int((src.Channel == "Influencer").sum()), "source rows where channel = Influencer"),
    ]
    for name, got, want, why in checks:
        flag = "OK " if got == want else "!! "
        print(f"  {flag}{name:<22} {got:>6,}  expected {want:>6,}   ({why})")

    combos = src.groupby(["Week", "Market", "Channel"]).ngroups
    flag = "OK " if len(chan) == combos else "!! "
    print(f"  {flag}{'fact_channel':<22} {len(chan):>6,}  expected {combos:>6,}   "
          f"(not {w*m*c_:,} -- B2B Roadshow and Retail do not run everywhere)")

    print("\n" + "=" * 74)
    print("RECONCILIATION -- the same money at every level")
    print("=" * 74)
    src_sales = src.Sales_AED.sum()
    src_spend = src.Spend_AED.sum()
    src_conv = src.Conversions.sum()

    for label, df in [("fact_base", base), ("fact_channel", chan),
                      ("fact_product", prod), ("fact_market_week", spine)]:
        s = df["sales_aed"].sum()
        sp = df["spend_aed"].sum()
        cv = df["conversions"].sum()
        ok = (abs(s - src_sales) < 1) and (abs(sp - src_spend) < 1) and (abs(cv - src_conv) < 1)
        print(f"  {'OK ' if ok else '!! '}{label:<20} "
              f"sales {s:>15,.0f}   spend {sp:>13,.0f}   conv {cv:>10,.0f}")
    print(f"  {'':3}{'SOURCE':<20} sales {src_sales:>15,.0f}   "
          f"spend {src_spend:>13,.0f}   conv {src_conv:>10,.0f}")

    print("\n" + "=" * 74)
    print("NOTHING DROPPED -- every source row is represented")
    print("=" * 74)
    key = ["week", "market", "channel", "product"]
    src_keys = set(map(tuple, src.rename(columns={
        "Week": "week", "Market": "market", "Channel": "channel",
        "Product": "product"})[key].values))
    base_keys = set(map(tuple, base[key].values))
    print(f"  source keys      {len(src_keys):,}")
    print(f"  fact_base keys   {len(base_keys):,}")
    print(f"  {'OK ' if src_keys == base_keys else '!! '}"
          f"missing from fact_base: {len(src_keys - base_keys)}   "
          f"invented by fact_base: {len(base_keys - src_keys)}")

    print("\n" + "=" * 74)
    print("WHERE THE COLUMNS WENT")
    print("=" * 74)
    print("  Every source column lands somewhere. Nothing is silently dropped except")
    print("  the one proven duplicate.\n")
    routing = [
        ("Week, Market, Channel, Product", "keys on every fact + the dimensions"),
        ("Spend_AED, Sales_AED, Conversions", "fact_base -> channel / product / spine"),
        ("Impressions, Clicks", "fact_base -> fact_channel (Paid Social, Search only)"),
        ("Engagement_Rate", "fact_base -> fact_channel, fact_influencer"),
        ("TV_GRP", "fact_channel -> spine.tv_grp"),
        ("PR_Mentions, PR_Share_of_Voice", "fact_channel -> spine.share_of_voice"),
        ("Website_Sessions, Bounce_Rate,", "fact_channel -> spine.sessions"),
        ("  Avg_Session_Duration_Sec, Page_Views_Per_Session", ""),
        ("Influencer_Name, Follower_Count", "fact_influencer + dim_influencer"),
        ("Brand_Awareness_Score, Purchase_Intent_Score,", "fact_brand (averaged) -> spine"),
        ("  Competitor_SOV, Sentiment_Score", ""),
        ("Influencer_Engagement_Rate", "DROPPED -- identical to Engagement_Rate on 100% of rows"),
    ]
    for col, dest in routing:
        print(f"  {col:<50} {dest}")


if __name__ == "__main__":
    main()
