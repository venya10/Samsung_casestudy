"""Shared constants, paths and assumptions.

Single place to change scope, taxonomy and the stated assumptions, so swapping
data or correcting a business rule touches one file.

REPORTING CURRENCY IS AED. The source carries `Spend_AED` and `Sales_AED`; no FX
conversion is applied anywhere. Every money column downstream is suffixed `_aed`
so a figure can never be mistaken for USD.
"""
from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
# Named for its original Power BI export; kept post-removal because
# build_site.py still reads these CSVs for the Data page's download buttons.
DATA_PBI = DATA_PROCESSED / "powerbi"
CONFIG = ROOT / "config"
OUTPUTS = ROOT / "outputs"
PROMPTS = ROOT / "prompts"
ASSETS = ROOT / "assets"
SITE = ROOT / "site"

for _p in (DATA_RAW, DATA_PROCESSED, DATA_PBI, CONFIG, OUTPUTS):
    _p.mkdir(parents=True, exist_ok=True)

SOURCE_FILE = DATA_RAW / "samsung_marketing_full_dataset.csv"
DUCKDB_PATH = DATA_PROCESSED / "marketing.duckdb"

CURRENCY = "AED"

# --------------------------------------------------------------------------
# Analysis grain
# --------------------------------------------------------------------------
# The source has no calendar dates -- only an integer week 1..8. We keep it as an
# integer rather than inventing dates, because fabricating a calendar would let
# seasonality claims creep in that the data cannot support.
N_WEEKS = 8
WEEKS = list(range(1, N_WEEKS + 1))

# Samsung subsidiary codes as they appear in the source.
#
# The expansions below are WORKING LABELS, not confirmed. They are shown as
# secondary text only; the code is always primary, because a wrong market name in
# a document going to Samsung is worse than an unexpanded code. Confirm against
# the subsidiary register before publishing.
MARKETS = ["SGE", "SESAR", "SEEG", "SELV", "SEMAG", "SEPAK", "SETK", "SEIL"]
MARKET_LABEL = {
    "SGE": "Gulf",
    "SESAR": "Saudi Arabia",
    "SEEG": "Egypt",
    "SELV": "Levant",
    "SEMAG": "Maghreb",
    "SEPAK": "Pakistan",
    "SETK": "Türkiye",
    "SEIL": "Israel",
}
MARKET_LABELS_CONFIRMED = False

PRODUCTS = [
    "Galaxy Z Fold8", "Galaxy Z Flip8", "Galaxy S24",
    "Galaxy Tab S10", "Galaxy Watch6", "Galaxy Buds3",
]

CHANNELS = ["TV", "Paid Social", "Search", "Influencer",
            "B2B Roadshow", "Retail", "PR", "Website"]

# --------------------------------------------------------------------------
# Channel classification
# --------------------------------------------------------------------------
# PR carries an explicit zero spend (360 rows, all 0.0) and Website carries no
# spend column at all. Both still carry outcomes, so they are the earned side of
# the ledger. The eight channels are treated as MUTUALLY EXCLUSIVE attribution
# buckets -- each row is one channel's own credited outcome -- which is why total
# sales is the sum across all eight and there is no double count to strip out.
PAID_CHANNELS = ["TV", "Paid Social", "Search", "Influencer", "B2B Roadshow", "Retail"]
EARNED_CHANNELS = ["PR", "Website"]

MEDIA_TYPE = {c: "paid" for c in PAID_CHANNELS} | {c: "earned" for c in EARNED_CHANNELS}

# Broad-reach channels build the brand slowly; response channels convert demand
# that already exists. Used to group the efficiency read, NOT to model carryover
# -- eight weeks cannot identify a decay rate.
CHANNEL_ROLE = {
    "TV": "brand", "PR": "brand", "B2B Roadshow": "brand",
    "Paid Social": "response", "Search": "response",
    "Influencer": "response", "Retail": "response", "Website": "owned",
}

# Which channels can support which metric. Coverage is structural, not missing
# data: TV has GRPs and no clicks; Website has sessions and no spend.
HAS_SPEND = PAID_CHANNELS + ["PR"]
HAS_CLICKS = ["Paid Social", "Search"]
HAS_IMPRESSIONS = ["Paid Social", "Search", "B2B Roadshow", "Retail"]
HAS_SALES = ["Paid Social", "Search", "Influencer", "B2B Roadshow",
             "Retail", "Website"]

# TV carries spend and GRPs but NO attributed sales or conversions -- and it is
# the single largest line in the budget. Any ROI, ROAS or CPA quoted for TV from
# this data would be fabricated, so TV is excluded from every efficiency ranking
# and evaluated on delivery (cost per GRP) and brand association instead.
# This is a headline constraint, not a footnote: see the executive summary.
NO_REVENUE_ATTRIBUTION = ["TV", "PR"]
REVENUE_ATTRIBUTED = [c for c in CHANNELS if c not in NO_REVENUE_ATTRIBUTION]

# --------------------------------------------------------------------------
# Stated assumptions
# --------------------------------------------------------------------------
# Blended gross margin. ROI on revenue flatters every channel; a budget decision
# turns on margin. Change this one number when Finance supplies the real figure.
GROSS_MARGIN = 0.22

# Brand metrics (awareness, purchase intent, competitor SOV, sentiment) appear on
# EVERY row and vary by up to ~39 points inside a single market-week. They are
# therefore not a market-level tracker. We average them to market-week and treat
# the result as an indicative index rather than a measurement. See the data
# quality log and the assumptions section of the executive summary.
BRAND_METRICS = ["brand_awareness", "purchase_intent", "competitor_sov", "sentiment"]
BRAND_METRIC_IS_INDICATIVE = True

# Minimum observations before a trend claim is allowed. With 8 weeks, anything
# needing a long baseline is out of scope by construction.
MIN_WEEKS_FOR_TREND = 4


def market_label(code: str) -> str:
    """'SGE (Gulf)' when we have a working label, else the bare code."""
    name = MARKET_LABEL.get(code)
    return f"{code} ({name})" if name else code
