"""Generate the eight synthetic source files described in the case study brief.

IMPORTANT: this is SYNTHETIC placeholder data, not Samsung data. It exists so the
pipeline, dashboard, assistant and alerting can be built and validated before the
real files arrive. See data/raw/SYNTHETIC_README.md.

The generator builds one latent "truth" (spend -> adstock -> brand equity -> sales)
and then emits eight files that are partial, inconsistent views of that truth --
different date formats, currencies, channel spellings, duplicates and nulls --
because the cleaning work in Part 1 has to be real work.

Planted signals (see common.EVENTS) that the analysis is expected to recover:
  1. Adstock carryover + a paid->earned mix shift keep awareness rising through a
     38% media spend cut (weeks 24-29).
  2. One mega influencer with bought-looking followers and a terrible CPA.
  3. Search/Meta CPC inflation of ~45% across weeks 34-44.
  4. A post-launch sentiment dip driven by pricing backlash.
  5. Rival A taking share of voice from week 38.
  6. Egypt sales falling while spend rises (weeks 44-49) on an FX-driven price rise.
  7. Brand equity eroding from week 42.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import (
    CATEGORIES,
    COMPETITORS,
    DATA_RAW,
    EVENTS,
    MARKET_CURRENCY,
    MARKETS,
    N_WEEKS,
    PAID_CHANNELS,
    SOCIAL_PLATFORMS,
    WEEKS,
    in_window,
)

RNG = np.random.default_rng(20260812)

# --------------------------------------------------------------------------
# Campaign calendar -- shared by paid media and influencer so that campaign
# level ROI can be computed across both.
# --------------------------------------------------------------------------
CAMPAIGNS = {
    "Always-On Brand": (0, 51),
    "White Friday Blitz": (14, 18),
    "Year End Gifting": (19, 22),
    "New Year Upgrade": (23, 28),
    "Galaxy Flagship Launch": (29, 36),
    "Ramadan Together": (29, 34),
    "Summer Cooling Push": (44, 51),
}


def campaigns_active(t: int) -> list[str]:
    return [c for c, (lo, hi) in CAMPAIGNS.items() if lo <= t <= hi]


# --------------------------------------------------------------------------
# 1. Spend plan
# --------------------------------------------------------------------------
MARKET_WEEKLY_SPEND_USD = {"UAE": 420_000, "KSA": 560_000, "Egypt": 175_000}

CHANNEL_SPLIT = {
    "Paid Search": 0.18,
    "Meta": 0.20,
    "TikTok": 0.12,
    "YouTube": 0.15,
    "Programmatic Display": 0.10,
    "TV": 0.20,
    "OOH": 0.05,
}


def seasonality(t: int) -> float:
    """Base spend multiplier before event overrides."""
    base = 1.0 + 0.08 * np.sin(2 * np.pi * t / 52.0)
    if in_window(t, "white_friday"):
        base *= [1.9, 2.4, 1.6][t - EVENTS["white_friday"][0]]
    if in_window(t, "holiday_peak"):
        base *= 1.45
    if in_window(t, "budget_cut"):
        # Deliberate Q1 budget reset: paid media down ~38%.
        base *= 0.62
    if in_window(t, "ramadan"):
        base *= 1.40
    if in_window(t, "product_launch"):
        base *= 1.25
    return float(base)


def build_spend_plan() -> pd.DataFrame:
    rows = []
    for t in range(N_WEEKS):
        week = WEEKS[t]
        for m in MARKETS:
            mkt_mult = 1.0
            # Egypt: budget pushed UP late in the year while sales fall.
            if m == "Egypt" and in_window(t, "egypt_sales_decline"):
                mkt_mult *= 1.32
            total = MARKET_WEEKLY_SPEND_USD[m] * seasonality(t) * mkt_mult
            active = campaigns_active(t)
            for ch, share in CHANNEL_SPLIT.items():
                # During the cut, brand channels are protected less than
                # performance -- a realistic (and wrong) CFO-driven choice.
                ch_mult = 1.0
                if in_window(t, "budget_cut") and ch in {"TV", "OOH"}:
                    ch_mult *= 0.55
                spend = total * share * ch_mult * RNG.normal(1.0, 0.05)
                spend = max(spend, 0.0)
                # Split across the campaigns live that week.
                weights = RNG.dirichlet(np.ones(len(active)) * 2.5)
                for camp, w in zip(active, weights):
                    rows.append(
                        {
                            "week": week,
                            "t": t,
                            "market": m,
                            "channel": ch,
                            "campaign": camp,
                            "spend_usd": spend * w,
                        }
                    )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 2. Delivery metrics (impressions / clicks / conversions) with CPC inflation
# --------------------------------------------------------------------------
BASE_CPM_USD = {
    "Paid Search": 42.0,
    "Meta": 8.5,
    "TikTok": 6.2,
    "YouTube": 11.0,
    "Programmatic Display": 3.4,
    "TV": 14.0,
    "OOH": 5.5,
}
BASE_CTR = {
    "Paid Search": 0.062,
    "Meta": 0.0115,
    "TikTok": 0.0138,
    "YouTube": 0.0072,
    "Programmatic Display": 0.0009,
    "TV": 0.0,
    "OOH": 0.0,
}
# Platform-CLAIMED conversion rates. These are deliberately generous: each
# platform counts conversions under its own last-click/view-through window, so
# the sum across platforms runs ahead of what the website actually recorded.
BASE_CVR = {
    "Paid Search": 0.0137,
    "Meta": 0.0062,
    "TikTok": 0.0042,
    "YouTube": 0.0033,
    "Programmatic Display": 0.0017,
    "TV": 0.0,
    "OOH": 0.0,
}


def cpc_inflation(t: int, channel: str) -> float:
    """Auction pressure on the two biggest performance channels."""
    if channel not in {"Paid Search", "Meta"}:
        return 1.0
    lo, hi = EVENTS["cpc_creep"]
    if t < lo:
        return 1.0
    if t > hi:
        return 1.42  # stays elevated -- it never came back down
    return 1.0 + 0.42 * (t - lo) / (hi - lo)


def add_delivery(spend: pd.DataFrame) -> pd.DataFrame:
    df = spend.copy()
    cpm = df["channel"].map(BASE_CPM_USD) * df.apply(
        lambda r: cpc_inflation(r["t"], r["channel"]), axis=1
    )
    cpm = cpm * RNG.normal(1.0, 0.06, len(df)).clip(0.8, 1.25)
    df["impressions"] = (df["spend_usd"] / cpm * 1000).round()
    ctr = df["channel"].map(BASE_CTR) * RNG.normal(1.0, 0.09, len(df)).clip(0.7, 1.3)
    df["clicks"] = (df["impressions"] * ctr).round()
    cvr = df["channel"].map(BASE_CVR) * RNG.normal(1.0, 0.11, len(df)).clip(0.6, 1.4)
    df["conversions"] = (df["clicks"] * cvr).round()
    return df


# --------------------------------------------------------------------------
# 3. Influencer roster
# --------------------------------------------------------------------------
INFLUENCERS = [
    # name, market, tier, followers, engagement_rate, cost_per_post_usd, quality
    ("GulfTechDaily", "UAE", "Mega", 1_350_000, 0.0038, 9_400, "poor"),
    ("LuxeLivingKSA", "KSA", "Macro", 620_000, 0.0061, 5_200, "poor"),
    ("TechBitesAr", "UAE", "Micro", 68_000, 0.0721, 780, "star"),
    ("NoorReviews", "KSA", "Micro", 91_000, 0.0654, 950, "star"),
    ("CairoGadgetGuy", "Egypt", "Mid", 245_000, 0.0402, 1_600, "good"),
    ("SaraSmartHome", "UAE", "Mid", 310_000, 0.0355, 2_100, "good"),
    ("KhaledUnboxed", "KSA", "Macro", 780_000, 0.0212, 4_800, "good"),
    ("MENAFilmMaker", "UAE", "Mid", 198_000, 0.0288, 1_450, "good"),
    ("UmmAhmadHome", "KSA", "Mid", 265_000, 0.0433, 1_750, "good"),
    ("AlexTechTalk", "Egypt", "Micro", 54_000, 0.0588, 520, "star"),
    ("DubaiFoodieLife", "UAE", "Macro", 540_000, 0.0176, 3_900, "poor"),
    ("RiyadhRunner", "KSA", "Micro", 77_000, 0.0512, 690, "good"),
    ("MasrMobileHub", "Egypt", "Mid", 182_000, 0.0367, 1_180, "good"),
    ("StyleByLayla", "UAE", "Macro", 465_000, 0.0243, 3_400, "good"),
    ("TheGamerGulf", "KSA", "Mid", 288_000, 0.0475, 1_900, "star"),
    ("NileHomeIdeas", "Egypt", "Micro", 62_000, 0.0499, 480, "good"),
    ("ZaidCreates", "UAE", "Mid", 221_000, 0.0331, 1_520, "good"),
    ("HalaLifestyle", "KSA", "Macro", 590_000, 0.0198, 4_100, "poor"),
]

# Conversion efficiency by audience quality: the "poor" cohort has followers that
# do not convert, which is the signal the influencer scorecard must surface.
QUALITY_CVR = {"poor": 0.0006, "good": 0.0089, "star": 0.0231}

# Influencer is a material line in the MENA budget (~12% of total media), not a
# rounding error. Without this the paid->influencer mix shift during the Q1 cut
# would be too small to explain the awareness result.
INFLUENCER_FEE_SCALE = 3.6


def build_influencers(spend_plan: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for t in range(N_WEEKS):
        week = WEEKS[t]
        # Influencer investment is scaled UP hard during the paid media cut --
        # this is the mix shift that keeps awareness rising.
        surge = 2.6 if in_window(t, "budget_cut") else 1.0
        if in_window(t, "ramadan"):
            surge = max(surge, 1.7)
        if in_window(t, "product_launch"):
            surge = max(surge, 2.2)
        active = [c for c in campaigns_active(t) if c != "Always-On Brand"] or [
            "Always-On Brand"
        ]
        for name, market, tier, followers, er, cpp, quality in INFLUENCERS:
            # Not every influencer posts every week.
            n_posts = RNG.poisson(0.9 * surge)
            if n_posts == 0:
                continue
            campaign = str(RNG.choice(active))
            reach = followers * RNG.uniform(0.22, 0.46) * n_posts
            # The poor-quality mega account buys impressions: impressions run far
            # ahead of genuine reach.
            imp_mult = RNG.uniform(2.6, 3.4) if quality == "poor" else RNG.uniform(1.1, 1.5)
            impressions = reach * imp_mult
            engagements = reach * er * RNG.normal(1.0, 0.12)
            likes = engagements * RNG.uniform(0.86, 0.93)
            comments = engagements * (
                RNG.uniform(0.004, 0.012) if quality == "poor" else RNG.uniform(0.05, 0.09)
            )
            shares = max(engagements - likes - comments, 0)
            clicks = engagements * RNG.uniform(0.06, 0.14)
            conversions = reach * QUALITY_CVR[quality] * RNG.normal(1.0, 0.18)
            fee = cpp * n_posts * INFLUENCER_FEE_SCALE * RNG.normal(1.0, 0.07)
            rows.append(
                {
                    "week": week,
                    "t": t,
                    "influencer": name,
                    "market": market,
                    "tier": tier,
                    "followers": followers,
                    "campaign": campaign,
                    "posts": int(n_posts),
                    "reach": round(reach),
                    "impressions": round(impressions),
                    "likes": round(likes),
                    "comments": round(max(comments, 0)),
                    "shares": round(shares),
                    "engagements": round(max(engagements, 0)),
                    "clicks": round(max(clicks, 0)),
                    "conversions": round(max(conversions, 0)),
                    "fee_usd": round(max(fee, 0), 2),
                    "_quality": quality,
                }
            )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 4. Latent brand equity -- driven by adstocked brand pressure, PR and influencer
# --------------------------------------------------------------------------
def adstock(x: np.ndarray, decay: float) -> np.ndarray:
    out = np.zeros_like(x, dtype=float)
    carry = 0.0
    for i, v in enumerate(x):
        carry = v + decay * carry
        out[i] = carry
    return out


def build_brand_equity(
    spend_plan: pd.DataFrame, infl: pd.DataFrame
) -> tuple[pd.DataFrame, dict]:
    """Weekly latent brand metrics per market."""
    records = []
    latent = {}
    for m in MARKETS:
        sp = spend_plan[spend_plan["market"] == m]
        brand_spend = (
            sp[sp["channel"].isin(["TV", "YouTube", "OOH", "Programmatic Display"])]
            .groupby("t")["spend_usd"]
            .sum()
            .reindex(range(N_WEEKS), fill_value=0.0)
            .to_numpy()
        )
        infl_m = infl[infl["market"] == m]
        infl_reach = (
            infl_m.groupby("t")["reach"]
            .sum()
            .reindex(range(N_WEEKS), fill_value=0.0)
            .to_numpy()
        )

        # Long carryover on brand pressure -- this is what cushions the cut.
        bs = adstock(brand_spend / brand_spend.mean(), 0.82)
        ir = adstock(infl_reach / max(infl_reach.mean(), 1e-9), 0.74)

        aw, cons, pref, nps = [], [], [], []
        a = 0.0
        base_aw = {"UAE": 0.612, "KSA": 0.648, "Egypt": 0.523}[m]
        for t in range(N_WEEKS):
            # Earned/influenced pressure is weighted higher per dollar than paid.
            drive = 0.55 * bs[t] / 5.0 + 0.45 * ir[t] / 4.0
            pr_boost = 0.010 if in_window(t, "product_launch") else 0.0
            if in_window(t, "budget_cut"):
                pr_boost += 0.006  # heavy earned PR push replacing paid
            competitor_drag = 0.0
            if in_window(t, "competitor_sov_rise"):
                lo, hi = EVENTS["competitor_sov_rise"]
                competitor_drag = 0.030 * (t - lo) / (hi - lo)
            sentiment_drag = 0.012 if in_window(t, "sentiment_dip") else 0.0

            target = base_aw + 0.085 * drive + pr_boost - competitor_drag - sentiment_drag
            a = 0.88 * (a if t else target) + 0.12 * target
            a += RNG.normal(0, 0.0035)
            awareness = float(np.clip(a, 0.30, 0.95))
            consideration = float(
                np.clip(awareness * 0.63 + RNG.normal(0, 0.004) - sentiment_drag * 0.8, 0.1, 0.9)
            )
            preference = float(np.clip(consideration * 0.58 + RNG.normal(0, 0.004), 0.05, 0.8))
            nps_v = float(
                np.clip(
                    28 + 60 * (preference - 0.22) - (140 * sentiment_drag) + RNG.normal(0, 1.4),
                    -20,
                    75,
                )
            )
            aw.append(awareness)
            cons.append(consideration)
            pref.append(preference)
            nps.append(nps_v)

        arr_aw = np.array(aw)
        arr_cons = np.array(cons)
        arr_pref = np.array(pref)
        arr_nps = np.array(nps)
        equity = (
            0.30 * (arr_aw / 0.65)
            + 0.30 * (arr_cons / 0.42)
            + 0.25 * (arr_pref / 0.24)
            + 0.15 * ((arr_nps + 20) / 70)
        ) * 62.0

        latent[m] = {"awareness": arr_aw, "equity": equity}
        for t in range(N_WEEKS):
            records.append(
                {
                    "week": WEEKS[t],
                    "t": t,
                    "market": m,
                    "awareness": round(arr_aw[t] * 100, 2),
                    "consideration": round(arr_cons[t] * 100, 2),
                    "preference": round(arr_pref[t] * 100, 2),
                    "nps": round(arr_nps[t], 1),
                    "brand_equity_index": round(equity[t], 2),
                }
            )
    return pd.DataFrame(records), latent


# --------------------------------------------------------------------------
# 5. Sales
# --------------------------------------------------------------------------
BASE_UNITS = {
    ("UAE", "Smartphones"): 9_400,
    ("UAE", "TV"): 2_600,
    ("UAE", "Home Appliances"): 3_100,
    ("KSA", "Smartphones"): 15_800,
    ("KSA", "TV"): 4_300,
    ("KSA", "Home Appliances"): 5_200,
    ("Egypt", "Smartphones"): 11_200,
    ("Egypt", "TV"): 3_400,
    ("Egypt", "Home Appliances"): 4_100,
}
ASP_LOCAL = {
    ("UAE", "Smartphones"): 2_450,
    ("UAE", "TV"): 3_100,
    ("UAE", "Home Appliances"): 2_050,
    ("KSA", "Smartphones"): 2_520,
    ("KSA", "TV"): 3_250,
    ("KSA", "Home Appliances"): 2_180,
    ("Egypt", "Smartphones"): 31_500,
    ("Egypt", "TV"): 39_800,
    ("Egypt", "Home Appliances"): 26_400,
}


def build_sales(spend_plan: pd.DataFrame, latent: dict) -> pd.DataFrame:
    rows = []
    for m in MARKETS:
        sp = spend_plan[spend_plan["market"] == m]
        perf_spend = (
            sp[sp["channel"].isin(["Paid Search", "Meta", "TikTok"])]
            .groupby("t")["spend_usd"]
            .sum()
            .reindex(range(N_WEEKS), fill_value=0.0)
            .to_numpy()
        )
        perf = adstock(perf_spend / perf_spend.mean(), 0.35)
        equity = latent[m]["equity"]
        equity_n = equity / equity.mean()

        for cat in CATEGORIES:
            base = BASE_UNITS[(m, cat)]
            asp0 = ASP_LOCAL[(m, cat)]
            for t in range(N_WEEKS):
                season = 1.0 + 0.10 * np.sin(2 * np.pi * (t + 6) / 52.0)
                if in_window(t, "white_friday"):
                    season *= [1.7, 2.2, 1.4][t - EVENTS["white_friday"][0]]
                if in_window(t, "holiday_peak"):
                    season *= 1.35
                if in_window(t, "ramadan"):
                    season *= 1.30
                if in_window(t, "product_launch") and cat == "Smartphones":
                    season *= 1.55

                price_mult = 1.0
                demand_mult = 1.0
                # Egypt: FX devaluation forces a price rise; volume collapses even
                # though media spend was increased to defend it.
                if m == "Egypt" and t >= EVENTS["egypt_sales_decline"][0]:
                    ramp = min(
                        1.0,
                        (t - EVENTS["egypt_sales_decline"][0] + 1)
                        / (EVENTS["egypt_sales_decline"][1] - EVENTS["egypt_sales_decline"][0] + 1),
                    )
                    price_mult = 1.0 + 0.28 * ramp
                    demand_mult = 1.0 - 0.30 * ramp

                units = (
                    base
                    * season
                    * demand_mult
                    * (1 + 0.16 * (perf[t] / max(perf.mean(), 1e-9) - 1))
                    * (1 + 0.34 * (equity_n[t] - 1))
                    * RNG.normal(1.0, 0.045)
                )
                asp = asp0 * price_mult * RNG.normal(1.0, 0.012)
                rows.append(
                    {
                        "week": WEEKS[t],
                        "t": t,
                        "market": m,
                        "category": cat,
                        "units_sold": int(max(units, 0)),
                        "asp_local": round(asp, 2),
                        "revenue_local": round(max(units, 0) * asp, 2),
                        "currency": MARKET_CURRENCY[m],
                    }
                )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 6. Remaining sources: social, TV GRP, PR SOV, website
# --------------------------------------------------------------------------
def build_social(spend_plan: pd.DataFrame, infl: pd.DataFrame, latent: dict) -> pd.DataFrame:
    rows = []
    plat_share = {"Instagram": 0.31, "TikTok": 0.27, "YouTube": 0.18, "X": 0.10, "Facebook": 0.14}
    for m in MARKETS:
        eq = latent[m]["equity"]
        eq_n = eq / eq.mean()
        infl_m = infl[infl["market"] == m].groupby("t")["reach"].sum().reindex(
            range(N_WEEKS), fill_value=0.0
        )
        paid_social = (
            spend_plan[
                (spend_plan["market"] == m)
                & (spend_plan["channel"].isin(["Meta", "TikTok", "YouTube"]))
            ]
            .groupby("t")["spend_usd"]
            .sum()
            .reindex(range(N_WEEKS), fill_value=0.0)
        )
        base_followers = {"UAE": 1_240_000, "KSA": 2_050_000, "Egypt": 1_680_000}[m]
        for t in range(N_WEEKS):
            growth = 1 + 0.0042 * t + 0.10 * (eq_n[t] - 1)
            for p, share in plat_share.items():
                followers = base_followers * share * growth * RNG.normal(1, 0.004)
                posts = int(RNG.integers(4, 12))
                organic_reach = followers * RNG.uniform(0.12, 0.24) * (1 + 0.35 * (eq_n[t] - 1))
                paid_reach = paid_social[t] * share * RNG.uniform(1.4, 2.2)
                infl_spill = infl_m[t] * share * 0.06
                reach = organic_reach + paid_reach + infl_spill
                impressions = reach * RNG.uniform(1.6, 2.4)
                er = {"Instagram": 0.041, "TikTok": 0.068, "YouTube": 0.029, "X": 0.017, "Facebook": 0.022}[p]
                if in_window(t, "ramadan"):
                    er *= 1.22
                if in_window(t, "sentiment_dip"):
                    er *= 1.11  # outrage drives engagement up, sentiment down
                engagements = reach * er * RNG.normal(1, 0.09)

                sentiment = 0.42 + 0.20 * (eq_n[t] - 1) + RNG.normal(0, 0.035)
                if in_window(t, "sentiment_dip"):
                    lo, hi = EVENTS["sentiment_dip"]
                    depth = 1 - abs((t - lo) - (hi - lo) / 2) / max((hi - lo) / 2, 1)
                    sentiment -= 0.46 * depth
                rows.append(
                    {
                        "week": WEEKS[t],
                        "t": t,
                        "market": m,
                        "platform": p,
                        "followers": int(followers),
                        "posts": posts,
                        "impressions": int(impressions),
                        "reach": int(reach),
                        "engagements": int(max(engagements, 0)),
                        "video_views": int(impressions * RNG.uniform(0.28, 0.52)),
                        "sentiment_score": round(float(np.clip(sentiment, -1, 1)), 3),
                    }
                )
    return pd.DataFrame(rows)


def build_tv(spend_plan: pd.DataFrame) -> pd.DataFrame:
    rows = []
    stations = {
        "UAE": ["MBC 1", "Dubai TV", "MBC 4"],
        "KSA": ["MBC 1", "SSC Sports", "Rotana Khalijia"],
        "Egypt": ["ON E", "CBC", "MBC Masr"],
    }
    tv = spend_plan[spend_plan["channel"] == "TV"]
    for (t, m), grp in tv.groupby(["t", "market"]):
        total = grp["spend_usd"].sum()
        if total <= 0:
            continue
        weights = RNG.dirichlet(np.ones(len(stations[m])) * 3)
        for st, w in zip(stations[m], weights):
            spend = total * w
            cost_per_grp = {"UAE": 780, "KSA": 690, "Egypt": 210}[m] * RNG.normal(1, 0.07)
            grps = spend / cost_per_grp
            rows.append(
                {
                    "week": WEEKS[t],
                    "t": t,
                    "market": m,
                    "station": st,
                    "campaign": str(RNG.choice(grp["campaign"].unique())),
                    "grps": round(grps, 1),
                    "spots": int(max(grps * RNG.uniform(1.6, 2.4), 1)),
                    "reach_pct_1plus": round(min(88.0, 100 * (1 - np.exp(-grps / 145))), 1),
                    # Agency-reported spend: intentionally ~3% off finance figures.
                    "agency_reported_spend_usd": round(spend * RNG.normal(1.03, 0.012), 2),
                }
            )
    return pd.DataFrame(rows)


def build_pr(latent: dict) -> pd.DataFrame:
    rows = []
    for m in MARKETS:
        eq = latent[m]["equity"]
        eq_n = eq / eq.mean()
        for t in range(N_WEEKS):
            base_total = {"UAE": 2_400, "KSA": 3_100, "Egypt": 2_050}[m]
            total_mentions = base_total * RNG.normal(1, 0.10)
            if in_window(t, "product_launch"):
                total_mentions *= 2.4
            if in_window(t, "budget_cut"):
                total_mentions *= 1.35  # earned PR push replacing paid

            samsung_share = 0.315 + 0.06 * (eq_n[t] - 1)
            rival_a = 0.245
            if in_window(t, "competitor_sov_rise"):
                lo, hi = EVENTS["competitor_sov_rise"]
                gain = 0.085 * (t - lo) / (hi - lo)
                rival_a += gain
                samsung_share -= gain * 0.8
            shares = np.array([samsung_share, rival_a, 0.20, 0.16])
            shares = np.clip(shares + RNG.normal(0, 0.008, 4), 0.02, None)
            shares = shares / shares.sum()
            for brand, sh in zip(COMPETITORS, shares):
                sent = 0.38 + RNG.normal(0, 0.06)
                if brand == "Samsung" and in_window(t, "sentiment_dip"):
                    sent -= 0.44
                rows.append(
                    {
                        "week": WEEKS[t],
                        "t": t,
                        "market": m,
                        "brand": brand,
                        "mentions": int(total_mentions * sh),
                        "share_of_voice_pct": round(sh * 100, 2),
                        "pr_sentiment": round(float(np.clip(sent, -1, 1)), 3),
                    }
                )
    return pd.DataFrame(rows)


# Average order value on the e-commerce site, by market. Shared by the website
# generator and the ad-platform attributed-revenue generator so the two stay in
# the same units -- otherwise the reconciliation picks up a currency artefact
# instead of the real over-claiming signal.
WEB_AOV_USD = {"UAE": 690, "KSA": 720, "Egypt": 210}


def build_web(spend_plan: pd.DataFrame, infl: pd.DataFrame, latent: dict) -> pd.DataFrame:
    """Website sessions by channel group. Organic/Direct scale with brand equity,
    which is how the earned-media contribution becomes visible."""
    rows = []
    for m in MARKETS:
        eq = latent[m]["equity"]
        eq_n = eq / eq.mean()
        sp = spend_plan[spend_plan["market"] == m]
        clicks_by = (
            sp.groupby(["t", "channel"])["clicks"].sum().unstack(fill_value=0.0)
            if "clicks" in sp.columns
            else None
        )
        infl_clicks = infl[infl["market"] == m].groupby("t")["clicks"].sum().reindex(
            range(N_WEEKS), fill_value=0.0
        )
        base_direct = {"UAE": 46_000, "KSA": 72_000, "Egypt": 38_000}[m]
        for t in range(N_WEEKS):
            groups = {
                "Paid Search": float(clicks_by.get("Paid Search", pd.Series()).get(t, 0.0)),
                "Paid Social": float(
                    clicks_by.get("Meta", pd.Series()).get(t, 0.0)
                    + clicks_by.get("TikTok", pd.Series()).get(t, 0.0)
                ),
                "Video": float(clicks_by.get("YouTube", pd.Series()).get(t, 0.0)),
                "Display": float(clicks_by.get("Programmatic Display", pd.Series()).get(t, 0.0)),
                "Influencer": float(infl_clicks[t]),
                "Organic Search": base_direct * 0.55 * (1 + 0.55 * (eq_n[t] - 1)) * RNG.normal(1, 0.05),
                "Direct": base_direct * 0.45 * (1 + 0.62 * (eq_n[t] - 1)) * RNG.normal(1, 0.05),
            }
            for g, sessions in groups.items():
                sessions = max(sessions * RNG.normal(1, 0.03), 0)
                if sessions < 1:
                    continue
                paid = g in {"Paid Search", "Paid Social", "Video", "Display"}
                bounce = RNG.uniform(0.48, 0.63) if paid else RNG.uniform(0.31, 0.44)
                # Site-measured conversion rates. Lower than what the ad platforms
                # claim -- this gap is the attribution reconciliation story.
                cvr = RNG.uniform(0.0029, 0.0075) if paid else RNG.uniform(0.0086, 0.0161)
                cvr *= 1 + 0.30 * (eq_n[t] - 1)
                transactions = sessions * cvr
                aov = WEB_AOV_USD[m] * RNG.normal(1, 0.04)
                rows.append(
                    {
                        "week": WEEKS[t],
                        "t": t,
                        "market": m,
                        "channel_group": g,
                        "sessions": int(sessions),
                        "users": int(sessions * RNG.uniform(0.72, 0.86)),
                        "bounce_rate": round(bounce, 4),
                        "avg_session_sec": int(RNG.uniform(58, 210)),
                        "product_views": int(sessions * RNG.uniform(1.4, 2.6)),
                        "add_to_cart": int(sessions * RNG.uniform(0.05, 0.12)),
                        "transactions": int(transactions),
                        "revenue_usd": round(transactions * aov, 2),
                    }
                )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 7. Emit with realistic mess
# --------------------------------------------------------------------------
class SourceFileLocked(RuntimeError):
    """A raw file is open in another program (usually Excel) and cannot be written."""


def _write(df: pd.DataFrame, path, **kwargs) -> None:
    """Write a source file, failing with a readable message if it is locked.

    Anyone inspecting the generated data in Excel will leave a file handle open,
    and the resulting bare PermissionError traceback says nothing useful about
    what to do. Name the file and the fix instead.
    """
    try:
        if path.suffix == ".xlsx":
            df.to_excel(path, index=False, **kwargs)
        else:
            df.to_csv(path, index=False, **kwargs)
    except PermissionError as exc:
        raise SourceFileLocked(
            f"\n\n  Cannot write {path.name} - it is open in another program.\n"
            f"  Close it (Excel holds a lock on .xlsx files) and re-run.\n"
            f"  Path: {path}\n"
            f"  To skip regeneration entirely: python src/run_all.py --keep-raw\n"
        ) from exc


def _dup(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """Append n exact duplicate rows -- every real export has them."""
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(df), size=n, replace=False)
    return pd.concat([df, df.iloc[idx]], ignore_index=True)


def _nullify(df: pd.DataFrame, col: str, frac: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    mask = rng.random(len(df)) < frac
    df.loc[mask, col] = np.nan
    return df


def main() -> None:
    print("Building latent truth...")
    spend = build_spend_plan()
    spend = add_delivery(spend)
    infl = build_influencers(spend)
    brand, latent = build_brand_equity(spend, infl)
    sales = build_sales(spend, latent)
    social = build_social(spend, infl, latent)
    tv = build_tv(spend)
    pr = build_pr(latent)
    web = build_web(spend, infl, latent)

    # ---------------- media_spend.csv -----------------------------------
    ms = spend.copy()
    ms["currency"] = ms["market"].map(MARKET_CURRENCY)
    inv_fx = {"AED": 3.6725, "SAR": 3.75, "EGP": 48.5}
    ms["spend"] = (ms["spend_usd"] * ms["currency"].map(inv_fx)).round(2)
    # Platform-attributed revenue: last-click / view-through, and therefore
    # systematically ahead of the revenue the website actually recorded from
    # paid sessions. The cleaning step has to reconcile the two.
    ms["attributed_revenue"] = (
        ms["conversions"]
        * ms["market"].map(WEB_AOV_USD)
        * RNG.uniform(0.97, 1.09, len(ms))
        * ms["currency"].map(inv_fx)
    ).round(2)
    ms["date"] = pd.to_datetime(ms["week"]).dt.strftime("%d-%m-%Y")
    # Inconsistent channel spellings across the year, as if the taxonomy changed.
    spellings = {
        "Paid Search": ["Paid Search", "paid_search", "PaidSearch", "Search"],
        "Meta": ["Meta", "meta", "Facebook/Instagram", "META"],
        "TikTok": ["TikTok", "tiktok", "Tik Tok"],
        "YouTube": ["YouTube", "youtube", "YT"],
        "Programmatic Display": ["Programmatic Display", "Programmatic", "Display"],
        "TV": ["TV", "Television", "tv"],
        "OOH": ["OOH", "Out of Home", "ooh"],
    }
    ms["channel_raw"] = [
        spellings[c][int(RNG.integers(0, len(spellings[c])))] for c in ms["channel"]
    ]
    ms_out = ms[
        ["date", "market", "channel_raw", "campaign", "currency", "spend",
         "impressions", "clicks", "conversions", "attributed_revenue"]
    ].rename(columns={"channel_raw": "channel"})
    # Credit notes appear as negative spend rows.
    credits = ms_out.sample(14, random_state=7).copy()
    credits["spend"] = -(credits["spend"] * 0.15).round(2)
    credits[["impressions", "clicks", "conversions", "attributed_revenue"]] = 0
    ms_out = pd.concat([ms_out, credits], ignore_index=True)
    ms_out = _dup(ms_out, 23, 11)
    ms_out["market"] = [
        m + "  " if RNG.random() < 0.06 else m for m in ms_out["market"]
    ]
    _write(ms_out, DATA_RAW / "media_spend.csv")

    # ---------------- social_media_performance.csv -----------------------
    so = social.copy()
    so["date"] = pd.to_datetime(so["week"]).dt.strftime("%Y-%m-%d")
    plat_alias = {
        "Instagram": ["Instagram", "instagram", "IG"],
        "TikTok": ["TikTok", "tiktok", "Tik Tok"],
        "YouTube": ["YouTube", "YT", "youtube"],
        "X": ["X", "Twitter", "X (Twitter)"],
        "Facebook": ["Facebook", "FB", "facebook"],
    }
    so["platform"] = [
        plat_alias[p][int(RNG.integers(0, len(plat_alias[p])))] for p in so["platform"]
    ]
    so_out = so[
        ["date", "market", "platform", "followers", "posts", "impressions", "reach",
         "engagements", "video_views", "sentiment_score"]
    ]
    so_out = _nullify(so_out.copy(), "video_views", 0.025, 3)
    so_out = _dup(so_out, 16, 5)
    _write(so_out, DATA_RAW / "social_media_performance.csv")

    # ---------------- influencer_campaigns.xlsx --------------------------
    inf_out = infl.drop(columns=["_quality", "t"]).copy()
    inf_out["start_date"] = pd.to_datetime(inf_out["week"]).dt.strftime("%d/%m/%Y")
    inf_out["end_date"] = (
        pd.to_datetime(inf_out["week"]) + pd.Timedelta(days=6)
    ).dt.strftime("%d/%m/%Y")
    inf_out["tier"] = [
        t.lower() if RNG.random() < 0.3 else t for t in inf_out["tier"]
    ]
    # Fees arrive as formatted text about a third of the time.
    inf_out["fee_usd"] = [
        f"${v:,.2f}" if RNG.random() < 0.35 else v for v in inf_out["fee_usd"]
    ]
    inf_out = inf_out.drop(columns=["week"])
    cols = ["start_date", "end_date", "campaign", "influencer", "market", "tier",
            "followers", "posts", "reach", "impressions", "likes", "comments",
            "shares", "engagements", "clicks", "conversions", "fee_usd"]
    _write(inf_out[cols], DATA_RAW / "influencer_campaigns.xlsx")

    # ---------------- tv_grps.csv ----------------------------------------
    tv_out = tv.copy()
    tv_out["date"] = pd.to_datetime(tv_out["week"]).dt.strftime("%b %d, %Y")
    tv_out["grps"] = [f"{v:,.1f}" for v in tv_out["grps"]]
    tv_out = tv_out[
        ["date", "market", "station", "campaign", "grps", "spots",
         "reach_pct_1plus", "agency_reported_spend_usd"]
    ]
    _write(tv_out, DATA_RAW / "tv_grps.csv")

    # ---------------- pr_share_of_voice.csv ------------------------------
    pr_out = pr.copy()
    pr_out["date"] = pd.to_datetime(pr_out["week"]).dt.strftime("%Y-%m-%d")
    pr_out["share_of_voice_pct"] = [f"{v}%" for v in pr_out["share_of_voice_pct"]]
    pr_out[["date", "market", "brand", "mentions", "share_of_voice_pct", "pr_sentiment"]].to_csv(
        DATA_RAW / "pr_share_of_voice.csv", index=False
    )

    # ---------------- brand_equity_tracking.xlsx -------------------------
    # Brand tracking is a MONTHLY wave study, not weekly. The pipeline must
    # interpolate to the weekly grain -- a documented assumption.
    be = brand.copy()
    be["month"] = pd.to_datetime(be["week"]).dt.to_period("M")
    monthly = (
        be.groupby(["month", "market"], as_index=False)[
            ["awareness", "consideration", "preference", "nps", "brand_equity_index"]
        ]
        .mean()
        .round(2)
    )
    monthly["wave_date"] = monthly["month"].dt.to_timestamp("M").dt.strftime("%Y-%m-%d")
    monthly["sample_size"] = RNG.integers(380, 620, len(monthly))
    _write(
        monthly[
            ["wave_date", "market", "sample_size", "awareness", "consideration",
             "preference", "nps", "brand_equity_index"]
        ],
        DATA_RAW / "brand_equity_tracking.xlsx",
    )

    # ---------------- website_analytics.csv ------------------------------
    web_out = web.copy()
    web_out["date"] = pd.to_datetime(web_out["week"]).dt.strftime("%Y-%m-%d")
    web_out["bounce_rate"] = [f"{v*100:.1f}%" for v in web_out["bounce_rate"]]
    web_out = web_out[
        ["date", "market", "channel_group", "sessions", "users", "bounce_rate",
         "avg_session_sec", "product_views", "add_to_cart", "transactions", "revenue_usd"]
    ]
    web_out = _dup(web_out, 12, 17)
    _write(web_out, DATA_RAW / "website_analytics.csv")

    # ---------------- sales_data.csv -------------------------------------
    sa = sales.copy()
    sa["date"] = pd.to_datetime(sa["week"]).dt.strftime("%Y-%m-%d")
    sa_out = sa[
        ["date", "market", "category", "units_sold", "asp_local", "revenue_local", "currency"]
    ]
    sa_out = _dup(sa_out, 9, 23)
    _write(sa_out, DATA_RAW / "sales_data.csv")

    print(f"Wrote 8 source files to {DATA_RAW}")
    for f in sorted(DATA_RAW.glob("*")):
        if f.suffix in {".csv", ".xlsx"}:
            print(f"  {f.name:38s} {f.stat().st_size/1024:8.1f} KB")


if __name__ == "__main__":
    main()

