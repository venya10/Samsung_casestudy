"""Assert that the seven planted signals survive cleaning and modelling.

Because the synthetic data has known ground truth, we can check that the
pipeline actually recovers what was planted rather than trusting that it does.
When the real Samsung files replace the synthetic ones this script stops being a
correctness test and becomes a smoke test -- it will fail loudly, which is the
correct behaviour, and the thresholds should then be removed or re-based.
"""
from __future__ import annotations

import pandas as pd

from common import DATA_PROCESSED, EVENTS, WEEKS

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((PASS if ok else FAIL, name, detail))


def wk(t: int) -> pd.Timestamp:
    return WEEKS[t]


def window(df: pd.DataFrame, lo: int, hi: int, col: str = "week") -> pd.DataFrame:
    return df[(df[col] >= wk(lo)) & (df[col] <= wk(hi))]


def main() -> None:
    spine = pd.read_parquet(DATA_PROCESSED / "fact_weekly_market.parquet")
    chan = pd.read_parquet(DATA_PROCESSED / "fact_weekly_channel.parquet")
    infl = pd.read_parquet(DATA_PROCESSED / "fact_weekly_influencer.parquet")
    pr = pd.read_parquet(DATA_PROCESSED / "fact_weekly_pr.parquet")

    # -- 1. Awareness holds up through the paid media cut ------------------
    lo, hi = EVENTS["budget_cut"]
    before = window(spine, lo - 6, lo - 1)
    during = window(spine, lo, hi)
    paid_delta = during["paid_spend_usd"].sum() / before["paid_spend_usd"].sum() - 1
    infl_delta = during["influencer_spend_usd"].sum() / before["influencer_spend_usd"].sum() - 1
    aw_start = window(spine, lo, lo)["awareness"].mean()
    aw_end = window(spine, hi, hi)["awareness"].mean()
    check(
        "1. Awareness rises despite paid media cut",
        paid_delta < -0.25 and aw_end > aw_start and infl_delta > 0.5,
        f"paid spend {paid_delta:+.1%}, influencer spend {infl_delta:+.1%}, "
        f"awareness {aw_start:.1f} -> {aw_end:.1f}pp",
    )

    # -- 2. The bought-audience cohort is isolated cleanly -----------------
    # Ground truth: four accounts were generated with bought audiences
    # (GulfTechDaily, LuxeLivingKSA, DubaiFoodieLife, HalaLifestyle). The test is
    # that the audience-quality flag has both full recall and no false positives,
    # and that those same accounts occupy the worst CPA slots -- not that any one
    # named influencer ranks last, which is noise-sensitive.
    planted_poor = {"GulfTechDaily", "LuxeLivingKSA", "DubaiFoodieLife", "HalaLifestyle"}
    scores = (
        infl.groupby("influencer")
        .agg(fee=("fee_usd", "sum"), conv=("conversions", "sum"), eng=("engagements", "sum"))
        .assign(cpa=lambda d: d.fee / d.conv.replace(0, pd.NA))
        .sort_values("cpa", ascending=False)
    )
    worst4 = set(scores.head(4).index)
    suspect = set(infl.loc[infl["audience_quality_flag"] == "suspect", "influencer"].unique())
    check(
        "2. Bought-audience cohort flagged with no false positives",
        suspect == planted_poor and worst4 == planted_poor,
        f"flagged={sorted(suspect)}; worst-4 CPA={sorted(worst4)} "
        f"(${scores['cpa'].max():,.0f} vs best ${scores['cpa'].min():,.0f})",
    )

    # -- 3. CPC inflation on Search + Meta ---------------------------------
    lo, hi = EVENTS["cpc_creep"]
    perf = chan[chan["channel"].isin(["Paid Search", "Meta"])]
    base = window(perf, lo - 6, lo - 1)
    late = window(perf, hi - 4, hi)
    cpc_base = base["spend_usd"].sum() / base["clicks"].sum()
    cpc_late = late["spend_usd"].sum() / late["clicks"].sum()
    # Blended CPC rises less than the underlying 42% auction inflation because
    # click mix shifts toward the cheaper of the two channels -- expected.
    check(
        "3. Search/Meta CPC inflates materially (>25% blended)",
        cpc_late / cpc_base > 1.25,
        f"CPC ${cpc_base:.2f} -> ${cpc_late:.2f} ({cpc_late/cpc_base-1:+.1%})",
    )

    # -- 4. Post-launch sentiment dip --------------------------------------
    lo, hi = EVENTS["sentiment_dip"]
    dip = window(spine, lo, hi)["sentiment_score"].mean()
    norm = spine[~spine["week"].isin(window(spine, lo, hi)["week"])]["sentiment_score"].mean()
    check(
        "4. Sentiment dips after launch",
        dip < norm - 0.10,
        f"sentiment {norm:.3f} baseline -> {dip:.3f} during dip ({dip-norm:+.3f})",
    )

    # -- 5. Rival A gains share of voice -----------------------------------
    lo, hi = EVENTS["competitor_sov_rise"]
    rival = pr[pr["brand"] == "Rival A"]
    r_start = window(rival, lo, lo + 2)["share_of_voice_pct"].mean()
    r_end = window(rival, hi - 2, hi)["share_of_voice_pct"].mean()
    sam = pr[pr["brand"] == "Samsung"]
    s_start = window(sam, lo, lo + 2)["share_of_voice_pct"].mean()
    s_end = window(sam, hi - 2, hi)["share_of_voice_pct"].mean()
    check(
        "5. Rival A takes SOV from Samsung",
        (r_end - r_start) > 3.0 and (s_end - s_start) < 0,
        f"Rival A {r_start:.1f} -> {r_end:.1f}pp, Samsung {s_start:.1f} -> {s_end:.1f}pp",
    )

    # -- 6. Egypt: spend up, sales down ------------------------------------
    lo, hi = EVENTS["egypt_sales_decline"]
    eg = spine[spine["market"] == "Egypt"]
    eg_before = window(eg, lo - 6, lo - 1)
    eg_during = window(eg, lo, hi)
    sp = eg_during["total_media_spend_usd"].sum() / eg_before["total_media_spend_usd"].sum() - 1
    un = eg_during["units_sold"].sum() / eg_before["units_sold"].sum() - 1
    check(
        "6. Egypt sales fall while spend rises",
        sp > 0.10 and un < -0.10,
        f"spend {sp:+.1%}, units {un:+.1%}",
    )

    # -- 7. Brand equity erodes late in the year ---------------------------
    lo, hi = EVENTS["brand_equity_slide"]
    be_start = window(spine, lo, lo + 1)["brand_equity_index"].mean()
    be_end = window(spine, hi - 1, hi)["brand_equity_index"].mean()
    check(
        "7. Brand equity slides from week 42",
        be_end < be_start,
        f"equity index {be_start:.1f} -> {be_end:.1f} ({be_end-be_start:+.1f})",
    )

    print(f"\n{'':4s} {'signal':52s} detail")
    print("-" * 130)
    for status, name, detail in results:
        print(f"{status:4s} {name:52s} {detail}")
    n_fail = sum(1 for s, _, _ in results if s == FAIL)
    print("-" * 130)
    print(f"{len(results) - n_fail}/{len(results)} signals recovered")
    if n_fail:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
