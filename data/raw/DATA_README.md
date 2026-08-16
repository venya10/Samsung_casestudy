# Source data

`samsung_marketing_full_dataset.csv` — 2,360 rows × 24 columns, the extract
provided for this case study.

## Shape

One long, sparse table at **week × market × channel × product**. No duplicate keys.

| Dimension | Values |
|---|---|
| Week | 1–8 (integers, **no calendar dates**) |
| Market | SGE, SESAR, SEEG, SELV, SEMAG, SEPAK, SETK, SEIL — subsidiary codes |
| Channel | TV, Paid Social, Search, Influencer, B2B Roadshow, Retail, PR, Website |
| Product | Galaxy Z Fold8, Z Flip8, S24, Tab S10, Watch6, Buds3 |
| Currency | AED throughout |

## The nulls are structural, not missing

Each row is one channel, and only the measures that channel carries are populated.
Filling them would invent data.

| Measure | Present on |
|---|---|
| `Spend_AED` | all paid channels + PR (PR is explicitly 0.00) |
| `Impressions` | Paid Social, Search, B2B Roadshow, Retail |
| `Clicks` | Paid Social, Search only |
| `Sales_AED`, `Conversions` | all except **TV** and PR |
| `TV_GRP` | TV only |
| `PR_Mentions`, `PR_Share_of_Voice` | PR only |
| `Website_Sessions`, `Bounce_Rate`, … | Website only |
| Brand scores, `Competitor_SOV`, `Sentiment_Score` | every row |

`src/ingest.py` verifies this coverage on every run and fails the data quality log
if it changes.

## Four things established before any analysis

**1. TV has spend but no attributed sales.** 48% of media spend, zero revenue
attribution. TV is excluded from every ROI ranking rather than scored as zero.

**2. Brand metrics are not a tracker.** `Brand_Awareness_Score`,
`Purchase_Intent_Score`, `Competitor_SOV` and `Sentiment_Score` sit on every row and
vary by up to **39 points inside a single market-week**. A brand survey cannot
legitimately differ between two advertising channels in the same market and week, so
these are averaged to market-week and reported as an *indicative index*.

**3. `Influencer_Engagement_Rate` duplicates `Engagement_Rate`** — identical on 100%
of influencer rows. Dropped.

**4. PR and Website carry no media cost but do carry sales.** Combined with the
per-row channel grain, the eight channels are treated as **mutually exclusive
attribution buckets** — so total sales is their sum, with no double count to strip
out, and PR + Website are the earned side of the ledger.

## What this data cannot support

- **A marketing mix model.** 8 weeks cannot identify advertising carryover. No
  channel contribution, incrementality, adstock or saturation is claimed anywhere.
- **Trends.** 8 weekly points are movements, not a direction of travel.
- **Platform-level social analysis.** No Instagram/TikTok/YouTube split, no organic
  metrics, no followers/reach/posts.
- **Full brand funnel.** Awareness and purchase intent only — no consideration,
  preference or NPS.

## Open questions for the data owner

1. **Confirm the subsidiary codes.** The dashboard shows working labels (SGE→Gulf,
   SESAR→Saudi Arabia, …) as secondary text only. The code is always primary,
   because a wrong market name in a Samsung document is worse than an unexpanded one.
2. **Are the brand scores intended to be per market-week or per product?** They are
   currently neither — they vary within both.

Neither blocks the analysis; both are stated as assumptions rather than waited on.

## Regenerating

```bash
python src/run_all.py     # ~3 seconds, end to end
```

The synthetic dataset used to build the pipeline before this extract arrived is in
`archive/synthetic-data/`, with its generator and ground-truth validator.
