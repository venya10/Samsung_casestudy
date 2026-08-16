"""Load and clean the source extract.

The source is one wide, sparse table at week x market x channel x product. Its
nulls are STRUCTURAL, not missing: TV rows carry GRPs and no clicks, Website rows
carry sessions and no spend. Filling them would invent data, so the cleaning job
here is to reshape rather than impute, and to record every judgement in a data
quality log so Part 1 can show its working instead of asserting it.

This is the only module that knows what the raw file looks like. Everything
downstream reads the modelled tables.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from common import (
    CHANNELS,
    HAS_CLICKS,
    HAS_IMPRESSIONS,
    HAS_SALES,
    HAS_SPEND,
    MARKETS,
    N_WEEKS,
    PRODUCTS,
    SOURCE_FILE,
)

# Source column -> our name. Everything monetary keeps an explicit _aed suffix.
RENAME = {
    "Week": "week",
    "Market": "market",
    "Channel": "channel",
    "Product": "product",
    "Impressions": "impressions",
    "Clicks": "clicks",
    "Spend_AED": "spend_aed",
    "Conversions": "conversions",
    "Sales_AED": "sales_aed",
    "Engagement_Rate": "engagement_rate",
    "Brand_Awareness_Score": "brand_awareness",
    "Purchase_Intent_Score": "purchase_intent",
    "Influencer_Name": "influencer",
    "Follower_Count": "followers",
    "Influencer_Engagement_Rate": "influencer_engagement_rate",
    "TV_GRP": "tv_grp",
    "PR_Mentions": "pr_mentions",
    "PR_Share_of_Voice": "pr_share_of_voice",
    "Website_Sessions": "sessions",
    "Bounce_Rate": "bounce_rate",
    "Avg_Session_Duration_Sec": "avg_session_sec",
    "Page_Views_Per_Session": "pages_per_session",
    "Competitor_SOV": "competitor_sov",
    "Sentiment_Score": "sentiment",
}

KEY = ["week", "market", "channel", "product"]


@dataclass
class DataQualityReport:
    entries: list[dict] = field(default_factory=list)

    def log(self, check: str, finding: str, rows: int, action: str) -> None:
        self.entries.append(
            {"check": check, "finding": finding, "rows": int(rows), "action": action}
        )

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.entries, columns=["check", "finding", "rows", "action"])


DQ = DataQualityReport()


class SchemaMismatch(RuntimeError):
    """The source file does not match the schema this pipeline was built for."""


# Columns without which nothing downstream can be built.
REQUIRED = ["Week", "Market", "Channel", "Product", "Spend_AED", "Sales_AED"]


def load_raw() -> pd.DataFrame:
    """Read the source, accepting .csv or .xlsx, and check the schema up front.

    A schema check here turns an unhelpful `KeyError: 'market'` thrown three
    functions deep into a message that names the file, the missing columns and the
    fix. The pipeline is deliberately strict about its input -- the same
    assertions that reject a wrong file are the ones that caught TV having no
    attributed sales -- but strict should never mean cryptic.
    """
    if not SOURCE_FILE.exists():
        raise SchemaMismatch(
            f"\n\n  No source file at {SOURCE_FILE}\n"
            f"  Place the extract there, named exactly '{SOURCE_FILE.name}'.\n"
        )

    if SOURCE_FILE.suffix.lower() in (".xlsx", ".xls", ".xlsm"):
        df = pd.read_excel(SOURCE_FILE)
    else:
        df = pd.read_csv(SOURCE_FILE)

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise SchemaMismatch(
            f"\n\n  {SOURCE_FILE.name} does not match the expected schema.\n\n"
            f"  Missing required columns: {missing}\n"
            f"  Found instead:            {list(df.columns)[:12]}"
            f"{' ...' if len(df.columns) > 12 else ''}\n\n"
            "  This pipeline is built for the Samsung MENA weekly extract. To point\n"
            "  it at a differently shaped file, edit the RENAME map at the top of\n"
            "  src/ingest.py and the taxonomy lists in src/common.py. Everything\n"
            "  downstream reads the modelled tables and needs no changes.\n"
        )

    optional_missing = [c for c in RENAME if c not in df.columns]
    if optional_missing:
        DQ.log("Schema", f"expected columns absent from the source: {optional_missing}",
               0, "downstream measures using them will be null")

    DQ.log("Source", f"{SOURCE_FILE.name}: {len(df):,} rows x {len(df.columns)} columns",
           len(df), "loaded")
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=RENAME).copy()

    # ---- keys -----------------------------------------------------------
    for c in ["market", "channel", "product"]:
        raw = df[c].astype(str)
        df[c] = raw.str.strip()
        n = int((raw != df[c]).sum())
        if n:
            DQ.log("Whitespace", f"{c} values with stray whitespace", n, "trimmed")

    df["week"] = pd.to_numeric(df["week"], errors="coerce").astype("Int64")

    dupes = int(df.duplicated(KEY).sum())
    if dupes:
        df = df.drop_duplicates(KEY, keep="first")
        DQ.log("Duplicates", f"duplicate {KEY} keys", dupes, "kept first occurrence")
    else:
        DQ.log("Duplicates", f"no duplicate {KEY} keys", 0, "none needed")

    # ---- unexpected members --------------------------------------------
    for col, expected, name in [
        ("market", MARKETS, "market"), ("channel", CHANNELS, "channel"),
        ("product", PRODUCTS, "product"),
    ]:
        unknown = sorted(set(df[col]) - set(expected))
        if unknown:
            DQ.log("Taxonomy", f"unexpected {name} values: {unknown}",
                   int(df[col].isin(unknown).sum()),
                   "retained and flagged -- update common.py before publishing")
        else:
            DQ.log("Taxonomy", f"all {df[col].nunique()} {name} values recognised",
                   len(df), "no mapping needed")

    weeks = sorted(df["week"].dropna().unique().tolist())
    DQ.log("Coverage", f"weeks present: {weeks}", len(df),
           f"{len(weeks)} weeks -- too few for carryover modelling, see insights.py")

    # ---- numerics -------------------------------------------------------
    num_cols = [c for c in df.columns if c not in KEY + ["influencer"]]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    neg = {c: int((df[c] < 0).sum()) for c in num_cols if (df[c] < 0).any()}
    if neg:
        DQ.log("Range", f"negative values found in {neg}", sum(neg.values()),
               "retained -- investigate before publishing")
    else:
        DQ.log("Range", "no negative values in any measure", len(df), "none needed")

    # ---- structural sparsity, verified rather than assumed --------------
    _check_structural(df, "spend_aed", HAS_SPEND)
    _check_structural(df, "clicks", HAS_CLICKS)
    _check_structural(df, "impressions", HAS_IMPRESSIONS)
    _check_structural(df, "sales_aed", HAS_SALES)

    # ---- redundant column ----------------------------------------------
    inf = df[df["channel"] == "Influencer"]
    if len(inf):
        identical = float(
            (inf["engagement_rate"] == inf["influencer_engagement_rate"]).mean()
        )
        if identical > 0.999:
            df = df.drop(columns=["influencer_engagement_rate"])
            DQ.log("Redundancy",
                   "influencer_engagement_rate is identical to engagement_rate "
                   "on 100% of influencer rows",
                   len(inf), "dropped the duplicate column")

    # ---- PR zero spend is real, not missing -----------------------------
    pr_zero = int(((df["channel"] == "PR") & (df["spend_aed"] == 0)).sum())
    if pr_zero:
        DQ.log("Zero values",
               f"PR spend is explicitly 0.00 on all {pr_zero} PR rows",
               pr_zero,
               "treated as genuinely unpaid (earned), not as missing data")

    # ---- brand metrics: establish their real grain -----------------------
    _check_brand_grain(df)

    return df


def _check_structural(df: pd.DataFrame, col: str, expected_channels: list[str]) -> None:
    """Confirm a measure is present exactly where it should be."""
    present = set(df.loc[df[col].notna(), "channel"].unique())
    expected = set(expected_channels)
    if present == expected:
        DQ.log("Structural sparsity",
               f"{col} present on exactly {sorted(expected)}",
               int(df[col].notna().sum()),
               "nulls elsewhere are structural, not missing -- left as null")
    else:
        DQ.log("Structural sparsity",
               f"{col} expected on {sorted(expected)} but found on {sorted(present)}",
               int(df[col].notna().sum()),
               "review -- coverage does not match the documented model")


def _check_brand_grain(df: pd.DataFrame) -> None:
    """Brand metrics arrive per row. Establish and record that.

    A brand tracker is a market-level survey; it cannot legitimately differ
    between two advertising channels in the same market and week. Here it does,
    and by a wide margin, so the honest treatment is to average to market-week and
    label the result indicative rather than measured.
    """
    for col in ["brand_awareness", "purchase_intent", "competitor_sov", "sentiment"]:
        if col not in df.columns:
            continue
        g = df.groupby(["market", "week"])[col]
        const_share = float((g.nunique() <= 1).mean())
        spread = float((g.max() - g.min()).mean())
        DQ.log(
            "Brand metric grain",
            f"{col} is constant within only {const_share:.0%} of market-weeks; "
            f"mean spread inside a market-week is {spread:.1f} points",
            int(df[col].notna().sum()),
            "averaged to market-week and reported as an indicative index, "
            "not a measurement",
        )


# --------------------------------------------------------------------------
def load() -> pd.DataFrame:
    return clean(load_raw())


if __name__ == "__main__":
    d = load()
    # NB: always use d["product"] -- attribute access collides with
    # DataFrame.product(), the arithmetic method.
    print(f"{len(d):,} rows x {len(d.columns)} cols")
    print(f"weeks {d['week'].min()}-{d['week'].max()} · "
          f"{d['market'].nunique()} markets · {d['channel'].nunique()} channels · "
          f"{d['product'].nunique()} products\n")
    print(DQ.to_frame().to_string(index=False))
