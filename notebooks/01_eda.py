# %% [markdown]
# # Part 1 — Marketing data analysis
#
# The working behind the dashboard: what arrived, what had to be decided before any
# number could be trusted, and what the data says once it is modelled.
#
# This is deliberately not a chart gallery — the dashboard is the chart gallery.
# This is the audit trail.
#
# **All figures AED.** 8 weeks · 8 subsidiaries · 8 channels · 6 devices.

# %%
import sys
from pathlib import Path

import pandas as pd

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT / "src"))

from common import DATA_PROCESSED, GROSS_MARGIN, SOURCE_FILE  # noqa: E402

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 60)


def L(name):
    return pd.read_parquet(DATA_PROCESSED / f"{name}.parquet")


# %% [markdown]
# ## 1. What arrived
#
# One file. Not eight, as the brief anticipated — the sources are already merged
# into a single long table at week × market × channel × product.

# %%
raw = pd.read_csv(SOURCE_FILE)
print(f"{SOURCE_FILE.name}: {raw.shape[0]:,} rows x {raw.shape[1]} columns")
print(f"\nweeks    {sorted(int(w) for w in raw.Week.unique())}")
print(f"markets  {sorted(raw.Market.unique())}")
print(f"channels {sorted(raw.Channel.unique())}")
print(f"products {sorted(raw['Product'].unique())}")

# %% [markdown]
# ### The nulls are structural, not missing
#
# Each row is one channel, and only the measures that channel carries are
# populated. TV has GRPs and no clicks; Website has sessions and no spend.
# Imputing them would invent data, so the cleaning job is to reshape, not fill.

# %%
cov = raw.groupby("Channel")[
    ["Impressions", "Clicks", "Spend_AED", "Conversions", "Sales_AED",
     "TV_GRP", "PR_Mentions", "Website_Sessions"]
].count()
cov

# %% [markdown]
# ## 2. Four things established before any analysis
#
# Each of these changes what may legitimately be reported. They are checks, not
# assumptions — every one is asserted in `src/ingest.py` and re-run on each build.

# %%
dq = L("data_quality_log")
pd.set_option("display.max_colwidth", 95)
dq[["check", "finding", "action"]]

# %% [markdown]
# ### 2a. TV has spend but no attributed sales — and it is the largest line
#
# This single fact shapes the whole analysis.

# %%
eff = L("channel_efficiency")
tv = eff[eff.channel == "TV"].iloc[0]
print(f"TV spend            {tv.spend_aed:>14,.0f} AED")
print(f"TV share of budget  {tv.share_of_spend:>14.1%}")
print(f"TV attributed sales {tv.sales_aed:>14,.0f} AED")
print(f"TV GRPs delivered   {tv.tv_grp:>14,.0f}")
print(f"Cost per GRP        {tv.cost_per_grp_aed:>14,.0f} AED")

# %% [markdown]
# Nearly half the budget cannot be evaluated on return. This is a *measurement
# gap*, not a performance result, and the two must not be allowed to look alike —
# so TV is excluded from every ROI ranking rather than scored as a zero.
#
# ### 2b. Brand metrics are not a market-level tracker
#
# A brand survey cannot legitimately differ between two advertising channels in the
# same market and week. Here it does, by a wide margin.

# %%
for col in ["Brand_Awareness_Score", "Purchase_Intent_Score", "Competitor_SOV"]:
    g = raw.groupby(["Market", "Week"])[col]
    print(f"{col:24s} constant within only {(g.nunique() <= 1).mean():.0%} of "
          f"market-weeks · mean spread {(g.max() - g.min()).mean():5.1f} points")

# %% [markdown]
# Averaged to market-week and reported as an **indicative index**. Practically:
# compare markets, do not read week-to-week movement — a weekly change is well
# inside the spread of the underlying values.
#
# ### 2c and 2d
#
# `Influencer_Engagement_Rate` is identical to `Engagement_Rate` on 100% of
# influencer rows, so it is dropped. PR spend is an explicit `0.00` on all 360 PR
# rows — genuinely unpaid, not missing — which with Website's absent spend makes
# PR and Website the earned side of the ledger.

# %% [markdown]
# ## 3. The modelled tables

# %%
spine = L("fact_market_week")
print(f"fact_market_week: {len(spine)} rows x {len(spine.columns)} cols "
      f"({spine.market.nunique()} markets x {spine.week.nunique()} weeks)")
spine[["week", "market", "spend_aed", "sales_aed", "conversions", "mer",
       "brand_awareness", "share_of_voice"]].head()

# %% [markdown]
# ## 4. Headline position

# %%
print(f"Sales        {spine.sales_aed.sum():>16,.0f} AED")
print(f"Media spend  {spine.spend_aed.sum():>16,.0f} AED")
print(f"Conversions  {spine.conversions.sum():>16,.0f}")
print(f"MER          {spine.sales_aed.sum()/spine.spend_aed.sum():>16.2f}x")
print(f"Media as %   {spine.spend_aed.sum()/spine.sales_aed.sum():>16.1%} of sales")

# %% [markdown]
# ## 5. Where the variation actually is
#
# The central finding. Before recommending anything, establish which dimension
# contains the opportunity.

# %%
ms, ps = L("market_scorecard"), L("product_summary")
meas = eff[eff.revenue_attributed & eff.roas.notna()]
print(f"Between channels  ROAS {meas.roas.min():5.1f}x -> {meas.roas.max():5.1f}x   "
      f"{meas.roas.max()/meas.roas.min():.0f}-fold")
print(f"Between markets   MER  {ms.mer.min():5.2f}x -> {ms.mer.max():5.2f}x   "
      f"{ms.mer.max()/ms.mer.min()-1:.0%}")
print(f"Between products  ROAS {ps.roas.min():5.1f}x -> {ps.roas.max():5.1f}x   "
      f"{ps.roas.max()/ps.roas.min()-1:.0%}")

# %% [markdown]
# Markets sit within 11% of each other and products within 8%. Channels differ by
# more than an order of magnitude. **The entire optimisation opportunity is channel
# mix** — re-planning by market or product would rearrange positions that are
# already broadly equivalent.

# %%
eff[["channel", "spend_aed", "share_of_spend", "sales_aed", "share_of_sales",
     "roas", "roi_gross_margin", "payback"]].round(3)

# %% [markdown]
# Search takes under a fifth of budget and returns 43% of sales. Influencer and B2B
# Roadshow take 10% of budget between them and return under 3% — and both fall
# below breakeven once the assumed 22% gross margin is applied.
#
# ## 6. Does spending more actually move sales?
#
# Observed ROAS is confounded: a channel deployed where demand already exists looks
# efficient. A panel regression of weekly market sales on channel spend, with
# market fixed effects and cluster-robust errors, asks a narrower question that 64
# observations can speak to.
#
# **This is not a marketing mix model.** No carryover, no saturation, no claim of
# causal contribution — 8 weeks cannot identify any of them.

# %%
pm = L("panel_model")
pm[["channel", "coefficient", "ci_low", "ci_high", "p_value", "significant_5pct"]].round(3)

# %% [markdown]
# **The intervals are the finding.** Only Search and TV are distinguishable from
# zero; every other interval crosses it. Eight weeks cannot rank channels on
# differences this fine, and a table of point estimates without intervals would
# invite exactly that error.
#
# Note the tension with the efficiency table: **TV has no attributed sales, yet its
# spend is significantly associated with market sales.** That is what a broad-reach
# channel looks like when last-click attribution cannot see it — an argument for
# measuring TV, not for cutting it and not for trusting it blindly.

# %% [markdown]
# ## 7. Influencer: a channel problem, not a roster problem

# %%
sc = L("influencer_scorecard")
print(f"creators {len(sc)}   fees {sc.spend_aed.sum():,.0f} AED   "
      f"median CPA {sc.cpa_aed.median():,.0f} AED")
print(f"ROAS  min {sc.roas.min():.2f}x  median {sc.roas.median():.2f}x  "
      f"max {sc.roas.max():.2f}x")
print(f"Best ROI on {GROSS_MARGIN:.0%} margin: {sc.roas.max()*GROSS_MARGIN:.2f}x  "
      f"(breakeven = 1.00x)")
print(f"Followers {sc.followers.min():,.0f}-{sc.followers.max():,.0f} "
      f"across {sc.tier.nunique()} tier(s)")

# %% [markdown]
# **Not one of the 24 creators returns above breakeven on gross margin**, and every
# one sits in a single follower tier. There is no micro or mid-tier presence — and
# that is where influencer efficiency usually lives. Dropping the worst few names
# would not fix a channel that does not pay back at any point on its current roster.

# %% [markdown]
# ## 8. Paid versus earned

# %%
L("paid_vs_earned").round(3)

# %% [markdown]
# PR and Website carry no media cost and produce **34% of all sales**. No ROAS is
# shown for them rather than an infinite one.
#
# **Earned is not free** — it is bought by brand investment made earlier, which is
# precisely why the TV measurement gap matters commercially. If broad-reach spend
# feeds this earned demand, cutting it to chase measurable channels would erode the
# most efficient line in the business.

# %% [markdown]
# ## 9. Competitive position

# %%
ms[["market", "share_of_voice", "competitor_sov", "sov_gap", "mer", "mer_rank"]].round(2)

# %% [markdown]
# Samsung leads share of voice in all eight markets, by a wide and stable margin.
# That lead sits in PR, which costs nothing — the cheapest asset in the portfolio
# to defend.

# %% [markdown]
# ## 10. What the numbers mean
#
# 1. **Half the budget cannot be evaluated.** TV is 48% of spend with no attributed
#    return. Commissioning incrementality testing is the highest-value analytics
#    investment available, and until it exists no reallocation involving TV is
#    defensible in either direction.
# 2. **The opportunity is channel mix, and only channel mix.** Markets and products
#    are already broadly equivalent.
# 3. **Influencer does not pay back at the margin** — as a channel, not as a roster.
#    The untested micro and mid tiers are the more promising move.
# 4. **A third of sales arrive at no media cost**, which is an argument for
#    protecting brand investment rather than reallocating away from it.
# 5. **Eight weeks limits what may be claimed.** Movements, not trends; association,
#    not contribution; comparison between markets, not attribution over time.
